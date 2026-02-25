from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from nba2k_editor.gm_rl.adapters.base import (
    ContractInfo,
    EditorAdapter,
    GMActionResult,
    LeagueContext,
    PhysicalAttributes,
    PlayerState,
    PlayerStats,
    RosterState,
    TeamState,
)
from nba2k_editor.gm_rl.adapters.base import safe_ratio


def _resolve_editor_base_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Offsets").is_dir() and (parent / "NBA Player Data").is_dir():
            return parent
    return here.parents[2]


BASE_DIR = _resolve_editor_base_dir()


class LocalMockAdapter(EditorAdapter):
    """Deterministic adapter that synthesizes a league from the bundled NBA data workbook."""

    def __init__(
        self,
        data_path: Path | str = BASE_DIR / "NBA Player Data" / "NBA DATA Master.xlsx",
        seed: int = 7,
    ) -> None:
        self.data_path = Path(data_path)
        self.seed = seed
        self._state: Optional[RosterState] = None

    # Adapter API ----------------------------------------------------------
    def load_roster_state(self, seed: Optional[int] = None) -> RosterState:
        rng = np.random.default_rng(seed if seed is not None else self.seed)
        players = self._load_players(rng)
        teams = self._build_teams(players, rng)
        context = LeagueContext(
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
        self._state = RosterState(teams=teams, players=players, context=context)
        return self._state

    def load_league_context(self) -> LeagueContext:
        if self._state is None:
            self.load_roster_state()
        assert self._state is not None
        return self._state.context

    def apply_gm_action(self, action: "GMTransaction") -> GMActionResult:
        if self._state is None:
            raise RuntimeError("call load_roster_state before applying actions")
        metadata: Dict[str, float] = {}
        state = self._state
        ctx = state.context

        if action.head == "draft":
            new_id = max(state.players.keys()) + 1
            # deterministic prospect
            stats = self._prospect_stats(action.payload.get("draft_slot", 0))
            phys = self._prospect_phys(action.payload.get("draft_slot", 0))
            player = PlayerState(
                player_id=new_id,
                name=f"Prospect-{action.payload.get('draft_slot', 0)}",
                position="G",
                age=20,
                stats=stats,
                physicals=phys,
                contract=ContractInfo(salary=7_500_000.0, years_left=4, is_extension=False),
                role="rookie",
                fatigue=0.05,
                injury_risk=0.05,
                team_id=action.payload["team_id"],
                minutes_per_game=18.0,
            )
            state.players[new_id] = player
            team = state.teams[action.payload["team_id"]]
            if len(team.roster) < ctx.maximum_roster:
                team.roster.append(new_id)
                team.rotation[new_id] = 18.0
                metadata["accepted"] = 1.0
            else:
                metadata["rejected_roster_full"] = 1.0

        elif action.head == "trade":
            team_id = action.payload["team_id"]
            target = action.payload.get("target_player_id")
            secondary = action.payload.get("secondary_player_id")
            accept = bool(action.payload.get("accept", False))
            if accept and target is not None and secondary is not None:
                # swap players if both exist
                if target in state.players and secondary in state.players:
                    p1 = state.players[target]
                    p2 = state.players[secondary]
                    team_a = state.teams[team_id]
                    team_b = state.teams[p2.team_id]
                    self._swap_players(team_a, team_b, p1.player_id, p2.player_id)
                    metadata["trade_executed"] = 1.0
                else:
                    metadata["trade_invalid_player"] = 1.0
            else:
                metadata["trade_declined"] = 1.0

        elif action.head == "rotation":
            team_id = action.payload["team_id"]
            minutes_map = action.payload.get("minutes", {})
            team = state.teams[team_id]
            total_minutes = sum(minutes_map.values())
            if total_minutes <= team.roster_size() * ctx.max_minutes_per_game:
                for pid, mins in minutes_map.items():
                    if pid in team.rotation:
                        team.rotation[pid] = float(mins)
                metadata["rotation_applied"] = 1.0
            else:
                metadata["rotation_rejected_minutes_cap"] = 1.0

        elif action.head == "contract":
            pid = action.payload["target_player_id"]
            if pid in state.players:
                player = state.players[pid]
                player.contract.salary = float(action.payload.get("contract_value", player.contract.salary))
                player.contract.years_left = int(action.payload.get("contract_years", player.contract.years_left))
                player.contract.is_extension = True
                metadata["extension_signed"] = 1.0
            else:
                metadata["contract_rejected_missing_player"] = 1.0

        elif action.head == "roster_move":
            team_id = action.payload["team_id"]
            team = state.teams[team_id]
            waive_id = action.payload.get("waive_player_id")
            sign_id = action.payload.get("sign_player_id")
            if waive_id and waive_id in team.roster:
                team.roster.remove(waive_id)
                team.rotation.pop(waive_id, None)
                metadata["waived"] = 1.0
            if sign_id and sign_id in state.players and sign_id not in team.roster:
                if len(team.roster) < ctx.maximum_roster:
                    team.roster.append(sign_id)
                    team.rotation[sign_id] = 12.0
                    state.players[sign_id].team_id = team_id
                    metadata["signed"] = 1.0
                else:
                    metadata["sign_rejected_roster_full"] = 1.0

        self._state = state
        return GMActionResult(new_state=state, metadata=metadata)

    def get_salary_cap(self, team_id: int) -> float:
        assert self._state is not None
        return self._state.teams[team_id].salary_cap

    def get_payroll(self, team_id: int) -> float:
        assert self._state is not None
        return self._state.teams[team_id].payroll

    # Internals ------------------------------------------------------------
    def _load_players(self, rng: np.random.Generator) -> Dict[int, PlayerState]:
        if self.data_path.exists():
            players = self._load_players_from_workbook(rng)
        else:
            players = self._synthetic_players(rng)
        return players

    def _load_players_from_workbook(self, rng: np.random.Generator) -> Dict[int, PlayerState]:
        per_game = pd.read_excel(self.data_path, sheet_name="Player Per Game")
        bio = pd.read_excel(self.data_path, sheet_name="Player Info")
        per_game = per_game.dropna(subset=["player"]).reset_index(drop=True)
        # Align by player name (lowercased)
        bio = bio.rename(columns=str.lower)
        per_game = per_game.rename(columns=str.lower)
        bio["key"] = bio["player"].str.lower()
        per_game["key"] = per_game["player"].str.lower()
        bio = bio.set_index("key")

        players: Dict[int, PlayerState] = {}
        max_players = 450  # 30 teams * 15 players
        for idx, row in per_game.head(max_players).iterrows():
            key = row["key"]
            bio_row_obj = bio.loc[key] if key in bio.index else {}
            if isinstance(bio_row_obj, pd.DataFrame):
                bio_row_obj = bio_row_obj.iloc[0] if not bio_row_obj.empty else {}
            if isinstance(bio_row_obj, pd.Series):
                bio_row = bio_row_obj.to_dict()
            elif isinstance(bio_row_obj, dict):
                bio_row = bio_row_obj
            else:
                bio_row = {}
            player_id = idx + 1
            height_in = float(bio_row.get("ht_in_in", 78.0))
            stats = PlayerStats(
                two_pa=float(row.get("fga", 0.0) * 0.6),
                two_p=float(row.get("fg_percent", 0.0) * row.get("fga", 0.0) * 0.6),
                two_p_pct=float(row.get("fg_percent", 0.0)),
                three_pa=float(row.get("fga", 0.0) * 0.4),
                three_p=float(row.get("x3p_percent", 0.0) * row.get("fga", 0.0) * 0.4),
                three_p_pct=float(row.get("x3p_percent", 0.0)),
                fga=float(row.get("fga", 0.0)),
                fg=float(row.get("fg_percent", 0.0) * row.get("fga", 0.0)),
                fg_pct=float(row.get("fg_percent", 0.0)),
                efg_pct=safe_ratio(
                    float(row.get("fg_percent", 0.0) * row.get("fga", 0.0) + 1.5 * row.get("x3p_percent", 0.0) * row.get("fga", 0.0) * 0.4),
                    max(row.get("fga", 0.0), 1.0),
                ),
                fta=float(row.get("fta", 0.0)),
                ft=float(row.get("ft_percent", 0.0) * row.get("fta", 0.0)),
                ft_pct=float(row.get("ft_percent", 0.0)),
                pts=float(row.get("pts_per_game", 0.0)),
                ast=float(row.get("ast_per_game", 0.0)),
                oreb=float(row.get("trb_per_game", 0.0) * 0.35),
                tov=float(row.get("tov_per_game", 0.0) if "tov_per_game" in row else 2.0),
                ftr=safe_ratio(float(row.get("fta", 0.0)), float(row.get("fga", 1.0))),
                ast_pct=safe_ratio(float(row.get("ast_per_game", 0.0)), float(row.get("pts_per_game", 1.0))),
                three_par=safe_ratio(float(row.get("x3pa_per_game", row.get("fga", 0.0) * 0.4)), float(row.get("fga", 1.0))),
                oreb_pct=0.15,
                bench_pts=float(row.get("pts_per_game", 0.0)) * (0.25 if idx % 5 else 0.1),
                pts_per_poss=safe_ratio(float(row.get("pts_per_game", 0.0)), 100.0 / 48.0 * float(row.get("mp_per_game", 1.0))),
                paint_pts=float(row.get("pts_per_game", 0.0) * 0.35),
                tov_pct=safe_ratio(float(row.get("tov_per_game", 2.0)), float(row.get("fga", 1.0))),
                stl=float(row.get("stl_per_game", 0.0)),
                blk=float(row.get("blk_per_game", 0.0)),
                pf=float(row.get("pf_per_game", 3.0) if "pf_per_game" in row else 3.0),
                dreb=float(row.get("trb_per_game", 0.0) * 0.65),
                dflc=0.5 + 0.1 * rng.standard_normal(),
                chrg=0.2 + 0.05 * rng.standard_normal(),
                recov=0.7 + 0.05 * rng.standard_normal(),
                dreb_pct=0.18,
                stl_pct=0.025,
                blk_pct=0.03,
                tf=0.1,
                inf=0.05,
                minutes=float(row.get("mp_per_game", 24.0)),
                plus_minus=float(row.get("pts_per_game", 0.0) * 0.2),
                eff=float(row.get("pts_per_game", 0.0) + row.get("trb_per_game", 0.0) + row.get("ast_per_game", 0.0) - row.get("tov_per_game", 2.0)),
                pie=float(row.get("pts_per_game", 0.0) / 30.0),
                per=None,
                dpr=None,
                pir=None,
                tsp=None,
                apm=None,
                bpm=None,
                vorp=None,
                opr=None,
                similarity_score=None,
                pecota_forecast=None,
            )
            physicals = PhysicalAttributes(
                strength_upper=0.5 + 0.5 * rng.random(),
                strength_lower=0.5 + 0.5 * rng.random(),
                speed=0.5 + 0.5 * rng.random(),
                agility=0.5 + 0.5 * rng.random(),
                endurance=0.5 + 0.5 * rng.random(),
                height_in=height_in,
                standing_reach_in=height_in + 8.0,
                wingspan_in=height_in + 6.0,
                flexibility=0.4 + 0.4 * rng.random(),
                balance=0.4 + 0.4 * rng.random(),
                contact_management=0.4 + 0.4 * rng.random(),
                high_intensity_capacity=0.5 + 0.5 * rng.random(),
            )
            players[player_id] = PlayerState(
                player_id=player_id,
                name=str(row["player"]),
                position=str(row.get("pos", "G")),
                age=int(bio_row.get("to", 2026) - bio_row.get("from", 2022) + 19)
                if "to" in bio_row and "from" in bio_row
                else 24,
                stats=stats,
                physicals=physicals,
                contract=ContractInfo(
                    salary=float(row.get("pts_per_game", 0.0)) * 1_000_000.0 / 1.5,
                    years_left=3,
                    is_extension=False,
                ),
                role="starter" if idx % 5 else "bench",
                fatigue=0.05,
                injury_risk=0.05 + 0.01 * rng.random(),
                team_id=idx % 30,
                minutes_per_game=float(row.get("mp_per_game", 24.0)),
            )
        return players

    def _synthetic_players(self, rng: np.random.Generator) -> Dict[int, PlayerState]:
        players: Dict[int, PlayerState] = {}
        total_players = 30 * 15
        for pid in range(1, total_players + 1):
            stats = PlayerStats(
                two_pa=8.0 + rng.random(),
                two_p=5.0 + rng.random(),
                two_p_pct=0.52,
                three_pa=5.0 + rng.random(),
                three_p=2.0 + rng.random(),
                three_p_pct=0.36,
                fga=13.0 + rng.random(),
                fg=7.0 + rng.random(),
                fg_pct=0.45,
                efg_pct=0.52,
                fta=4.0 + rng.random(),
                ft=3.5 + rng.random(),
                ft_pct=0.82,
                pts=17.0 + rng.random(),
                ast=5.0 + rng.random(),
                oreb=1.5 + rng.random(),
                tov=2.1 + rng.random(),
                ftr=0.25,
                ast_pct=0.18,
                three_par=0.38,
                oreb_pct=0.1,
                bench_pts=6.0 + rng.random(),
                pts_per_poss=1.06,
                paint_pts=6.5 + rng.random(),
                tov_pct=0.13,
                stl=1.0 + rng.random(),
                blk=0.4 + rng.random(),
                pf=2.8 + rng.random(),
                dreb=3.2 + rng.random(),
                dflc=0.6 + rng.random() * 0.1,
                chrg=0.12 + rng.random() * 0.05,
                recov=0.75 + rng.random() * 0.05,
                dreb_pct=0.17,
                stl_pct=0.022,
                blk_pct=0.025,
                tf=0.12,
                inf=0.08,
                minutes=26.0 + rng.random() * 4,
                plus_minus=1.0 + rng.random(),
                eff=19.0 + rng.random() * 3,
                pie=0.12 + rng.random() * 0.01,
            )
            physicals = PhysicalAttributes(
                strength_upper=0.6 + rng.random() * 0.2,
                strength_lower=0.6 + rng.random() * 0.2,
                speed=0.6 + rng.random() * 0.2,
                agility=0.6 + rng.random() * 0.2,
                endurance=0.6 + rng.random() * 0.2,
                height_in=74 + rng.integers(-3, 5),
                standing_reach_in=94 + rng.integers(-2, 4),
                wingspan_in=80 + rng.integers(-2, 5),
                flexibility=0.5 + rng.random() * 0.1,
                balance=0.5 + rng.random() * 0.1,
                contact_management=0.5 + rng.random() * 0.1,
                high_intensity_capacity=0.6 + rng.random() * 0.1,
            )
            players[pid] = PlayerState(
                player_id=pid,
                name=f"Mock Player {pid}",
                position="G" if pid % 3 == 0 else "F" if pid % 3 == 1 else "C",
                age=int(22 + rng.integers(0, 10)),
                stats=stats,
                physicals=physicals,
                contract=ContractInfo(salary=8_000_000.0 + 200_000 * pid, years_left=3),
                role="starter" if pid % 5 != 0 else "bench",
                fatigue=0.05,
                injury_risk=0.07,
                team_id=(pid - 1) % 30,
                minutes_per_game=28.0,
            )
        return players

    def _build_teams(self, players: Dict[int, PlayerState], rng: np.random.Generator) -> Dict[int, TeamState]:
        teams: Dict[int, TeamState] = {}
        team_ids = list(range(30))
        team_names = [f"Mock Team {tid}" for tid in team_ids]
        divisions = ["Atlantic", "Central", "Southeast", "Pacific", "Northwest", "Southwest"]
        conferences = ["East"] * 15 + ["West"] * 15
        for tid, name in zip(team_ids, team_names):
            roster = [pid for pid, p in players.items() if p.team_id == tid][:15]
            rotation = {pid: players[pid].minutes_per_game for pid in roster}
            payroll = float(np.mean([players[pid].contract.salary for pid in roster])) * len(roster)
            teams[tid] = TeamState(
                team_id=tid,
                name=name,
                wins=int(rng.integers(10, 40)),
                losses=int(rng.integers(5, 40)),
                division=divisions[tid % len(divisions)],
                conference=conferences[tid],
                playoff_rank=int(tid + 1),
                possessions_per_game=99.5 + rng.random(),
                salary_cap=136_000_000.0,
                payroll=payroll,
                luxury_tax_line=150_000_000.0,
                roster=roster,
                rotation=rotation,
                assets={"1st_round": 1.0, "2nd_round": 1.0},
                defensive_rating=110.0 + rng.random() * 4,
                offensive_rating=112.0 + rng.random() * 4,
            )
        return teams

    def _swap_players(self, team_a: TeamState, team_b: TeamState, pid_a: int, pid_b: int) -> None:
        if pid_a in team_a.roster and pid_b in team_b.roster:
            team_a.roster[team_a.roster.index(pid_a)] = pid_b
            team_b.roster[team_b.roster.index(pid_b)] = pid_a
            team_a.rotation[pid_b] = team_a.rotation.pop(pid_a, 18.0)
            team_b.rotation[pid_a] = team_b.rotation.pop(pid_b, 18.0)
        # Update player team ids
        self._state.players[pid_a].team_id, self._state.players[pid_b].team_id = (
            team_b.team_id,
            team_a.team_id,
        )

    def _prospect_stats(self, draft_slot: int) -> PlayerStats:
        base = 12.0 + max(0, 10 - draft_slot) * 0.6
        return PlayerStats(
            two_pa=8.0,
            two_p=5.0,
            two_p_pct=0.55,
            three_pa=4.0,
            three_p=1.6,
            three_p_pct=0.4,
            fga=12.0,
            fg=6.6,
            fg_pct=0.52,
            efg_pct=0.57,
            fta=4.0,
            ft=3.4,
            ft_pct=0.85,
            pts=base,
            ast=3.0,
            oreb=1.6,
            tov=2.2,
            ftr=0.32,
            ast_pct=0.16,
            three_par=0.33,
            oreb_pct=0.08,
            bench_pts=4.0,
            pts_per_poss=1.05,
            paint_pts=5.0,
            tov_pct=0.12,
            stl=1.2,
            blk=0.5,
            pf=2.5,
            dreb=3.0,
            dflc=0.65,
            chrg=0.18,
            recov=0.7,
            dreb_pct=0.16,
            stl_pct=0.022,
            blk_pct=0.025,
            tf=0.1,
            inf=0.07,
            minutes=22.0,
            plus_minus=1.5,
            eff=18.0,
            pie=0.13,
        )

    def _prospect_phys(self, draft_slot: int) -> PhysicalAttributes:
        base = 0.55 + 0.02 * max(0, 10 - draft_slot)
        return PhysicalAttributes(
            strength_upper=base,
            strength_lower=base,
            speed=base + 0.05,
            agility=base + 0.05,
            endurance=base + 0.05,
            height_in=77 + (2 if draft_slot < 10 else 0),
            standing_reach_in=98 + (2 if draft_slot < 10 else 0),
            wingspan_in=82 + (2 if draft_slot < 10 else 0),
            flexibility=0.5,
            balance=0.5,
            contact_management=0.5,
            high_intensity_capacity=base + 0.05,
        )


# Late import for type checking
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from nba2k_editor.gm_rl.actions import GMTransaction
