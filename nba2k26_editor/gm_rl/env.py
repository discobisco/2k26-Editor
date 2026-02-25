from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence, Tuple, TYPE_CHECKING, cast

import numpy as np

from nba2k_editor.gm_rl.actions import ActionGrammar, ActionMaskBuilder, ActionSpaceSpec
from nba2k_editor.gm_rl.adapters.base import EditorAdapter, RosterState
from nba2k_editor.gm_rl.cba.repository import load_ruleset_for_season
from nba2k_editor.gm_rl.cba.schema import CbaRuleSet
from nba2k_editor.gm_rl.features import FeatureConfig, FeatureEncoder, ObservationBatch

if TYPE_CHECKING:
    import gymnasium as gym
    from gymnasium.spaces import Box, MultiDiscrete
    BaseEnv = gym.Env
else:
    try:
        import gymnasium as gym  # type: ignore[import-not-found,reportMissingImports]
        from gymnasium.spaces import Box, MultiDiscrete  # type: ignore[import-not-found,reportMissingImports]
        BaseEnv = gym.Env
    except ImportError:  # pragma: no cover - optional dev dependency
        gym = cast(Any, None)
        BaseEnv = object

        class MultiDiscrete:
            def __init__(self, nvec: Sequence[int]) -> None:
                self.nvec = np.array(nvec, dtype=np.int64)

        class Box:
            def __init__(self, low: Any, high: Any, shape: Tuple[int, ...], dtype: Any) -> None:
                self.low = low
                self.high = high
                self.shape = shape
                self.dtype = dtype


@dataclass
class RewardWeights:
    win_weight: float = 1.0
    asset_weight: float = 0.3
    development_weight: float = 0.2
    player_value_weight: float = 0.4
    rank_weight: float = 0.5
    realism_penalty: float = 0.1


@dataclass
class GMEnvConfig:
    horizon_games: int = 82
    step_granularity: str = "game"  # or "week"
    team_id: int = 1
    reward_weights: RewardWeights = field(default_factory=RewardWeights)
    feature_config: FeatureConfig = field(default_factory=FeatureConfig)
    action_spec: ActionSpaceSpec = field(default_factory=ActionSpaceSpec)
    repair_illegal_actions: bool = True
    cba_rules_path: str | None = None
    cba_season: str = "2025-26"


