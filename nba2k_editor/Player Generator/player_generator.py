from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from nba2k_editor.core import offsets as offsets_mod
from nba2k_editor.models.schema import FieldEntry
from contracts import GeneratorInputContract
from player_evidence import PlayerEvidence
from player_rules import (
    PlayerProfileResult,
    PlayerRuleResult,
    ProfileValue,
    RuleValue,
    derive_player_profile_values,
    derive_player_rule_values,
)
from workbook_sqlite import ensure_workbook_sqlite_database, iter_workbook_sqlite_sheet_rows, workbook_sqlite_sheet_names

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
) -> GeneratedPlayerProposal:
    source_team = str(evidence.team or "").strip().upper()
    profile_result = derive_player_profile_values(evidence)
    rule_result = derive_player_rule_values(evidence)
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
        },
        field_candidates=candidates,
    )


def generate_player_proposal_from_contract(
    contract: GeneratorInputContract,
    *,
    player_id: str,
    team: str,
    offsets_path: str | Path | None = None,
) -> GeneratedPlayerProposal:
    context = season_context_index(contract, offsets_path=offsets_path)
    return generate_player_proposal_from_index(context, player_id=player_id, team=team)


def generate_player_proposal_from_index(
    context: SeasonPlayerContextIndex,
    *,
    player_id: str,
    team: str,
) -> GeneratedPlayerProposal:
    evidence = context.evidence_for(player_id=player_id, team=team)
    return generate_player_proposal(evidence, field_index=context.field_index)


def generate_player_proposals_for_contract(
    contract: GeneratorInputContract,
    *,
    team_filter: str | None = None,
    offsets_path: str | Path | None = None,
) -> GeneratedPlayerBatch:
    context = season_context_index(contract, offsets_path=offsets_path)
    return generate_player_proposals_from_index(context, team_filter=team_filter)


def generate_player_proposals_from_index(
    context: SeasonPlayerContextIndex,
    *,
    team_filter: str | None = None,
) -> GeneratedPlayerBatch:
    proposals = [generate_player_proposal_from_index(context, player_id=player_id, team=team) for player_id, team in context.player_keys(team_filter=team_filter)]
    return GeneratedPlayerBatch(season=context.season, proposals=tuple(proposals))


def generate_draft_class_proposals(
    draft_year: int,
    *,
    mode: DraftClassMode | str = DraftClassMode.DRAFT_PICKS,
    source_root: str | Path | None = None,
    offsets_path: str | Path | None = None,
) -> GeneratedDraftClass:
    if isinstance(draft_year, bool) or not isinstance(draft_year, int):
        raise ValueError("draft_year must be an int")
    draft_mode = mode if isinstance(mode, DraftClassMode) else DraftClassMode(str(mode))
    rookie_season = draft_year + 1
    contract = GeneratorInputContract(
        season=rookie_season,
        source_root=Path(source_root) if source_root is not None else _GENERATOR_DIR / "NBA Player Data",
        output_target="proposal",
    )
    context = season_context_index(contract, offsets_path=offsets_path)
    if draft_mode is DraftClassMode.DRAFT_PICKS:
        proposals = _draft_pick_mode_proposals(context, draft_year)
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
    for draft_row in _draft_pick_rows(context.source_database_path, draft_year):
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
    draft_rows = {str(row.get("player_id") or "").strip().upper(): row for row in _draft_pick_rows(context.source_database_path, draft_year)}
    rookie_keys: list[tuple[str, str]] = []
    for player_id, team in context.player_keys():
        evidence = context.evidence_for(player_id=player_id, team=team)
        if _is_rookie_year_evidence(evidence, context.season):
            rookie_keys.append((player_id, team))
    rookie_keys.sort(key=lambda key: _rookie_year_sort_key(context, key, draft_rows))

    proposals: list[GeneratedPlayerProposal] = []
    for player_id, team in rookie_keys:
        proposal = generate_player_proposal_from_index(context, player_id=player_id, team=team)
        proposals.append(_proposal_with_draft_class_metadata(proposal, draft_rows.get(player_id), DraftClassMode.ROOKIE_YEAR, draft_year, context.season))
    return proposals


def _context_keys_by_player_id(context: SeasonPlayerContextIndex) -> dict[str, tuple[tuple[str, str], ...]]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for player_id, team in context.player_keys():
        grouped.setdefault(str(player_id).strip().upper(), []).append((player_id, team))
    return {player_id: tuple(sorted(keys)) for player_id, keys in grouped.items()}


def _draft_pick_rows(database: Path, draft_year: int) -> tuple[dict[str, Any], ...]:
    rows = [row for row in iter_workbook_sqlite_sheet_rows(database, "Draft Picks") if row.get("season") == int(draft_year)]
    return tuple(sorted(rows, key=_draft_pick_sort_key))


def _draft_pick_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    overall = _int_value(row.get("overall_pick"))
    round_number = _int_value(row.get("round"))
    name = str(row.get("player") or "").strip().upper()
    if overall is None or round_number is None or not name:
        raise ValueError("draft pick row is missing sort evidence")
    return (overall, round_number, name)


def _is_rookie_year_evidence(evidence: PlayerEvidence, rookie_season: int) -> bool:
    experience = _int_value(evidence.season_info.get("experience"))
    first_season = _int_value(evidence.identity.get("from"))
    return experience == 1 or first_season == int(rookie_season)


