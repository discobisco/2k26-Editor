from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import torch

from nba2k_editor.gm_rl.actions import ActionMask
from nba2k_editor.gm_rl.env import NBA2KGMEnv
from nba2k_editor.gm_rl.features import FeatureEncoder
from nba2k_editor.gm_rl.models import GMPolicy, ModelConfig
from nba2k_editor.gm_rl.train import load_config, set_seed


class AgentRuntime:
    """Background worker for evaluation, live assist, and training."""

    def __init__(self, adapter_factory: Callable[[str, bool], object]) -> None:
        self.adapter_factory = adapter_factory
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._queue: queue.Queue[dict] = queue.Queue()
        self._process: subprocess.Popen | None = None
        self._running_mode: str | None = None

    # Public control ----------------------------------------------------
    @property
    def events(self) -> queue.Queue:
        return self._queue

    def stop(self) -> None:
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        self._process = None
        self._running_mode = None

    def start_evaluate(
        self,
        *,
        adapter: str = "mock",
        config_path: str | None = None,
        checkpoint: str | None = None,
        episodes: int = 3,
        team_id: Optional[int] = None,
        apply_writes: bool = False,
    ) -> None:
        self.stop()
        self._stop_event.clear()
        self._running_mode = "evaluate"
        self._thread = threading.Thread(
            target=self._run_evaluate,
            args=(adapter, config_path, checkpoint, episodes, team_id, apply_writes),
            daemon=True,
        )
        self._thread.start()

    def start_live_assist(
        self,
        *,
        adapter: str = "mock",
        config_path: str | None = None,
        checkpoint: str | None = None,
        team_id: Optional[int] = None,
        apply_writes: bool = False,
    ) -> None:
        self.stop()
        self._stop_event.clear()
        self._running_mode = "live_assist"
        self._thread = threading.Thread(
            target=self._run_live_assist,
            args=(adapter, config_path, checkpoint, team_id, apply_writes),
            daemon=True,
        )
        self._thread.start()

    def start_training(self, *, config_path: str | None = None) -> None:
        self.stop()
        self._stop_event.clear()
        self._running_mode = "train"
        self._thread = threading.Thread(target=self._run_training, args=(config_path,), daemon=True)
        self._thread.start()

    # Internals ---------------------------------------------------------
    @staticmethod
    def _mask_from_info(mask_info: dict, device: torch.device) -> ActionMask:
        def _to_mask(key: str) -> torch.Tensor:
            return torch.as_tensor(mask_info[key], device=device, dtype=torch.bool).unsqueeze(0)

        return ActionMask(
            draft=_to_mask("draft"),
            trade=_to_mask("trade"),
            rotation=_to_mask("rotation"),
            contract=_to_mask("contract"),
            roster_move=_to_mask("roster_move"),
        )

    def _run_evaluate(
        self,
        adapter_name: str,
        config_path: str | None,
        checkpoint: str | None,
        episodes: int,
        team_id: Optional[int],
        apply_writes: bool,
    ) -> None:
        try:
            cfg = load_config(Path(config_path) if config_path else None)
            if adapter_name:
                cfg.adapter = adapter_name
            if team_id is not None:
                cfg.env.team_id = int(team_id)
            set_seed(cfg.seed)
            adapter = self.adapter_factory(adapter_name, apply_writes)

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
            rewards: list[float] = []

            for ep in range(max(1, episodes)):
                if self._stop_event.is_set():
                    break
                obs, info = env.reset(seed=cfg.seed + ep)
                done = False
                ep_reward = 0.0
                while not done and not self._stop_event.is_set():
                    obs_t = {k: torch.as_tensor(v[None, ...], device=device) for k, v in obs.items()}
                    mask_info = info["action_mask"]
                    mask = self._mask_from_info(mask_info, device)
                    actions, _, _, _ = policy.act(obs_t, mask, deterministic=True)
                    action_array = actions.squeeze(0).cpu().numpy()
                    obs, reward, terminated, truncated, info = env.step(tuple(int(a) for a in action_array))
                    ep_reward += reward
                    done = bool(terminated or truncated)
                rewards.append(ep_reward)

            if rewards:
                metrics = {
                    "mean_reward": float(sum(rewards) / len(rewards)),
                    "std_reward": float(torch.tensor(rewards).std().item()) if len(rewards) > 1 else 0.0,
                    "episodes": len(rewards),
                }
                self._queue.put({"type": "metrics", "metrics": metrics, "mode": "evaluate"})
        except Exception as exc:  # noqa: BLE001
            self._queue.put({"type": "error", "message": str(exc)})
        finally:
            self._queue.put({"type": "done", "mode": "evaluate"})
            self._running_mode = None

    def _run_live_assist(
        self,
        adapter_name: str,
        config_path: str | None,
        checkpoint: str | None,
        team_id: Optional[int],
        apply_writes: bool,
    ) -> None:
        try:
            cfg = load_config(Path(config_path) if config_path else None)
            if adapter_name:
                cfg.adapter = adapter_name
            if team_id is not None:
                cfg.env.team_id = int(team_id)
            set_seed(cfg.seed)
            adapter = self.adapter_factory(adapter_name, apply_writes)

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
            obs, info = env.reset(seed=cfg.seed)
            while not self._stop_event.is_set():
                obs_t = {k: torch.as_tensor(v[None, ...], device=device) for k, v in obs.items()}
                mask_info = info["action_mask"]
                mask = self._mask_from_info(mask_info, device)
                actions, _, _, _ = policy.act(obs_t, mask, deterministic=False)
                action_array = actions.squeeze(0).cpu().numpy()
                obs, reward, terminated, truncated, info = env.step(tuple(int(a) for a in action_array))
                self._queue.put({"type": "step", "reward": float(reward), "metadata": info.get("metadata", {}), "mode": "live_assist"})
                if terminated or truncated:
                    obs, info = env.reset(seed=cfg.seed)
        except Exception as exc:  # noqa: BLE001
            self._queue.put({"type": "error", "message": str(exc)})
        finally:
            self._queue.put({"type": "done", "mode": "live_assist"})
            self._running_mode = None

    def _run_training(self, config_path: str | None) -> None:
        cmd = [sys.executable, "-m", "nba2k_editor.entrypoints.editor_train_hook"]
        if config_path:
            cmd.extend(["--config", str(config_path)])
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert self._process.stdout is not None
            for line in self._process.stdout:
                if self._stop_event.is_set():
                    try:
                        self._process.terminate()
                    except Exception:
                        pass
                    break
                self._queue.put({"type": "log", "message": line.rstrip(), "mode": "train"})
            rc = self._process.wait()
            self._queue.put({"type": "done", "mode": "train", "returncode": rc})
        except Exception as exc:  # noqa: BLE001
            self._queue.put({"type": "error", "message": str(exc)})
        finally:
            self._running_mode = None


__all__ = ["AgentRuntime"]
