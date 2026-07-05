from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from player_evidence import PlayerEvidence

_PRE_NBA_DIR_NAME = "Pre-NBA DATA"
_PRE_NBA_DATABASE_NAME = "pre_nba.sqlite"
_PLAYERS_TABLE = "pre_nba_all_players"
_TEAMS_TABLE = "pre_nba_teams"
_DEPTH_CHARTS_TABLE = "pre_nba_depth_charts"
_CAREER_TABLE = "pre_nba_player_career_summary"


def pre_nba_database_path(source_root: str | Path) -> Path:
    root = Path(source_root).expanduser().resolve()
    return root.parent / _PRE_NBA_DIR_NAME / _PRE_NBA_DATABASE_NAME


def pre_nba_database_available(source_root: str | Path) -> bool:
    return pre_nba_database_path(source_root).is_file()


def pre_nba_seasons(source_root: str | Path) -> tuple[int, ...]:
    database = pre_nba_database_path(source_root)
    if not database.is_file():
        return ()
    seasons: set[int] = set()
    with sqlite3.connect(database) as connection:
        if not _table_exists(connection, _PLAYERS_TABLE):
            return ()
        for (year,) in connection.execute(f'SELECT DISTINCT year FROM "{_PLAYERS_TABLE}" WHERE year IS NOT NULL').fetchall():
            if season := _year_end(year):
                seasons.add(season)
    return tuple(sorted(seasons, reverse=True))


def has_pre_nba_season(source_root: str | Path, season: int) -> bool:
    return bool(pre_nba_context_rows(source_root, season))


def pre_nba_context_rows(source_root: str | Path, season: int) -> tuple[dict[str, Any], ...]:
    return _player_season_rows(str(pre_nba_database_path(source_root)), int(season))


@lru_cache(maxsize=None)
def _player_season_rows(database_path: str, season: int) -> tuple[dict[str, Any], ...]:
    all_player_rows = _all_player_rows_for_season(database_path, season)
    depth = _depth_chart_rows_by_season_team_player(database_path, season)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in all_player_rows:
        player_id = _player_id(row)
        team = str(row.get("team") or "").strip()
        if not player_id or not team:
            continue
        team_key = team.upper()
        key = (player_id, team_key)
        if key in seen:
            continue
        seen.add(key)
        player = _full_player_name(row)
        depth_row = depth.get((team_key, _person_key(player)), {})
        out.append(
            {
                "team_name": team,
                "season": _season_label_from_year(row.get("year")),
                "season_start_year": _year_start(row.get("year")),
                "season_end_year": season,
                "player_id": player_id,
                "player": player,
                "pos": depth_row.get("pos") or row.get("pos"),
                "roster_spot": depth_row.get("roster_spot"),
                "height": row.get("height_in"),
                "weight": row.get("weight"),
                "college": row.get("college"),
                "games": row.get("ga"),
                "fgm": row.get("fgm"),
                "ftm": row.get("ftm"),
                "fta": row.get("fta"),
                "fg_pct": row.get("pct"),
                "ast": row.get("ast"),
                "pts": row.get("pts"),
                "avg": row.get("avg"),
                "url": row.get("url"),
                "history_summary": row.get("statistics_and_history_summary"),
            }
        )
    return tuple(sorted(out, key=lambda row: (str(row.get("team_name") or ""), _int_sort(row.get("roster_spot")), str(row.get("player") or ""))))


def build_pre_nba_evidence_by_key(source_root: str | Path, season: int) -> dict[tuple[str, str], PlayerEvidence]:
    database = str(pre_nba_database_path(source_root))
    rows = pre_nba_context_rows(source_root, season)
    all_players = _all_player_rows_by_player_season_team(database, int(season))
    career = _career_rows_by_player(database)
    teams = _team_rows_by_season_team(database, int(season))
    depth = _depth_chart_rows_by_season_team_player(database, int(season))

    team_rosters: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        team = _team_key(row)
        if team:
            team_rosters.setdefault(team, []).append(row)

    evidence: dict[tuple[str, str], PlayerEvidence] = {}
    for row in rows:
        player_id = _player_id(row)
        team = _team_key(row)
        if not player_id or not team:
            continue
        all_player = all_players.get((player_id, team), {})
        career_row = career.get(player_id, {})
        team_row = teams.get(team, {})
        depth_row = depth.get((team, _person_key(row.get("player") or _full_player_name(all_player))), {})
        evidence.setdefault((player_id, team), _player_evidence(row, team_rosters.get(team, ()), all_player, career_row, team_row, depth_row))
    return evidence


