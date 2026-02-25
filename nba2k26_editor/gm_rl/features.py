from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import torch

from nba2k_editor.gm_rl.adapters.base import PlayerState, RosterState, safe_ratio


@dataclass
class FeatureConfig:
    max_players: int = 15
    include_pro_metrics: bool = True
    impute_value: float = 0.0
    normalize_observations: bool = True
    reward_normalization: bool = False
    eps: float = 1e-8


@dataclass
class ObservationBatch:
    team: np.ndarray
    players: np.ndarray
    player_mask: np.ndarray
    league: np.ndarray

    def to_torch(self, device: torch.device) -> Dict[str, torch.Tensor]:
        return {
            "team": torch.as_tensor(self.team, device=device, dtype=torch.float32),
            "players": torch.as_tensor(self.players, device=device, dtype=torch.float32),
            "player_mask": torch.as_tensor(self.player_mask, device=device, dtype=torch.bool),
            "league": torch.as_tensor(self.league, device=device, dtype=torch.float32),
        }


class RunningMeanStd:
    """Track running mean/var for online normalization."""

    def __init__(self, shape: Tuple[int, ...]) -> None:
        self.mean = np.zeros(shape, dtype=np.float64)
        self.var = np.ones(shape, dtype=np.float64)
        self.count = 1e-4

    def update(self, x: np.ndarray) -> None:
        x = np.asarray(x, dtype=np.float64)
        batch_mean = x.mean(axis=0)
        batch_var = x.var(axis=0)
        batch_count = x.shape[0]
        delta = batch_mean - self.mean
        tot_count = self.count + batch_count
        new_mean = self.mean + delta * batch_count / tot_count
        m_a = self.var * self.count
        m_b = batch_var * batch_count
        new_var = (m_a + m_b + delta ** 2 * self.count * batch_count / tot_count) / tot_count
        self.mean, self.var, self.count = new_mean, new_var, tot_count

    def normalize(self, x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
        return (x - self.mean) / np.sqrt(self.var + eps)


class FeatureEncoder:
    def __init__(self, cfg: FeatureConfig) -> None:
        self.cfg = cfg
        # running stats for team, player, league vectors
        self.team_norm = RunningMeanStd((self._team_dim(),))
        self.player_norm = RunningMeanStd((self._player_dim(),))
        self.league_norm = RunningMeanStd((self._league_dim(),))

    # Public API -----------------------------------------------------------
    def encode(self, state: RosterState, team_id: int, update_stats: bool = True) -> ObservationBatch:
        team_vec = self._team_features(state, team_id)
        league_vec = self._league_features(state)
        player_table, mask = self._player_table(state, team_id)

        if self.cfg.normalize_observations:
            if update_stats:
                self.team_norm.update(team_vec[None, :])
                self.player_norm.update(player_table)
                self.league_norm.update(league_vec[None, :])
            team_vec = self.team_norm.normalize(team_vec)
            player_table = self.player_norm.normalize(player_table)
            league_vec = self.league_norm.normalize(league_vec)

        return ObservationBatch(team=team_vec, players=player_table, player_mask=mask, league=league_vec)

    # Feature assembly ----------------------------------------------------
    def _team_features(self, state: RosterState, team_id: int) -> np.ndarray:
        team = state.get_team(team_id)
        players = [state.players[pid] for pid in team.roster]
        pts = np.array([p.stats.pts for p in players], dtype=np.float64)
        poss = np.array([state.players[pid].stats.pts_per_poss for pid in team.roster], dtype=np.float64)
        net_rating = safe_ratio(pts.mean(), poss.mean() * 100.0 / 48.0)
        payroll_ratio = safe_ratio(team.payroll, team.salary_cap)
        wins, losses = team.wins, team.losses
        usage = np.array([p.minutes_per_game for p in players], dtype=np.float64)
        avg_usage = usage.mean() if usage.size else 0.0
        division_id = float(self._encode_division(team.division))
        conference_id = float(self._encode_conference(team.conference))
        playoff_rank = float(team.playoff_rank)
        vec = np.array(
            [
                wins,
                losses,
                team.offensive_rating,
                team.defensive_rating,
                net_rating,
                payroll_ratio,
                len(team.roster),
                avg_usage,
                division_id,
                conference_id,
                playoff_rank,
            ],
            dtype=np.float32,
        )
        vec = np.nan_to_num(vec, nan=self.cfg.impute_value)
        return vec

    def _league_features(self, state: RosterState) -> np.ndarray:
        ctx = state.context
        vec = np.array(
            [
                ctx.season_year,
                ctx.total_weeks,
                ctx.current_week,
                ctx.games_played,
                ctx.games_per_season,
                ctx.trade_deadline_week,
                ctx.soft_cap,
                ctx.hard_cap,
                ctx.luxury_tax_line,
                ctx.minimum_roster,
                ctx.maximum_roster,
                ctx.max_minutes_per_game,
                ctx.first_apron_level,
                ctx.second_apron_level,
                1.0 if ctx.moratorium_start else 0.0,
                1.0 if ctx.moratorium_end else 0.0,
            ],
            dtype=np.float32,
        )
        return np.nan_to_num(vec, nan=self.cfg.impute_value)

    def _player_table(self, state: RosterState, team_id: int) -> Tuple[np.ndarray, np.ndarray]:
        team = state.get_team(team_id)
        roster_players = [state.players[pid] for pid in team.roster]
        roster_players = sorted(roster_players, key=lambda p: (-p.minutes_per_game, p.player_id))
        rows: List[np.ndarray] = []
        mask_rows: List[bool] = []
        for player in roster_players[: self.cfg.max_players]:
            rows.append(self._player_row(player))
            mask_rows.append(True)
        # pad
        while len(rows) < self.cfg.max_players:
            rows.append(np.zeros(self._player_dim(), dtype=np.float32))
            mask_rows.append(False)
        table = np.stack(rows, axis=0)
        mask = np.array(mask_rows, dtype=bool)
        return table, mask

    # Dimensions -----------------------------------------------------------
    def _team_dim(self) -> int:
        return 11

    def _league_dim(self) -> int:
        return 16

    def _player_dim(self) -> int:
        # Keep in sync with _player_row mandatory feature count.
        base = 41
        pro = 9 if self.cfg.include_pro_metrics else 0
        physicals = 12
        return base + pro + physicals

    # Player row ----------------------------------------------------------
    def _player_row(self, p: PlayerState) -> np.ndarray:
        s = p.stats
        phys = p.physicals
        base_feats = [
            s.two_pa,
            s.two_p,
            s.two_p_pct,
            s.three_pa,
            s.three_p,
            s.three_p_pct,
            s.fga,
            s.fg,
            s.fg_pct,
            s.efg_pct,
            s.fta,
            s.ft,
            s.ft_pct,
            s.pts,
            s.ast,
            s.oreb,
            s.tov,
            s.ftr,
            s.ast_pct,
            s.three_par,
            s.oreb_pct,
            s.bench_pts,
            s.pts_per_poss,
            s.paint_pts,
            s.tov_pct,
            s.stl,
            s.blk,
            s.pf,
            s.dreb,
            s.dflc,
            s.chrg,
            s.recov,
            s.dreb_pct,
            s.stl_pct,
            s.blk_pct,
            s.tf,
            s.inf,
            s.minutes,
            s.plus_minus,
            s.eff,
            s.pie,
        ]
        pro_feats = []
        if self.cfg.include_pro_metrics:
            pro_feats = [
                self._opt_val(s.per),
                self._opt_val(s.dpr),
                self._opt_val(s.pir),
                self._opt_val(s.tsp),
                self._opt_val(s.apm),
                self._opt_val(s.bpm),
                self._opt_val(s.vorp),
                self._opt_val(s.opr),
                self._opt_val(s.similarity_score),
            ]
        phys_feats = [
            phys.strength_upper,
            phys.strength_lower,
            phys.speed,
            phys.agility,
            phys.endurance,
            phys.height_in,
            phys.standing_reach_in,
            phys.wingspan_in,
            phys.flexibility,
            phys.balance,
            phys.contact_management,
            phys.high_intensity_capacity,
        ]
        row = np.array(base_feats + pro_feats + phys_feats, dtype=np.float32)
        row = np.nan_to_num(row, nan=self.cfg.impute_value)
        return row

    def _opt_val(self, v: float | None) -> float:
        return float(v) if v is not None and not np.isnan(v) else self.cfg.impute_value

    def _encode_division(self, division: str) -> int:
        order = [
            "Atlantic",
            "Central",
            "Southeast",
            "Pacific",
            "Northwest",
            "Southwest",
        ]
        try:
            return order.index(division)
        except ValueError:
            return 0

    def _encode_conference(self, conference: str) -> int:
        return 0 if conference.lower().startswith("e") else 1
