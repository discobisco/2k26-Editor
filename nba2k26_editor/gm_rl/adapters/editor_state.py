from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Optional, TYPE_CHECKING

import numpy as np

from nba2k_editor.gm_rl.adapters.base import (
    ContractInfo,
    LeagueContext,
    PhysicalAttributes,
    PlayerState,
    PlayerStats,
    RosterState,
    TeamState,
)
from nba2k_editor.gm_rl.adapters.local_mock import LocalMockAdapter

if TYPE_CHECKING:  # pragma: no cover
    from nba2k_editor.models.data_model import PlayerDataModel
    from nba2k_editor.models.player import Player


def _default_context() -> LeagueContext:
    return LeagueContext(
        season_year=2026,
        total_weeks=26,
        current_week=0,
        games_played=0,
        games_per_season=82,
        trade_deadline_week=18,
        soft_cap=136_000_000.0,
        hard_cap=170_000_000.0,
        luxury_tax_line=150_000_000.0,
        minimum_roster=13,
        maximum_roster=15,
        max_minutes_per_game=48.0,
        first_apron_level=187_500_000.0,
        second_apron_level=199_000_000.0,
        moratorium_start="July 1 12:01 AM ET",
        moratorium_end="July 6 12:00 PM ET",
    )


def _synthetic_stats(rng: np.random.Generator) -> PlayerStats:
    return PlayerStats(
        two_pa=8.0 + float(rng.random()),
        two_p=5.0 + float(rng.random()),
        two_p_pct=0.52,
        three_pa=5.0 + float(rng.random()),
        three_p=2.0 + float(rng.random()),
        three_p_pct=0.36,
        fga=13.0 + float(rng.random()),
        fg=7.0 + float(rng.random()),
        fg_pct=0.45,
        efg_pct=0.52,
        fta=4.0 + float(rng.random()),
        ft=3.5 + float(rng.random()),
        ft_pct=0.82,
        pts=17.0 + float(rng.random()),
        ast=5.0 + float(rng.random()),
        oreb=1.5 + float(rng.random()),
        tov=2.1 + float(rng.random()),
        ftr=0.25,
        ast_pct=0.18,
        three_par=0.38,
        oreb_pct=0.1,
        bench_pts=6.0 + float(rng.random()),
        pts_per_poss=1.06,
        paint_pts=6.5 + float(rng.random()),
        tov_pct=0.13,
        stl=1.0 + float(rng.random()),
        blk=0.4 + float(rng.random()),
        pf=2.8 + float(rng.random()),
        dreb=3.2 + float(rng.random()),
        dflc=0.6 + float(rng.random() * 0.1),
        chrg=0.12 + float(rng.random() * 0.05),
        recov=0.75 + float(rng.random() * 0.05),
        dreb_pct=0.17,
        stl_pct=0.022,
        blk_pct=0.025,
        tf=0.12,
        inf=0.08,
        minutes=26.0 + float(rng.random() * 4),
        plus_minus=1.0 + float(rng.random()),
        eff=19.0 + float(rng.random() * 3),
        pie=0.12 + float(rng.random() * 0.01),
    )


def _synthetic_phys(rng: np.random.Generator) -> PhysicalAttributes:
    return PhysicalAttributes(
        strength_upper=0.6 + float(rng.random() * 0.2),
        strength_lower=0.6 + float(rng.random() * 0.2),
        speed=0.6 + float(rng.random() * 0.2),
        agility=0.6 + float(rng.random() * 0.2),
        endurance=0.6 + float(rng.random() * 0.2),
        height_in=74 + int(rng.integers(-3, 5)),
        standing_reach_in=94 + int(rng.integers(-2, 4)),
        wingspan_in=80 + int(rng.integers(-2, 5)),
        flexibility=0.5 + float(rng.random() * 0.1),
        balance=0.5 + float(rng.random() * 0.1),
        contact_management=0.5 + float(rng.random() * 0.1),
        high_intensity_capacity=0.6 + float(rng.random() * 0.1),
    )


def _clone_stats(stats: PlayerStats) -> PlayerStats:
    return PlayerStats(**asdict(stats))


def _clone_phys(phys: PhysicalAttributes) -> PhysicalAttributes:
    return PhysicalAttributes(**asdict(phys))


def _norm_name(text: str) -> str:
    return " ".join(str(text or "").lower().split())