def _player_evidence(
    row: dict[str, Any],
    team_roster: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    all_player: dict[str, Any],
    career: dict[str, Any],
    team_row: dict[str, Any],
    depth_row: dict[str, Any],
) -> PlayerEvidence:
    player_id = _player_id(row)
    team = _team_key(row)
    season = int(row.get("season_end_year") or _year_end(all_player.get("year")) or 0)
    player_name = row.get("player") or _full_player_name(all_player) or _full_player_name(career) or player_id
    position = row.get("pos") or depth_row.get("pos") or all_player.get("pos")
    height = all_player.get("height_in") or career.get("height_in") or row.get("height")
    weight = all_player.get("weight") or career.get("weight") or row.get("weight")
    college = all_player.get("college") or career.get("college") or row.get("college")
    games = all_player.get("ga") or row.get("games")
    fgm = all_player.get("fgm") or row.get("fgm")
    ftm = all_player.get("ftm") or row.get("ftm")
    fta = all_player.get("fta") or row.get("fta")
    pts = all_player.get("pts") or row.get("pts")
    avg = all_player.get("avg") if all_player.get("avg") is not None else row.get("avg")
    fg_pct = all_player.get("pct") if all_player.get("pct") is not None else row.get("fg_pct")
    ast = all_player.get("ast") or row.get("ast")

    identity = {
        "player": player_name,
        "player_id": player_id,
        "pos": position,
        "ht_in_in": _height_inches(height),
        "wt": weight,
        "colleges": college,
        "birth_date": _excel_serial_from_date_text(all_player.get("born") or career.get("born")),
        "born": all_player.get("born") or career.get("born"),
        "died": all_player.get("died") or career.get("died"),
        "home_town": all_player.get("hometown") or career.get("hometown"),
        "from": row.get("season_start_year") or _year_start(all_player.get("year")),
        "to": row.get("season_end_year") or _year_end(all_player.get("year")),
    }
    season_info = {
        "season": season,
        "team": team,
        "team_name": row.get("team_name") or all_player.get("team"),
        "player_id": player_id,
        "player": player_name,
        "pos": position,
        "g": games,
        "roster_spot": row.get("roster_spot") or depth_row.get("roster_spot"),
        "league": all_player.get("league") or team_row.get("league"),
    }
    per_game = {
        "season": season,
        "team": team,
        "player_id": player_id,
        "player": player_name,
        "g": games,
        "fg_per_game": _per_game(fgm, games),
        "fg_percent": fg_pct,
        "ft_per_game": _per_game(ftm, games),
        "fta_per_game": _per_game(fta, games),
        "ast_per_game": _per_game(ast, games),
        "pts_per_game": avg if avg is not None else _per_game(pts, games),
    }
    totals = {
        "season": season,
        "team": team,
        "player_id": player_id,
        "player": player_name,
        "g": games,
        "fg": fgm,
        "ft": ftm,
        "fta": fta,
        "ast": ast,
        "pts": pts,
    }
    team_summary = {
        "season": season,
        "team": team,
        "league": team_row.get("league"),
        "record": team_row.get("record"),
        "wins": team_row.get("wins"),
        "losses": team_row.get("losses"),
        "ties": team_row.get("ties"),
        "coach": team_row.get("coach"),
    }
    source_context = {"source": "pre_nba.sqlite", "source_workbook": "AllPlayers.xlsx", "player_id": player_id, "team": team, "season": season}
    _merge_source_context(source_context, "pre_nba_all_players", all_player)
    _merge_source_context(source_context, "pre_nba_career", career)
    _merge_source_context(source_context, "pre_nba_team", team_row)
    _merge_source_context(source_context, "pre_nba_depth_chart", depth_row)
    return PlayerEvidence(
        player_id=player_id,
        season=season,
        team=team,
        identity=identity,
        season_info=season_info,
        per_game=per_game,
        totals=totals,
        per_36={},
        per_100={},
        advanced={},
        shooting={},
        play_by_play={},
        team_roster=tuple(team_roster),
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary=team_summary,
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context=source_context,
        missing_sources=("Player Per 36 min", "Player Per 100 Poss", "Advanced", "Player Shooting", "Player Play by Play", "Opponent Stats"),
    )


@lru_cache(maxsize=None)
def _all_player_rows_for_season(database_path: str, season: int) -> tuple[dict[str, Any], ...]:
    database = Path(database_path)
    if not database.is_file():
        return ()
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        if not _table_exists(connection, _PLAYERS_TABLE):
            return ()
        rows = connection.execute(f'SELECT * FROM "{_PLAYERS_TABLE}" WHERE team IS NOT NULL AND player_id IS NOT NULL').fetchall()
    return tuple(dict(row) for row in rows if _year_end(row["year"]) == int(season))


