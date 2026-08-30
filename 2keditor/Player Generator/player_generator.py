from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.core import offsets as offsets_mod
from nba2k_editor.models.schema import FieldEntry
from player_evidence import PlayerEvidence, shotquality_contest_rows
from player_generation_models import (
    FREE_THROW_FIELD_KEY,
    FreeThrowExecutionArtifact,
    load_free_throw_execution_artifact,
)
from player_rules import (
    PlayerProfileResult,
    PlayerRuleResult,
    ProfileValue,
    RuleValue,
    derive_player_profile_values,
    derive_player_rule_values,
    select_positions_from_evidence,
)
from workbook_sqlite import ensure_workbook_sqlite_database, iter_workbook_sqlite_sheet_rows, query_rows_for_season, workbook_sqlite_sheet_names

_GENERATOR_DIR = Path(__file__).resolve().parent
_DEFAULT_OFFSETS_PLAYERS_PATH = _GENERATOR_DIR.parent / "core" / "Offsets" / "offsets_players.json"
_BASE_PLAYER_SEASON_SHEET = "Player Season Info"
_PLAYER_IDENTITY_SHEET = "Player Info"
_PLAYER_PER_GAME_SHEET = "Player Per Game"
_PLAYER_TOTALS_SHEET = "Player Totals"
_PLAYER_PER_36_SHEET = "Player Per 36 min"
_PLAYER_PER_100_SHEET = "Player Per 100 Poss"
_PLAYER_ADVANCED_SHEET = "Advanced"
_PLAYER_SHOOTING_SHEET = "Player Shooting"
_PLAYER_PLAY_BY_PLAY_SHEET = "Player Play by Play"

_MULTI_TEAM_MARKERS = {"TOT", "2TM", "3TM", "4TM", "5TM"}
_TEAM_STATS_PER_GAME_SHEET = "Team Stats Per Game"
_TEAM_STATS_PER_100_SHEET = "Team Stats Per 100 Pos"
_TEAM_SUMMARY_SHEET = "Team Summaries"
_OPPONENT_STATS_PER_GAME_SHEET = "Opponent Stats Per Game"
_OPPONENT_STATS_PER_100_SHEET = "Opponent Stats Per 100 Poss"

_PLAYER_EVIDENCE_SHEETS = (
    _BASE_PLAYER_SEASON_SHEET,
    _PLAYER_PER_GAME_SHEET,
    _PLAYER_TOTALS_SHEET,
    _PLAYER_PER_36_SHEET,
    _PLAYER_PER_100_SHEET,
    _PLAYER_ADVANCED_SHEET,
    _PLAYER_SHOOTING_SHEET,
    _PLAYER_PLAY_BY_PLAY_SHEET,
)
_TEAM_EVIDENCE_SHEETS = (
    _TEAM_STATS_PER_GAME_SHEET,
    _TEAM_STATS_PER_100_SHEET,
    _TEAM_SUMMARY_SHEET,
    _OPPONENT_STATS_PER_GAME_SHEET,
    _OPPONENT_STATS_PER_100_SHEET,
)
_PLAYER_CAREER_CONTEXT_SHEETS = {
    "Draft Picks",
    _PLAYER_IDENTITY_SHEET,
    "All Star Selections",
    "All Teams",
    "Player Award Shares",
    "All team Voting",
}



@dataclass(frozen=True)
class GeneratedPlayerFieldCandidate:
    domain: str
    section: str
    group: str
    normalized_name: str
    display_name: str
    field_key: str
    display_value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]
    ordinal: int


@dataclass(frozen=True)
class GeneratedPlayerProposal:
    player_id: str
    season: int
    team: str
    identity: dict[str, Any]
    field_candidates: tuple[GeneratedPlayerFieldCandidate, ...]

    def by_field_key(self) -> dict[str, GeneratedPlayerFieldCandidate]:
        return {candidate.field_key: candidate for candidate in self.field_candidates}


@dataclass(frozen=True)
class GeneratedPlayerBatch:
    season: int
    proposals: tuple[GeneratedPlayerProposal, ...]

    def by_player_team(self) -> dict[tuple[str, str], GeneratedPlayerProposal]:
        return {(proposal.player_id, proposal.team): proposal for proposal in self.proposals}


class DraftClassMode(StrEnum):
    DRAFT_PICKS = "draft_picks"
    ROOKIE_YEAR = "rookie_year"
    FIRST_APPEARANCE = "first_appearance"


@dataclass(frozen=True)
class GeneratedDraftClass:
    draft_year: int
    rookie_season: int
    mode: DraftClassMode
    proposals: tuple[GeneratedPlayerProposal, ...]


@dataclass(frozen=True)
class SeasonPlayerContextIndex:
    """Backend-only generated data cache for one workbook season.

    UI code should call generator functions; it should not store this object.
    The index owns the expensive workbook-derived structures: selected-year
    comparison rows, per-player evidence, and authored offset field metadata.
    """

    season: int
    source_database_path: Path
    selected_league: str | None
    comparison_rows: tuple[dict[str, Any], ...]
    evidence_by_key: dict[tuple[str, str], PlayerEvidence]
    field_index: dict[str, FieldEntry]

    def comparison_row_for(self, *, player_id: str, team: str) -> dict[str, Any]:
        key = _player_team_key(player_id, team)
        for row in self.comparison_rows:
            if _player_team_key(row.get("player_id"), row.get("team")) == key:
                return row
        raise KeyError(f"missing comparison row for player_id={player_id} team={team} season={self.season}")

    def evidence_for(self, *, player_id: str, team: str) -> PlayerEvidence:
        key = _player_team_key(player_id, team)
        try:
            return self.evidence_by_key[key]
        except KeyError as exc:
            raise KeyError(f"missing evidence for player_id={player_id} team={team} season={self.season}") from exc

    def player_keys(self, *, team_filter: str | None = None) -> tuple[tuple[str, str], ...]:
        selected_team = str(team_filter or "").strip().upper()
        keys = tuple(sorted(self.evidence_by_key))
        if not selected_team:
            return keys
        return tuple(key for key in keys if key[1] == selected_team)


