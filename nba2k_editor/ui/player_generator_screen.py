from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any

PLAYER_GENERATOR_SCREEN = "Player Generator"
DEFAULT_GENERATOR_SEASON = 2025
MAX_PREVIEW_ROWS = 240
ALL_TEAMS_FILTER = "All Teams"
_PLAYER_SEASON_INFO_SHEET = "Player Season Info"


@dataclass(frozen=True)
class PlayerGeneratorPreviewRow:
    field_key: str
    section: str
    group: str
    field: str
    value: int | str
    source_rule: str


@dataclass(frozen=True)
class PlayerGeneratorPreview:
    player_id: str
    season: int
    team: str
    player_name: str
    rows: tuple[PlayerGeneratorPreviewRow, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PlayerGeneratorBatchPreview:
    season: int
    previews: tuple[PlayerGeneratorPreview, ...]


@dataclass
class PlayerGeneratorScreenState:
    season: int = DEFAULT_GENERATOR_SEASON
    player_id: str = ""
    team: str = ""
    team_filter: str = ALL_TEAMS_FILTER
    player_option: str = ""
    generated_count: int = 0
    status: str = "Choose year and team, then generate team."
    preview: PlayerGeneratorPreview | None = None
    batch: PlayerGeneratorBatchPreview | None = None


@dataclass(frozen=True)
class PlayerGeneratorOption:
    label: str
    player_id: str
    team: str
    player_name: str


def build_player_generator_preview(*, season: int, player_id: str, team: str) -> PlayerGeneratorPreview:
    generator_root = _generator_root()
    _ensure_import_path(generator_root)
    contracts = import_module("contracts")
    source_data = import_module("source_data")
    player_generator = import_module("player_generator")

    source_root = source_data.GeneratorSourceInventory.from_default().root
    contract = contracts.GeneratorInputContract(
        season=int(season),
        source_root=source_root,
        output_target=contracts.OutputTarget.PROPOSAL,
    ).validate()
    proposal = player_generator.generate_player_proposal_from_contract(
        contract,
        player_id=str(player_id).strip(),
        team=str(team).strip(),
    )
    return _preview_from_proposal(proposal)


def generate_preview_into_state(state: PlayerGeneratorScreenState, *, season: int, player_id: str, team: str) -> PlayerGeneratorPreview:
    state.season = int(season)
    state.player_id = str(player_id).strip()
    state.team = str(team).strip().upper()
    state.status = "Generating player..."
    state.preview = build_player_generator_preview(season=state.season, player_id=state.player_id, team=state.team)
    state.status = f"Generated player: {state.preview.player_name} {state.preview.season} {state.preview.team} ({len(state.preview.rows)} fields)."
    return state.preview


def apply_preview_to_game(model: Any, state: PlayerGeneratorScreenState, *, player_index: int) -> Any:
    if state.preview is None:
        raise ValueError("generate a player preview before applying to game")
    generator_root = _generator_root()
    _ensure_import_path(generator_root)
    game_port = import_module("game_port")
    result = game_port.apply_generated_rows_to_game(model, state.preview.rows, player_index=int(player_index))
    state.status = f"Applied {result.succeeded}/{result.attempted} generated fields to game player index {player_index}."
    return result


def apply_batch_to_game(model: Any, state: PlayerGeneratorScreenState, *, player_indices: tuple[int, ...]) -> Any:
    if state.batch is None:
        raise ValueError("generate a player year before applying batch to game")
    generator_root = _generator_root()
    _ensure_import_path(generator_root)
    game_port = import_module("game_port")
    result = game_port.apply_generated_players_to_game(model, state.batch.previews, player_indices=player_indices)
    state.status = f"Applied {result.applied_players} generated players / {result.succeeded} fields to game."
    return result


@lru_cache(maxsize=1)
def generator_year_options() -> tuple[int, ...]:
    return tuple(sorted({int(row["season"]) for row in _all_player_season_rows() if row.get("season") is not None}, reverse=True))


@lru_cache(maxsize=None)
def generator_team_filter_options(*, season: int) -> tuple[str, ...]:
    rows = _player_season_rows(season=season)
    teams = sorted({str(row.get("team") or "").strip().upper() for row in rows if str(row.get("team") or "").strip()})
    return (ALL_TEAMS_FILTER, *teams)


@lru_cache(maxsize=None)
def generator_player_options(*, season: int, team_filter: str = ALL_TEAMS_FILTER) -> tuple[PlayerGeneratorOption, ...]:
    selected_team = str(team_filter or ALL_TEAMS_FILTER).strip().upper()
    options: list[PlayerGeneratorOption] = []
    seen: set[tuple[str, str]] = set()
    for row in _player_season_rows(season=season):
        team = str(row.get("team") or "").strip().upper()
        if selected_team != ALL_TEAMS_FILTER.upper() and team != selected_team:
            continue
        player_id = str(row.get("player_id") or "").strip()
        player_name = str(row.get("player") or "").strip()
        if not player_id or not team:
            continue
        key = (player_id, team)
        if key in seen:
            continue
        seen.add(key)
        label = f"{player_name} ({player_id}) — {team}" if player_name else f"{player_id} — {team}"
        options.append(PlayerGeneratorOption(label=label, player_id=player_id, team=team, player_name=player_name))
    return tuple(sorted(options, key=lambda option: (option.team, option.player_name.lower(), option.player_id)))


def generate_preview_from_option_into_state(
    state: PlayerGeneratorScreenState,
    *,
    season: int,
    team_filter: str,
    player_option_label: str,
) -> PlayerGeneratorPreview:
    state.season = int(season)
    state.team_filter = str(team_filter or ALL_TEAMS_FILTER).strip() or ALL_TEAMS_FILTER
    state.player_option = str(player_option_label or "").strip()
    option = _option_by_label(season=state.season, team_filter=state.team_filter, label=state.player_option)
    return generate_preview_into_state(state, season=state.season, player_id=option.player_id, team=option.team)


def generate_year_into_state(
    state: PlayerGeneratorScreenState,
    *,
    season: int,
    team_filter: str,
    player_option_label: str,
) -> PlayerGeneratorBatchPreview:
    generator_root = _generator_root()
    _ensure_import_path(generator_root)
    contracts = import_module("contracts")
    source_data = import_module("source_data")
    player_generator = import_module("player_generator")

    state.season = int(season)
    state.team_filter = str(team_filter or ALL_TEAMS_FILTER).strip() or ALL_TEAMS_FILTER
    state.player_option = str(player_option_label or "").strip()
    selected_team = _team_filter_for_generation(state.team_filter)
    scope_text = selected_team or "full season"
    state.status = f"Generating {state.season} {scope_text}..."
    source_root = source_data.GeneratorSourceInventory.from_default().root
    contract = contracts.GeneratorInputContract(
        season=state.season,
        source_root=source_root,
        output_target=contracts.OutputTarget.PROPOSAL,
    ).validate()
    generated_batch = player_generator.generate_player_proposals_for_contract(contract, team_filter=selected_team)
    previews = tuple(_preview_from_proposal(proposal) for proposal in generated_batch.proposals)
    state.batch = PlayerGeneratorBatchPreview(season=generated_batch.season, previews=previews)
    state.generated_count = len(previews)
    select_generated_preview_into_state(state, player_option_label=state.player_option)
    return state.batch


def _team_filter_for_generation(team_filter: str | None) -> str | None:
    selected = str(team_filter or "").strip().upper()
    if not selected or selected == ALL_TEAMS_FILTER.upper():
        return None
    return selected


def select_generated_preview_into_state(state: PlayerGeneratorScreenState, *, player_option_label: str) -> PlayerGeneratorPreview | None:
    state.player_option = str(player_option_label or "").strip()
    if state.batch is None:
        return state.preview
    option = _option_by_label(season=state.season, team_filter=state.team_filter, label=state.player_option)
    state.preview = next((preview for preview in state.batch.previews if preview.player_id == option.player_id and preview.team.upper() == option.team.upper()), state.batch.previews[0] if state.batch.previews else None)
    if state.preview is None:
        raise ValueError(f"no generated players for {state.season}")
    state.player_id = state.preview.player_id
    state.team = state.preview.team
    scope_text = _team_filter_for_generation(state.team_filter) or "full season"
    state.status = f"Generated {state.generated_count} players for {state.season} {scope_text}; showing {state.preview.player_name} {state.preview.team}."
    return state.preview


def _preview_from_proposal(proposal: Any) -> PlayerGeneratorPreview:
    return PlayerGeneratorPreview(
        player_id=proposal.player_id,
        season=proposal.season,
        team=proposal.team,
        player_name=str(proposal.identity.get("player") or ""),
        rows=tuple(
            PlayerGeneratorPreviewRow(
                field_key=candidate.field_key,
                section=candidate.section,
                group=candidate.group,
                field=candidate.display_name,
                value=candidate.display_value,
                source_rule=candidate.source_rule,
            )
            for candidate in proposal.field_candidates
        ),
        warnings=proposal.warnings,
    )


def _option_by_label(*, season: int, team_filter: str, label: str) -> PlayerGeneratorOption:
    for option in generator_player_options(season=season, team_filter=team_filter):
        if option.label == label:
            return option
    raise KeyError(f"player option not found: {label}")


@lru_cache(maxsize=1)
def _all_player_season_rows() -> tuple[dict[str, Any], ...]:
    generator_root = _generator_root()
    _ensure_import_path(generator_root)
    source_data = import_module("source_data")
    workbook_sqlite = import_module("workbook_sqlite")
    source_root = source_data.GeneratorSourceInventory.from_default().root
    database_path = workbook_sqlite.ensure_workbook_sqlite_database(source_root)
    return tuple(workbook_sqlite.iter_workbook_sqlite_sheet_rows(database_path, _PLAYER_SEASON_INFO_SHEET))


@lru_cache(maxsize=None)
def _player_season_rows(*, season: int) -> tuple[dict[str, Any], ...]:
    return tuple(row for row in _all_player_season_rows() if row.get("season") == int(season))


def _generator_root() -> Path:
    return Path(__file__).resolve().parents[1] / "Player Generator"


def _ensure_import_path(path: Path) -> None:
    resolved = str(path.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


__all__ = [
    "DEFAULT_GENERATOR_SEASON",
    "MAX_PREVIEW_ROWS",
    "PLAYER_GENERATOR_SCREEN",
    "ALL_TEAMS_FILTER",
    "PlayerGeneratorBatchPreview",
    "PlayerGeneratorOption",
    "PlayerGeneratorPreview",
    "PlayerGeneratorPreviewRow",
    "PlayerGeneratorScreenState",
    "apply_batch_to_game",
    "apply_preview_to_game",
    "build_player_generator_preview",
    "generate_preview_from_option_into_state",
    "generate_preview_into_state",
    "generate_year_into_state",
    "generator_player_options",
    "generator_team_filter_options",
    "generator_year_options",
    "select_generated_preview_into_state",
]
