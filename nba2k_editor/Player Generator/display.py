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
_LEAGUE_ALL = "All leagues"
_POSITION_ALL = "All positions"
_PLAYER_LABEL_SEPARATOR = " | "
_MATCH_DISPLAY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Player Match", "player_match"),
    ("Offensive Player Match", "offensive_player_match"),
    ("Defensive Player Match", "defensive_player_match"),
)
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
class GeneratorSourceRosterPlayer:
    player: str
    source_teams: tuple[str, ...]
    player_id: str

    @property
    def identity(self) -> dict[str, str]:
        return {"player": self.player}


@dataclass(frozen=True)
class GeneratorDisplayState:
    source_loaded: bool
    seasons: tuple[str, ...]
    selected_season: str
    league_filters: tuple[str, ...]
    selected_league: str
    position_filters: tuple[str, ...]
    selected_position: str
    source_team_filters: tuple[str, ...]
    selected_source_team: str
    players: tuple[str, ...]
    selected_player: str
    status: str
    rows: tuple[GeneratorFieldDisplayRow, ...] = ()
    field_columns: tuple[str, ...] = ()
    player_rows: tuple[GeneratorPlayerDisplayRow, ...] = ()
    generated_proposals: tuple[Any, ...] = ()
    preview_target: str = "Players"
    proposal_cache_season: str = ""
    proposal_cache_league: str = ""
    proposal_cache: tuple[Any, ...] = ()
    roster_check_season: str = ""
    roster_check_source_count: int = 0
    roster_check_loaded_count: int = 0
    roster_check_missing_players: tuple[str, ...] = ()
    roster_check_out_of_season_players: tuple[str, ...] = ()


def empty_generator_display_state(status: str = "Load generator source data to display player options.") -> GeneratorDisplayState:
    return GeneratorDisplayState(
        source_loaded=False,
        seasons=(),
        selected_season="",
        league_filters=(_LEAGUE_ALL,),
        selected_league=_LEAGUE_ALL,
        position_filters=(_POSITION_ALL,),
        selected_position=_POSITION_ALL,
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
    selected_league = _LEAGUE_ALL
    selected_position = _POSITION_ALL
    selected_source_team = _SOURCE_TEAM_ALL
    league_filters = (_LEAGUE_ALL, *_league_options(database, int(season)))
    source_team_filters = (_SOURCE_TEAM_ALL, *_source_team_options(database, int(season), selected_league))
    position_filters = (_POSITION_ALL, *_position_options(database, int(season), selected_league))
    players = _player_options(database, int(season), selected_league, selected_source_team, selected_position)
    selected_player = players[0] if players else ""
    return GeneratorDisplayState(
        source_loaded=True,
        seasons=seasons,
        selected_season=season,
        league_filters=league_filters,
        selected_league=selected_league,
        position_filters=position_filters,
        selected_position=selected_position,
        source_team_filters=source_team_filters,
        selected_source_team=selected_source_team,
        players=players,
        selected_player=selected_player,
        status=_option_status(season, selected_league, selected_position, selected_source_team, players),
    )


def update_generator_display_selection(
    state: GeneratorDisplayState,
    *,
    selected_season: str | int | None = None,
    selected_league: str | None = None,
    selected_position: str | None = None,
    selected_source_team: str | None = None,
    selected_player: str | None = None,
) -> GeneratorDisplayState:
    if not state.source_loaded:
        return state
    database = _database_path()
    season = state.selected_season if selected_season is None else _require_option(selected_season, state.seasons, "season")
    league_filters = (_LEAGUE_ALL, *_league_options(database, int(season)))
    requested_league = state.selected_league if selected_league is None else str(selected_league or "").strip()
    league = requested_league if requested_league in league_filters else _LEAGUE_ALL
    position_filters = (_POSITION_ALL, *_position_options(database, int(season), league))
    requested_position = state.selected_position if selected_position is None else str(selected_position or "").strip()
    position = requested_position if requested_position in position_filters else _POSITION_ALL
    source_team_filters = (_SOURCE_TEAM_ALL, *_source_team_options(database, int(season), league))
    requested_source_team = state.selected_source_team if selected_source_team is None else str(selected_source_team or "").strip()
    source_team = requested_source_team if requested_source_team in source_team_filters else _SOURCE_TEAM_ALL
    players = _player_options(database, int(season), league, source_team, position)
    if selected_player is None:
        player = state.selected_player if state.selected_player in players else (players[0] if players else "")
    else:
        player = _require_option(selected_player, players, "player")
    season_changed = season != state.selected_season
    selection_changed = (
        season_changed
        or league != state.selected_league
        or position != state.selected_position
        or source_team != state.selected_source_team
        or player != state.selected_player
        or players != state.players
    )
    return replace(
        state,
        selected_season=season,
        league_filters=league_filters,
        selected_league=league,
        position_filters=position_filters,
        selected_position=position,
        source_team_filters=source_team_filters,
        selected_source_team=source_team,
        players=players,
        selected_player=player,
        rows=() if selection_changed else state.rows,
        field_columns=() if selection_changed else state.field_columns,
        player_rows=() if selection_changed else state.player_rows,
        generated_proposals=() if selection_changed else state.generated_proposals,
        proposal_cache_season="" if season_changed else state.proposal_cache_season,
        proposal_cache=() if season_changed else state.proposal_cache,
        roster_check_season="" if season_changed else state.roster_check_season,
        roster_check_source_count=0 if season_changed else state.roster_check_source_count,
        roster_check_loaded_count=0 if season_changed else state.roster_check_loaded_count,
        roster_check_missing_players=() if season_changed else state.roster_check_missing_players,
        roster_check_out_of_season_players=() if season_changed else state.roster_check_out_of_season_players,
        status=_option_status(season, league, position, source_team, players) if selection_changed else state.status,
    )


def add_current_roster_to_pool_display_state(model: Any, state: GeneratorDisplayState, *, progress_callback: Any | None = None) -> GeneratorDisplayState:
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
            "Use Sync Player Pool SQL to rebuild offset-backed Pool columns."
        ),
    )


