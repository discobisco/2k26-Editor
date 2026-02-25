from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
from torch import nn, optim

from nba2k_editor.gm_rl.actions import ActionMask, ActionSpaceSpec
from nba2k_editor.gm_rl.env import SyncVecEnv
from nba2k_editor.gm_rl.features import RunningMeanStd
from nba2k_editor.gm_rl.models import GMPolicy

try:
    from torch.utils.tensorboard import SummaryWriter
except Exception:  # pragma: no cover - optional dependency
    SummaryWriter = None  # type: ignore


@dataclass
class PPOConfig:
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    vf_coef: float = 0.5
    ent_coef: float = 0.01
    lr: float = 3e-4
    max_grad_norm: float = 0.5
    rollout_steps: int = 64
    batch_size: int = 128
    epochs: int = 4
    target_kl: float = 0.08
    normalize_advantages: bool = True
    reward_norm: bool = False
    n_envs: int = 1
    total_timesteps: int = 20_000
    log_interval: int = 10
    device: str = "cpu"


class RolloutBuffer:
    def __init__(self, cfg: PPOConfig, obs_shapes: Dict[str, Tuple[int, ...]], action_spec: ActionSpaceSpec, device: torch.device) -> None:
        self.cfg = cfg
        self.device = device
        steps, n_envs = cfg.rollout_steps, cfg.n_envs
        self.observations = {k: torch.zeros((steps, n_envs, *shape), device=device) for k, shape in obs_shapes.items() if k != "player_mask"}
        self.player_mask = torch.zeros((steps, n_envs, obs_shapes["player_mask"][0]), dtype=torch.bool, device=device)
        self.actions = torch.zeros((steps, n_envs, len(action_spec.sizes)), dtype=torch.long, device=device)
        self.log_probs = torch.zeros((steps, n_envs), device=device)
        self.rewards = torch.zeros((steps, n_envs), device=device)
        self.dones = torch.zeros((steps, n_envs), device=device)
        self.values = torch.zeros((steps, n_envs), device=device)
        # masks
        self.action_masks = {
            "draft": torch.zeros((steps, n_envs, action_spec.draft_slots), dtype=torch.bool, device=device),
            "trade": torch.zeros((steps, n_envs, action_spec.trade_candidates), dtype=torch.bool, device=device),
            "rotation": torch.zeros((steps, n_envs, action_spec.rotation_templates), dtype=torch.bool, device=device),
            "contract": torch.zeros((steps, n_envs, action_spec.contract_candidates), dtype=torch.bool, device=device),
            "roster_move": torch.zeros((steps, n_envs, action_spec.roster_moves), dtype=torch.bool, device=device),
        }
        self.pos = 0

    def add(
        self,
        obs: Dict[str, np.ndarray],
        actions: torch.Tensor,
        log_probs: torch.Tensor,
        rewards: np.ndarray,
        dones: np.ndarray,
        values: torch.Tensor,
        masks: List[ActionMask],
    ) -> None:
        assert self.pos < self.cfg.rollout_steps
        idx = self.pos
        self.observations["team"][idx] = torch.as_tensor(obs["team"], device=self.device)
        self.observations["players"][idx] = torch.as_tensor(obs["players"], device=self.device)
        self.player_mask[idx] = torch.as_tensor(obs["player_mask"], device=self.device, dtype=torch.bool)
        self.observations["league"][idx] = torch.as_tensor(obs["league"], device=self.device)
        self.actions[idx] = actions
        self.log_probs[idx] = log_probs
        self.rewards[idx] = torch.as_tensor(rewards, device=self.device, dtype=torch.float32)
        self.dones[idx] = torch.as_tensor(dones, device=self.device, dtype=torch.float32)
        self.values[idx] = values
        for env_i, m in enumerate(masks):
            self.action_masks["draft"][idx, env_i] = m.draft
            self.action_masks["trade"][idx, env_i] = m.trade
            self.action_masks["rotation"][idx, env_i] = m.rotation
            self.action_masks["contract"][idx, env_i] = m.contract
            self.action_masks["roster_move"][idx, env_i] = m.roster_move
        self.pos += 1

    def compute_returns_and_advantages(self, last_values: torch.Tensor, gamma: float, gae_lambda: float) -> Tuple[torch.Tensor, torch.Tensor]:
        steps = self.cfg.rollout_steps
        n_envs = self.cfg.n_envs
        advantages = torch.zeros((steps, n_envs), device=self.device)
        last_gae = torch.zeros(n_envs, device=self.device)
        for t in reversed(range(steps)):
            if t == steps - 1:
                next_values = last_values
                next_non_terminal = 1.0 - self.dones[t]
            else:
                next_values = self.values[t + 1]
                next_non_terminal = 1.0 - self.dones[t + 1]
            delta = self.rewards[t] + gamma * next_values * next_non_terminal - self.values[t]
            last_gae = delta + gamma * gae_lambda * next_non_terminal * last_gae
            advantages[t] = last_gae
        returns = advantages + self.values
        return advantages, returns

    def get_batches(self, advantages: torch.Tensor, returns: torch.Tensor, batch_size: int):
        steps = self.cfg.rollout_steps
        n_envs = self.cfg.n_envs
        total = steps * n_envs
        indices = np.arange(total)
        np.random.shuffle(indices)

        obs_flat = {k: v.reshape(total, *v.shape[2:]) for k, v in self.observations.items()}
        obs_flat["player_mask"] = self.player_mask.reshape(total, *self.player_mask.shape[2:])
        actions_flat = self.actions.reshape(total, -1)
        logp_flat = self.log_probs.reshape(total)
        adv_flat = advantages.reshape(total)
        ret_flat = returns.reshape(total)
        values_flat = self.values.reshape(total)
        masks_flat = {k: v.reshape(total, v.shape[-1]) for k, v in self.action_masks.items()}

        for start in range(0, total, batch_size):
            idx = indices[start : start + batch_size]
            batch_obs = {k: v[idx] for k, v in obs_flat.items()}
            batch_masks = ActionMask(
                draft=masks_flat["draft"][idx],
                trade=masks_flat["trade"][idx],
                rotation=masks_flat["rotation"][idx],
                contract=masks_flat["contract"][idx],
                roster_move=masks_flat["roster_move"][idx],
            )
            yield batch_obs, batch_masks, actions_flat[idx], logp_flat[idx], adv_flat[idx], ret_flat[idx], values_flat[idx]

    def reset(self) -> None:
        self.pos = 0


