from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_GENERATOR_DIR = Path(__file__).resolve().parent
_SOURCE_ROOT = _GENERATOR_DIR / "NBA Player Data"
_DATABASE_NAME = "NBA_DATA_Master.sqlite"
_BASE_PLAYER_SEASON_SHEET = "Player Season Info"
_SOURCE_TEAM_ALL = "All source teams"
_PLAYER_LABEL_SEPARATOR = " | "
_MULTI_TEAM_MARKERS = {"TOT", "2TM", "3TM", "4TM", "5TM"}


@dataclass(frozen=True)
class GeneratorFieldDisplayRow:
    section: str
    group: str
    field: str
    value: str
    source: str


@dataclass(frozen=True)
class GeneratorPlayerDisplayRow:
    player: str
    source_team: str
    player_id: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class GeneratorDisplayState:
    source_loaded: bool
    seasons: tuple[str, ...]
    selected_season: str
    source_team_filters: tuple[str, ...]
    selected_source_team: str
    players: tuple[str, ...]
    selected_player: str
    status: str
    rows: tuple[GeneratorFieldDisplayRow, ...] = ()
    field_columns: tuple[str, ...] = ()
    player_rows: tuple[GeneratorPlayerDisplayRow, ...] = ()


def empty_generator_display_state(status: str = "Load generator source data to display player options.") -> GeneratorDisplayState:
    return GeneratorDisplayState(
        source_loaded=False,
        seasons=(),
        selected_season="",
        source_team_filters=(_SOURCE_TEAM_ALL,),
        selected_source_team=_SOURCE_TEAM_ALL,
        players=(),
        selected_player="",
        status=status,
    )


def load_generator_display_state(*, selected_season: str | int | None = None) -> GeneratorDisplayState:
    database = _database_path()
    seasons = _season_options(database)
    if not seasons:
        return empty_generator_display_state("Generator source data loaded, but no seasons were found.")
    season = seasons[0] if selected_season is None else _require_option(selected_season, seasons, "season")
    source_team_filters = (_SOURCE_TEAM_ALL, *_source_team_options(database, int(season)))
    selected_source_team = _SOURCE_TEAM_ALL
    players = _player_options(database, int(season), selected_source_team)
    selected_player = players[0] if players else ""
    return GeneratorDisplayState(
        source_loaded=True,
        seasons=seasons,
        selected_season=season,
        source_team_filters=source_team_filters,
        selected_source_team=selected_source_team,
        players=players,
        selected_player=selected_player,
        status=_option_status(season, selected_source_team, players),
    )


def update_generator_display_selection(
    state: GeneratorDisplayState,
    *,
    selected_season: str | int | None = None,
    selected_source_team: str | None = None,
    selected_player: str | None = None,
) -> GeneratorDisplayState:
    if not state.source_loaded:
        return state
    database = _database_path()
    season = state.selected_season if selected_season is None else _require_option(selected_season, state.seasons, "season")
    source_team_filters = (_SOURCE_TEAM_ALL, *_source_team_options(database, int(season)))
    source_team = state.selected_source_team if selected_source_team is None else _require_option(selected_source_team, source_team_filters, "source team")
    players = _player_options(database, int(season), source_team)
    if selected_player is None:
        player = state.selected_player if state.selected_player in players else (players[0] if players else "")
    else:
        player = _require_option(selected_player, players, "player")
    return replace(
        state,
        selected_season=season,
        source_team_filters=source_team_filters,
        selected_source_team=source_team,
        players=players,
        selected_player=player,
        rows=(),
        field_columns=(),
        player_rows=(),
        status=_option_status(season, source_team, players),
    )


def generate_generator_preview_display_state(state: GeneratorDisplayState) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before generating a display preview.")
    selected = update_generator_display_selection(
        state,
        selected_season=state.selected_season,
        selected_source_team=state.selected_source_team,
    )

    _ensure_generator_import_path()
    from contracts import GeneratorInputContract, OutputTarget
    from player_generator import generate_player_proposals_from_index, season_context_index

    contract = GeneratorInputContract(
        season=int(selected.selected_season),
        source_root=_SOURCE_ROOT,
        output_target=OutputTarget.PREVIEW,
    )
    team_filter = None if selected.selected_source_team == _SOURCE_TEAM_ALL else selected.selected_source_team
    batch = generate_player_proposals_from_index(season_context_index(contract), team_filter=team_filter)
    columns: list[str] = []
    proposal_values: dict[tuple[str, str], dict[str, str]] = {}
    for proposal in batch.proposals:
        values: dict[str, str] = {}
        for candidate in proposal.field_candidates:
            column = _field_column(candidate)
            if column not in columns:
                columns.append(column)
            values[column] = str(candidate.display_value)
        proposal_values[(str(proposal.player_id).strip(), str(proposal.team).strip().upper())] = values
    rows = [
        GeneratorPlayerDisplayRow(player=player, source_team=source_team, player_id=player_id, values=tuple(proposal_values.get((player_id, source_team), {}).get(column, "") for column in columns))
        for label in selected.players
        for player_id, source_team, player in (_parse_player_label(label),)
    ]
    return replace(
        selected,
        rows=(),
        field_columns=tuple(columns),
        player_rows=tuple(rows),
        status=f"Displaying {len(rows)} generated players and {len(columns)} data columns for {selected.selected_season} / {selected.selected_source_team}.",
    )


