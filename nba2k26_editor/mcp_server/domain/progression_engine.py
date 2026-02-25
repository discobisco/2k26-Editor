from __future__ import annotations

import random

from ..api.v1.models import ProgressionResult, RosterPlayer


class ProgressionEngine:
    def _yearly_delta(self, *, age: int, potential: float, rng: random.Random) -> float:
        potential_factor = (potential - 50.0) / 50.0
        if age <= 24:
            return rng.uniform(0.8, 3.8) * (0.7 + potential_factor)
        if age <= 28:
            return rng.uniform(-0.5, 1.8) * (0.6 + potential_factor)
        if age <= 31:
            return rng.uniform(-2.4, 0.9) * (0.6 + potential_factor * 0.5)
        return rng.uniform(-4.0, -0.8) * (0.5 + potential_factor * 0.3)

    def _injury_risk(self, age: int, years: int) -> float:
        base = 0.05 + (max(0, age - 24) * 0.01) + (years * 0.01)
        return max(0.01, min(0.95, base))

    def simulate(self, *, players: list[RosterPlayer], years: int, seed: int) -> list[ProgressionResult]:
        rng = random.Random(seed)
        results: list[ProgressionResult] = []
        for player in players:
            current = player.overall
            age = player.age
            for _ in range(years):
                current += self._yearly_delta(age=age, potential=player.potential, rng=rng)
                age += 1
            current = max(40.0, min(99.0, current))
            results.append(
                ProgressionResult(
                    player_id=player.player_id,
                    before_overall=float(round(player.overall, 2)),
                    after_overall=float(round(current, 2)),
                    injury_risk=float(round(self._injury_risk(player.age, years), 4)),
                )
            )
        return results
