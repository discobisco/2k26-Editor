from __future__ import annotations

from ..api.v1.models import DynastySeasonInput, DynastySnapshot


class DynastyEngine:
    def track(self, *, team: str, history: list[DynastySeasonInput]) -> DynastySnapshot:
        seasons = len(history)
        rings = sum(item.rings for item in history)
        mvps = sum(item.mvps for item in history)
        all_nba = sum(item.all_nba for item in history)
        wins = sum(item.wins for item in history)
        avg_wins = wins / max(1, seasons)

        legacy_score = (rings * 22.0) + (mvps * 9.5) + (all_nba * 2.75) + (avg_wins * 0.35)
        summary = (
            f"{team} legacy profile: {rings} rings, {mvps} MVPs, {all_nba} All-NBA selections "
            f"across {seasons} seasons."
        )
        return DynastySnapshot(
            team=team,
            seasons=seasons,
            rings=rings,
            mvps=mvps,
            all_nba=all_nba,
            legacy_score=float(round(legacy_score, 2)),
            summary=summary,
        )