def sync_generator_pool_display_state(state: GeneratorDisplayState, *, progress_callback: Any | None = None) -> GeneratorDisplayState:
    _ensure_generator_import_path()
    from player_generation_pool import ensure_player_generation_pool_current

    pool_manifest = ensure_player_generation_pool_current(progress_callback=progress_callback)
    return replace(
        state,
        rows=(),
        field_columns=(),
        player_rows=(),
        generated_proposals=(),
        proposal_cache_season="",
        proposal_cache=(),
        status=(
            f"Player pool SQL current: "
            f"{pool_manifest.get('candidate_rows', 0)} players, "
            f"{pool_manifest.get('candidate_position_rows', 0)} position rows. "
            "Preview cleared; run Display Preview again before importing."
        ),
    )


def check_loaded_roster_display_state(
    model: Any,
    state: GeneratorDisplayState,
    *,
    progress_callback: Any | None = None,
) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before checking the loaded roster.")
    selected = update_generator_display_selection(state, selected_season=state.selected_season)
    source_players = _source_roster_players_for_season(int(selected.selected_season))
    loaded = getattr(model, "loaded_items", {})
    loaded_players = loaded.get("Players", {}) if isinstance(loaded, dict) else {}
    if not loaded_players:
        return replace(
            selected,
            roster_check_season="",
            roster_check_source_count=0,
            roster_check_loaded_count=0,
            roster_check_missing_players=(),
            roster_check_out_of_season_players=(),
            status="Load Players before checking the loaded roster.",
        )
    _ensure_generator_import_path()
    from game_port import (
        active_loaded_players_not_in_generated_source,
        missing_generated_players_and_active_placeholder_indices,
    )

    if progress_callback is not None:
        progress_callback(0, 2, f"Checking {len(source_players)} source players against the loaded roster")
    missing_players, _target_indices, skipped_existing = missing_generated_players_and_active_placeholder_indices(
        model,
        source_players,
        placeholder_name="A Z",
    )
    if progress_callback is not None:
        progress_callback(1, 2, "Checking active loaded players against the selected source season")
    out_of_season_players = active_loaded_players_not_in_generated_source(
        model,
        source_players,
        placeholder_name="A Z",
    )
    if progress_callback is not None:
        progress_callback(2, 2, f"Checked the loaded roster against {len(source_players)} source players")
    missing_labels = tuple(_source_roster_player_label(player) for player in missing_players)
    out_of_season_labels = tuple(
        f"{player_name} | roster index {player_index}"
        for player_index, player_name in out_of_season_players
    )
    return replace(
        selected,
        roster_check_season=selected.selected_season,
        roster_check_source_count=len(source_players),
        roster_check_loaded_count=skipped_existing,
        roster_check_missing_players=missing_labels,
        roster_check_out_of_season_players=out_of_season_labels,
        status=(
            f"Checked loaded roster for {selected.selected_season}: "
            f"{skipped_existing}/{len(source_players)} source players loaded; "
            f"{len(missing_labels)} source players not loaded; "
            f"{len(out_of_season_labels)} active loaded players not in the source season."
        ),
    )