def _rookie_year_sort_key(
    context: SeasonPlayerContextIndex,
    key: tuple[str, str],
    draft_rows: dict[str, dict[str, Any]],
) -> tuple[int, int, int, str]:
    player_id, team = key
    draft_row = draft_rows.get(player_id)
    evidence = context.evidence_for(player_id=player_id, team=team)
    player_name = str(evidence.identity.get("player") or player_id).strip().upper()
    if draft_row is None:
        raise ValueError(f"rookie-year row has no draft pick evidence: {player_id}")
    overall, round_number, _ = _draft_pick_sort_key(draft_row)
    return (0, overall, round_number, player_name)


def _proposal_with_draft_class_metadata(
    proposal: GeneratedPlayerProposal,
    draft_row: dict[str, Any] | None,
    mode: DraftClassMode,
    draft_year: int,
    rookie_season: int,
) -> GeneratedPlayerProposal:
    identity = dict(proposal.identity)
    identity["draft_class_mode"] = mode.value
    identity["draft_year"] = draft_year
    identity["rookie_season"] = rookie_season
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


def selected_year_player_comparison_rows(contract: GeneratorInputContract) -> tuple[dict[str, Any], ...]:
    return season_context_index(contract).comparison_rows


def season_context_index(
    contract: GeneratorInputContract,
    *,
    offsets_path: str | Path | None = None,
) -> SeasonPlayerContextIndex:
    validated = contract.validate()
    database_path = ensure_workbook_sqlite_database(validated.source_root)
    offset_path = Path(offsets_path).expanduser().resolve() if offsets_path is not None else _DEFAULT_OFFSETS_PLAYERS_PATH.resolve()
    return _cached_season_context_index(str(database_path), int(validated.season), str(offset_path))


@lru_cache(maxsize=None)
def _cached_season_context_index(database_path: str, season: int, offsets_path: str) -> SeasonPlayerContextIndex:
    database = Path(database_path)
    sheet_names = workbook_sqlite_sheet_names(database)
    field_index = _cached_authored_player_field_index(offsets_path)
    multi_team_primary = _multi_team_primary_teams(database, season)
    multi_team_shares = _multi_team_stat_shares(database, season, multi_team_primary)

    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    player_static: dict[str, dict[str, Any]] = {}
    team_context: dict[str, dict[str, Any]] = {}
    identity_by_player_id: dict[str, dict[str, Any]] = {}
    player_sheet_rows: dict[str, dict[tuple[str, str], dict[str, Any]]] = {sheet: {} for sheet in _PLAYER_EVIDENCE_SHEETS}
    team_sheet_rows: dict[str, dict[str, dict[str, Any]]] = {sheet: {} for sheet in _TEAM_EVIDENCE_SHEETS}
    team_rosters: dict[str, list[dict[str, Any]]] = {}

    for sheet in sheet_names:
        prefix = _context_prefix(sheet)
        for row in iter_workbook_sqlite_sheet_rows(database, sheet):
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

    comparison_rows = tuple(rows_by_key[key] for key in sorted(rows_by_key))
    evidence_by_key = _build_evidence_index(
        season=season,
        keys=tuple(sorted(rows_by_key)),
        identity_by_player_id=identity_by_player_id,
        player_sheet_rows=player_sheet_rows,
        team_sheet_rows=team_sheet_rows,
        team_rosters=team_rosters,
        source_context_by_key=rows_by_key,
    )
    return SeasonPlayerContextIndex(
        season=season,
        source_database_path=database,
        comparison_rows=comparison_rows,
        evidence_by_key=evidence_by_key,
        field_index=dict(field_index),
    )


def _build_evidence_index(
    *,
    season: int,
    keys: tuple[tuple[str, str], ...],
    identity_by_player_id: dict[str, dict[str, Any]],
    player_sheet_rows: dict[str, dict[tuple[str, str], dict[str, Any]]],
    team_sheet_rows: dict[str, dict[str, dict[str, Any]]],
    team_rosters: dict[str, list[dict[str, Any]]],
    source_context_by_key: dict[tuple[str, str], dict[str, Any]],
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
    return len(text) == 3 and text[0].isdigit() and text[1:] == "TM"


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


def _multi_team_primary_teams(database: Path, season: int) -> dict[str, str]:
    saw_multi: set[str] = set()
    primary: dict[str, str] = {}
    for row in iter_workbook_sqlite_sheet_rows(database, _BASE_PLAYER_SEASON_SHEET):
        if row.get("season") != int(season):
            continue
        player_id = str(row.get("player_id") or "").strip().upper()
        team = str(row.get("team") or "").strip().upper()
        if not player_id or not team:
            continue
        if _is_multi_team_marker(team):
            saw_multi.add(player_id)
            continue
        if player_id in saw_multi:
            primary.setdefault(player_id, team)
    return primary


def _multi_team_stat_shares(database: Path, season: int, primary_by_player_id: dict[str, str]) -> dict[str, tuple[dict[str, Any], ...]]:
    aggregate_games: dict[str, float] = {}
    actual_rows: dict[str, list[dict[str, Any]]] = {}
    for row in iter_workbook_sqlite_sheet_rows(database, _PLAYER_TOTALS_SHEET):
        if row.get("season") != int(season):
            continue
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
    "generate_player_proposal_from_contract",
    "generate_player_proposal_from_index",
    "generate_player_proposals_for_contract",
    "generate_player_proposals_from_index",
    "generate_draft_class_proposals",
    "player_field_candidates_from_results",
    "season_context_index",
    "selected_year_player_comparison_rows",
]