class LiveRosterBuilder:
    """Transform a PlayerDataModel snapshot into the gm_rl RosterState."""

    def __init__(self, model: "PlayerDataModel", fallback: LocalMockAdapter, dry_run: bool = True) -> None:
        self.model = model
        self.fallback = fallback
        self.dry_run = dry_run
        self._fallback_cache: RosterState | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self, seed: Optional[int] = None) -> RosterState:
        """Return a RosterState sourced from live memory when possible."""
        if self.model is None:
            return self._fallback_state(seed)
        try:
            self.model.refresh_players()
        except Exception:
            return self._fallback_state(seed)

        players_list: list[Player] = getattr(self.model, "players", None) or []
        if not players_list:
            return self._fallback_state(seed)

        team_entries = getattr(self.model, "team_list", None) or []
        if not team_entries:
            build = getattr(self.model, "_build_team_list_from_players", None)
            if callable(build):
                try:
                    team_entries = build(players_list)
                except Exception:
                    team_entries = []

        fb_state = self._fallback_state(seed)
        fb_by_name: Dict[str, PlayerState] = {}
        if fb_state:
            for pl in fb_state.players.values():
                fb_by_name[_norm_name(pl.name)] = pl
        ctx = fb_state.context if fb_state else _default_context()

        rng = np.random.default_rng(seed)
        players: Dict[int, PlayerState] = {}
        team_rosters: Dict[int, list[int]] = {}

        for idx, p in enumerate(players_list):
            player_id = int(getattr(p, "index", idx))
            name_parts = []
            for attr in ("first_name", "last_name"):
                val = getattr(p, attr, "") or ""
                if val:
                    name_parts.append(val)
            name = " ".join(name_parts).strip() or getattr(p, "full_name", f"Player {player_id}")

            fb = fb_by_name.get(_norm_name(name))
            stats = _clone_stats(fb.stats) if fb else _synthetic_stats(rng)
            physicals = _clone_phys(fb.physicals) if fb else _synthetic_phys(rng)
            contract = ContractInfo(
                salary=float(fb.contract.salary if fb else 8_000_000.0),
                years_left=int(fb.contract.years_left if fb else 3),
                is_extension=False,
            )
            position = getattr(p, "position", None) or (fb.position if fb else "G")
            age_val = getattr(p, "age", None)
            age = int(age_val if age_val is not None else (fb.age if fb else 24))
            team_id = getattr(p, "team_id", None)
            if team_id is None:
                team_id = -1
            minutes = float(getattr(fb, "minutes_per_game", stats.minutes))

            role = "starter" if len(team_rosters.get(team_id, [])) < 5 else "bench"
            player_state = PlayerState(
                player_id=player_id,
                name=name,
                position=str(position or "G"),
                age=age,
                stats=stats,
                physicals=physicals,
                contract=contract,
                role=role,
                fatigue=0.05,
                injury_risk=0.05,
                team_id=team_id,
                minutes_per_game=minutes,
            )
            players[player_id] = player_state
            team_rosters.setdefault(team_id, []).append(player_id)

        teams: Dict[int, TeamState] = {}
        for team_id, name in team_entries:
            roster = team_rosters.get(team_id, [])
            rotation = {pid: players[pid].minutes_per_game for pid in roster}
            payroll = sum(players[pid].contract.salary for pid in roster)
            teams[int(team_id)] = TeamState(
                team_id=int(team_id),
                name=str(name),
                wins=0,
                losses=0,
                division="",
                conference="East" if int(team_id) % 2 == 0 else "West",
                playoff_rank=max(1, int(team_id) if isinstance(team_id, int) else 1),
                possessions_per_game=99.5,
                salary_cap=ctx.soft_cap,
                payroll=payroll,
                luxury_tax_line=ctx.luxury_tax_line,
                roster=roster,
                rotation=rotation,
                assets={"1st_round": 1.0, "2nd_round": 1.0},
                defensive_rating=110.0,
                offensive_rating=112.0,
            )

        for tid, roster in team_rosters.items():
            if tid in teams:
                continue
            rotation = {pid: players[pid].minutes_per_game for pid in roster}
            payroll = sum(players[pid].contract.salary for pid in roster)
            teams[int(tid)] = TeamState(
                team_id=int(tid),
                name="Free Agents" if tid == -1 else f"Team {tid}",
                wins=0,
                losses=0,
                division="",
                conference="",
                playoff_rank=1,
                possessions_per_game=99.5,
                salary_cap=ctx.soft_cap,
                payroll=payroll,
                luxury_tax_line=ctx.luxury_tax_line,
                roster=roster,
                rotation=rotation,
                assets={"1st_round": 0.0, "2nd_round": 0.0},
                defensive_rating=110.0,
                offensive_rating=112.0,
            )

        return RosterState(teams=teams, players=players, context=ctx)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _fallback_state(self, seed: Optional[int]) -> RosterState:
        if self._fallback_cache is None:
            self._fallback_cache = self.fallback.load_roster_state(seed=seed)
        return self._fallback_cache


__all__ = ["LiveRosterBuilder"]
