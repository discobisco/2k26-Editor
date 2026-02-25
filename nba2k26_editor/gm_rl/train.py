from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from nba2k_editor.gm_rl.actions import ActionSpaceSpec
from nba2k_editor.gm_rl.adapters.base import EditorAdapter
from nba2k_editor.gm_rl.adapters.editor_live import EditorLiveAdapter
from nba2k_editor.gm_rl.adapters.local_mock import LocalMockAdapter
from nba2k_editor.gm_rl.env import GMEnvConfig, NBA2KGMEnv, make_vec_env
from nba2k_editor.gm_rl.features import FeatureConfig, FeatureEncoder
from nba2k_editor.gm_rl.models import GMPolicy, ModelConfig
from nba2k_editor.gm_rl.ppo import PPOConfig, PPOTrainer


@dataclass
class TrainingConfig:
    seed: int = 42
    adapter: str = "mock"  # mock | live
    ppo: PPOConfig = field(default_factory=PPOConfig)
    env: GMEnvConfig = field(default_factory=GMEnvConfig)
    feature: FeatureConfig = field(default_factory=FeatureConfig)
    action_spec: ActionSpaceSpec = field(default_factory=ActionSpaceSpec)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(False)


def load_config(path: Path | None) -> TrainingConfig:
    if path is None or not path.exists():
        return TrainingConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    # nested dataclasses reconstruction
    cfg = TrainingConfig(
        seed=data.get("seed", 42),
        adapter=data.get("adapter", "mock"),
        ppo=PPOConfig(**data.get("ppo", {})),
        env=GMEnvConfig(**data.get("env", {})),
        feature=FeatureConfig(**data.get("feature", {})),
        action_spec=ActionSpaceSpec(**data.get("action_spec", {})),
    )
    return cfg


def save_config(cfg: TrainingConfig, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "config.json", "w", encoding="utf-8") as fp:
        json.dump(asdict(cfg), fp, indent=2)


def build_adapter(adapter_name: str) -> EditorAdapter:
    if adapter_name == "mock":
        return LocalMockAdapter()
    return EditorLiveAdapter()


def main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None, help="Path to JSON config")
    parser.add_argument("--adapter", type=str, default=None, choices=["mock", "live"])
    parser.add_argument("--total-steps", type=int, default=None)
    parser.add_argument("--n-envs", type=int, default=None)
    parsed = parser.parse_args(args)

    cfg = load_config(Path(parsed.config) if parsed.config else None)
    if parsed.adapter:
        cfg.adapter = parsed.adapter
    if parsed.total_steps:
        cfg.ppo.total_timesteps = parsed.total_steps
    if parsed.n_envs:
        cfg.ppo.n_envs = parsed.n_envs
    cfg.env.action_spec = cfg.action_spec  # ensure env uses same spec

    set_seed(cfg.seed)

    run_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    run_dir = Path("logs") / "gm_rl" / "runs" / run_id
    save_config(cfg, run_dir)

    adapter = build_adapter(cfg.adapter)
    feature_encoder = FeatureEncoder(cfg.feature)
    model_cfg = ModelConfig(
        team_dim=feature_encoder._team_dim(),
        player_dim=feature_encoder._player_dim(),
        league_dim=feature_encoder._league_dim(),
        max_players=cfg.feature.max_players,
    )
    policy = GMPolicy(model_cfg, cfg.action_spec)

    def env_fn():
        return NBA2KGMEnv(adapter, cfg.env)

    envs = make_vec_env(env_fn, cfg.ppo.n_envs, seed=cfg.seed)
    trainer = PPOTrainer(
        policy=policy,
        envs=envs,
        cfg=cfg.ppo,
        action_spec=cfg.action_spec,
        log_dir=run_dir,
        reward_norm=cfg.feature.reward_normalization,
        seed=cfg.seed,
    )
    trainer.train()
    trainer.save_checkpoint(run_dir / "checkpoints", asdict(cfg))


if __name__ == "__main__":
    main()
