from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict

from nba2k_editor.gm_rl.adapters.base import (
    ContractInfo,
    EditorAdapter,
    GMActionResult,
    LeagueContext,
    PhysicalAttributes,
    PlayerState,
    PlayerStats,
    RosterState,
)
from nba2k_editor.gm_rl.adapters.local_mock import LocalMockAdapter
from nba2k_editor.gm_rl.adapters.editor_state import LiveRosterBuilder


def _resolve_editor_base_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Offsets").is_dir() and (parent / "NBA Player Data").is_dir():
            return parent
    return here.parents[2]


BASE_DIR = _resolve_editor_base_dir()


class EditorLiveAdapter(EditorAdapter):
    """Adapter that pulls live data from the editor when available."""

    def __init__(
        self,
        model=None,
        offsets_dir: Path | str = BASE_DIR / "Offsets",
        player_data_dir: Path | str = BASE_DIR / "NBA Player Data",
        dry_run: bool = True,
        seed: int = 11,
    ) -> None:
        self.model = model
        self.dry_run = dry_run
        self.offsets_dir = Path(offsets_dir)
        self.player_data_dir = Path(player_data_dir)
        self.seed = seed
        self._fallback = LocalMockAdapter(data_path=self.player_data_dir / "NBA DATA Master.xlsx", seed=seed)
        self._builder = LiveRosterBuilder(model, self._fallback, dry_run=dry_run) if model is not None else None
        self._state: RosterState | None = None

    def load_roster_state(self, seed: Optional[int] = None) -> RosterState:
        if self._builder is not None:
            try:
                self._state = self._builder.build(seed=seed)
                return self._state
            except Exception:
                pass
        self._state = self._fallback.load_roster_state(seed=seed)
        return self._state

    def load_league_context(self) -> LeagueContext:
        if self._state is None:
            self.load_roster_state(seed=self.seed)
        if self._state is None:
            return self._fallback.load_league_context()
        return self._state.context

    def apply_gm_action(self, action: "GMTransaction") -> GMActionResult:
        state = self._state or self.load_roster_state(seed=self.seed)
        metadata: Dict[str, float] = {}
        ctx = state.context

        if action.head == "draft":
            new_id = max(state.players.keys()) + 1 if state.players else 1
            player = self._make_prospect(new_id, action.payload.get("draft_slot", 0), action.payload.get("team_id", 0))
            state.players[new_id] = player
            team = state.teams.get(player.team_id)
            if team:
                if len(team.roster) < ctx.maximum_roster:
                    team.roster.append(new_id)
                    team.rotation[new_id] = player.minutes_per_game
                    metadata["accepted"] = 1.0
                else:
                    metadata["rejected_roster_full"] = 1.0
            else:
                metadata["rejected_roster_full"] = 1.0

        elif action.head == "trade":
            team_id = action.payload.get("team_id")
            target = action.payload.get("target_player_id")
            secondary = action.payload.get("secondary_player_id")
            accept = bool(action.payload.get("accept", False))
            if accept and target in state.players and secondary in state.players:
                p_target = state.players[target]
                p_secondary = state.players[secondary]
                team_a = state.teams.get(p_target.team_id)
                team_b = state.teams.get(p_secondary.team_id)
                if team_a and team_b:
                    self._swap_players(team_a, team_b, p_target, p_secondary)
                    metadata["trade_executed"] = 1.0
                else:
                    metadata["trade_invalid_player"] = 1.0
            else:
                metadata["trade_invalid_player"] = 1.0

        elif action.head == "rotation":
            team_id = action.payload.get("team_id")
            minutes_map = action.payload.get("minutes", {}) or {}
            team = state.teams.get(team_id)
            if team:
                total_minutes = sum(minutes_map.values())
                cap = ctx.max_minutes_per_game * max(1, team.roster_size())
                if total_minutes <= cap:
                    for pid, mins in minutes_map.items():
                        if pid in team.rotation:
                            team.rotation[pid] = float(mins)
                    metadata["rotation_applied"] = 1.0
                else:
                    metadata["rotation_rejected_minutes_cap"] = 1.0

        elif action.head == "contract":
            pid = action.payload.get("target_player_id")
            if pid in state.players:
                player = state.players[pid]
                player.contract.salary = float(action.payload.get("contract_value", player.contract.salary))
                player.contract.years_left = int(action.payload.get("contract_years", player.contract.years_left))
                player.contract.is_extension = True
                metadata["extension_signed"] = 1.0
            else:
                metadata["contract_rejected_missing_player"] = 1.0

        elif action.head == "roster_move":
            team_id = action.payload.get("team_id")
            team = state.teams.get(team_id)
            waive_id = action.payload.get("waive_player_id")
            sign_id = action.payload.get("sign_player_id")
            if team:
                if waive_id and waive_id in team.roster:
                    team.roster.remove(waive_id)
                    team.rotation.pop(waive_id, None)
                    if waive_id in state.players:
                        state.players[waive_id].team_id = -1
                    metadata["waived"] = 1.0
                if sign_id and sign_id in state.players and sign_id not in team.roster:
                    if len(team.roster) < ctx.maximum_roster:
                        team.roster.append(sign_id)
                        team.rotation[sign_id] = 12.0
                        state.players[sign_id].team_id = team_id
                        metadata["signed"] = 1.0
                    else:
                        metadata["sign_rejected_roster_full"] = 1.0

        self._refresh_payrolls()
        self._state = state
        return GMActionResult(new_state=state, metadata=metadata)

    def get_salary_cap(self, team_id: int) -> float:
        if self._state is None:
            self.load_roster_state(seed=self.seed)
        if self._state and team_id in self._state.teams:
            return self._state.teams[team_id].salary_cap
        return self._fallback.get_salary_cap(team_id)

    def get_payroll(self, team_id: int) -> float:
        if self._state is None:
            self.load_roster_state(seed=self.seed)
        if self._state and team_id in self._state.teams:
            return self._state.teams[team_id].payroll
        return self._fallback.get_payroll(team_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _make_prospect(self, player_id: int, draft_slot: int, team_id: int) -> PlayerState:
        base = 12.0 + max(0, 10 - draft_slot) * 0.6
        stats = PlayerStats(
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
        phys = PhysicalAttributes(
            strength_upper=0.6,
            strength_lower=0.6,
            speed=0.62,
            agility=0.62,
            endurance=0.62,
            height_in=77 + (2 if draft_slot < 10 else 0),
            standing_reach_in=98 + (2 if draft_slot < 10 else 0),
            wingspan_in=82 + (2 if draft_slot < 10 else 0),
            flexibility=0.5,
            balance=0.5,
            contact_management=0.5,
            high_intensity_capacity=0.62,
        )
        contract = ContractInfo(salary=7_500_000.0, years_left=4, is_extension=False)
        return PlayerState(
            player_id=player_id,
            name=f"Prospect-{draft_slot}",
            position="G",
            age=20,
            stats=stats,
            physicals=phys,
            contract=contract,
            role="rookie",
            fatigue=0.05,
            injury_risk=0.05,
            team_id=team_id,
            minutes_per_game=22.0,
        )

    @staticmethod
    def _swap_players(team_a, team_b, player_a: PlayerState, player_b: PlayerState) -> None:
        if player_a.player_id in team_a.roster and player_b.player_id in team_b.roster:
            team_a.roster[team_a.roster.index(player_a.player_id)] = player_b.player_id
            team_b.roster[team_b.roster.index(player_b.player_id)] = player_a.player_id
            team_a.rotation[player_b.player_id] = team_a.rotation.pop(player_a.player_id, player_a.minutes_per_game)
            team_b.rotation[player_a.player_id] = team_b.rotation.pop(player_b.player_id, player_b.minutes_per_game)
            player_a.team_id, player_b.team_id = team_b.team_id, team_a.team_id

    def _refresh_payrolls(self) -> None:
        if self._state is None:
            return
        for team in self._state.teams.values():
            team.payroll = sum(
                self._state.players[pid].contract.salary for pid in team.roster if pid in self._state.players
            )


from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from nba2k_editor.gm_rl.actions import GMTransaction
