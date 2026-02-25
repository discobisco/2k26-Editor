from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, TypedDict

import numpy as np
import torch

from nba2k_editor.gm_rl.actions import ActionMask
from nba2k_editor.gm_rl.adapters.editor_live import EditorLiveAdapter
from nba2k_editor.gm_rl.adapters.local_mock import LocalMockAdapter
from nba2k_editor.gm_rl.env import NBA2KGMEnv
from nba2k_editor.gm_rl.features import FeatureEncoder
from nba2k_editor.gm_rl.models import GMPolicy, ModelConfig
from nba2k_editor.gm_rl.train import load_config, set_seed


def build_adapter(name: str):
    return LocalMockAdapter() if name == "mock" else EditorLiveAdapter()


class EvalMetrics(TypedDict):
    mean_reward: float
    std_reward: float
    action_distribution: Dict[str, List[int]]


def evaluate(config_path: str | None = None, checkpoint: str | None = None, episodes: int = 3) -> EvalMetrics:
    cfg = load_config(Path(config_path) if config_path else None)
    set_seed(cfg.seed)
    adapter = build_adapter(cfg.adapter)

    encoder = FeatureEncoder(cfg.feature)
    model_cfg = ModelConfig(
        team_dim=encoder._team_dim(),
        player_dim=encoder._player_dim(),
        league_dim=encoder._league_dim(),
        max_players=cfg.feature.max_players,
    )
    policy = GMPolicy(model_cfg, cfg.action_spec)
    device = torch.device(cfg.ppo.device)
    policy.to(device)

    if checkpoint:
        state = torch.load(checkpoint, map_location=device)
        policy.load_state_dict(state["policy"])

    env = NBA2KGMEnv(adapter, cfg.env)
    rewards = []
    head_names = ["draft", "trade", "rotation", "contract", "roster_move"]
    action_counts = [np.zeros(n, dtype=np.int64) for n in cfg.action_spec.sizes]

    for _ in range(episodes):
        obs, info = env.reset(seed=cfg.seed)
        done = False
        ep_reward = 0.0
        while not done:
            obs_t = {k: torch.as_tensor(v[None, ...], device=device) for k, v in obs.items()}
            mask_info = info["action_mask"]
            mask = ActionMask(
                draft=torch.as_tensor(mask_info["draft"][None, ...], device=device, dtype=torch.bool),
                trade=torch.as_tensor(mask_info["trade"][None, ...], device=device, dtype=torch.bool),
                rotation=torch.as_tensor(mask_info["rotation"][None, ...], device=device, dtype=torch.bool),
                contract=torch.as_tensor(mask_info["contract"][None, ...], device=device, dtype=torch.bool),
                roster_move=torch.as_tensor(mask_info["roster_move"][None, ...], device=device, dtype=torch.bool),
            )
            actions, _, _, _ = policy.act(obs_t, mask, deterministic=True)
            action_array = actions.squeeze(0).cpu().numpy()
            obs, reward, terminated, truncated, info = env.step(tuple(int(a) for a in action_array))
            ep_reward += reward
            done = terminated or truncated
            for head_idx, a in enumerate(action_array):
                action_counts[head_idx][int(a)] += 1
        rewards.append(ep_reward)

    return {
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "action_distribution": {name: counts.tolist() for name, counts in zip(head_names, action_counts)},
    }


def main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--episodes", type=int, default=3)
    parsed = parser.parse_args(args)
    metrics = evaluate(parsed.config, parsed.checkpoint, parsed.episodes)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