def authored_player_field_index(offsets_path: str | Path | None = None) -> dict[str, FieldEntry]:
    path = Path(offsets_path) if offsets_path is not None else _DEFAULT_OFFSETS_PLAYERS_PATH
    return dict(_cached_authored_player_field_index(str(path.expanduser().resolve())))


@lru_cache(maxsize=None)
def _cached_authored_player_field_index(offsets_path: str) -> dict[str, FieldEntry]:
    path = Path(offsets_path)
    if path.resolve() == _DEFAULT_OFFSETS_PLAYERS_PATH.resolve():
        players = offsets_mod.get_editor_layout_for_super("Players")
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        players = payload.get("Players")
        if not isinstance(players, dict):
            raise KeyError("offsets_players.json is missing Players")

    index: dict[str, FieldEntry] = {}
    ordinal = 0
    for section, groups in players.items():
        if not isinstance(groups, dict):
            continue
        for group, rows in groups.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized = str(row.get("normalized_name") or row.get("display_name") or "").strip()
                if not normalized:
                    ordinal += 1
                    continue
                key = f"{section}/{normalized}"
                index[key] = FieldEntry(domain="Players", section=str(section), group=str(group), ordinal=ordinal, field=row)
                ordinal += 1
    return index


def generate_player_proposal(
    evidence: PlayerEvidence,
    *,
    offsets_path: str | Path | None = None,
    field_index: dict[str, FieldEntry] | None = None,
    league_player_rows: Any = (),
    free_throw_artifact: FreeThrowExecutionArtifact | None = None,
) -> GeneratedPlayerProposal:
    source_team = str(evidence.team or "").strip().upper()
    positions = select_positions_from_evidence(evidence.play_by_play, evidence.season_info.get("pos") or evidence.identity.get("pos"))
    profile_result = derive_player_profile_values(evidence, positions=positions)
    active_field_keys = set(field_index) if field_index is not None else None
    rule_result = derive_player_rule_values(
        evidence,
        positions=positions,
        league_player_rows=league_player_rows,
        active_field_keys=active_field_keys,
    )
    rule_result = _with_model_authored_free_throw(
        rule_result,
        evidence=evidence,
        active_field_keys=active_field_keys,
        artifact=free_throw_artifact,
    )
    candidates = player_field_candidates_from_results(profile_result, rule_result, offsets_path=offsets_path, field_index=field_index)
    return GeneratedPlayerProposal(
        player_id=evidence.player_id,
        season=evidence.season,
        team=source_team,
        identity={
            "player": evidence.identity.get("player"),
            "player_id": evidence.player_id,
            "team": source_team,
            "team_abbrev": source_team,
            "team_name": _team_display_name(evidence),
            "multi_team_stat_shares": evidence.source_context.get("multi_team_stat_shares"),
            "source": evidence.source_context.get("source"),
        },
        field_candidates=candidates,
    )


def _with_model_authored_free_throw(
    rule_result: PlayerRuleResult,
    *,
    evidence: PlayerEvidence,
    active_field_keys: set[str] | None,
    artifact: FreeThrowExecutionArtifact | None,
) -> PlayerRuleResult:
    if active_field_keys is not None and FREE_THROW_FIELD_KEY not in active_field_keys:
        return rule_result
    target = evidence.per_game.get("ft_percent")
    target_evidence = ("PlayerEvidence.per_game.ft_percent",)
    if target is None:
        fta_per_game = _float(evidence.per_game.get("fta_per_game"))
        if fta_per_game != 0.0:
            return rule_result
        target = 0.0
        target_evidence = (
            "PlayerEvidence.per_game.ft_percent=null",
            "PlayerEvidence.per_game.fta_per_game=0",
            "zero_attempt_free_throw_target=0",
        )
    response = artifact or load_free_throw_execution_artifact()
    solved = response.solve_rating(target)
    if not solved.resolved or solved.rating is None:
        return rule_result
    if solved.predicted_make_probability is None or solved.absolute_error is None:
        return rule_result
    values = dict(rule_result.values)
    values[FREE_THROW_FIELD_KEY] = RuleValue(
        value=solved.rating,
        source_rule="model_free_throw_inverse",
        evidence_keys=target_evidence
        + (
            f"target_make_probability={solved.target_make_probability:.12g}",
            f"predicted_make_probability={solved.predicted_make_probability:.12g}",
            f"absolute_response_error={solved.absolute_error:.12g}",
            "objective=minimum_absolute_forward_response_error",
            "tie_break=middle_supported_rating_then_lower",
            "tied_ratings=" + ",".join(str(rating) for rating in solved.tied_ratings),
            f"boundary_limited={str(solved.boundary_limited).lower()}",
            f"pool_fingerprint={response.pool_fingerprint}",
        ),
    )
    return PlayerRuleResult(values=values)


def generate_player_proposal_from_index(
    context: SeasonPlayerContextIndex,
    *,
    player_id: str,
    team: str,
) -> GeneratedPlayerProposal:
    evidence = context.evidence_for(player_id=player_id, team=team)
    return generate_player_proposal(
        evidence,
        field_index=context.field_index,
        league_player_rows=context.comparison_rows,
    )


def generate_player_proposals_from_index(
    context: SeasonPlayerContextIndex,
    *,
    team_filter: str | None = None,
) -> GeneratedPlayerBatch:
    proposals = tuple(
        generate_player_proposal_from_index(context, player_id=player_id, team=team)
        for player_id, team in context.player_keys(team_filter=team_filter)
    )
    return GeneratedPlayerBatch(season=context.season, proposals=proposals)


