from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import torch
import torch.nn as nn
from torch.distributions import Categorical

from nba2k_editor.gm_rl.actions import ActionMask, ActionSpaceSpec


class MaskedCategorical(Categorical):
    """Categorical distribution that respects legality masks."""

    def __init__(self, logits: torch.Tensor, mask: torch.Tensor) -> None:
        # mask: bool tensor same shape as logits
        masked_logits = logits.masked_fill(~mask, -1e9)
        super().__init__(logits=masked_logits)

    def entropy(self) -> torch.Tensor:  # type: ignore[override]
        # override to ensure masked entries don't produce NaN
        p = self.probs
        log_p = torch.log(p + 1e-12)
        return -torch.sum(p * log_p, dim=-1)


class AttentionPool(nn.Module):
    def __init__(self, embed_dim: int, num_heads: int = 4, dropout: float = 0.1) -> None:
        super().__init__()
        self.attn = nn.MultiheadAttention(embed_dim, num_heads, dropout=dropout, batch_first=True)
        self.norm = nn.LayerNorm(embed_dim)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        # mask: (batch, seq) True for valid tokens
        key_padding = ~mask
        attn_out, _ = self.attn(x, x, x, key_padding_mask=key_padding)
        pooled = attn_out.mean(dim=1)
        return self.norm(pooled)


@dataclass
class ModelConfig:
    team_dim: int
    player_dim: int
    league_dim: int
    max_players: int
    hidden_size: int = 256
    player_hidden: int = 128
    use_attention: bool = True
    attention_heads: int = 4
    dropout: float = 0.05
    shared_value: bool = True  # shared critic across heads for stability


class GMPolicy(nn.Module):
    def __init__(self, cfg: ModelConfig, action_spec: ActionSpaceSpec) -> None:
        super().__init__()
        self.cfg = cfg
        self.action_spec = action_spec

        self.player_encoder = nn.Sequential(
            nn.Linear(cfg.player_dim, cfg.player_hidden),
            nn.ReLU(),
            nn.LayerNorm(cfg.player_hidden),
        )
        self.attn = AttentionPool(cfg.player_hidden, num_heads=cfg.attention_heads, dropout=cfg.dropout) if cfg.use_attention else None

        trunk_input = cfg.team_dim + cfg.league_dim + cfg.player_hidden
        self.trunk = nn.Sequential(
            nn.Linear(trunk_input, cfg.hidden_size),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_size, cfg.hidden_size),
            nn.ReLU(),
        )
        self.action_heads = nn.ModuleList([nn.Linear(cfg.hidden_size, n) for n in action_spec.sizes])
        self.value_head = nn.Linear(cfg.hidden_size, 1)

    def forward(self, obs: Dict[str, torch.Tensor], action_mask: ActionMask) -> Tuple[List[MaskedCategorical], torch.Tensor]:
        player_embed = self.player_encoder(obs["players"])  # (b, max_p, hidden)
        if self.attn is not None:
            pooled_players = self.attn(player_embed, obs["player_mask"])
        else:
            # fallback: mean over valid players; note this scales with roster size
            masked = player_embed * obs["player_mask"].unsqueeze(-1)
            pooled_players = masked.sum(dim=1) / (obs["player_mask"].sum(dim=1, keepdim=True) + 1e-6)

        flat = torch.cat([obs["team"], obs["league"], pooled_players], dim=-1)
        trunk_out = self.trunk(flat)
        logits = [head(trunk_out) for head in self.action_heads]

        dists = [
            MaskedCategorical(logits=logits[0], mask=action_mask.draft),
            MaskedCategorical(logits=logits[1], mask=action_mask.trade),
            MaskedCategorical(logits=logits[2], mask=action_mask.rotation),
            MaskedCategorical(logits=logits[3], mask=action_mask.contract),
            MaskedCategorical(logits=logits[4], mask=action_mask.roster_move),
        ]
        values = self.value_head(trunk_out).squeeze(-1)
        return dists, values

    def act(
        self, obs: Dict[str, torch.Tensor], action_mask: ActionMask, deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        dists, values = self.forward(obs, action_mask)
        if deterministic:
            actions = torch.stack([torch.argmax(d.logits, dim=-1) for d in dists], dim=-1)
        else:
            samples = [d.sample() for d in dists]
            actions = torch.stack(samples, dim=-1)
        log_probs = torch.stack([d.log_prob(a) for d, a in zip(dists, actions.unbind(-1))], dim=-1).sum(dim=-1)
        entropies = torch.stack([d.entropy() for d in dists], dim=-1)
        return actions, log_probs, values, entropies