class PPOTrainer:
    def __init__(
        self,
        policy: GMPolicy,
        envs: SyncVecEnv,
        cfg: PPOConfig,
        action_spec: ActionSpaceSpec,
        log_dir: Path,
        reward_norm: bool = False,
        seed: int = 0,
    ) -> None:
        self.policy = policy
        self.envs = envs
        self.cfg = cfg
        self.device = torch.device(cfg.device)
        self.policy.to(self.device)
        self.seed = seed
        obs_shapes = {
            "team": (policy.cfg.team_dim,),
            "players": (policy.cfg.max_players, policy.cfg.player_dim),
            "league": (policy.cfg.league_dim,),
            "player_mask": (policy.cfg.max_players,),
        }
        self.buffer = RolloutBuffer(cfg, obs_shapes, action_spec, self.device)
        self.optimizer = optim.Adam(self.policy.parameters(), lr=cfg.lr)
        self.reward_rms = RunningMeanStd(()) if reward_norm else None

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.writer = SummaryWriter(self.log_dir) if SummaryWriter is not None else None
        self.update_count = 0

    @staticmethod
    def _stack_action_masks(masks: List[ActionMask], device: torch.device) -> ActionMask:
        return ActionMask(
            draft=torch.stack([m.draft for m in masks], dim=0).to(device=device, dtype=torch.bool),
            trade=torch.stack([m.trade for m in masks], dim=0).to(device=device, dtype=torch.bool),
            rotation=torch.stack([m.rotation for m in masks], dim=0).to(device=device, dtype=torch.bool),
            contract=torch.stack([m.contract for m in masks], dim=0).to(device=device, dtype=torch.bool),
            roster_move=torch.stack([m.roster_move for m in masks], dim=0).to(device=device, dtype=torch.bool),
        )

    # Training loop -------------------------------------------------------
    def train(self) -> None:
        obs, infos = self.envs.reset(seed=self.seed)
        action_masks = self._mask_list_from_info(infos)

        total_updates = self.cfg.total_timesteps // (self.cfg.rollout_steps * self.cfg.n_envs)
        global_step = 0

        for update in range(total_updates):
            # Collect rollout
            self.buffer.reset()
            for step in range(self.cfg.rollout_steps):
                obs_t = {k: torch.as_tensor(v, device=self.device) for k, v in obs.items()}
                mask_t = self._stack_action_masks(action_masks, self.device)
                actions, logp, values, entropies = self.policy.act(obs_t, mask_t, deterministic=False)
                actions_np = actions.cpu().numpy()

                next_obs, rewards, terms, truncs, next_infos = self.envs.step(actions_np)
                if self.reward_rms is not None:
                    self.reward_rms.update(rewards)
                    rewards = (rewards - self.reward_rms.mean) / np.sqrt(self.reward_rms.var + 1e-8)

                dones = np.logical_or(terms, truncs)
                self.buffer.add(
                    obs,
                    actions,
                    logp.detach(),
                    rewards,
                    dones,
                    values.detach(),
                    action_masks,
                )
                obs = next_obs
                action_masks = self._mask_list_from_info(next_infos)
                global_step += self.cfg.n_envs

            # bootstrap value
            with torch.no_grad():
                obs_t = {k: torch.as_tensor(v, device=self.device) for k, v in obs.items()}
                mask_t = self._stack_action_masks(action_masks, self.device)
                _, next_values = self.policy.forward(obs_t, mask_t)
            advantages, returns = self.buffer.compute_returns_and_advantages(next_values.detach(), self.cfg.gamma, self.cfg.gae_lambda)

            if self.cfg.normalize_advantages:
                advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

            # Optimize policy
            for epoch in range(self.cfg.epochs):
                for batch in self.buffer.get_batches(advantages, returns, self.cfg.batch_size):
                    batch_obs, batch_masks, actions_b, old_logp_b, adv_b, ret_b, val_b = batch
                    batch_obs_t = {k: v.to(self.device) for k, v in batch_obs.items()}
                    batch_masks = batch_masks.to(self.device)

                    dists, values = self.policy.forward(batch_obs_t, batch_masks)
                    new_logp = torch.stack([d.log_prob(a) for d, a in zip(dists, actions_b.T)], dim=-1).sum(dim=-1)
                    entropy = torch.stack([d.entropy() for d in dists], dim=-1).mean()

                    ratio = torch.exp(new_logp - old_logp_b)
                    pg1 = ratio * adv_b
                    pg2 = torch.clamp(ratio, 1.0 - self.cfg.clip_range, 1.0 + self.cfg.clip_range) * adv_b
                    policy_loss = -torch.min(pg1, pg2).mean()

                    value_pred_clipped = val_b + (values - val_b).clamp(-self.cfg.clip_range, self.cfg.clip_range)
                    value_losses = (values - ret_b) ** 2
                    value_losses_clipped = (value_pred_clipped - ret_b) ** 2
                    value_loss = 0.5 * torch.max(value_losses, value_losses_clipped).mean()

                    loss = policy_loss + self.cfg.vf_coef * value_loss - self.cfg.ent_coef * entropy

                    self.optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.policy.parameters(), self.cfg.max_grad_norm)
                    self.optimizer.step()

                # KL early stop
                with torch.no_grad():
                    kl = (old_logp_b - new_logp).mean()
                    if kl > self.cfg.target_kl:
                        break

            self._log_metrics(policy_loss, value_loss, entropy, kl, advantages, returns, action_masks, global_step)

    # Logging and helpers -------------------------------------------------
    def _mask_list_from_info(self, infos: List[Dict]) -> List[ActionMask]:
        masks: List[ActionMask] = []
        for info in infos:
            m = info.get("action_mask", {})
            masks.append(
                ActionMask(
                    draft=torch.as_tensor(m.get("draft"), dtype=torch.bool),
                    trade=torch.as_tensor(m.get("trade"), dtype=torch.bool),
                    rotation=torch.as_tensor(m.get("rotation"), dtype=torch.bool),
                    contract=torch.as_tensor(m.get("contract"), dtype=torch.bool),
                    roster_move=torch.as_tensor(m.get("roster_move"), dtype=torch.bool),
                )
            )
        return masks

    def _log_metrics(
        self,
        policy_loss: torch.Tensor,
        value_loss: torch.Tensor,
        entropy: torch.Tensor,
        kl: torch.Tensor,
        advantages: torch.Tensor,
        returns: torch.Tensor,
        action_masks: List[ActionMask],
        global_step: int,
    ) -> None:
        if self.writer is None:
            return
        self.writer.add_scalar("loss/policy", policy_loss.item(), global_step)
        self.writer.add_scalar("loss/value", value_loss.item(), global_step)
        self.writer.add_scalar("loss/kl", kl.item(), global_step)
        self.writer.add_scalar("loss/entropy", entropy.item(), global_step)
        self.writer.add_scalar("advantage/mean", advantages.mean().item(), global_step)
        self.writer.add_scalar("returns/mean", returns.mean().item(), global_step)
        # action frequencies
        drafts = torch.stack([m.draft.float().mean() for m in action_masks]).mean()
        trades = torch.stack([m.trade.float().mean() for m in action_masks]).mean()
        self.writer.add_scalar("mask/draft_available", drafts.item(), global_step)
        self.writer.add_scalar("mask/trade_available", trades.item(), global_step)
        self.writer.flush()

    def save_checkpoint(self, path: Path, config: Dict) -> None:
        path.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "policy": self.policy.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "config": config,
                "update": self.update_count,
            },
            path / "checkpoint.pt",
        )
        with open(path / "config.json", "w", encoding="utf-8") as fp:
            json.dump(config, fp, indent=2)