def import_generator_to_game_display_state(model: Any, state: GeneratorDisplayState, *, match_existing_player_names: bool = False, progress_callback: Any | None = None) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before importing generated players.")
    _ensure_generator_import_path()
    from contracts import GeneratorInputContract, OutputTarget
    from game_port import import_generated_players_to_game

    import_kwargs: dict[str, Any] = {
        "team_filter": None if state.selected_source_team == _SOURCE_TEAM_ALL else state.selected_source_team,
        "match_existing_player_names": match_existing_player_names,
    }
    if progress_callback is not None:
        import_kwargs["progress_callback"] = progress_callback
    result = import_generated_players_to_game(
        model,
        GeneratorInputContract(int(state.selected_season), _SOURCE_ROOT, OutputTarget.OVERWRITE_CURRENT_ROSTER, f"Player Generator {state.selected_season}"),
        **import_kwargs,
    )
    applied = result.apply_result
    mode = " by matching loaded Players names" if match_existing_player_names else ""
    return replace(state, status=f"Imported {applied.applied_players}/{applied.generated_count} generated players{mode}. Fields: {applied.succeeded} ok, {applied.failed} failed.")


def _field_column(candidate: Any) -> str:
    return " / ".join(
        str(part)
        for part in (getattr(candidate, "section", ""), getattr(candidate, "group", ""), getattr(candidate, "display_name", "") or getattr(candidate, "normalized_name", ""))
        if str(part).strip()
    )


def _database_path() -> Path:
    database = _SOURCE_ROOT / _DATABASE_NAME
    if not database.is_file():
        raise FileNotFoundError(f"missing generator SQLite database: {database}")
    return database


def _season_options(database: Path) -> tuple[str, ...]:
    table = _table_name(database, _BASE_PLAYER_SEASON_SHEET)
    with sqlite3.connect(database) as connection:
        rows = connection.execute(f'SELECT DISTINCT season FROM "{table}" WHERE season IS NOT NULL ORDER BY season DESC').fetchall()
    return tuple(str(int(row[0])) for row in rows)


def _source_team_options(database: Path, season: int) -> tuple[str, ...]:
    table = _table_name(database, _BASE_PLAYER_SEASON_SHEET)
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            f'SELECT DISTINCT team FROM "{table}" WHERE season = ? AND team IS NOT NULL AND TRIM(team) != "" ORDER BY team',
            (int(season),),
        ).fetchall()
    return tuple(str(row[0]).strip().upper() for row in rows if str(row[0]).strip().upper() not in _MULTI_TEAM_MARKERS)


def _player_options(database: Path, season: int, source_team: str) -> tuple[str, ...]:
    table = _table_name(database, _BASE_PLAYER_SEASON_SHEET)
    params: list[Any] = [int(season)]
    where = 'season = ? AND player_id IS NOT NULL AND TRIM(player_id) != "" AND player IS NOT NULL AND TRIM(player) != ""'
    if source_team and source_team != _SOURCE_TEAM_ALL:
        where += " AND UPPER(team) = ?"
        params.append(source_team.upper())
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            f'SELECT player, team, player_id FROM "{table}" WHERE {where} ORDER BY player COLLATE NOCASE, team COLLATE NOCASE',
            params,
        ).fetchall()
    labels: list[str] = []
    seen_player_ids: set[str] = set()
    seen_team_rows: set[tuple[str, str]] = set()
    all_source_teams = not source_team or source_team == _SOURCE_TEAM_ALL
    for player, team, player_id in rows:
        team_key = str(team or "").strip().upper()
        player_id_key = str(player_id).strip()
        if not team_key or team_key in _MULTI_TEAM_MARKERS or not player_id_key:
            continue
        if all_source_teams:
            if player_id_key in seen_player_ids:
                continue
            seen_player_ids.add(player_id_key)
        else:
            key = (player_id_key, team_key)
            if key in seen_team_rows:
                continue
            seen_team_rows.add(key)
        labels.append(_player_label(str(player).strip(), team_key, player_id_key))
    return tuple(labels)


def _table_name(database: Path, sheet_name: str) -> str:
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT table_name FROM workbook_tables WHERE sheet_name = ?", (sheet_name,)).fetchone()
    if row is None:
        raise KeyError(f"workbook sheet not found in SQLite database: {sheet_name}")
    return str(row[0])


def _player_label(player: str, source_team: str, player_id: str) -> str:
    return _PLAYER_LABEL_SEPARATOR.join((player, source_team, player_id))


def _parse_player_label(label: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in str(label or "").split(_PLAYER_LABEL_SEPARATOR)]
    if len(parts) != 3:
        return "", "", ""
    player, source_team, player_id = parts
    return player_id, source_team.upper(), player


def _require_option(value: object, options: tuple[str, ...], label: str) -> str:
    text = str(value or "").strip()
    if text in options:
        return text
    raise ValueError(f"invalid generator {label}: {text}")


def _option_status(season: str, source_team: str, players: tuple[str, ...]) -> str:
    return f"Displaying {len(players)} player options for {season} / {source_team}."


def _ensure_generator_import_path() -> None:
    path = str(_GENERATOR_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)


__all__ = [
    "GeneratorDisplayState",
    "GeneratorFieldDisplayRow",
    "GeneratorPlayerDisplayRow",
    "empty_generator_display_state",
    "generate_generator_preview_display_state",
    "import_generator_to_game_display_state",
    "load_generator_display_state",
    "update_generator_display_selection",
]