class NBA2KGMEnv(BaseEnv):
    """Gymnasium-style environment around the editor adapter."""

    metadata: Dict = {"render.modes": []}

    def __init__(self, adapter: EditorAdapter, cfg: GMEnvConfig) -> None:
        self.adapter = adapter
        self.cfg = cfg
        self.encoder = FeatureEncoder(cfg.feature_config)
        self.cba_rules: CbaRuleSet | None = None
        try:
            self.cba_rules = load_ruleset_for_season(cfg.cba_season, cfg.cba_rules_path)
        except Exception:
            self.cba_rules = None
        self.grammar = ActionGrammar(cfg.action_spec, repair_illegal=cfg.repair_illegal_actions, cba_rules=self.cba_rules)
        self.mask_builder = ActionMaskBuilder(cfg.action_spec, cba_rules=self.cba_rules)
        self.state: RosterState | None = None
        self.steps = 0
        self._rng = np.random.default_rng()
        self._active_team_id: int = cfg.team_id

        self.action_space = MultiDiscrete(cfg.action_spec.sizes)

        # Gymnasium requires observation_space to be a Space. Keep a dict for convenience and expose
        # a flattened Box as the official observation_space.
        self._obs_dict = {
            "team": Box(-np.inf, np.inf, shape=(self.encoder._team_dim(),), dtype=np.float32),
            "players": Box(-np.inf, np.inf, shape=(cfg.feature_config.max_players, self.encoder._player_dim()), dtype=np.float32),
            "player_mask": Box(0, 1, shape=(cfg.feature_config.max_players,), dtype=np.int8),
            "league": Box(-np.inf, np.inf, shape=(self.encoder._league_dim(),), dtype=np.float32),
        }
        flat_dim = (
            self.encoder._team_dim()
            + cfg.feature_config.max_players * self.encoder._player_dim()
            + cfg.feature_config.max_players
            + self.encoder._league_dim()
        )
        self.observation_space = Box(-np.inf, np.inf, shape=(flat_dim,), dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: Dict | None = None) -> Tuple[Dict[str, np.ndarray], Dict]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self.state = self.adapter.load_roster_state(seed=seed)
        self.steps = 0
        if self.state and self.cfg.team_id < 0:
            try:
                self._active_team_id = int(self._rng.integers(0, len(self.state.teams)))
            except Exception:
                self._active_team_id = 0
        else:
            self._active_team_id = self.cfg.team_id
        obs_batch = self.encoder.encode(self.state, self._active_team_id, update_stats=True)
        info = {"action_mask": self._build_action_mask()}
        return self._to_obs_dict(obs_batch), info

    def step(self, action: Sequence[int]) -> Tuple[Dict[str, np.ndarray], float, bool, bool, Dict]:
        assert self.state is not None, "call reset before step"
        self.steps += 1
        head = cast(Tuple[int, int, int, int, int], tuple(int(a) for a in action))
        txn = self.grammar.decode(head, self.state, self._active_team_id)
        result = self.adapter.apply_gm_action(txn)
        for code in self.grammar.last_cba_block_reasons:
            result.metadata[code] = 1.0
        for code in self.grammar.last_cba_warn_reasons:
            result.metadata[code] = 1.0
        if self.grammar.last_cba_citation_ids:
            result.metadata["cba_citation_ids"] = ",".join(self.grammar.last_cba_citation_ids)
        self.state = result.new_state
        reward = self._compute_reward(result.metadata)
        terminated = self.steps >= self._episode_length()
        truncated = False
        obs_batch = self.encoder.encode(self.state, self._active_team_id, update_stats=True)
        info = {"metadata": result.metadata, "action_mask": self._build_action_mask()}
        return self._to_obs_dict(obs_batch), reward, terminated, truncated, info

    # Helpers -------------------------------------------------------------
    def _to_obs_dict(self, batch: ObservationBatch) -> Dict[str, np.ndarray]:
        return {"team": batch.team, "players": batch.players, "player_mask": batch.player_mask, "league": batch.league}

    def _episode_length(self) -> int:
        if self.cfg.step_granularity == "week":
            return math.ceil(self.cfg.horizon_games / 3.0)
        return self.cfg.horizon_games

    def _build_action_mask(self) -> Dict[str, np.ndarray]:
        assert self.state is not None
        mask = self.mask_builder.build(self.state, self._active_team_id)
        info = {
            "draft": mask.draft.cpu().numpy(),
            "trade": mask.trade.cpu().numpy(),
            "rotation": mask.rotation.cpu().numpy(),
            "contract": mask.contract.cpu().numpy(),
            "roster_move": mask.roster_move.cpu().numpy(),
        }
        if self.mask_builder.last_cba_block_reasons:
            info["cba_block_reasons"] = list(self.mask_builder.last_cba_block_reasons)
        if self.mask_builder.last_cba_warn_reasons:
            info["cba_warn_reasons"] = list(self.mask_builder.last_cba_warn_reasons)
        if self.mask_builder.last_cba_citation_ids:
            info["cba_citation_ids"] = list(self.mask_builder.last_cba_citation_ids)
        return info

    def _compute_reward(self, metadata: Dict[str, float]) -> float:
        assert self.state is not None
        team = self.state.get_team(self._active_team_id)
        rw = self.cfg.reward_weights

        # short-term: net rating proxy
        net_rating = team.offensive_rating - team.defensive_rating
        short_term = rw.win_weight * net_rating / 10.0

        # asset value proxy: draft picks + cheapest contract headroom
        asset_value = rw.asset_weight * (team.assets.get("1st_round", 0.0) + team.assets.get("2nd_round", 0.0))

        # player value: aggregate of offensive/defensive/other/pro/physical attributes
        player_values = [self._player_value(self.state.players[pid]) for pid in team.roster]
        team_player_value = float(np.mean(player_values)) if player_values else 0.0
        player_value_term = rw.player_value_weight * team_player_value

        # playoff positioning: higher rank (lower number) rewarded
        max_rank = max(1, len(self.state.teams))
        rank_score = (max_rank - (team.playoff_rank - 1)) / max_rank
        rank_term = rw.rank_weight * rank_score

        # development: negative variance of minutes encourages balanced growth
        minutes = np.array(list(team.rotation.values())) if team.rotation else np.zeros(1)
        development = -rw.development_weight * float(np.var(minutes) / 100.0)

        # realism penalties based on metadata flags
        realism = 0.0
        if metadata.get("rotation_rejected_minutes_cap"):
            realism -= rw.realism_penalty
        if metadata.get("rejected_roster_full"):
            realism -= rw.realism_penalty
        if metadata.get("trade_invalid_player"):
            realism -= rw.realism_penalty

        return float(short_term + asset_value + player_value_term + rank_term + development + realism)

    def _player_value(self, player) -> float:
        s = player.stats
        p = player.physicals
        # Offensive core per-minute normalization
        min_div = max(player.minutes_per_game, 1e-3)
        offense = (
            (s.pts + 1.5 * s.ast + 1.2 * s.oreb - 1.2 * s.tov)
            + 0.5 * (s.efg_pct + s.ft_pct + s.three_p_pct + s.two_p_pct)
            + 0.3 * (s.ftr + s.ast_pct + s.three_par + s.oreb_pct)
            + 0.2 * (s.bench_pts + s.pts_per_poss + s.paint_pts - s.tov_pct)
        ) / min_div
        # Defensive
        defense = (
            s.stl
            + s.blk
            + 0.6 * s.dreb
            + 0.4 * (s.dflc + s.chrg + s.recov)
            + 0.3 * (s.dreb_pct + s.stl_pct + s.blk_pct)
            - 0.2 * s.pf
        ) / min_div
        # Other impact
        other = (s.plus_minus + s.eff + s.pie + s.tf - s.inf) / min_div

        # Pro metrics (optional)
        pro_terms = []
        if self.cfg.feature_config.include_pro_metrics:
            pro_candidates = [s.per, s.dpr, s.pir, s.tsp, s.apm, s.bpm, s.vorp, s.opr, s.similarity_score]
            pro_terms = [float(x) for x in pro_candidates if x is not None and not math.isnan(x)]
        pro_val = float(np.mean(pro_terms)) if pro_terms else 0.0

        # Physical attributes (normalized to 0-1 range inputs)
        phys_val = np.mean(
            [
                p.strength_upper,
                p.strength_lower,
                p.speed,
                p.agility,
                p.endurance,
                p.height_in / 96.0,  # ~8ft normalization
                p.standing_reach_in / 110.0,
                p.wingspan_in / 110.0,
                p.flexibility,
                p.balance,
                p.contact_management,
                p.high_intensity_capacity,
            ]
        )

        return float(offense + defense + other + 0.5 * pro_val + phys_val)