def generate_generator_preview_display_state(state: GeneratorDisplayState) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before generating a display preview.")
    selected = update_generator_display_selection(
        state,
        selected_season=state.selected_season,
        selected_league=state.selected_league,
        selected_position=state.selected_position,
        selected_source_team=state.selected_source_team,
    )

    _ensure_generator_import_path()
    from contracts import GeneratorInputContract, OutputTarget
    from player_generator import generate_player_proposals_from_index, season_context_index

    cache_season = str(selected.selected_season)
    cache_league = str(selected.selected_league)
    if selected.proposal_cache_season == cache_season and selected.proposal_cache_league == cache_league:
        season_proposals = selected.proposal_cache
    else:
        contract = GeneratorInputContract(
            season=int(selected.selected_season),
            source_root=_SOURCE_ROOT,
            output_target=OutputTarget.PREVIEW,
            selected_league=selected.selected_league,
        )
        season_proposals = tuple(generate_player_proposals_from_index(season_context_index(contract)).proposals)
    selected_keys = {
        (player_id, source_team)
        for label in selected.players
        for player_id, source_team, _player in (_parse_player_label(label),)
    }
    proposals = tuple(
        proposal
        for proposal in season_proposals
        if (str(proposal.player_id).strip(), str(proposal.team).strip().upper()) in selected_keys
    )
    columns: list[str] = [label for label, _key in _MATCH_DISPLAY_COLUMNS]
    proposal_values: dict[tuple[str, str], dict[str, str]] = {}
    for proposal in proposals:
        values: dict[str, str] = {
            label: str(getattr(proposal, "identity", {}).get(key) or "")
            for label, key in _MATCH_DISPLAY_COLUMNS
        }
        for candidate in proposal.field_candidates:
            column = _field_column(candidate)
            if column not in columns:
                columns.append(column)
            values[column] = str(candidate.display_value)
        proposal_values[(str(proposal.player_id).strip(), str(proposal.team).strip().upper())] = values
    rows = [
        GeneratorPlayerDisplayRow(
            player=player,
            source_team=source_team,
            player_id=player_id,
            values=tuple(
                _nonblank_display_value(proposal_values.get((player_id, source_team), {}).get(column))
                for column in columns
            ),
        )
        for label in selected.players
        for player_id, source_team, player in (_parse_player_label(label),)
    ]
    return replace(
        selected,
        rows=(),
        field_columns=tuple(columns),
        player_rows=tuple(rows),
        generated_proposals=proposals,
        preview_target="Players",
        proposal_cache_season=cache_season,
        proposal_cache_league=cache_league,
        proposal_cache=season_proposals,
        status=(
            f"Displaying {len(rows)} generated players and {len(columns)} data columns for "
            f"{selected.selected_season} / {selected.selected_league} / {selected.selected_position} / {selected.selected_source_team}."
        ),
    )


