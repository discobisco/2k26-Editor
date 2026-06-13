from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

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
from workbook_reader import iter_sheet_rows, workbook_sheet_names

_GENERATOR_DIR = Path(__file__).resolve().parent
_DEFAULT_OFFSETS_PLAYERS_PATH = _GENERATOR_DIR.parent / "core" / "Offsets" / "offsets_players.json"
_WORKBOOK_NAME = "NBA DATA Master.xlsx"
_BASE_PLAYER_SEASON_SHEET = "Player Season Info"
_PLAYER_IDENTITY_SHEET = "Player Info"
_PLAYER_PER_GAME_SHEET = "Player Per Game"
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
    warnings: tuple[str, ...]

    def by_field_key(self) -> dict[str, GeneratedPlayerFieldCandidate]:
        return {candidate.field_key: candidate for candidate in self.field_candidates}


@dataclass(frozen=True)
class GeneratedPlayerBatch:
    season: int
    proposals: tuple[GeneratedPlayerProposal, ...]
    failures: tuple[str, ...]

    def by_player_team(self) -> dict[tuple[str, str], GeneratedPlayerProposal]:
        return {(proposal.player_id, proposal.team): proposal for proposal in self.proposals}


@dataclass(frozen=True)
class SeasonPlayerContextIndex:
    """Backend-only generated data cache for one workbook season.

    UI code should call generator functions; it should not store this object.
    The index owns the expensive workbook-derived structures: selected-year
    comparison rows, per-player evidence, and authored offset field metadata.
    """

    season: int
    workbook_path: Path
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
    league_player_rows: Iterable[dict[str, Any]] = (),
    offsets_path: str | Path | None = None,
    field_index: dict[str, FieldEntry] | None = None,
) -> GeneratedPlayerProposal:
    profile_result = derive_player_profile_values(evidence)
    rule_result = derive_player_rule_values(evidence, league_player_rows=league_player_rows)
    candidates = player_field_candidates_from_results(profile_result, rule_result, offsets_path=offsets_path, field_index=field_index)
    warnings = _warnings_from_skips(profile_result.skipped, rule_result.skipped)
    return GeneratedPlayerProposal(
        player_id=evidence.player_id,
        season=evidence.season,
        team=evidence.team,
        identity={"player": evidence.identity.get("player"), "player_id": evidence.player_id},
        field_candidates=candidates,
        warnings=warnings,
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
    return generate_player_proposal(evidence, league_player_rows=context.comparison_rows, field_index=context.field_index)


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
    proposals: list[GeneratedPlayerProposal] = []
    failures: list[str] = []
    for player_id, team in context.player_keys(team_filter=team_filter):
        try:
            proposals.append(generate_player_proposal_from_index(context, player_id=player_id, team=team))
        except Exception as exc:
            failures.append(f"{player_id}/{team}: {exc}")
    return GeneratedPlayerBatch(season=context.season, proposals=tuple(proposals), failures=tuple(failures))


def selected_year_player_comparison_rows(contract: GeneratorInputContract) -> tuple[dict[str, Any], ...]:
    return season_context_index(contract).comparison_rows


def season_context_index(
    contract: GeneratorInputContract,
    *,
    offsets_path: str | Path | None = None,
) -> SeasonPlayerContextIndex:
    validated = contract.validate()
    workbook_path = (Path(validated.source_root) / _WORKBOOK_NAME).expanduser().resolve()
    offset_path = Path(offsets_path).expanduser().resolve() if offsets_path is not None else _DEFAULT_OFFSETS_PLAYERS_PATH.resolve()
    return _cached_season_context_index(str(workbook_path), int(validated.season), str(offset_path))


@lru_cache(maxsize=None)
def _cached_season_context_index(workbook_path: str, season: int, offsets_path: str) -> SeasonPlayerContextIndex:
    workbook = Path(workbook_path)
    sheet_names = workbook_sheet_names(workbook)
    field_index = _cached_authored_player_field_index(offsets_path)

    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    player_static: dict[str, dict[str, Any]] = {}
    team_context: dict[str, dict[str, Any]] = {}
    identity_by_player_id: dict[str, dict[str, Any]] = {}
    player_sheet_rows: dict[str, dict[tuple[str, str], dict[str, Any]]] = {sheet: {} for sheet in _PLAYER_EVIDENCE_SHEETS}
    team_sheet_rows: dict[str, dict[str, dict[str, Any]]] = {sheet: {} for sheet in _TEAM_EVIDENCE_SHEETS}
    team_rosters: dict[str, list[dict[str, Any]]] = {}

    for sheet in sheet_names:
        prefix = _context_prefix(sheet)
        for row in iter_sheet_rows(workbook, sheet):
            player_id = str(row.get("player_id") or "").strip()
            team = _row_team(row)
            abbreviation = str(row.get("abbreviation") or "").strip()

            if sheet == _PLAYER_IDENTITY_SHEET and player_id:
                identity_by_player_id.setdefault(player_id.upper(), row)

            if row.get("season") is not None and row.get("season") != season:
                continue

            if sheet in player_sheet_rows and player_id and team:
                key = _player_team_key(player_id, team)
                player_sheet_rows[sheet].setdefault(key, row)
                if sheet == _BASE_PLAYER_SEASON_SHEET:
                    team_rosters.setdefault(key[1], []).append(row)

            if sheet in team_sheet_rows and abbreviation:
                team_sheet_rows[sheet].setdefault(abbreviation.upper(), row)

            if sheet == _BASE_PLAYER_SEASON_SHEET and player_id and team:
                key = _player_team_key(player_id, team)
                merged = rows_by_key.setdefault(key, {"player_id": player_id, "team": key[1], "season": season})
                _merge_sheet_row(merged, prefix, row)
                continue

            if player_id and team:
                key = _player_team_key(player_id, team)
                merged = rows_by_key.setdefault(key, {"player_id": player_id, "team": key[1], "season": season})
                _merge_sheet_row(merged, prefix, row)
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
        _merge_prefixed_context(merged, team_context.get(team, {}))

    comparison_rows = tuple(rows_by_key[key] for key in sorted(rows_by_key))
    evidence_by_key = _build_evidence_index(
        season=season,
        keys=tuple(sorted(rows_by_key)),
        identity_by_player_id=identity_by_player_id,
        player_sheet_rows=player_sheet_rows,
        team_sheet_rows=team_sheet_rows,
        team_rosters=team_rosters,
    )
    return SeasonPlayerContextIndex(
        season=season,
        workbook_path=workbook,
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
) -> dict[tuple[str, str], PlayerEvidence]:
    evidence_by_key: dict[tuple[str, str], PlayerEvidence] = {}
    for key in keys:
        player_id, team = key
        missing: list[str] = []
        identity = identity_by_player_id.get(player_id)
        if not identity:
            raise KeyError(f"missing player identity row: {player_id}")
        season_info = _required_indexed_player_row(player_sheet_rows, _BASE_PLAYER_SEASON_SHEET, key, season)
        per_game = _required_indexed_player_row(player_sheet_rows, _PLAYER_PER_GAME_SHEET, key, season)
        per_100 = _optional_indexed_player_row(player_sheet_rows, _PLAYER_PER_100_SHEET, key, missing)
        advanced = _optional_indexed_player_row(player_sheet_rows, _PLAYER_ADVANCED_SHEET, key, missing)
        shooting = _optional_indexed_player_row(player_sheet_rows, _PLAYER_SHOOTING_SHEET, key, missing)
        play_by_play = _optional_indexed_player_row(player_sheet_rows, _PLAYER_PLAY_BY_PLAY_SHEET, key, missing)
        roster_rows = tuple(team_rosters.get(team, ()))
        if not roster_rows:
            raise KeyError(f"missing team roster rows for team={team} season={season}")
        source_player_id = str(season_info.get("player_id") or identity.get("player_id") or player_id).strip() or player_id
        source_team = str(season_info.get("team") or team).strip().upper() or team
        evidence_by_key[key] = PlayerEvidence(
            player_id=source_player_id,
            season=season,
            team=source_team,
            identity=identity,
            season_info=season_info,
            per_game=per_game,
            per_100=per_100,
            advanced=advanced,
            shooting=shooting,
            play_by_play=play_by_play,
            team_roster=roster_rows,
            team_stats_per_game=_optional_indexed_team_row(team_sheet_rows, _TEAM_STATS_PER_GAME_SHEET, team, missing),
            team_stats_per_100=_optional_indexed_team_row(team_sheet_rows, _TEAM_STATS_PER_100_SHEET, team, missing),
            team_summary=_optional_indexed_team_row(team_sheet_rows, _TEAM_SUMMARY_SHEET, team, missing),
            opponent_stats_per_game=_optional_indexed_team_row(team_sheet_rows, _OPPONENT_STATS_PER_GAME_SHEET, team, missing),
            opponent_stats_per_100=_optional_indexed_team_row(team_sheet_rows, _OPPONENT_STATS_PER_100_SHEET, team, missing),
            missing_sources=tuple(dict.fromkeys(missing)),
        )
    return evidence_by_key


def _required_indexed_player_row(
    rows_by_sheet: dict[str, dict[tuple[str, str], dict[str, Any]]],
    sheet: str,
    key: tuple[str, str],
    season: int,
) -> dict[str, Any]:
    row = rows_by_sheet.get(sheet, {}).get(key, {})
    if row:
        return row
    player_id, team = key
    raise KeyError(f"missing required {sheet} row for player_id={player_id} team={team} season={season}")


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
) -> dict[str, Any]:
    row = rows_by_sheet.get(sheet, {}).get(str(team).strip().upper(), {})
    if row:
        return row
    missing_sources.append(sheet)
    return {}