def generate_draft_class_proposals(
    draft_year: int,
    *,
    mode: DraftClassMode | str = DraftClassMode.DRAFT_PICKS,
    source_root: str | Path | None = None,
    offsets_path: str | Path | None = None,
    base_season: int | None = None,
) -> GeneratedDraftClass:
    if isinstance(draft_year, bool) or not isinstance(draft_year, int):
        raise ValueError("draft_year must be an int")
    draft_mode = mode if isinstance(mode, DraftClassMode) else DraftClassMode(str(mode))
    rookie_season = draft_year + 1
    context = season_context_index(rookie_season, source_root, offsets_path=offsets_path)
    if draft_mode is DraftClassMode.DRAFT_PICKS:
        proposals = _draft_pick_mode_proposals(context, draft_year)
    elif draft_mode is DraftClassMode.FIRST_APPEARANCE:
        proposals = _first_appearance_mode_proposals(context, draft_year, base_season=base_season)
    else:
        proposals = _rookie_year_mode_proposals(context, draft_year)
    return GeneratedDraftClass(
        draft_year=draft_year,
        rookie_season=rookie_season,
        mode=draft_mode,
        proposals=tuple(proposals),
    )


def _draft_pick_mode_proposals(context: SeasonPlayerContextIndex, draft_year: int) -> list[GeneratedPlayerProposal]:
    proposals: list[GeneratedPlayerProposal] = []
    by_player = _context_keys_by_player_id(context)
    for draft_row in _draft_pick_rows(context.source_database_path, draft_year, player_ids=set(by_player)):
        player_id = str(draft_row.get("player_id") or "").strip().upper()
        if not player_id:
            continue
        keys = by_player.get(player_id, ())
        if not keys:
            continue
        proposal = generate_player_proposal_from_index(context, player_id=keys[0][0], team=keys[0][1])
        proposals.append(_proposal_with_draft_class_metadata(proposal, draft_row, DraftClassMode.DRAFT_PICKS, draft_year, context.season))
    return proposals


def _rookie_year_mode_proposals(context: SeasonPlayerContextIndex, draft_year: int) -> list[GeneratedPlayerProposal]:
    context_player_ids = {player_id for player_id, _team in context.player_keys()}
    draft_row_entries = _draft_pick_rows(context.source_database_path, draft_year, player_ids=context_player_ids)
    draft_rows = {str(row.get("player_id") or "").strip().upper(): row for row in draft_row_entries}
    draft_order = {str(row.get("player_id") or "").strip().upper(): index for index, row in enumerate(draft_row_entries)}
    rookie_keys: list[tuple[str, str]] = []
    for player_id, team in context.player_keys():
        evidence = context.evidence_for(player_id=player_id, team=team)
        if _is_rookie_year_evidence(evidence, context.season):
            rookie_keys.append((player_id, team))
    rookie_keys.sort(key=lambda key: _rookie_year_sort_key(key, draft_order))

    proposals: list[GeneratedPlayerProposal] = []
    for player_id, team in rookie_keys:
        proposal = generate_player_proposal_from_index(context, player_id=player_id, team=team)
        proposals.append(_proposal_with_draft_class_metadata(proposal, draft_rows.get(player_id), DraftClassMode.ROOKIE_YEAR, draft_year, context.season))
    return proposals


def _first_appearance_mode_proposals(
    context: SeasonPlayerContextIndex,
    draft_year: int,
    *,
    base_season: int | None = None,
) -> list[GeneratedPlayerProposal]:
    first_source_season = _draft_class_base_season(draft_year, base_season)
    previous_person_keys = _person_keys_for_seasons(context.source_database_path, range(first_source_season, int(draft_year) + 1))
    selected_by_person: dict[str, tuple[str, str]] = {}
    for player_id, team in context.player_keys():
        evidence = context.evidence_for(player_id=player_id, team=team)
        person_key = _person_identity_key(evidence)
        if not person_key or person_key in previous_person_keys:
            continue
        current = selected_by_person.get(person_key)
        if current is None or _draft_class_evidence_sort_key(evidence) < _draft_class_evidence_sort_key(context.evidence_for(player_id=current[0], team=current[1])):
            selected_by_person[person_key] = (player_id, team)

    selected_keys = sorted(
        selected_by_person.values(),
        key=lambda key: _draft_class_output_sort_key(context.evidence_for(player_id=key[0], team=key[1])),
    )
    proposals: list[GeneratedPlayerProposal] = []
    for player_id, team in selected_keys:
        proposal = generate_player_proposal_from_index(context, player_id=player_id, team=team)
        proposals.append(
            _proposal_with_draft_class_metadata(
                proposal,
                None,
                DraftClassMode.FIRST_APPEARANCE,
                draft_year,
                context.season,
                base_season=first_source_season,
            )
        )
    return proposals


def _draft_class_base_season(draft_year: int, base_season: int | None) -> int:
    if base_season is not None:
        if isinstance(base_season, bool) or not isinstance(base_season, int):
            raise ValueError("base_season must be an int")
        if base_season > draft_year:
            raise ValueError("base_season must be less than or equal to draft_year")
        return base_season
    return 1947 if draft_year >= 1947 else draft_year


def _person_keys_for_seasons(database: Path, seasons: Iterable[int]) -> set[str]:
    source_root = database.parent
    keys: set[str] = set()
    available = set(_available_source_seasons(database))
    for season in seasons:
        if int(season) not in available:
            continue
        context = season_context_index(int(season), source_root)
        for player_id, team in context.player_keys():
            person_key = _person_identity_key(context.evidence_for(player_id=player_id, team=team))
            if person_key:
                keys.add(person_key)
    return keys


def _available_source_seasons(database: Path) -> tuple[int, ...]:
    seasons: set[int] = set()
    try:
        table_name = _workbook_table_name(database, _BASE_PLAYER_SEASON_SHEET)
    except Exception:
        table_name = ""
    if table_name:
        with sqlite3.connect(database) as connection:
            rows = connection.execute(f'SELECT DISTINCT season FROM "{table_name}" WHERE season IS NOT NULL').fetchall()
        for (season,) in rows:
            value = _int_value(season)
            if value is not None:
                seasons.add(value)
    return tuple(sorted(seasons))


