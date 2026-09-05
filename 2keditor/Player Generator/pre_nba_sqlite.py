from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from player_evidence import PlayerEvidence


_DATABASE_NAME = "pre_nba.sqlite"
_DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parent / "NBA Player Data"
_MIN_SEASON = 1898
_MAX_SEASON = 1946
_MISSING_PLAYER_SOURCES = (
    "Player Per 36 min",
    "Player Per 100 Poss",
    "Advanced",
    "Player Shooting",
    "Player Play by Play",
)
_MISSING_TEAM_SOURCES = (
    "Team Stats Per Game",
    "Team Stats Per 100 Pos",
    "Opponent Stats Per Game",
    "Opponent Stats Per 100 Poss",
)


@dataclass(frozen=True)
class PreNbaSeasonPayload:
    database_path: Path
    season: int
    selected_league: str | None
    comparison_rows: tuple[dict[str, Any], ...]
    evidence_by_key: dict[tuple[str, str], PlayerEvidence]


def pre_nba_database_path(source_root: str | Path | None = None) -> Path:
    root = Path(source_root).expanduser().resolve() if source_root is not None else _DEFAULT_SOURCE_ROOT
    database = (root / _DATABASE_NAME).resolve()
    if not database.is_file():
        raise FileNotFoundError(f"pre-NBA SQLite database does not exist: {database}")
    with _connect(database) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        }
    required = {"players", "player_season", "teams", "v_pro_season"}
    missing = sorted(required - tables)
    if missing:
        raise ValueError(f"pre-NBA SQLite database is missing required objects: {', '.join(missing)}")
    return database