def _player_team_key(player_id: object, team: object) -> tuple[str, str]:
    return (str(player_id or "").strip().upper(), str(team or "").strip().upper())

def _row_team(row: dict[str, Any]) -> str:
    team = str(row.get("team") or "").strip()
    if team:
        return team
    return str(row.get("tm") or "").strip()


def _merge_sheet_row(target: dict[str, Any], prefix: str, row: dict[str, Any], *, include_bare: bool = True) -> None:
    for column, value in row.items():
        if value is None:
            continue
        target.setdefault(f"{prefix}.{column}", value)
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
    if section != field_entry.section or normalized != field_entry.normalized_name:
        raise KeyError(f"generated field key does not match authored field entry: {key}")
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


def _warnings_from_skips(profile_skipped: dict[str, str], rule_skipped: dict[str, str]) -> tuple[str, ...]:
    warnings: list[str] = []
    for skipped in (profile_skipped, rule_skipped):
        for field_key in sorted(skipped):
            warnings.append(f"{field_key}: {skipped[field_key]}")
    return tuple(warnings)


__all__ = [
    "GeneratedPlayerFieldCandidate",
    "GeneratedPlayerProposal",
    "GeneratedPlayerBatch",
    "SeasonPlayerContextIndex",
    "authored_player_field_index",
    "generate_player_proposal",
    "generate_player_proposal_from_contract",
    "generate_player_proposal_from_index",
    "generate_player_proposals_for_contract",
    "generate_player_proposals_from_index",
    "player_field_candidates_from_results",
    "season_context_index",
    "selected_year_player_comparison_rows",
]
