from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping


EARLY_HONORS_LAST_SEASON = 1954
HONOR_ATTRIBUTE_KEYS = frozenset(
    {
        "Attributes/INTANGIBLES",
        "Attributes/HUSTLE",
        "Attributes/OFFENSIVECONSISTENCY",
        "Attributes/DEFENSECONSISTENCY",
    }
)


def season_honors_by_player(database: str | Path, season: int) -> dict[str, dict[str, tuple[Any, ...]]]:
    path = Path(database).expanduser().resolve()
    honors: dict[str, dict[str, list[Any]]] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute(
            """
            SELECT award, player_id
            FROM player_award_shares
            WHERE season = ? AND winner = 1 AND player_id IS NOT NULL
            ORDER BY award, player_id
            """,
            (int(season),),
        ):
            player_id = str(row["player_id"] or "").strip().upper()
            award = str(row["award"] or "").strip().lower()
            if player_id and award:
                honors.setdefault(player_id, {"award_wins": [], "all_teams": []})["award_wins"].append(award)
        for row in connection.execute(
            """
            SELECT lg, type, number_tm, player_id
            FROM all_teams
            WHERE season = ? AND player_id IS NOT NULL
            ORDER BY lg, type, number_tm, player_id
            """,
            (int(season),),
        ):
            player_id = str(row["player_id"] or "").strip().upper()
            if not player_id:
                continue
            selection = (
                str(row["lg"] or "").strip().upper(),
                str(row["type"] or "").strip(),
                str(row["number_tm"] or "").strip().lower(),
            )
            honors.setdefault(player_id, {"award_wins": [], "all_teams": []})["all_teams"].append(selection)
    return {
        player_id: {
            "award_wins": tuple(data["award_wins"]),
            "all_teams": tuple(data["all_teams"]),
        }
        for player_id, data in honors.items()
    }


def early_honor_attribute_bonus(evidence: Any) -> tuple[int, tuple[str, ...]]:
    season = int(getattr(evidence, "season", 0) or 0)
    if season <= 0 or season > EARLY_HONORS_LAST_SEASON:
        return 0, ()
    league = str(getattr(evidence, "season_info", {}).get("lg") or "").strip().upper()
    source_context = getattr(evidence, "source_context", {})
    honors = source_context.get("season_honors") if isinstance(source_context, dict) else None
    if not isinstance(honors, Mapping):
        return 0, ()

    candidates: list[tuple[int, str]] = []
    league_prefix = league.lower() + " " if league else ""
    for award in honors.get("award_wins", ()):
        normalized = str(award or "").strip().lower()
        if league_prefix and not normalized.startswith(league_prefix):
            continue
        if normalized.endswith(" mvp"):
            candidates.append((8, f"player_award_shares:{normalized}:winner"))
        elif normalized.endswith(" roy"):
            candidates.append((3, f"player_award_shares:{normalized}:winner"))
    for selection in honors.get("all_teams", ()):
        if not isinstance(selection, (tuple, list)) or len(selection) != 3:
            continue
        selection_league, selection_type, number_team = selection
        if str(selection_league or "").strip().upper() != league:
            continue
        normalized_team = str(number_team or "").strip().lower()
        if normalized_team == "1st":
            candidates.append((6, f"all_teams:{selection_league}:{selection_type}:1st"))
        elif normalized_team == "2nd":
            candidates.append((3, f"all_teams:{selection_league}:{selection_type}:2nd"))
    if not candidates:
        return 0, ()
    bonus, source = max(candidates, key=lambda item: (item[0], item[1]))
    return bonus, (
        "early_season_honors_scope=attributes_only",
        "honor_attribute_fields=INTANGIBLES,HUSTLE,OFFENSIVECONSISTENCY,DEFENSECONSISTENCY",
        "honor_tier_uses_max_not_stack",
        source,
        f"honor_attribute_bonus={bonus}",
    )


__all__ = [
    "EARLY_HONORS_LAST_SEASON",
    "HONOR_ATTRIBUTE_KEYS",
    "early_honor_attribute_bonus",
    "season_honors_by_player",
]
