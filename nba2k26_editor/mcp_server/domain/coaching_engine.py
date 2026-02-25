from __future__ import annotations

from ..api.v1.models import RosterPlayer


class CoachingEngine:
    def system_fit(self, *, scheme: str, roster: list[RosterPlayer]) -> dict[str, float | str]:
        if not roster:
            return {"scheme": scheme, "fit_score": 0.0}
        spacing = sum(player.overall for player in roster) / (len(roster) * 100.0)
        age_factor = sum(max(0.0, 35.0 - player.age) for player in roster) / (len(roster) * 20.0)
        fit_score = max(0.0, min(1.0, (spacing * 0.7) + (age_factor * 0.3)))
        return {"scheme": scheme, "fit_score": round(fit_score, 4)}