def _person_identity_key(evidence: PlayerEvidence) -> str:
    name = str(evidence.identity.get("player") or evidence.season_info.get("player") or "").strip()
    if name:
        return re.sub(r"[^A-Z0-9]", "", name.upper())
    player_id = str(evidence.player_id or "").strip().upper()
    return player_id[:-1] if player_id.endswith("N") else player_id


def _draft_class_evidence_sort_key(evidence: PlayerEvidence) -> tuple[int, float, float, str, str]:
    games = _float(evidence.season_info.get("g") or evidence.per_game.get("g") or evidence.totals.get("g")) or 0.0
    points = _float(evidence.totals.get("pts") or evidence.per_game.get("pts_per_game") or evidence.season_info.get("pts")) or 0.0
    has_stats = 0 if games > 0 or points > 0 else 1
    name = str(evidence.identity.get("player") or evidence.player_id or "")
    return (has_stats, -games, -points, name, str(evidence.team))


def _draft_class_output_sort_key(evidence: PlayerEvidence) -> tuple[int, str, str]:
    name = str(evidence.identity.get("player") or evidence.season_info.get("player") or evidence.player_id or "").strip()
    return (1 if name.startswith("###") else 0, name.upper(), str(evidence.player_id).upper())


def _context_keys_by_player_id(context: SeasonPlayerContextIndex) -> dict[str, tuple[tuple[str, str], ...]]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for player_id, team in context.player_keys():
        grouped.setdefault(str(player_id).strip().upper(), []).append((player_id, team))
    return {player_id: tuple(sorted(keys)) for player_id, keys in grouped.items()}


def _draft_pick_rows(database: Path, draft_year: int, *, player_ids: set[str] | None = None) -> tuple[dict[str, Any], ...]:
    wanted_players = {str(player_id).strip().upper() for player_id in player_ids} if player_ids is not None else None
    rows = []
    for row in iter_workbook_sqlite_sheet_rows(database, "Draft Picks"):
        if row.get("season") != int(draft_year):
            continue
        player_id = str(row.get("player_id") or "").strip().upper()
        if wanted_players is not None and player_id not in wanted_players:
            continue
        rows.append(row)
    return tuple(rows)


def _is_rookie_year_evidence(evidence: PlayerEvidence, rookie_season: int) -> bool:
    experience = _int_value(evidence.season_info.get("experience"))
    first_season = _int_value(evidence.identity.get("from"))
    return experience == 1 or first_season == int(rookie_season)


def _rookie_year_sort_key(
    key: tuple[str, str],
    draft_order: dict[str, int],
) -> int:
    return draft_order.get(key[0], len(draft_order))


def _proposal_with_draft_class_metadata(
    proposal: GeneratedPlayerProposal,
    draft_row: dict[str, Any] | None,
    mode: DraftClassMode,
    draft_year: int,
    rookie_season: int,
    *,
    base_season: int | None = None,
) -> GeneratedPlayerProposal:
    identity = dict(proposal.identity)
    identity["draft_class_mode"] = mode.value
    identity["draft_year"] = draft_year
    identity["rookie_season"] = rookie_season
    if base_season is not None:
        identity["draft_class_base_season"] = base_season
    if draft_row:
        identity["draft_overall_pick"] = draft_row.get("overall_pick")
        identity["draft_round"] = draft_row.get("round")
        identity["draft_team"] = draft_row.get("tm")
        identity["draft_college"] = draft_row.get("college")
    return replace(proposal, identity=identity)


