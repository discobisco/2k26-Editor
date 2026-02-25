from __future__ import annotations

from nba2k_editor.gm_rl.adapters.local_mock import LocalMockAdapter

from ..api.v1.models import FranchiseState, RosterPlayer


class GmRlAdapter:
    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._mock = LocalMockAdapter(seed=seed)

    def load_franchise_state(self, *, team_id: int = 0) -> FranchiseState:
        state = self._mock.load_roster_state(seed=self._seed)
        team = state.get_team(team_id)
        roster: list[RosterPlayer] = []
        for pid in team.roster:
            player = state.get_player(pid)
            overall = max(45.0, min(99.0, (player.stats.pts * 2.2) + 45.0))
            potential = max(45.0, min(99.0, overall + ((25 - player.age) * 0.9)))
            roster.append(
                RosterPlayer(
                    player_id=player.player_id,
                    name=player.name,
                    team=team.name,
                    age=player.age,
                    overall=round(overall, 2),
                    potential=round(potential, 2),
                    contract_years=player.contract.years_left,
                    salary=player.contract.salary,
                )
            )
        payroll = sum(player.salary for player in roster)
        cap_space = max(0.0, team.salary_cap - payroll)
        return FranchiseState(
            era="2025-26",
            team=team.name,
            cap_space=cap_space,
            owner_goal="win-now",
            roster=roster,
        )