def generate_draft_class_display_state(state: GeneratorDisplayState) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before building a draft class.")
    selected = update_generator_display_selection(
        state,
        selected_season=state.selected_season,
        selected_league=state.selected_league,
        selected_position=state.selected_position,
        selected_source_team=state.selected_source_team,
    )
    _ensure_generator_import_path()
    from player_generator import DraftClassMode, generate_draft_class_proposals

    draft_year = int(selected.selected_season)
    draft_class = generate_draft_class_proposals(
        draft_year,
        mode=DraftClassMode.FIRST_APPEARANCE,
        source_root=_SOURCE_ROOT,
    )
    proposals = draft_class.proposals
    columns: list[str] = [label for label, _key in _MATCH_DISPLAY_COLUMNS]
    rows: list[GeneratorPlayerDisplayRow] = []
    for proposal in proposals:
        values: dict[str, str] = {
            label: str(getattr(proposal, "identity", {}).get(key) or "")
            for label, key in _MATCH_DISPLAY_COLUMNS
        }
        for candidate in proposal.field_candidates:
            column = _field_column(candidate)
            if column not in columns:
                columns.append(column)
            values[column] = str(candidate.display_value)
        identity = getattr(proposal, "identity", {})
        rows.append(
            GeneratorPlayerDisplayRow(
                player=str(identity.get("player") or proposal.player_id),
                source_team=str(getattr(proposal, "team", "") or ""),
                player_id=str(getattr(proposal, "player_id", "") or ""),
                values=tuple(_nonblank_display_value(values.get(column)) for column in columns),
            )
        )
    return replace(
        selected,
        rows=(),
        field_columns=tuple(columns),
        player_rows=tuple(rows),
        generated_proposals=proposals,
        preview_target="Draft Class",
        status=(
            f"Built {len(rows)} generated Draft Class players for {draft_class.rookie_season}. "
            f"Subtracted players already present from {proposals[0].identity.get('draft_class_base_season', draft_year) if proposals else draft_year}-{draft_year}."
        ),
    )


def import_draft_class_display_state(model: Any, state: GeneratorDisplayState, *, progress_callback: Any | None = None) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before importing a draft class.")
    import_state = state
    if getattr(import_state, "preview_target", "Players") != "Draft Class" or not import_state.generated_proposals:
        return replace(import_state, status="Build Draft Class before importing to Draft Class.")
    target_items = tuple(model.player_items_for_team_filter("Draft Class").values())
    if not target_items:
        return replace(import_state, status="Load Draft Class before importing generated draft players.")
    snapshot = _draft_class_snapshot(import_state.generated_proposals)
    result = model.apply_player_roster_snapshot(
        snapshot,
        target_items=target_items,
        progress_callback=progress_callback,
    )
    return replace(
        import_state,
        status=(
            f"Imported {min(len(import_state.generated_proposals), len(target_items))}/{len(import_state.generated_proposals)} generated draft players "
            f"to Draft Class. Fields: {result.get('succeeded', 0)} ok, {result.get('failed', 0)} failed, {result.get('skipped', 0)} skipped."
        ),
    )