def _int_value(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def validated_season(value: object) -> int:
    """A generation run needs an explicit season-ending year; there is no default."""
    if isinstance(value, bool):
        raise ValueError("season must be an explicit season-ending year")
    if isinstance(value, int):
        season = value
    elif isinstance(value, str) and value.strip().isdigit():
        season = int(value.strip())
    else:
        raise ValueError("season must be an explicit season-ending year")
    if season <= 0:
        raise ValueError("season must be an explicit season-ending year")
    return season


def normalized_league(value: object) -> str | None:
    """`None` means every league in the season, which is what "All Leagues" selects."""
    league = str(value or "").strip().upper() or None
    return None if league == "ALL LEAGUES" else league


def season_context_index(
    season: int,
    source_root: str | Path | None = None,
    *,
    selected_league: str | None = None,
    offsets_path: str | Path | None = None,
) -> SeasonPlayerContextIndex:
    resolved_season = validated_season(season)
    root = Path(source_root) if source_root is not None else _GENERATOR_DIR / "NBA Player Data"
    # ensure_workbook_sqlite_database checks the root, the database file and its
    # workbook metadata, so a missing or unusable source fails here rather than
    # part-way through a whole-season run.
    database_path = ensure_workbook_sqlite_database(root.expanduser().resolve())
    offset_path = Path(offsets_path).expanduser().resolve() if offsets_path is not None else _DEFAULT_OFFSETS_PLAYERS_PATH.resolve()
    return _cached_season_context_index(
        str(database_path),
        resolved_season,
        str(offset_path),
        str(normalized_league(selected_league) or ""),
    )


@lru_cache(maxsize=None)
def _cached_season_context_index(
    database_path: str,
    season: int,
    offsets_path: str,
    selected_league: str,
) -> SeasonPlayerContextIndex:
    database = Path(database_path)
    field_index = _cached_authored_player_field_index(offsets_path)
    sheet_names = workbook_sqlite_sheet_names(database)
    multi_team_primary = _multi_team_primary_teams(database, season)
    multi_team_shares = _multi_team_stat_shares(database, season, multi_team_primary)

    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    player_static: dict[str, dict[str, Any]] = {}
    team_context: dict[str, dict[str, Any]] = {}
    identity_by_player_id: dict[str, dict[str, Any]] = {}
    player_sheet_rows: dict[str, dict[tuple[str, str], dict[str, Any]]] = {sheet: {} for sheet in _PLAYER_EVIDENCE_SHEETS}
    team_sheet_rows: dict[str, dict[str, dict[str, Any]]] = {sheet: {} for sheet in _TEAM_EVIDENCE_SHEETS}
    team_rosters: dict[str, list[dict[str, Any]]] = {}
    shotquality_by_player_id = shotquality_contest_rows(str(database), season, "NBA")

    for sheet in sheet_names:
        prefix = _context_prefix(sheet)
        for row in _context_sheet_rows(database, sheet, season):
            player_id = str(row.get("player_id") or "").strip()
            team = _row_team(row)
            abbreviation = str(row.get("abbreviation") or "").strip()

            if sheet == _PLAYER_IDENTITY_SHEET and player_id:
                identity_by_player_id.setdefault(player_id.upper(), row)

            if row.get("season") is not None and row.get("season") != season and sheet not in _PLAYER_CAREER_CONTEXT_SHEETS:
                continue

            canonical_team = _canonical_team_for_player(player_id, team, multi_team_primary) if player_id and team else ""

            if sheet in player_sheet_rows and player_id and team and canonical_team:
                key = _player_team_key(player_id, canonical_team)
                canonical_row = _canonicalized_player_row(row, canonical_team, multi_team_shares.get(player_id.upper()))
                if _is_multi_team_marker(team):
                    player_sheet_rows[sheet][key] = canonical_row
                else:
                    player_sheet_rows[sheet].setdefault(key, canonical_row)
                    if sheet == _BASE_PLAYER_SEASON_SHEET:
                        team_rosters.setdefault(key[1], []).append(canonical_row)

            if sheet in team_sheet_rows and abbreviation:
                team_sheet_rows[sheet].setdefault(abbreviation.upper(), row)

            if sheet == _BASE_PLAYER_SEASON_SHEET and player_id and team:
                if not canonical_team:
                    continue
                key = _player_team_key(player_id, canonical_team)
                canonical_row = _canonicalized_player_row(row, canonical_team, multi_team_shares.get(player_id.upper()))
                merged = rows_by_key.setdefault(key, {"player_id": player_id, "team": key[1], "season": season})
                _merge_sheet_row(merged, prefix, canonical_row, overwrite=_is_multi_team_marker(team))
                continue

            if player_id and team:
                if not canonical_team:
                    continue
                key = _player_team_key(player_id, canonical_team)
                canonical_row = _canonicalized_player_row(row, canonical_team, multi_team_shares.get(player_id.upper()))
                if key in rows_by_key:
                    _merge_sheet_row(rows_by_key[key], prefix, canonical_row)
                else:
                    static = player_static.setdefault(player_id.upper(), {})
                    _merge_sheet_row(static, prefix, canonical_row, include_bare=False)
                continue

            if player_id:
                static = player_static.setdefault(player_id.upper(), {})
                _merge_sheet_row(static, prefix, row, include_bare=False)
                continue

            if abbreviation:
                context = team_context.setdefault(abbreviation.upper(), {})
                _merge_sheet_row(context, prefix, row, include_bare=False)

    for (player_id, team), merged in rows_by_key.items():
        _merge_prefixed_context(merged, player_static.get(player_id, {}))
        _merge_prefixed_context(merged, _team_context_for_player(team_context, team, multi_team_shares.get(player_id)))
        league = str(merged.get("player_season_info.lg") or merged.get("lg") or "").strip().upper()
        shotquality_contest = shotquality_by_player_id.get(player_id, {}) if league == "NBA" else {}
        if shotquality_contest:
            _merge_sheet_row(
                merged,
                "crafted_source_shotquality",
                shotquality_contest,
                include_bare=False,
            )

    normalized_league = str(selected_league or "").strip().upper()
    selected_keys = tuple(
        key
        for key in sorted(rows_by_key)
        if not normalized_league or _comparison_row_league(rows_by_key[key]) == normalized_league
    )
    comparison_rows = tuple(
        rows_by_key[key]
        for key in selected_keys
        if _comparison_row_has_positive_games(rows_by_key[key])
    )
    _impute_sparse_fg_percent(database, season, player_sheet_rows[_PLAYER_PER_GAME_SHEET])

    evidence_by_key = _build_evidence_index(
        season=season,
        keys=selected_keys,
        identity_by_player_id=identity_by_player_id,
        player_sheet_rows=player_sheet_rows,
        team_sheet_rows=team_sheet_rows,
        team_rosters=team_rosters,
        source_context_by_key=rows_by_key,
        shotquality_by_player_id=shotquality_by_player_id,
    )
    return SeasonPlayerContextIndex(
        season=season,
        source_database_path=database,
        selected_league=normalized_league or None,
        comparison_rows=comparison_rows,
        evidence_by_key=evidence_by_key,
        field_index=dict(field_index),
    )


def _comparison_row_league(row: dict[str, Any]) -> str:
    return str(
        row.get("player_season_info.lg")
        or row.get("season_info.lg")
        or row.get("lg")
        or ""
    ).strip().upper()


def _comparison_row_has_positive_games(row: dict[str, Any]) -> bool:
    games: float | None = None
    for key in ("player_per_game.g", "per_game.g", "g"):
        if key in row:
            games = _float(row.get(key))
            break
    return games is not None and games > 0.0


def _context_sheet_rows(database: Path, sheet: str, season: int) -> tuple[dict[str, Any], ...]:
    if sheet in _PLAYER_CAREER_CONTEXT_SHEETS:
        return iter_workbook_sqlite_sheet_rows(database, sheet)
    return _season_sheet_rows(database, sheet, season)


def _season_sheet_rows(database: Path, sheet: str, season: int) -> tuple[dict[str, Any], ...]:
    try:
        return query_rows_for_season(database, _workbook_table_name(database, sheet), season)
    except (KeyError, sqlite3.Error, ValueError):
        return tuple(
            row
            for row in iter_workbook_sqlite_sheet_rows(database, sheet)
            if row.get("season") == int(season)
        )


def _workbook_table_name(database: Path, sheet_name: str) -> str:
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT table_name FROM workbook_tables WHERE sheet_name = ?", (sheet_name,)).fetchone()
    if row is None:
        raise KeyError(f"workbook sheet not found in SQLite database: {sheet_name}")
    return str(row[0])


def _build_evidence_index(
    *,
    season: int,
    keys: tuple[tuple[str, str], ...],
    identity_by_player_id: dict[str, dict[str, Any]],
    player_sheet_rows: dict[str, dict[tuple[str, str], dict[str, Any]]],
    team_sheet_rows: dict[str, dict[str, dict[str, Any]]],
    team_rosters: dict[str, list[dict[str, Any]]],
    source_context_by_key: dict[tuple[str, str], dict[str, Any]],
    shotquality_by_player_id: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], PlayerEvidence]:
    evidence_by_key: dict[tuple[str, str], PlayerEvidence] = {}
    for key in keys:
        player_id, team = key
        missing: list[str] = []
        identity = identity_by_player_id.get(player_id)
        if not identity:
            missing.append(_PLAYER_IDENTITY_SHEET)
            context_row = source_context_by_key.get(key, {})
            identity = {
                "player_id": player_id,
                "player": context_row.get("player") or player_id,
            }
        season_info = _required_indexed_player_row(player_sheet_rows, _BASE_PLAYER_SEASON_SHEET, key, season, missing)
        per_game = _required_indexed_player_row(player_sheet_rows, _PLAYER_PER_GAME_SHEET, key, season, missing)
        totals = _optional_indexed_player_row(player_sheet_rows, _PLAYER_TOTALS_SHEET, key, missing)
        per_36 = _optional_indexed_player_row(player_sheet_rows, _PLAYER_PER_36_SHEET, key, missing)
        per_100 = _optional_indexed_player_row(player_sheet_rows, _PLAYER_PER_100_SHEET, key, missing)
        advanced = _optional_indexed_player_row(player_sheet_rows, _PLAYER_ADVANCED_SHEET, key, missing)
        shooting = _optional_indexed_player_row(player_sheet_rows, _PLAYER_SHOOTING_SHEET, key, missing)
        play_by_play = _optional_indexed_player_row(player_sheet_rows, _PLAYER_PLAY_BY_PLAY_SHEET, key, missing)
        league = str(season_info.get("lg") or "").strip().upper()
        shotquality_contest = shotquality_by_player_id.get(player_id, {}) if league == "NBA" else {}
        roster_rows = tuple(team_rosters.get(team, ()))
        if not roster_rows:
            missing.append("Team Roster")
        source_player_id = str(season_info.get("player_id") or identity.get("player_id") or player_id).strip() or player_id
        source_team = str(season_info.get("team") or team).strip().upper() or team
        evidence_by_key[key] = PlayerEvidence(
            player_id=source_player_id,
            season=season,
            team=source_team,
            identity=identity,
            season_info=season_info,
            per_game=per_game,
            totals=totals,
            per_36=per_36,
            per_100=per_100,
            advanced=advanced,
            shooting=shooting,
            play_by_play=play_by_play,
            team_roster=roster_rows,
            team_stats_per_game=_optional_indexed_team_row(team_sheet_rows, _TEAM_STATS_PER_GAME_SHEET, team, missing, multi_team_shares=season_info.get("multi_team_stat_shares")),
            team_stats_per_100=_optional_indexed_team_row(team_sheet_rows, _TEAM_STATS_PER_100_SHEET, team, missing, multi_team_shares=season_info.get("multi_team_stat_shares")),
            team_summary=_optional_indexed_team_row(team_sheet_rows, _TEAM_SUMMARY_SHEET, team, missing, multi_team_shares=season_info.get("multi_team_stat_shares")),
            opponent_stats_per_game=_optional_indexed_team_row(team_sheet_rows, _OPPONENT_STATS_PER_GAME_SHEET, team, missing, multi_team_shares=season_info.get("multi_team_stat_shares")),
            opponent_stats_per_100=_optional_indexed_team_row(team_sheet_rows, _OPPONENT_STATS_PER_100_SHEET, team, missing, multi_team_shares=season_info.get("multi_team_stat_shares")),
            source_context=dict(source_context_by_key.get(key, {})),
            missing_sources=tuple(dict.fromkeys(missing)),
            shotquality_contest=shotquality_contest,
        )
    return evidence_by_key