def available_pre_nba_seasons(source_root: str | Path | None = None) -> tuple[int, ...]:
    database = pre_nba_database_path(source_root)
    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT season_start_year
            FROM v_pro_season
            WHERE season_start_year BETWEEN ? AND ?
              AND ga > 0
              AND is_multi_year_span = 0
            ORDER BY season_start_year
            """,
            (_MIN_SEASON, _MAX_SEASON),
        ).fetchall()
    return tuple(int(row[0]) for row in rows)


def load_pre_nba_season_payload(
    source_root: str | Path,
    season: int,
    *,
    selected_league: str | None = None,
) -> PreNbaSeasonPayload:
    database = pre_nba_database_path(source_root)
    league = str(selected_league or "").strip().upper()
    if league == "ALL LEAGUES":
        league = ""
    return _cached_pre_nba_season_payload(str(database), int(season), league)


@lru_cache(maxsize=None)
def _cached_pre_nba_season_payload(
    database_path: str,
    season: int,
    selected_league: str,
) -> PreNbaSeasonPayload:
    if season < _MIN_SEASON or season > _MAX_SEASON:
        raise ValueError(f"pre-NBA season must be between {_MIN_SEASON} and {_MAX_SEASON}: {season}")
    database = Path(database_path)
    with _connect(database) as connection:
        sql = """
            SELECT *
            FROM v_pro_season
            WHERE season_start_year = ?
              AND ga > 0
              AND is_multi_year_span = 0
        """
        params: list[Any] = [season]
        if selected_league:
            sql += " AND upper(league) = ?"
            params.append(selected_league)
        sql += " ORDER BY player_id, id"
        source_rows = tuple(dict(row) for row in connection.execute(sql, params))
        team_rows = tuple(
            dict(row)
            for row in connection.execute(
                "SELECT * FROM teams WHERE season_start_year = ? ORDER BY id",
                (season,),
            )
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        player_id = str(row.get("player_id") or "").strip()
        if player_id:
            grouped[player_id].append(row)

    team_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in team_rows:
        key = (_normalized(row.get("team_norm")), _normalized(row.get("league")))
        team_index[key].append(row)

    aggregates = tuple(
        _aggregate_player_year(rows, season=season, selected_league=selected_league, team_index=team_index)
        for _player_id, rows in sorted(grouped.items(), key=lambda item: item[0].upper())
    )
    roster_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for aggregate in aggregates:
        roster_rows[(aggregate["league"], aggregate["team_key"])].append(aggregate["season_info"])

    evidence_by_key: dict[tuple[str, str], PlayerEvidence] = {}
    comparison_rows: list[dict[str, Any]] = []
    for aggregate in aggregates:
        key = (aggregate["player_id"].upper(), aggregate["team_key"])
        team_summary = aggregate["team_summary"]
        missing = [*_MISSING_PLAYER_SOURCES, *_MISSING_TEAM_SOURCES]
        if not team_summary:
            missing.append("Team Summaries")
        source_context = dict(aggregate["comparison_row"])
        source_context.update(aggregate["source_context"])
        evidence_by_key[key] = PlayerEvidence(
            player_id=aggregate["player_id"],
            season=season,
            team=aggregate["team_key"],
            identity=aggregate["identity"],
            season_info=aggregate["season_info"],
            per_game=aggregate["per_game"],
            totals=aggregate["totals"],
            per_36={},
            per_100={},
            advanced={},
            shooting={},
            play_by_play={},
            team_roster=tuple(roster_rows.get((aggregate["league"], aggregate["team_key"]), ())),
            team_stats_per_game={},
            team_stats_per_100={},
            team_summary=team_summary,
            opponent_stats_per_game={},
            opponent_stats_per_100={},
            source_context=source_context,
            missing_sources=tuple(missing),
            shotquality_contest={},
        )
        comparison_rows.append(source_context)

    return PreNbaSeasonPayload(
        database_path=database,
        season=season,
        selected_league=selected_league or None,
        comparison_rows=tuple(comparison_rows),
        evidence_by_key=evidence_by_key,
    )


def _aggregate_player_year(
    rows: list[dict[str, Any]],
    *,
    season: int,
    selected_league: str,
    team_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    ordered = tuple(sorted(rows, key=lambda row: int(row["id"])))
    primary = max(ordered, key=lambda row: (_number(row.get("ga")) or 0.0, -int(row["id"])))
    positioned = tuple(row for row in ordered if str(row.get("pos") or "").strip())
    position_row = max(
        positioned,
        key=lambda row: (_number(row.get("ga")) or 0.0, -int(row["id"])),
    ) if positioned else None

    player_id = str(primary.get("player_id") or "").strip()
    player_name = " ".join(
        part for part in (str(primary.get("first_name") or "").strip(), str(primary.get("last_name") or "").strip()) if part
    ) or player_id
    team_name = str(primary.get("team") or "").strip()
    team_key = _normalized(team_name or primary.get("team_norm") or "NA") or "NA"
    league = selected_league or _normalized(primary.get("league"))
    raw_position = str(position_row.get("pos") or "").strip() if position_row is not None else ""
    games = sum(float(row["ga"]) for row in ordered)
    aggregate_totals = {
        column: _complete_sum(ordered, column)
        for column in ("fgm", "ftm", "fta", "ast", "pts")
    }
    end_year = max(int(row["season_end_year"]) for row in ordered)
    born = str(primary.get("born") or "").strip()
    birth = _parse_birth_date(born)
    age = _age_on_january_31(birth, end_year) if birth is not None else None
    birth_serial = (birth - date(1899, 12, 30)).days if birth is not None else None

    identity = _without_none({
        "player": player_name,
        "player_id": player_id,
        "pos": raw_position or None,
        "ht_in_in": primary.get("height_in"),
        "wt": primary.get("weight_lb"),
        "colleges": primary.get("college"),
        "birth_date": birth_serial,
        "source_url": primary.get("source_url"),
        "born_raw": born or None,
    })
    season_info = _without_none({
        "season": season,
        "season_start_year": season,
        "season_end_year": end_year,
        "season_raw": primary.get("season_raw") or primary.get("season"),
        "lg": league,
        "player": player_name,
        "player_id": player_id,
        "team": team_key,
        "source_team": team_name or None,
        "team_norm": primary.get("team_norm"),
        "pos": raw_position or None,
        "age": age,
        "g": games,
    })
    totals = _without_none({
        "season": season,
        "lg": league,
        "player": player_name,
        "player_id": player_id,
        "team": team_key,
        "pos": raw_position or None,
        "g": games,
        "fg": aggregate_totals["fgm"],
        "ft": aggregate_totals["ftm"],
        "fta": aggregate_totals["fta"],
        "ast": aggregate_totals["ast"],
        "pts": aggregate_totals["pts"],
    })
    per_game = _without_none({
        "season": season,
        "lg": league,
        "player": player_name,
        "player_id": player_id,
        "team": team_key,
        "pos": raw_position or None,
        "g": games,
        "fg_per_game": _per_game(aggregate_totals["fgm"], games),
        "ft_per_game": _per_game(aggregate_totals["ftm"], games),
        "fta_per_game": _per_game(aggregate_totals["fta"], games),
        "ft_percent": _ratio(aggregate_totals["ftm"], aggregate_totals["fta"]),
        "ast_per_game": _per_game(aggregate_totals["ast"], games),
        "pts_per_game": _per_game(aggregate_totals["pts"], games),
    })
    team_summary = _aggregate_team_summary(
        ordered,
        team_index=team_index,
        aggregate_games=games,
        season=season,
        league=league,
        primary=primary,
        team_key=team_key,
    )

    components = tuple(
        {
            "source_row_id": int(row["id"]),
            "source_player_id": str(row.get("player_id") or ""),
            "season": row.get("season"),
            "season_raw": row.get("season_raw"),
            "season_start_year": row.get("season_start_year"),
            "season_end_year": row.get("season_end_year"),
            "team": row.get("team"),
            "team_norm": row.get("team_norm"),
            "league": row.get("league"),
            "pos": row.get("pos"),
            "ga": row.get("ga"),
            "fgm": row.get("fgm"),
            "ftm": row.get("ftm"),
            "fta": row.get("fta"),
            "ft_pct": row.get("ft_pct"),
            "ast": row.get("ast"),
            "pts": row.get("pts"),
            "ppg": row.get("ppg"),
            "shares_key_with_other_row": row.get("shares_key_with_other_row"),
        }
        for row in ordered
    )
    component_ids = tuple(component["source_row_id"] for component in components)
    component_shares = tuple(
        {
            "source_row_id": component["source_row_id"],
            "team": _normalized(component["team"] or component["team_norm"] or "NA") or "NA",
            "league": _normalized(component["league"]),
            "games": float(component["ga"]),
            "stat_share": round(float(component["ga"]) / games, 8),
        }
        for component in components
    )
    complete_fields = {
        column: aggregate_totals[column] is not None
        for column in aggregate_totals
    }

    comparison = {
        "player_id": player_id,
        "player": player_name,
        "team": team_key,
        "season": season,
        "lg": league,
        "pos": raw_position or None,
    }
    _merge_prefixed(comparison, "player_info", identity, include_bare=False)
    _merge_prefixed(comparison, "player_season_info", season_info)
    _merge_prefixed(comparison, "player_per_game", per_game)
    _merge_prefixed(comparison, "player_totals", totals)
    if team_summary:
        _merge_prefixed(comparison, "team_summaries", team_summary, include_bare=False)

    return {
        "player_id": player_id,
        "team_key": team_key,
        "league": league,
        "identity": identity,
        "season_info": season_info,
        "per_game": per_game,
        "totals": totals,
        "team_summary": team_summary,
        "comparison_row": comparison,
        "source_context": {
            "source": _DATABASE_NAME,
            "source_database": _DATABASE_NAME,
            "source_table": "player_season",
            "source_grain": "exact_player_id_season_start_year_after_selected_league_filter",
            "source_player_id": player_id,
            "source_component_ids": component_ids,
            "source_components": components,
            "source_component_count": len(components),
            "source_leagues": tuple(dict.fromkeys(str(component["league"] or "") for component in components)),
            "source_teams": tuple(dict.fromkeys(str(component["team"] or "") for component in components)),
            "source_positions": tuple(dict.fromkeys(str(component["pos"] or "") for component in components if component["pos"])),
            "source_born_raw": born or None,
            "multi_team_stat_shares": component_shares,
            "aggregation_contract": "same_exact_player_id_and_season_start_year_is_one_player_year",
            "aggregation_scope": selected_league or "ALL LEAGUES",
            "additive_field_completeness": complete_fields,
            "missing_component_values_are_not_zero": True,
        },
    }


def _aggregate_team_summary(
    rows: tuple[dict[str, Any], ...],
    *,
    team_index: dict[tuple[str, str], list[dict[str, Any]]],
    aggregate_games: float,
    season: int,
    league: str,
    primary: dict[str, Any],
    team_key: str,
) -> dict[str, Any]:
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for component in rows:
        key = (_normalized(component.get("team_norm")), _normalized(component.get("league")))
        candidates = team_index.get(key, ())
        if len(candidates) != 1:
            return {}
        matched.append((component, candidates[0]))
    if not matched or aggregate_games <= 0.0:
        return {}

    def weighted(column: str) -> float | None:
        values: list[tuple[float, float]] = []
        for component, team_row in matched:
            value = _number(team_row.get(column))
            games = _number(component.get("ga"))
            if value is None or games is None:
                return None
            values.append((value, games / aggregate_games))
        return sum(value * weight for value, weight in values)

    primary_key = (_normalized(primary.get("team_norm")), _normalized(primary.get("league")))
    primary_rows = team_index.get(primary_key, ())
    primary_team = primary_rows[0] if len(primary_rows) == 1 else {}
    return _without_none({
        "season": season,
        "lg": league,
        "team": team_key,
        "team_name": primary_team.get("team_name") or primary.get("team"),
        "w": weighted("wins"),
        "l": weighted("losses"),
        "ties": weighted("ties"),
        "win_pct": weighted("win_pct"),
        "coach": primary_team.get("coach"),
        "multi_team_weighted_context": len(rows) > 1,
    })


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _complete_sum(rows: tuple[dict[str, Any], ...], column: str) -> float | None:
    numbers: list[float] = []
    for row in rows:
        value = _number(row.get(column))
        if value is None:
            return None
        numbers.append(value)
    return sum(numbers) if numbers else None


def _per_game(total: float | int | None, games: float) -> float | None:
    if total is None or games <= 0.0:
        return None
    return float(total) / games


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator is None or float(denominator) <= 0.0:
        return None
    return float(numerator) / float(denominator)


def _parse_birth_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text or text.isdigit():
        return None
    for pattern in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _age_on_january_31(birth: date, season_end_year: int) -> int:
    reference = date(int(season_end_year), 1, 31)
    return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized(value: Any) -> str:
    return str(value or "").strip().upper()


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _merge_prefixed(
    target: dict[str, Any],
    prefix: str,
    row: dict[str, Any],
    *,
    include_bare: bool = True,
) -> None:
    for key, value in row.items():
        if value is None:
            continue
        target[f"{prefix}.{key}"] = value
        if include_bare:
            target.setdefault(key, value)


__all__ = [
    "PreNbaSeasonPayload",
    "available_pre_nba_seasons",
    "load_pre_nba_season_payload",
    "pre_nba_database_path",
]