def _draft_class_snapshot(proposals: tuple[Any, ...]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for proposal in proposals:
        identity = getattr(proposal, "identity", {})
        fields = {
            str(candidate.field_key): {"display_value": candidate.display_value}
            for candidate in getattr(proposal, "field_candidates", ())
        }
        records.append(
            {
                "label": str(identity.get("player") or getattr(proposal, "player_id", "")),
                "player_id": str(getattr(proposal, "player_id", "")),
                "source_team": str(getattr(proposal, "team", "")),
                "fields": fields,
            }
        )
    return {
        "domain": "Players",
        "mode": "Player Generator Draft Class",
        "record_count": len(records),
        "records": records,
    }


def import_generator_to_game_display_state(model: Any, state: GeneratorDisplayState, *, match_existing_player_names: bool = False, progress_callback: Any | None = None) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before importing generated players.")
    _ensure_generator_import_path()
    from contracts import GeneratorInputContract, OutputTarget
    from game_port import import_generated_players_to_game

    import_state = state
    if getattr(import_state, "preview_target", "Players") == "Draft Class":
        return replace(import_state, status="Current preview targets Draft Class; use Import Draft Class.")
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


def missing_generator_import_preview(model: Any, state: GeneratorDisplayState) -> dict[str, Any]:
    if not state.source_loaded or not state.generated_proposals:
        return {"names": (), "missing_count": 0, "target_count": 0, "skipped_existing": 0}
    _ensure_generator_import_path()
    from game_port import missing_generated_players_and_active_placeholder_indices

    missing_players, target_indices, skipped_existing = missing_generated_players_and_active_placeholder_indices(model, state.generated_proposals, placeholder_name="A Z")
    names = tuple(_generated_player_label(player) for player in missing_players)
    return {
        "names": names,
        "missing_count": len(missing_players),
        "target_count": len(target_indices),
        "skipped_existing": skipped_existing,
    }


def import_missing_generator_to_game_display_state(model: Any, state: GeneratorDisplayState, *, progress_callback: Any | None = None) -> GeneratorDisplayState:
    if not state.source_loaded:
        return empty_generator_display_state("Load generator source data before importing missing generated players.")
    _ensure_generator_import_path()
    from contracts import GeneratorInputContract, OutputTarget
    from game_port import import_generated_players_to_game, missing_generated_players_and_active_placeholder_indices

    import_state = state
    if not import_state.generated_proposals:
        return replace(import_state, status="Display preview before importing missing generated players.")
    missing_players, target_indices, skipped_existing = missing_generated_players_and_active_placeholder_indices(model, import_state.generated_proposals, placeholder_name="A Z")
    import_kwargs: dict[str, Any] = {
        "generated_players": missing_players,
        "player_indices": target_indices,
        "team_filter": None if import_state.selected_source_team == _SOURCE_TEAM_ALL else import_state.selected_source_team,
    }
    if progress_callback is not None:
        import_kwargs["progress_callback"] = progress_callback
    result = import_generated_players_to_game(
        model,
        GeneratorInputContract(int(import_state.selected_season), _SOURCE_ROOT, OutputTarget.OVERWRITE_CURRENT_ROSTER, f"Player Generator Missing {import_state.selected_season}"),
        **import_kwargs,
    )
    applied = result.apply_result
    return replace(
        import_state,
        status=(
            f"Added missing players: imported {applied.applied_players}/{len(missing_players)} missing generated players onto active A Z players. "
            f"Skipped {skipped_existing} generated players already active. "
            f"Targets: {len(target_indices)} active A Z players. Fields: {applied.succeeded} ok, {applied.failed} failed."
        ),
    )


def _generated_player_label(generated: Any) -> str:
    identity = getattr(generated, "identity", None)
    if isinstance(identity, dict):
        for key in ("player", "name"):
            value = str(identity.get(key) or "").strip()
            if value:
                return value
    by_field = getattr(generated, "by_field_key", None)
    if callable(by_field):
        try:
            fields = by_field()
        except Exception:
            fields = {}
        if isinstance(fields, dict):
            first = fields.get("Vitals/FIRSTNAME")
            last = fields.get("Vitals/LASTNAME")
            name = f"{getattr(first, 'display_value', '')} {getattr(last, 'display_value', '')}".strip()
            if name:
                return name
    return str(getattr(generated, "player_id", "")).strip()


def _source_roster_players_for_season(season: int) -> tuple[GeneratorSourceRosterPlayer, ...]:
    context = _generator_context_for_season(season)
    grouped: dict[str, dict[str, Any]] = {}
    for player_id, team in context.player_keys():
        evidence = context.evidence_for(player_id=player_id, team=team)
        source_player_id = str(evidence.player_id or player_id).strip()
        source_team = str(evidence.team or team).strip().upper()
        player_name = str(evidence.identity.get("player") or evidence.season_info.get("player") or source_player_id).strip()
        identity_key = source_player_id.upper() or f"{player_name.upper()}|{source_team}"
        source = grouped.setdefault(
            identity_key,
            {"player": player_name, "player_id": source_player_id, "source_teams": set()},
        )
        if source_team:
            source["source_teams"].add(source_team)
    return tuple(
        sorted(
            (
                GeneratorSourceRosterPlayer(
                    player=str(source["player"]),
                    source_teams=tuple(sorted(source["source_teams"])),
                    player_id=str(source["player_id"]),
                )
                for source in grouped.values()
            ),
            key=lambda player: (player.player.casefold(), player.player_id.casefold()),
        )
    )


def _source_roster_player_label(player: GeneratorSourceRosterPlayer) -> str:
    return _PLAYER_LABEL_SEPARATOR.join((player.player, "/".join(player.source_teams), player.player_id))


def _field_column(candidate: Any) -> str:
    return " / ".join(
        str(part)
        for part in (getattr(candidate, "section", ""), getattr(candidate, "group", ""), getattr(candidate, "display_name", "") or getattr(candidate, "normalized_name", ""))
        if str(part).strip()
    )


def _nonblank_display_value(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text if text else "N/A"


def _database_path() -> Path:
    database = _SOURCE_ROOT / _DATABASE_NAME
    if not database.is_file():
        raise FileNotFoundError(f"missing generator SQLite database: {database}")
    return database


def _season_options(database: Path) -> tuple[str, ...]:
    table = _table_name(database, _BASE_PLAYER_SEASON_SHEET)
    with sqlite3.connect(database) as connection:
        rows = connection.execute(f'SELECT DISTINCT season FROM "{table}" WHERE season IS NOT NULL ORDER BY season DESC').fetchall()
    seasons = {str(int(row[0])) for row in rows}
    return tuple(sorted(seasons, key=lambda value: int(value), reverse=True))


def _league_options(database: Path, season: int) -> tuple[str, ...]:
    context = _generator_context_for_season(season)
    leagues = {_evidence_league(context.evidence_for(player_id=player_id, team=team)) for player_id, team in context.player_keys()}
    return tuple(sorted(league for league in leagues if league))


def _source_team_options(database: Path, season: int, league: str) -> tuple[str, ...]:
    context = _generator_context_for_season(season)
    return tuple(
        sorted(
            {
                team
                for player_id, team in context.player_keys()
                if _league_matches(context.evidence_for(player_id=player_id, team=team), league)
            }
        )
    )


def _position_options(database: Path, season: int, league: str) -> tuple[str, ...]:
    context = _generator_context_for_season(season)
    positions: set[str] = set()
    for player_id, team in context.player_keys():
        evidence = context.evidence_for(player_id=player_id, team=team)
        if not _league_matches(evidence, league):
            continue
        positions.update(_evidence_positions(evidence))
    order = {position: index for index, position in enumerate(("PG", "SG", "SF", "PF", "C"))}
    return tuple(sorted(positions, key=lambda value: (order.get(value, 99), value)))


def _player_options(database: Path, season: int, league: str, source_team: str, position: str) -> tuple[str, ...]:
    context = _generator_context_for_season(season)
    team_filter = None if not source_team or source_team == _SOURCE_TEAM_ALL else source_team
    selected_position = str(position or "").strip().upper()
    labels: list[str] = []
    for player_id, team in context.player_keys(team_filter=team_filter):
        evidence = context.evidence_for(player_id=player_id, team=team)
        if not _league_matches(evidence, league):
            continue
        if selected_position and selected_position != _POSITION_ALL.upper() and selected_position not in _evidence_positions(evidence):
            continue
        source_player_id = str(evidence.player_id or player_id).strip()
        source_team = str(evidence.team or team).strip().upper()
        player_name = str(evidence.identity.get("player") or evidence.season_info.get("player") or source_player_id).strip()
        labels.append(_player_label(player_name, source_team, source_player_id))
    return tuple(sorted(labels, key=str.casefold))


def _league_matches(evidence: Any, selected_league: str) -> bool:
    league = _evidence_league(evidence)
    return not selected_league or selected_league == _LEAGUE_ALL or league == selected_league


def _evidence_league(evidence: Any) -> str:
    return str(evidence.season_info.get("lg") or evidence.season_info.get("league") or "").strip().upper()


def _evidence_positions(evidence: Any) -> tuple[str, ...]:
    _ensure_generator_import_path()
    from stat_neighbor_framework import select_positions_from_evidence

    selected = select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
    return tuple(position for position in selected.all_positions if position)


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


def _option_status(season: str, league: str, position: str, source_team: str, players: tuple[str, ...]) -> str:
    return f"Displaying {len(players)} player options for {season} / {league} / {position} / {source_team}."


def _ensure_generator_import_path() -> None:
    path = str(_GENERATOR_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)


__all__ = [
    "GeneratorDisplayState",
    "GeneratorFieldDisplayRow",
    "GeneratorPlayerDisplayRow",
    "GeneratorSourceRosterPlayer",
    "add_current_roster_to_pool_display_state",
    "check_loaded_roster_display_state",
    "empty_generator_display_state",
    "generate_draft_class_display_state",
    "generate_generator_preview_display_state",
    "import_draft_class_display_state",
    "import_generator_to_game_display_state",
    "load_generator_display_state",
    "sync_generator_pool_display_state",
    "update_generator_display_selection",
]