def _required_indexed_player_row(
    rows_by_sheet: dict[str, dict[tuple[str, str], dict[str, Any]]],
    sheet: str,
    key: tuple[str, str],
    season: int,
    missing_sources: list[str],
) -> dict[str, Any]:
    row = rows_by_sheet.get(sheet, {}).get(key, {})
    if row:
        return row
    missing_sources.append(sheet)
    return {}


def _optional_indexed_player_row(
    rows_by_sheet: dict[str, dict[tuple[str, str], dict[str, Any]]],
    sheet: str,
    key: tuple[str, str],
    missing_sources: list[str],
) -> dict[str, Any]:
    row = rows_by_sheet.get(sheet, {}).get(key, {})
    if row:
        return row
    missing_sources.append(sheet)
    return {}


def _optional_indexed_team_row(
    rows_by_sheet: dict[str, dict[str, dict[str, Any]]],
    sheet: str,
    team: str,
    missing_sources: list[str],
    *,
    multi_team_shares: object = None,
) -> dict[str, Any]:
    weighted = _weighted_team_row(rows_by_sheet.get(sheet, {}), team, multi_team_shares)
    if weighted:
        return weighted
    row = rows_by_sheet.get(sheet, {}).get(str(team).strip().upper(), {})
    if row:
        return row
    missing_sources.append(sheet)
    return {}


def _team_context_for_player(team_context: dict[str, dict[str, Any]], team: str, multi_team_shares: object) -> dict[str, Any]:
    weighted = _weighted_team_row(team_context, team, multi_team_shares)
    if weighted:
        return weighted
    return team_context.get(str(team).strip().upper(), {})