# --------------------------------------------------------------------------- #
# Simple synchronous vectorized wrapper
# --------------------------------------------------------------------------- #


class SyncVecEnv:
    def __init__(self, env_fns: List[Callable[[], "NBA2KGMEnv"]]) -> None:
        self.envs = [fn() for fn in env_fns]

    @property
    def num_envs(self) -> int:
        return len(self.envs)

    def reset(self, seed: int | None = None) -> Tuple[Dict[str, np.ndarray], List[Dict]]:
        obs_list = []
        info_list = []
        for idx, env in enumerate(self.envs):
            obs, info = env.reset(seed=seed + idx if seed is not None else None)
            obs_list.append(obs)
            info_list.append(info)
        batched = self._stack(obs_list)
        return batched, info_list

    def step(self, actions: Sequence[Sequence[int]]) -> Tuple[Dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray, List[Dict]]:
        obs_list = []
        rewards = []
        terms = []
        truncs = []
        infos = []
        for env, act in zip(self.envs, actions):
            o, r, t, tr, info = env.step(act)
            obs_list.append(o)
            rewards.append(r)
            terms.append(t)
            truncs.append(tr)
            infos.append(info)
        batched_obs = self._stack(obs_list)
        return batched_obs, np.array(rewards, dtype=np.float32), np.array(terms, dtype=bool), np.array(truncs, dtype=bool), infos

    def _stack(self, obs_list: List[Dict[str, np.ndarray]]) -> Dict[str, np.ndarray]:
        keys = obs_list[0].keys()
        return {k: np.stack([o[k] for o in obs_list], axis=0) for k in keys}


def make_vec_env(env_fn, n_envs: int, seed: int | None = None) -> SyncVecEnv:
    return SyncVecEnv([env_fn for _ in range(n_envs)])
