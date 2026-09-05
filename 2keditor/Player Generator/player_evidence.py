from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class PlayerEvidence:
    player_id: str
    season: int
    team: str
    identity: dict[str, Any]
    season_info: dict[str, Any]
    per_game: dict[str, Any]
    totals: dict[str, Any]
    per_36: dict[str, Any]
    per_100: dict[str, Any]
    advanced: dict[str, Any]
    shooting: dict[str, Any]
    play_by_play: dict[str, Any]
    team_roster: tuple[dict[str, Any], ...]
    team_stats_per_game: dict[str, Any]
    team_stats_per_100: dict[str, Any]
    team_summary: dict[str, Any]
    opponent_stats_per_game: dict[str, Any]
    opponent_stats_per_100: dict[str, Any]
    source_context: dict[str, Any]
    missing_sources: tuple[str, ...]
    shotquality_contest: dict[str, Any] = field(default_factory=dict)


@lru_cache(maxsize=None)
def shotquality_contest_rows(
    database_path: str,
    season: int,
    league: str,
) -> dict[str, dict[str, Any]]:
    """Load exact mapped season-level dContest rows from the Data Master."""

    if str(league).strip().upper() != "NBA":
        return {}
    uri = f"file:{database_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        required_tables = {"crafted_source_shotquality", "crafted_player_id_map", "player_per_game"}
        available_tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not required_tables.issubset(available_tables):
            return {}
        source_rows = connection.execute(
            """
            SELECT
                CAST(CAST(s.nba_id AS INTEGER) AS TEXT) AS nba_id,
                CAST(s.year AS INTEGER) AS season,
                s.team_abbreviation AS source_team_abbreviation,
                s.dcontest,
                m.player_id,
                m.match_method
            FROM crafted_source_shotquality AS s
            JOIN crafted_player_id_map AS m
              ON m.nba_id = CAST(CAST(s.nba_id AS INTEGER) AS TEXT)
             AND m.status = 'mapped'
             AND m.player_id IS NOT NULL
            WHERE CAST(s.year AS INTEGER) = ?
              AND s.dcontest IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM player_per_game AS p
                  WHERE p.season = ?
                    AND upper(p.lg) = 'NBA'
                    AND upper(p.player_id) = upper(m.player_id)
                    AND p.g > 0
              )
            ORDER BY m.player_id, s.source_row_id
            """,
            (int(season), int(season)),
        )

        rows: dict[str, dict[str, Any]] = {}
        ambiguous: set[str] = set()
        for source_row in source_rows:
            player_id = str(source_row["player_id"] or "").strip().upper()
            if not player_id or player_id in ambiguous:
                continue
            if player_id in rows:
                rows.pop(player_id, None)
                ambiguous.add(player_id)
                continue
            row = dict(source_row)
            row["identity_contract"] = "crafted_player_id_map.status=mapped;nba_id_only;no_name_fallback"
            row["source_database"] = "NBA_DATA_Master.sqlite"
            row["source_table"] = "crafted_source_shotquality"
            row["source_grain"] = "exact_nba_id_season"
            rows[player_id] = row
        return rows


__all__ = ["PlayerEvidence", "shotquality_contest_rows"]
