from __future__ import annotations

import random

from ..api.v1.models import DraftClass, DraftProspect
from ..errors import ServiceError

_FIRST_NAMES = [
    "Jalen",
    "Cooper",
    "Malik",
    "Andre",
    "Darius",
    "Cameron",
    "Isaiah",
    "Terrence",
    "Marcus",
    "Tobias",
]
_LAST_NAMES = [
    "Brooks",
    "Henderson",
    "Williams",
    "Bates",
    "Ellis",
    "Jackson",
    "Parker",
    "Mills",
    "Thompson",
    "Stewart",
]
_POSITIONS = ["PG", "SG", "SF", "PF", "C"]


class DraftEngine:
    def generate_class(
        self,
        *,
        era: str,
        season: str,
        class_size: int,
        seed: int,
        include_historical_imports: bool,
    ) -> DraftClass:
        if era.lower() != "modern":
            raise ServiceError(
                status_code=400,
                code="UNSUPPORTED_ERA",
                message=f"Draft generation currently supports only modern era. Got '{era}'.",
                details={"supported_eras": ["modern"]},
            )

        rng = random.Random(seed)
        prospects: list[DraftProspect] = []
        for _ in range(class_size):
            name = f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
            age = rng.randint(19, 23)
            base = rng.uniform(63, 82)
            if include_historical_imports:
                base += 0.8
            floor = max(50.0, base - rng.uniform(4, 12))
            ceiling = min(99.0, base + rng.uniform(6, 15))
            scouting_confidence = rng.uniform(0.35, 0.92)
            prospects.append(
                DraftProspect(
                    name=name,
                    age=age,
                    position=rng.choice(_POSITIONS),
                    overall=round(base, 2),
                    potential_floor=round(floor, 2),
                    potential_ceiling=round(ceiling, 2),
                    scouting_confidence=round(scouting_confidence, 4),
                )
            )
        return DraftClass(era=era, seed=seed, prospects=prospects)

    def simulate_lottery(self, *, teams: list[str], odds: list[float], seed: int, draws: int = 1) -> list[str]:
        if len(teams) < 2:
            raise ServiceError(
                status_code=400,
                code="INVALID_LOTTERY_INPUT",
                message="At least two teams are required for lottery simulation.",
                details={},
            )
        if odds and len(odds) != len(teams):
            raise ServiceError(
                status_code=400,
                code="INVALID_LOTTERY_INPUT",
                message="Odds length must match teams length.",
                details={"teams": len(teams), "odds": len(odds)},
            )
        weights = odds[:] if odds else [1.0 for _ in teams]
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ServiceError(
                status_code=400,
                code="INVALID_LOTTERY_ODDS",
                message="Lottery odds must be non-negative with a positive total.",
                details={},
            )

        rng = random.Random(seed)
        pairings = list(zip(teams, weights))
        # Re-run draws and return the final draw outcome to support convergence tests.
        order: list[str] = teams[:]
        for _ in range(draws):
            remaining = pairings[:]
            order = []
            while remaining:
                names = [team for team, _ in remaining]
                probs = [weight for _, weight in remaining]
                pick = rng.choices(names, weights=probs, k=1)[0]
                order.append(pick)
                remaining = [(team, weight) for team, weight in remaining if team != pick]
        return order