def _weighted_team_row(rows_by_team: dict[str, dict[str, Any]], primary_team: str, multi_team_shares: object) -> dict[str, Any]:
    shares = _valid_multi_team_shares(multi_team_shares)
    if len(shares) < 2:
        return {}
    weighted: dict[str, Any] = {}
    total_weight = 0.0
    for share in shares:
        team = str(share.get("team") or "").strip().upper()
        row = rows_by_team.get(team, {})
        weight = _float(share.get("stat_share"))
        if not row or weight is None or weight <= 0.0:
            continue
        total_weight += weight
        for column, value in row.items():
            number = _float(value)
            if number is None:
                continue
            weighted[column] = weighted.get(column, 0.0) + number * weight

    if not weighted or total_weight <= 0.0:
        return {}
    for column, value in tuple(weighted.items()):
        weighted[column] = value / total_weight

    primary_row = rows_by_team.get(str(primary_team).strip().upper(), {})
    first_share_row = next((rows_by_team.get(str(share.get("team") or "").strip().upper(), {}) for share in shares if rows_by_team.get(str(share.get("team") or "").strip().upper(), {})), {})
    for row in (primary_row, first_share_row):
        for column, value in row.items():
            if column not in weighted and value is not None:
                weighted[column] = value
    weighted["multi_team_weighted_context"] = True
    weighted["multi_team_context_teams"] = tuple(str(share.get("team") or "").strip().upper() for share in shares if share.get("team"))
    return weighted


