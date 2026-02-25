from __future__ import annotations

import math
import random

from ..api.v1.models import SeasonOutcome, TeamStrengthInput


class SimulationEngine:
    def _win_probability(self, strength: float, league_avg: float) -> float:
        return 1.0 / (1.0 + math.exp(-((strength - league_avg) / 9.0)))

    def simulate_season(
        self,
        *,
        team_strengths: list[TeamStrengthInput],
        iterations: int,
        seed: int,
        pace_factor: float,
    ) -> list[SeasonOutcome]:
        rng = random.Random(seed)
        league_avg = sum(entry.strength for entry in team_strengths) / max(1, len(team_strengths))
        wins_by_team = {entry.team: 0 for entry in team_strengths}
        champ_counts = {entry.team: 0 for entry in team_strengths}

        for _ in range(iterations):
            trial_wins: dict[str, int] = {}
            for entry in team_strengths:
                p_win = self._win_probability(entry.strength, league_avg)
                wins = sum(1 for _ in range(82) if rng.random() <= p_win)
                trial_wins[entry.team] = wins
                wins_by_team[entry.team] += wins
            champion = max(trial_wins.items(), key=lambda x: (x[1], rng.random()))[0]
            champ_counts[champion] += 1

        outcomes: list[SeasonOutcome] = []
        for entry in sorted(team_strengths, key=lambda item: item.team):
            avg_wins = wins_by_team[entry.team] / iterations
            playoff_odds = max(0.0, min(1.0, (avg_wins - 25.0) / 35.0))
            champ_odds = champ_counts[entry.team] / iterations
            outcomes.append(
                SeasonOutcome(
                    team=entry.team,
                    wins=int(round(avg_wins)),
                    losses=82 - int(round(avg_wins)),
                    playoff_odds=float(round(playoff_odds, 4)),
                    championship_odds=float(round(champ_odds, 4)),
                    pace_adjustment=float(round(pace_factor, 4)),
                )
            )
        return outcomes
