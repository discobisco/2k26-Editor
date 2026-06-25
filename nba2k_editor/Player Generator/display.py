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
    generated_proposals: tuple[Any, ...] = ()


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
    selection_changed = (
        season != state.selected_season
        or source_team != state.selected_source_team
        or player != state.selected_player
        or players != state.players
    )
    return replace(
        state,
        selected_season=season,
        source_team_filters=source_team_filters,
        selected_source_team=source_team,
        players=players,
        selected_player=player,
        rows=() if selection_changed else state.rows,
        field_columns=() if selection_changed else state.field_columns,
        player_rows=() if selection_changed else state.player_rows,
        generated_proposals=() if selection_changed else state.generated_proposals,
        status=_option_status(season, source_team, players) if selection_changed else state.status,
    )


def add_current_roster_to_pool_display_state(model: Any, state: GeneratorDisplayState, *, progress_callback: Any | None = None) -> GeneratorDisplayState:
    if not state.source_loaded:
        state = load_generator_display_state()
    _ensure_generator_import_path()
    from player_generation_pool import add_current_roster_to_player_generation_pool

    pool_manifest = add_current_roster_to_player_generation_pool(model, progress_callback=progress_callback)
    return replace(
        state,
        status=(
            f"Added current roster to player pool SQL as {pool_manifest.get('added_snapshot_id')}: "
            f"{pool_manifest.get('added_stats_rows', 0)} stats rows, "
            f"{pool_manifest.get('added_attribute_rows', 0)} attribute rows, "
            f"{pool_manifest.get('added_tendency_rows', 0)} tendency rows. "
            "Use Sync Player Pool SQL to rebuild the neighbor model."
        ),
    )


def sync_generator_pool_display_state(state: GeneratorDisplayState, *, progress_callback: Any | None = None) -> GeneratorDisplayState:
    if not state.source_loaded:
        state = load_generator_display_state()
    _ensure_generator_import_path()
    from player_generation_pool import ensure_player_generation_pool_current
    from stat_neighbor_framework import load_latest_stat_neighbor_model

    pool_manifest = ensure_player_generation_pool_current(root=_GENERATOR_DIR.parents[1], progress_callback=progress_callback)
    load_latest_stat_neighbor_model.cache_clear()
    return replace(
        state,
        rows=(),
        field_columns=(),
        player_rows=(),
        generated_proposals=(),
        status=(
            f"Player pool SQL current: "
            f"{pool_manifest.get('candidate_rows', 0)} players, "
            f"{pool_manifest.get('candidate_position_rows', 0)} position rows, "
            f"model {pool_manifest.get('model_sqlite') or pool_manifest.get('output_dir')}. "
            "Preview cleared; run Display Preview again before importing."
        ),
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
        generated_proposals=batch.proposals,
        status=f"Displaying {len(rows)} generated players and {len(columns)} data columns for {selected.selected_season} / {selected.selected_source_team}.",
    )


def import_generator_to_game_display_state(model: Any, state: GeneratorDisplayState, *, match_existing_player_names: bool = False, progress_callback: Any | None = None) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before importing generated players.")
    _ensure_generator_import_path()
    from contracts import GeneratorInputContract, OutputTarget
    from game_port import import_generated_players_to_game

    import_state = state
    if not import_state.generated_proposals:
        return replace(import_state, status="Display preview before importing generated players.")
    import_kwargs: dict[str, Any] = {
        "generated_players": import_state.generated_proposals,
        "team_filter": None if import_state.selected_source_team == _SOURCE_TEAM_ALL else import_state.selected_source_team,
        "match_existing_player_names": match_existing_player_names,
    }
    if progress_callback is not None:
        import_kwargs["progress_callback"] = progress_callback
    result = import_generated_players_to_game(
        model,
        GeneratorInputContract(int(import_state.selected_season), _SOURCE_ROOT, OutputTarget.OVERWRITE_CURRENT_ROSTER, f"Player Generator {import_state.selected_season}"),
        **import_kwargs,
    )
    applied = result.apply_result
    mode = " by matching loaded Players names" if match_existing_player_names else ""
    return replace(import_state, status=f"Imported {applied.applied_players}/{applied.generated_count} generated players{mode}. Fields: {applied.succeeded} ok, {applied.failed} failed.")


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
    context = _generator_context_for_season(season)
    return tuple(sorted({team for _player_id, team in context.player_keys()}))


def _player_options(database: Path, season: int, source_team: str) -> tuple[str, ...]:
    context = _generator_context_for_season(season)
    team_filter = None if not source_team or source_team == _SOURCE_TEAM_ALL else source_team
    labels: list[str] = []
    for player_id, team in context.player_keys(team_filter=team_filter):
        evidence = context.evidence_for(player_id=player_id, team=team)
        source_player_id = str(evidence.player_id or player_id).strip()
        source_team = str(evidence.team or team).strip().upper()
        player_name = str(evidence.identity.get("player") or evidence.season_info.get("player") or source_player_id).strip()
        labels.append(_player_label(player_name, source_team, source_player_id))
    return tuple(sorted(labels, key=str.casefold))


def _generator_context_for_season(season: int) -> Any:
    _ensure_generator_import_path()
    from contracts import GeneratorInputContract, OutputTarget
    from player_generator import season_context_index

    contract = GeneratorInputContract(
        season=int(season),
        source_root=_SOURCE_ROOT,
        output_target=OutputTarget.PREVIEW,
    )
    return season_context_index(contract)


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
    "add_current_roster_to_pool_display_state",
    "empty_generator_display_state",
    "generate_generator_preview_display_state",
    "import_generator_to_game_display_state",
    "load_generator_display_state",
    "sync_generator_pool_display_state",
    "update_generator_display_selection",
]