def _valid_multi_team_shares(multi_team_shares: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(multi_team_shares, (list, tuple)):
        return ()
    shares: list[dict[str, Any]] = []
    for share in multi_team_shares:
        if not isinstance(share, dict):
            continue
        team = str(share.get("team") or "").strip().upper()
        weight = _float(share.get("stat_share"))
        if team and weight is not None and weight > 0.0:
            shares.append(share)
    return tuple(shares)


def _is_multi_team_marker(team: object) -> bool:
    text = str(team or "").strip().upper()
    return text in _MULTI_TEAM_MARKERS or (len(text) == 3 and text[0].isdigit() and text[1:] == "TM")


def _canonical_team_for_player(player_id: str, team: str, primary_by_player_id: dict[str, str]) -> str:
    selected_team = str(team or "").strip().upper()
    primary = primary_by_player_id.get(str(player_id or "").strip().upper())
    if not primary:
        return selected_team
    if _is_multi_team_marker(selected_team):
        return primary
    return selected_team if selected_team == primary else ""


def _canonicalized_player_row(row: dict[str, Any], canonical_team: str, stat_shares: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any]:
    current_team = str(row.get("team") or "").strip().upper()
    if current_team == canonical_team and not stat_shares:
        return row
    copied = dict(row)
    if current_team and current_team != canonical_team:
        copied.setdefault("source_team", current_team)
    copied["team"] = canonical_team
    if stat_shares:
        copied["multi_team_stat_shares"] = stat_shares
    return copied


def _impute_sparse_fg_enabled() -> bool:
    """Test hook toggle. Set PLAYERGEN_IMPUTE_SPARSE_FG=0 to disable."""
    return os.environ.get("PLAYERGEN_IMPUTE_SPARSE_FG", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


@lru_cache(maxsize=None)
def _sparse_fg_percent_baseline(database_path: str, season: int) -> tuple[tuple[str, float], ...]:
    """League-season field-goal percentage by position family (G / F / C), attempt-weighted,
    plus an ``_ALL`` overall entry.

    Sourced from ``generated_pseudo_per_1947_1951`` because that is the only table carrying
    both attempts and a position for the 1947-1949 seasons where one league (the NBL) recorded
    makes but never attempts. Returns an empty tuple whenever the table (and therefore the
    early-era context) is absent, which makes the imputation below a no-op for every modern
    season.
    """

    try:
        uri = f"file:{database_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            has_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generated_pseudo_per_1947_1951'"
            ).fetchone()
            if not has_table:
                return ()
            rows = connection.execute(
                """
                SELECT pos_family AS family, SUM(fg) AS fg, SUM(fga) AS fga
                FROM generated_pseudo_per_1947_1951
                WHERE season = ? AND fga IS NOT NULL AND fga > 0
                GROUP BY pos_family
                """,
                (int(season),),
            ).fetchall()
    except sqlite3.Error:
        return ()

    baseline: dict[str, float] = {}
    total_fg = 0.0
    total_fga = 0.0
    for row in rows:
        family = str(row["family"] or "").strip().upper()[:1]
        made = _float(row["fg"])
        attempted = _float(row["fga"])
        if family not in {"G", "F", "C"} or not attempted:
            continue
        baseline[family] = made / attempted
        total_fg += made
        total_fga += attempted
    if total_fga > 0.0:
        baseline["_ALL"] = total_fg / total_fga
    return tuple(sorted(baseline.items()))


def _position_family(row: dict[str, Any]) -> str:
    pos = str(row.get("pos") or row.get("player_per_game.pos") or "").strip().upper()
    return pos[:1] if pos[:1] in {"G", "F", "C"} else ""


def _impute_sparse_fg_percent(
    database: Path,
    season: int,
    per_game_rows: dict[tuple[str, str], dict[str, Any]],
) -> int:
    """TEST HOOK — substitute the league-season position FG% average for players whose
    season recorded field-goal makes but not attempts (1947-1949 NBL).

    Without this, every such player reaches the shooting rules with ``per_game.fg_percent``
    (and every derived shot-quality signal) missing, so those rules collapse to role/size
    defaults and roughly 40% of the 1947 pool ends up with near-identical shooting cards.
    Here we fill ``fg_percent`` / ``e_fg_percent`` from the league-season average for the
    player's position, and back out an implied ``fga_per_game`` from recorded makes so the
    exposure-reliability weighting engages at a sensible confidence. The substitution is
    marked on the row (``fg_percent_source``) and only touches the subject's own evidence —
    the league comparison population is left untouched. Disable with PLAYERGEN_IMPUTE_SPARSE_FG=0.
    """

    if not _impute_sparse_fg_enabled():
        return 0
    baseline = dict(_sparse_fg_percent_baseline(str(database), season))
    if not baseline:
        return 0
    overall = baseline.get("_ALL")
    imputed = 0
    for row in per_game_rows.values():
        if row.get("fg_percent") is not None:
            continue
        percent = baseline.get(_position_family(row), overall)
        if percent is None or percent <= 0.0:
            continue
        row["fg_percent"] = round(percent, 4)
        row["e_fg_percent"] = round(percent, 4)  # no 3-point attempts in this era
        made_per_game = _float(row.get("fg_per_game"))
        if made_per_game is not None and made_per_game >= 0.0:
            row["fga_per_game"] = round(made_per_game / percent, 2)
        row["fg_percent_source"] = "imputed_league_season_position_mean"
        imputed += 1
    return imputed


def _multi_team_primary_teams(database: Path, season: int) -> dict[str, str]:
    saw_multi: set[str] = set()
    primary: dict[str, str] = {}
    for row in _season_sheet_rows(database, _BASE_PLAYER_SEASON_SHEET, season):
        player_id = str(row.get("player_id") or "").strip().upper()
        team = str(row.get("team") or "").strip().upper()
        if not player_id or not team:
            continue
        if _is_multi_team_marker(team):
            saw_multi.add(player_id)
            continue
        primary.setdefault(player_id, team)
    return {player_id: team for player_id, team in primary.items() if player_id in saw_multi}


def _multi_team_stat_shares(database: Path, season: int, primary_by_player_id: dict[str, str]) -> dict[str, tuple[dict[str, Any], ...]]:
    aggregate_games: dict[str, float] = {}
    actual_rows: dict[str, list[dict[str, Any]]] = {}
    for row in _season_sheet_rows(database, _PLAYER_TOTALS_SHEET, season):
        player_id = str(row.get("player_id") or "").strip().upper()
        team = str(row.get("team") or "").strip().upper()
        if player_id not in primary_by_player_id or not team:
            continue
        if _is_multi_team_marker(team):
            games = _float(row.get("g"))
            if games is not None:
                aggregate_games[player_id] = games
        else:
            actual_rows.setdefault(player_id, []).append(row)

    shares: dict[str, tuple[dict[str, Any], ...]] = {}
    for player_id, rows in actual_rows.items():
        total_games = aggregate_games.get(player_id)
        if total_games is None or total_games <= 0.0:
            continue
        entries: list[dict[str, Any]] = []
        for row in rows:
            games = _float(row.get("g"))
            minutes = _float(row.get("mp"))
            if games is None or minutes is None:
                continue
            entries.append(
                {
                    "team": str(row.get("team") or "").strip().upper(),
                    "games": games,
                    "minutes": minutes,
                    "stat_share": round(games / total_games, 6),
                }
            )
        if entries:
            shares[player_id] = tuple(entries)
    return shares


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _player_team_key(player_id: object, team: object) -> tuple[str, str]:
    return (str(player_id or "").strip().upper(), str(team or "").strip().upper())

def _row_team(row: dict[str, Any]) -> str:
    team = str(row.get("team") or "").strip()
    if team:
        return team
    return str(row.get("tm") or "").strip()


def _merge_sheet_row(target: dict[str, Any], prefix: str, row: dict[str, Any], *, include_bare: bool = True, overwrite: bool = False) -> None:
    for column, value in row.items():
        if value is None:
            continue
        prefixed_key = f"{prefix}.{column}"
        if overwrite:
            target[prefixed_key] = value
            if include_bare:
                target[column] = value
            continue
        target.setdefault(prefixed_key, value)
        if include_bare and column not in target:
            target[column] = value


def _merge_prefixed_context(target: dict[str, Any], context: dict[str, Any]) -> None:
    for column, value in context.items():
        if value is not None and column not in target:
            target[column] = value


def _context_prefix(sheet: str) -> str:
    return sheet.lower().replace(" ", "_")


def player_field_candidates_from_results(
    profile_result: PlayerProfileResult,
    rule_result: PlayerRuleResult,
    *,
    offsets_path: str | Path | None = None,
    field_index: dict[str, FieldEntry] | None = None,
) -> tuple[GeneratedPlayerFieldCandidate, ...]:
    authored = field_index if field_index is not None else authored_player_field_index(offsets_path)
    candidates: list[GeneratedPlayerFieldCandidate] = []
    for key, value in _combined_values(profile_result, rule_result):
        field_entry = authored[key]
        candidates.append(_candidate_from_value(key, value, field_entry))
    return tuple(sorted(candidates, key=lambda candidate: candidate.ordinal))


def _combined_values(
    profile_result: PlayerProfileResult,
    rule_result: PlayerRuleResult,
) -> tuple[tuple[str, ProfileValue | RuleValue], ...]:
    values: list[tuple[str, ProfileValue | RuleValue]] = []
    values.extend(profile_result.values.items())
    values.extend(rule_result.values.items())
    return tuple(values)


def _candidate_from_value(
    key: str,
    value: ProfileValue | RuleValue,
    field_entry: FieldEntry,
) -> GeneratedPlayerFieldCandidate:
    section, normalized = key.split("/", 1)
    return GeneratedPlayerFieldCandidate(
        domain="Players",
        section=field_entry.section,
        group=field_entry.group,
        normalized_name=field_entry.normalized_name,
        display_name=field_entry.display_name,
        field_key=key,
        display_value=value.value,
        source_rule=value.source_rule,
        evidence_keys=tuple(value.evidence_keys),
        ordinal=field_entry.ordinal,
    )


def _team_display_name(evidence: PlayerEvidence) -> str:
    for row in (evidence.team_summary, evidence.team_stats_per_game, evidence.team_stats_per_100):
        value = row.get("team") if isinstance(row, dict) else None
        text = str(value or "").strip()
        if text:
            return text
    return ""


__all__ = [
    "GeneratedPlayerFieldCandidate",
    "GeneratedPlayerProposal",
    "GeneratedPlayerBatch",
    "GeneratedDraftClass",
    "DraftClassMode",
    "SeasonPlayerContextIndex",
    "authored_player_field_index",
    "generate_player_proposal",
    "generate_player_proposal_from_index",
    "generate_player_proposals_from_index",
    "generate_draft_class_proposals",
    "player_field_candidates_from_results",
    "season_context_index",
]