@lru_cache(maxsize=None)
def _all_player_rows_by_player_season_team(database_path: str, season: int) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _all_player_rows_for_season(database_path, season):
        player_id = _player_id(row)
        team = str(row.get("team") or "").strip().upper()
        if player_id and team:
            rows.setdefault((player_id, team), row)
    return rows


@lru_cache(maxsize=None)
def _career_rows_by_player(database_path: str) -> dict[str, dict[str, Any]]:
    database = Path(database_path)
    if not database.is_file():
        return {}
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        if not _table_exists(connection, _CAREER_TABLE):
            return {}
        rows = connection.execute(f'SELECT * FROM "{_CAREER_TABLE}" WHERE player_id IS NOT NULL').fetchall()
    return {_player_id(dict(row)): dict(row) for row in rows if _player_id(dict(row))}


@lru_cache(maxsize=None)
def _team_rows_by_season_team(database_path: str, season: int) -> dict[str, dict[str, Any]]:
    database = Path(database_path)
    if not database.is_file():
        return {}
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        if not _table_exists(connection, _TEAMS_TABLE):
            return {}
        rows = connection.execute(f'SELECT * FROM "{_TEAMS_TABLE}" WHERE season_end_year = ?', (int(season),)).fetchall()
    return {str(row["team_name"] or "").strip().upper(): dict(row) for row in rows if str(row["team_name"] or "").strip()}


@lru_cache(maxsize=None)
def _depth_chart_rows_by_season_team_player(database_path: str, season: int) -> dict[tuple[str, str], dict[str, Any]]:
    database = Path(database_path)
    if not database.is_file():
        return {}
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        if not _table_exists(connection, _DEPTH_CHARTS_TABLE):
            return {}
        rows = connection.execute(f'SELECT * FROM "{_DEPTH_CHARTS_TABLE}" WHERE season_end_year = ?', (int(season),)).fetchall()
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        team = str(row["team_name"] or "").strip().upper()
        player = _person_key(row["player"])
        if team and player:
            out.setdefault((team, player), dict(row))
    return out


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)).fetchone() is not None


def _merge_source_context(target: dict[str, Any], prefix: str, row: dict[str, Any]) -> None:
    for key, value in row.items():
        if value is not None and value != "":
            target[f"{prefix}.{key}"] = value


def _player_id(row: dict[str, Any]) -> str:
    return str(row.get("player_id") or "").strip().upper()


def _team_key(row: dict[str, Any]) -> str:
    return str(row.get("team_name") or row.get("team") or "").strip().upper()


def _full_player_name(row: dict[str, Any]) -> str:
    first = str(row.get("first_name") or "").strip()
    last = str(row.get("last_name") or "").strip()
    return " ".join(part for part in (first, last) if part).strip()


def _person_key(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _per_game(total: object, games: object) -> float | None:
    total_value = _float(total)
    games_value = _float(games)
    if total_value is None or games_value in (None, 0):
        return None
    return total_value / games_value


def _height_inches(value: object) -> int | None:
    number = _float(value)
    return int(round(number)) if number is not None else None


def _year_end(value: object) -> int | None:
    text = str(value or "").strip()
    if not text or "-" not in text:
        return None
    start_text, end_text = text.split("-", 1)
    try:
        start = _normalize_year_typo(int(start_text))
    except ValueError:
        return None
    end_digits = "".join(ch for ch in end_text if ch.isdigit())
    if not end_digits:
        return None
    if len(end_digits) <= 2:
        end = start // 100 * 100 + int(end_digits)
        if end < start:
            end += 100
    else:
        end = _normalize_year_typo(int(end_digits))
    return end if 1890 <= end <= 1951 else None


def _normalize_year_typo(year: int) -> int:
    if 2900 <= year <= 2999:
        return year - 1000
    if 1980 <= year <= 1999:
        return year - 100
    return year


def _year_start(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        year = _normalize_year_typo(int(text.split("-", 1)[0]))
    except ValueError:
        return None
    return year if 1890 <= year <= 1951 else None


def _season_label_from_year(value: object) -> str:
    start = _year_start(value)
    end = _year_end(value)
    if start and end:
        return f"{start}-{end}"
    return str(value or "").strip()


def _excel_serial_from_date_text(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%b %d, %Y")
    except ValueError:
        return None
    return (parsed - datetime(1899, 12, 30)).days


def _int_sort(value: object) -> int:
    number = _float(value)
    return int(number) if number is not None else 999999


def _float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "build_pre_nba_evidence_by_key",
    "has_pre_nba_season",
    "pre_nba_context_rows",
    "pre_nba_database_available",
    "pre_nba_database_path",
    "pre_nba_seasons",
]
