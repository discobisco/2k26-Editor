from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from nba2k_editor.models.schema import FieldEntry
from player_generator import (
    authored_player_field_index,
    generate_player_proposals_from_index,
    season_context_index,
    validated_season,
)



@dataclass(frozen=True)
class GamePortFieldResult:
    field_key: str
    section: str
    group: str
    normalized_name: str
    display_name: str
    attempted_value: int | str | None
    readback_value: Any
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class GamePortResult:
    player_index: int
    attempted: int
    succeeded: int
    failed: int
    fields: tuple[GamePortFieldResult, ...]

    @property
    def ok(self) -> bool:
        return self.failed == 0


_MATCHED_NAME_IMPORT_SECTIONS: frozenset[str] = frozenset({"Attributes", "Tendencies"})
_MATCHED_NAME_IMPORT_FIELD_KEYS: frozenset[str] = frozenset(
    {"Vitals/AGE", "Vitals/POSITION", "Vitals/SECONDARYPOSITION"}
)


@dataclass(frozen=True)
class GamePortBatchResult:
    player_results: tuple[GamePortResult, ...]
    generated_count: int
    target_count: int

    @property
    def attempted(self) -> int:
        return sum(result.attempted for result in self.player_results)

    @property
    def succeeded(self) -> int:
        return sum(result.succeeded for result in self.player_results)

    @property
    def failed(self) -> int:
        return sum(result.failed for result in self.player_results)

    @property
    def applied_players(self) -> int:
        return len(self.player_results)

    @property
    def unapplied_generated(self) -> int:
        return self.generated_count - self.applied_players

    @property
    def unused_targets(self) -> int:
        return self.target_count - self.applied_players

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.unapplied_generated == 0


@dataclass(frozen=True)
class GeneratedPlayerGameImportResult:
    season: int
    roster_label: str
    team_filter: str | None
    apply_result: GamePortBatchResult

    @property
    def ok(self) -> bool:
        return self.apply_result.ok


@dataclass(frozen=True)
class GeneratedPlayerTeamAssignment:
    generated_player: Any
    generated_player_label: str
    generated_team_key: str
    generated_team_label: str
    team_source: str
    live_team_index: int
    live_team_address: int
    live_team_label: str
    target_player_index: int
    target_player_label: str
    team_slot: int
    destination_kind: str = "team"


@dataclass(frozen=True)
class GeneratedPlayerTeamImportIssue:
    generated_player_label: str
    generated_team_key: str
    generated_team_label: str
    reason: str
    blocking: bool = True


@dataclass(frozen=True)
class GeneratedPlayerTeamRosterEntry:
    generated_player: Any
    generated_player_label: str
    generated_team_key: str
    generated_team_label: str
    team_source: str
    destination_kind: str = "team"


@dataclass(frozen=True)
class GeneratedPlayerTeamRosterPlan:
    entries: tuple[GeneratedPlayerTeamRosterEntry, ...]
    issues: tuple[GeneratedPlayerTeamImportIssue, ...]
    generated_count: int
    source_generated_count: int
    authored_count: int
    free_agent_count: int

    @property
    def ready(self) -> bool:
        return len(self.entries) == self.generated_count and not any(issue.blocking for issue in self.issues)

    @property
    def generated_players(self) -> tuple[Any, ...]:
        return tuple(entry.generated_player for entry in self.entries)


@dataclass(frozen=True)
class GeneratedPlayerTeamImportPlan:
    assignments: tuple[GeneratedPlayerTeamAssignment, ...]
    issues: tuple[GeneratedPlayerTeamImportIssue, ...]
    generated_count: int
    target_count: int
    source_generated_count: int = 0
    authored_count: int = 0
    free_agent_count: int = 0

    @property
    def ready(self) -> bool:
        return not any(issue.blocking for issue in self.issues)

    @property
    def generated_players(self) -> tuple[Any, ...]:
        return tuple(assignment.generated_player for assignment in self.assignments)

    @property
    def player_indices(self) -> tuple[int, ...]:
        return tuple(assignment.target_player_index for assignment in self.assignments)


def import_generated_players_to_game(
    model: Any,
    season: int,
    source_root: str | Path | None = None,
    *,
    roster_label: str,
    selected_league: str | None = None,
    generated_players: Iterable[Any] | None = None,
    team_filter: str | None = None,
    player_indices: Iterable[int] | None = None,
    match_existing_player_names: bool = False,
    offsets_path: str | Path | None = None,
    stop_on_error: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> GeneratedPlayerGameImportResult:
    resolved_season = validated_season(season)
    label = str(roster_label or "").strip()
    if not label:
        # This writes over the roster in the loaded game, so the caller has to name
        # what is being overwritten. It is also reported back on the result.
        raise ValueError("roster_label is required to import generated players into the game")

    if generated_players is None:
        context = season_context_index(
            resolved_season,
            source_root,
            selected_league=selected_league,
            offsets_path=offsets_path,
        )
        batch = generate_player_proposals_from_index(context, team_filter=team_filter)
        generated_tuple = batch.proposals
        field_index = context.field_index
    else:
        generated_tuple = tuple(generated_players)
        field_index = None

    if stop_on_error:
        validate_generated_player_names_match_offsets(generated_tuple, field_index=field_index)
    if match_existing_player_names:
        player_indices = None
        matched = _generated_player_name_matches(model, generated_tuple)
        generated_tuple = tuple(generated for generated, _index in matched)
        player_indices = tuple(index for _generated, index in matched)
    apply_result = apply_generated_players_to_game(
        model,
        generated_tuple,
        player_indices=player_indices,
        field_index=field_index,
        include_sections=_MATCHED_NAME_IMPORT_SECTIONS if match_existing_player_names else None,
        include_field_keys=_MATCHED_NAME_IMPORT_FIELD_KEYS if match_existing_player_names else None,
        stop_on_error=stop_on_error,
        progress_callback=progress_callback,
    )
    return GeneratedPlayerGameImportResult(
        season=resolved_season,
        roster_label=label,
        team_filter=team_filter,
        apply_result=apply_result,
    )


def missing_generated_players_and_active_placeholder_indices(
    model: Any,
    generated_players: Iterable[Any],
    *,
    placeholder_name: str = "A Z",
) -> tuple[tuple[Any, ...], tuple[int, ...], int]:
    generated_tuple = tuple(generated_players)
    active_name_keys = _active_loaded_player_name_keys(model)
    active_profanity_name_keys = _active_loaded_player_profanity_name_keys(model)
    missing: list[Any] = []
    seen_missing_keys: set[str] = set()
    for generated in generated_tuple:
        generated_keys = _generated_player_name_keys(generated)
        if any(key in active_name_keys for key in generated_keys):
            continue
        profanity_keys = _generated_player_profanity_name_keys(generated)
        if profanity_keys and any(key in active_profanity_name_keys for key in profanity_keys):
            continue
        primary_key = generated_keys[0] if generated_keys else str(id(generated))
        if primary_key in seen_missing_keys:
            continue
        seen_missing_keys.add(primary_key)
        missing.append(generated)
    placeholder_indices = _active_placeholder_player_indices(model, placeholder_name)
    skipped_existing = len(generated_tuple) - len(missing)
    return tuple(missing), placeholder_indices, skipped_existing


def active_loaded_players_not_in_generated_source(
    model: Any,
    generated_players: Iterable[Any],
    *,
    placeholder_name: str = "A Z",
) -> tuple[tuple[int, str], ...]:
    generated_tuple = tuple(generated_players)
    source_name_keys = {
        key
        for generated in generated_tuple
        for key in _generated_player_name_keys(generated)
    }
    source_profanity_name_keys = {
        key
        for generated in generated_tuple
        for key in _generated_player_profanity_name_keys(generated)
    }
    placeholder_keys = set(_person_name_keys(placeholder_name))
    not_in_source: list[tuple[int, str]] = []
    for player in _loaded_items(model, "Players"):
        if not _player_is_active(model, player):
            continue
        name_values = _live_player_name_values(model, player)
        player_name_keys = {
            key
            for value in name_values
            for key in _person_name_keys(value)
        }
        if player_name_keys & placeholder_keys:
            continue
        if player_name_keys & source_name_keys:
            continue
        player_profanity_name_keys = {
            key
            for value in name_values
            for key in _profanity_fragment_value_keys(value)
        }
        if player_profanity_name_keys & source_profanity_name_keys:
            continue
        player_name = next(
            (
                cleaned
                for value in name_values
                if (cleaned := _strip_record_index_prefix(value).strip())
            ),
            _safe_label(player),
        )
        not_in_source.append((int(getattr(player, "index")), player_name))
    return tuple(not_in_source)


def apply_generated_players_to_game(
    model: Any,
    generated_players: Iterable[Any],
    *,
    player_indices: Iterable[int] | None = None,
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
    extra_rows: Iterable[Any] = (),
    include_sections: Iterable[str] | None = None,
    include_field_keys: Iterable[str] | None = None,
    stop_on_error: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> GamePortBatchResult:
    generated_tuple = tuple(generated_players)
    if player_indices is None:
        raise ValueError("team imports require player indices from an approved cemented roster plan")
    index_tuple = tuple(int(index) for index in player_indices)
    if len(index_tuple) != len(generated_tuple):
        raise ValueError("generated player count and approved target-player count differ")
    target_count = len(index_tuple)
    player_results: list[GamePortResult] = []
    extra_row_tuple = tuple(extra_rows)
    allowed_sections = frozenset(str(section) for section in include_sections) if include_sections is not None else None
    allowed_field_keys = frozenset(str(field_key) for field_key in include_field_keys) if include_field_keys is not None else None
    total_players = len(generated_tuple)
    if progress_callback is not None:
        progress_callback(0, total_players, f"Preparing to import {total_players} generated players")
    for imported_count, (generated, player_index) in enumerate(zip(generated_tuple, index_tuple), start=1):
        player_results.append(
            apply_generated_rows_to_game(
                model,
                (*tuple(_generated_rows_for_import(generated, allowed_sections, allowed_field_keys)), *extra_row_tuple),
                player_index=player_index,
                field_index=field_index,
                offsets_path=offsets_path,
                stop_on_error=stop_on_error,
            )
        )
        if progress_callback is not None:
            progress_callback(imported_count, total_players, f"Imported {imported_count}/{total_players} generated players")
    return GamePortBatchResult(
        player_results=tuple(player_results),
        generated_count=len(generated_tuple),
        target_count=target_count,
    )


def _generated_player_name_matches(model: Any, generated_players: Iterable[Any]) -> tuple[tuple[Any, int], ...]:
    players_by_name = _loaded_players_by_name_key(model)
    active_by_index: dict[int, bool] = {}
    used_indices: set[int] = set()
    matches: list[tuple[Any, int]] = []
    for generated in generated_players:
        try:
            keys = _generated_player_name_keys(generated)
        except Exception:
            continue
        player_index = _matched_name_player_index(model, players_by_name, keys, used_indices, active_by_index)
        if player_index is None:
            continue
        matches.append((generated, player_index))
        used_indices.add(player_index)
    return tuple(matches)


def _matched_name_player_index(
    model: Any,
    players_by_name: dict[str, tuple[Any, ...]],
    keys: Iterable[str],
    used_indices: set[int],
    active_by_index: dict[int, bool],
) -> int | None:
    # A roster can carry two records for one person: the one on a team and an
    # inactive leftover duplicate. Name keys match both, and taking whichever the
    # scan reached first writes the generated ratings onto the duplicate, so the
    # player in the game never changes. Read ISACTIVE and take the first active
    # record across every name key, falling back to the first record found when
    # the roster has no active one to write to.
    fallback: int | None = None
    seen: set[int] = set()
    for key in keys:
        for player in players_by_name.get(key, ()):
            try:
                player_index = int(getattr(player, "index"))
            except Exception:
                continue
            if player_index in used_indices or player_index in seen:
                continue
            seen.add(player_index)
            if fallback is None:
                fallback = player_index
            if player_index not in active_by_index:
                active_by_index[player_index] = _player_is_active(model, player)
            if active_by_index[player_index]:
                return player_index
    return fallback


_FIRST_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "ALEX": ("ALEXANDER", "ALEXANDRE"),
    "ALEXANDER": ("ALEX", "ALEXANDRE"),
    "ALEXANDRE": ("ALEX", "ALEXANDER"),
    "BUB": ("CARLTON",),
    "CARLTON": ("BUB",),
    "BONES": ("NAH", "NAHSHON"),
    "CAM": ("CAMERON",),
    "CAMERON": ("CAM",),
    "MO": ("MOHAMED", "MOUHAMED"),
    "MOHAMED": ("MO", "MOUHAMED"),
    "MOUHAMED": ("MO", "MOHAMED"),
    "NIC": ("NICK", "NICOLAS", "NICHOLAS"),
    "NICK": ("NIC", "NICOLAS", "NICHOLAS"),
    "NICOLAS": ("NIC", "NICK", "NICHOLAS"),
    "NICHOLAS": ("NIC", "NICK", "NICOLAS"),
    "ROB": ("ROBERT",),
    "ROBERT": ("ROB",),
    "SVI": ("SVIATOSLAV",),
    "SVIATOSLAV": ("SVI",),
}

_NAME_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}
_PROFANITY_MATCH_FRAGMENTS = ("CON", "FUC")


def _loaded_players_by_name_key(model: Any) -> dict[str, tuple[Any, ...]]:
    raw: dict[str, list[Any]] = {}
    loaded = getattr(model, "loaded_items", {})
    players = loaded.get("Players", {}) if isinstance(loaded, dict) else {}
    if isinstance(players, dict):
        iterable = ((_safe_label(item), item) for item in players.values())
    elif isinstance(players, (list, tuple)):
        iterable = ((_safe_label(item), item) for item in players)
    else:
        iterable = ()
    for label, item in iterable:
        for value in (*_loaded_player_name_values(label, item), *_live_player_name_values(model, item)):
            try:
                keys = _person_name_keys(value)
            except Exception:
                keys = ()
            for key in keys:
                raw.setdefault(key, []).append(item)
    return {key: _unique_items_by_index(items) for key, items in raw.items()}


def _active_loaded_player_name_keys(model: Any) -> set[str]:
    keys: set[str] = set()
    for player in _loaded_items(model, "Players"):
        if not _player_is_active(model, player):
            continue
        for value in _live_player_name_values(model, player):
            keys.update(_person_name_keys(value))
    return keys


def _active_loaded_player_profanity_name_keys(model: Any) -> set[str]:
    keys: set[str] = set()
    for player in _loaded_items(model, "Players"):
        if not _player_is_active(model, player):
            continue
        for value in _live_player_name_values(model, player):
            keys.update(_profanity_fragment_value_keys(value))
    return keys


def _active_placeholder_player_indices(model: Any, placeholder_name: str) -> tuple[int, ...]:
    placeholder_keys = set(_person_name_keys(placeholder_name))
    indices: list[int] = []
    for player in _loaded_items(model, "Players"):
        if not _player_is_active(model, player):
            continue
        player_keys: set[str] = set()
        for value in _live_player_name_values(model, player):
            player_keys.update(_person_name_keys(value))
        if player_keys & placeholder_keys:
            indices.append(int(getattr(player, "index")))
    return tuple(indices)


def _player_is_active(model: Any, player: Any) -> bool:
    active_reader = getattr(model, "_read_player_is_active", None)
    if callable(active_reader):
        try:
            return bool(active_reader(player))
        except Exception:
            return False
    raw_reader = getattr(model, "_read_named_raw_int", None)
    if callable(raw_reader):
        try:
            value = raw_reader("Players", player, "ISACTIVE")
            return bool(int(str(value or 0)))
        except Exception:
            return False
    return bool(getattr(player, "active", False))



def _live_player_name_values(model: Any, player: Any) -> tuple[object, ...]:
    reader = getattr(model, "_read_named_value", None)
    if callable(reader):
        try:
            first = reader("Players", player, ("FIRSTNAME", "FIRST NAME"))
            last = reader("Players", player, ("LASTNAME", "LAST NAME"))
            full_name = f"{first} {last}".strip()
            if full_name and full_name != "-- --":
                return (full_name,)
        except Exception:
            pass
    return _loaded_player_name_values(_safe_label(player), player)


def _unique_items_by_index(items: Iterable[Any]) -> tuple[Any, ...]:
    unique: list[Any] = []
    seen: set[int] = set()
    for item in items:
        try:
            index = int(item.index)
        except Exception:
            index = id(item)
        if index in seen:
            continue
        seen.add(index)
        unique.append(item)
    return tuple(unique)


def _loaded_player_name_values(label: object, item: Any) -> tuple[object, ...]:
    return (
        _strip_record_index_prefix(label),
        _safe_getattr(item, "label"),
        _strip_record_index_prefix(_safe_getattr(item, "display_label")),
    )


def _safe_label(item: Any) -> str:
    return _strip_record_index_prefix(_safe_getattr(item, "display_label") or _safe_getattr(item, "label"))


def _safe_getattr(item: Any, name: str) -> object:
    try:
        return getattr(item, name, "")
    except Exception:
        return ""


def _generated_player_name_keys(generated: Any) -> tuple[str, ...]:
    values: list[object] = list(_generated_player_name_values(generated))
    return _person_name_keys(*values)


def _generated_player_profanity_name_keys(generated: Any) -> tuple[str, ...]:
    keys: list[str] = []
    for value in _generated_player_name_values(generated):
        keys.extend(_profanity_fragment_value_keys(value))
    return tuple(dict.fromkeys(key for key in keys if key))


def _generated_player_name_values(generated: Any) -> tuple[object, ...]:
    identity = _safe_getattr(generated, "identity")
    identity = identity if isinstance(identity, dict) else {}
    values: list[object] = [identity.get("player"), _safe_getattr(generated, "player_id")]
    by_field = _safe_getattr(generated, "by_field_key")
    if callable(by_field):
        try:
            fields = by_field()
        except Exception:
            fields = {}
        if isinstance(fields, dict):
            first = fields.get("Vitals/FIRSTNAME")
            last = fields.get("Vitals/LASTNAME")
            if first is not None or last is not None:
                values.append(f"{_safe_getattr(first, 'display_value')} {_safe_getattr(last, 'display_value')}")
    return tuple(values)


def _person_name_keys(*values: object) -> tuple[str, ...]:
    keys: list[str] = []
    for value in values:
        exact = _identity(value)
        if exact:
            keys.append(exact)
        tokens = _name_tokens(value)
        if not tokens:
            continue
        without_suffix = tuple(token for token in tokens if token not in _NAME_SUFFIXES)
        if without_suffix and without_suffix != tokens:
            keys.append("".join(without_suffix))
        keys.extend(_profanity_fragment_name_keys(without_suffix))
        if len(without_suffix) >= 2:
            first = without_suffix[0]
            last = without_suffix[-1]
            keys.append(first + last)
            for alias in _FIRST_NAME_ALIASES.get(first, ()):
                keys.append(alias + last)
    return tuple(dict.fromkeys(key for key in keys if key))


def _profanity_fragment_value_keys(value: object) -> tuple[str, ...]:
    tokens = tuple(token for token in _name_tokens(value) if token not in _NAME_SUFFIXES)
    return _profanity_fragment_name_keys(tokens)


def _profanity_fragment_name_keys(tokens: tuple[str, ...]) -> tuple[str, ...]:
    if len(tokens) < 2:
        return ()
    joined = "".join(tokens)
    if not _has_profanity_fragment(joined):
        return ()
    keys: list[str] = []
    first = tokens[0]
    tail = "".join(tokens[1:])
    for first_value in (first, *_FIRST_NAME_ALIASES.get(first, ())):
        for tail_key in _profanity_fragment_tail_keys(tail):
            keys.append(first_value + tail_key)
    keys.extend(_profanity_fragment_tail_keys(joined))
    return tuple(dict.fromkeys(key for key in keys if key))


def _profanity_fragment_tail_keys(value: str) -> tuple[str, ...]:
    variants: set[str] = {value}
    for fragment in _PROFANITY_MATCH_FRAGMENTS:
        if fragment not in value:
            continue
        stripped = value.replace(fragment, "")
        if stripped:
            variants.update((stripped, _without_vowels(stripped)))
            singular = stripped[:-1] if stripped.endswith("S") else stripped
            variants.update((singular, _without_vowels(singular)))
    return tuple(sorted(key for key in variants if key))


def _has_profanity_fragment(value: str) -> bool:
    return any(fragment in value for fragment in _PROFANITY_MATCH_FRAGMENTS)


def _without_vowels(value: str) -> str:
    return re.sub(r"[AEIOU]+", "", value)


def _name_tokens(value: object) -> tuple[str, ...]:
    text = _ascii_name_text(value).upper()
    return tuple(token for token in re.split(r"[^A-Z0-9]+", text) if token)


def _strip_record_index_prefix(value: object) -> str:
    return re.sub(r"^\s*\[\d+\]\s*", "", str(value or "")).strip()


def validate_generated_player_names_match_offsets(
    generated_players: Iterable[Any],
    *,
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
) -> None:
    authored = field_index if field_index is not None else authored_player_field_index(offsets_path)
    errors: list[str] = []
    for generated in generated_players:
        identity = getattr(generated, "identity", None)
        player_label = str(identity.get("player") if isinstance(identity, dict) else getattr(generated, "player_id", "")).strip()
        for row in _generated_rows(generated):
            field_key = str(getattr(row, "field_key", "")).strip()
            entry = authored.get(field_key)
            if entry is None:
                errors.append(f"{player_label}: generated field {field_key or '<empty>'} is not in offsets_players.json")
                continue
            row_section = str(getattr(row, "section", entry.section))
            row_group = str(getattr(row, "group", entry.group))
            row_name = str(getattr(row, "normalized_name", entry.normalized_name))
            if row_section != entry.section or row_group != entry.group or row_name != entry.normalized_name:
                errors.append(
                    f"{player_label}: {field_key} metadata does not match offsets "
                    f"({row_section}/{row_group}/{row_name} != {entry.section}/{entry.group}/{entry.normalized_name})"
                )
    if errors:
        raise KeyError("; ".join(errors))


_BASE_TEAM_COUNT = 30


def plan_generated_team_rosters(generated_players: Iterable[Any]) -> GeneratedPlayerTeamRosterPlan:
    generated_tuple = tuple(generated_players)
    seasons = {
        int(season)
        for generated in generated_tuple
        if (season := getattr(generated, "season", None)) is not None
    }
    if seasons == {1947}:
        return _plan_authored_1947_team_rosters(generated_tuple)

    entries: list[GeneratedPlayerTeamRosterEntry] = []
    issues: list[GeneratedPlayerTeamImportIssue] = []
    for generated in generated_tuple:
        identity = _generated_team_plan_identity(generated)
        if not identity.team_key:
            issues.append(
                GeneratedPlayerTeamImportIssue(
                    generated_player_label=_generated_player_label(generated),
                    generated_team_key="",
                    generated_team_label=identity.team_label,
                    reason=identity.exclude_reason or "generated player has no source team identity",
                    blocking=True,
                )
            )
            continue
        entries.append(
            GeneratedPlayerTeamRosterEntry(
                generated_player=generated,
                generated_player_label=_generated_player_label(generated),
                generated_team_key=identity.team_key,
                generated_team_label=identity.team_label,
                team_source=identity.team_source,
            )
        )
        if identity.exclude_reason:
            issues.append(
                GeneratedPlayerTeamImportIssue(
                    generated_player_label=_generated_player_label(generated),
                    generated_team_key=identity.team_key,
                    generated_team_label=identity.team_label,
                    reason=identity.exclude_reason,
                    blocking=identity.blocking,
                )
            )
    return GeneratedPlayerTeamRosterPlan(
        entries=tuple(entries),
        issues=tuple(issues),
        generated_count=len(generated_tuple),
        source_generated_count=len(generated_tuple),
        authored_count=len(generated_tuple),
        free_agent_count=0,
    )


def _plan_authored_1947_team_rosters(
    generated_players: tuple[Any, ...],
) -> GeneratedPlayerTeamRosterPlan:
    from opening_rosters_1947 import (
        AUTHORED_OPENING_ROSTER_BY_PLAYER_ID_1947,
        AUTHORED_OPENING_ROSTERS_1947,
    )

    entries: list[GeneratedPlayerTeamRosterEntry] = []
    for generated in generated_players:
        player_id = str(getattr(generated, "player_id", "") or "").strip()
        authored = AUTHORED_OPENING_ROSTER_BY_PLAYER_ID_1947.get(player_id)
        if authored is None:
            entries.append(
                GeneratedPlayerTeamRosterEntry(
                    generated_player=generated,
                    generated_player_label=_generated_player_label(generated),
                    generated_team_key="FREEAGENTS",
                    generated_team_label="Free Agents",
                    team_source="not on the authored 1946-47 opening-day team rosters",
                    destination_kind="free_agent",
                )
            )
            continue
        team, member = authored
        entries.append(
            GeneratedPlayerTeamRosterEntry(
                generated_player=generated,
                generated_player_label=member.name,
                generated_team_key=_identity(team.team_name),
                generated_team_label=team.team_name,
                team_source=(
                    f"authored 1946-47 opening roster "
                    f"({team.league} {team.confidence}; {member.status})"
                ),
            )
        )

    issues = tuple(
        GeneratedPlayerTeamImportIssue(
            generated_player_label=member.name,
            generated_team_key=_identity(team.team_name),
            generated_team_label=team.team_name,
            reason="authored opening-roster member has no PlayerGen source record",
            blocking=False,
        )
        for team in AUTHORED_OPENING_ROSTERS_1947
        for member in team.members
        if member.player_id is None
    )
    return GeneratedPlayerTeamRosterPlan(
        entries=tuple(entries),
        issues=issues,
        generated_count=len(entries),
        source_generated_count=len(generated_players),
        authored_count=sum(len(team.members) for team in AUTHORED_OPENING_ROSTERS_1947),
        free_agent_count=sum(entry.destination_kind == "free_agent" for entry in entries),
    )


def plan_generated_players_by_team(
    model: Any,
    generated_players: Iterable[Any],
    *,
    roster_plan: GeneratedPlayerTeamRosterPlan | None = None,
) -> GeneratedPlayerTeamImportPlan:
    generated_tuple = tuple(generated_players)
    if not generated_tuple:
        return GeneratedPlayerTeamImportPlan(assignments=(), issues=(), generated_count=0, target_count=0)
    if roster_plan is None:
        raise ValueError("live target planning requires an approved cemented roster plan")
    cemented = roster_plan
    if cemented.generated_count != len(generated_tuple):
        raise ValueError("cemented team roster no longer matches generated players")
    if tuple(id(player) for player in cemented.generated_players) != tuple(id(player) for player in generated_tuple):
        raise ValueError("cemented team roster no longer matches the displayed player order")
    if not cemented.ready:
        return GeneratedPlayerTeamImportPlan(
            assignments=(),
            issues=cemented.issues,
            generated_count=cemented.generated_count,
            target_count=0,
            source_generated_count=cemented.source_generated_count,
            authored_count=cemented.authored_count,
            free_agent_count=cemented.free_agent_count,
        )
    teams = _loaded_items(model, "Teams")
    players = _loaded_items(model, "Players")
    if not teams:
        raise ValueError("load Teams before planning generated players by team")
    if not players:
        raise ValueError("load Players before planning generated players by team")

    base_teams = tuple(teams[:_BASE_TEAM_COUNT])
    team_entries = tuple(entry for entry in cemented.entries if entry.destination_kind == "team")
    free_agent_entries = tuple(entry for entry in cemented.entries if entry.destination_kind == "free_agent")
    generated_team_order = tuple(dict.fromkeys(entry.generated_team_key for entry in team_entries))
    generated_profiles = {
        team_key: _GeneratedTeamMatchProfile(city_keys=(), name_keys=(), full_keys=(team_key,))
        for team_key in generated_team_order
    }
    team_by_generated_key = _assign_generated_profiles_to_live_teams(
        model,
        generated_team_order,
        base_teams,
        generated_profiles,
    )
    target_records_by_team_address = _team_target_records_by_address(model, base_teams)
    players_by_team: dict[str, list[Any]] = {key: [] for key in generated_team_order}
    team_labels: dict[str, str] = {}
    team_sources: dict[str, str] = {}
    authored_labels_by_object: dict[int, str] = {}
    for entry in team_entries:
        players_by_team[entry.generated_team_key].append(entry.generated_player)
        team_labels.setdefault(entry.generated_team_key, entry.generated_team_label)
        team_sources.setdefault(entry.generated_team_key, entry.team_source)
        authored_labels_by_object[id(entry.generated_player)] = entry.generated_player_label

    assignments: list[GeneratedPlayerTeamAssignment] = []
    issues: list[GeneratedPlayerTeamImportIssue] = list(cemented.issues)
    used_target_player_indices: set[int] = set()
    assigned_addresses = {int(team.address) for team in team_by_generated_key.values()}
    free_agent_targets = _free_agent_target_items(model) if free_agent_entries else ()
    target_count = (
        sum(len(target_records_by_team_address.get(address, ())) for address in assigned_addresses)
        + len(free_agent_targets)
    )

    for generated_key in generated_team_order:
        source_players = tuple(players_by_team.get(generated_key, ()))
        if not source_players:
            continue
        generated_team_label = team_labels.get(generated_key) or generated_key
        team_source = team_sources.get(generated_key, "generator source team")
        live_team = team_by_generated_key.get(generated_key)
        if live_team is None:
            for generated in source_players:
                issues.append(
                    GeneratedPlayerTeamImportIssue(
                        generated_player_label=authored_labels_by_object.get(id(generated), _generated_player_label(generated)),
                        generated_team_key=generated_key,
                        generated_team_label=generated_team_label,
                        reason=f"source team {generated_team_label or generated_key} did not match one live team",
                    )
                )
            continue

        live_team_address = int(live_team.address)
        target_records = target_records_by_team_address.get(live_team_address, ())
        for offset, generated in enumerate(source_players):
            if offset >= len(target_records):
                issues.append(
                    GeneratedPlayerTeamImportIssue(
                        generated_player_label=authored_labels_by_object.get(id(generated), _generated_player_label(generated)),
                        generated_team_key=generated_key,
                        generated_team_label=generated_team_label,
                        reason=f"live team {_safe_label(live_team)} has no remaining authored PLAYER slot",
                        blocking=False,
                    )
                )
                continue
            target_player, placement = target_records[offset]
            target_player_index = int(target_player.index)
            if target_player_index in used_target_player_indices:
                issues.append(
                    GeneratedPlayerTeamImportIssue(
                        generated_player_label=authored_labels_by_object.get(id(generated), _generated_player_label(generated)),
                        generated_team_key=generated_key,
                        generated_team_label=generated_team_label,
                        reason=f"live PLAYER slot reuses player index {target_player_index}",
                    )
                )
                continue
            used_target_player_indices.add(target_player_index)
            assignments.append(
                GeneratedPlayerTeamAssignment(
                    generated_player=generated,
                    generated_player_label=authored_labels_by_object.get(id(generated), _generated_player_label(generated)),
                    generated_team_key=generated_key,
                    generated_team_label=generated_team_label,
                    team_source=team_source,
                    live_team_index=int(live_team.index),
                    live_team_address=live_team_address,
                    live_team_label=_safe_label(live_team),
                    target_player_index=target_player_index,
                    target_player_label=_safe_label(target_player),
                    team_slot=int(placement["team_slot"]),
                )
            )

    for offset, entry in enumerate(free_agent_entries):
        if offset >= len(free_agent_targets):
            issues.append(
                GeneratedPlayerTeamImportIssue(
                    generated_player_label=entry.generated_player_label,
                    generated_team_key="FREEAGENTS",
                    generated_team_label="Free Agents",
                    reason="no remaining live Free Agent target record",
                    blocking=False,
                )
            )
            continue
        target_player = free_agent_targets[offset]
        target_player_index = int(target_player.index)
        if target_player_index in used_target_player_indices:
            issues.append(
                GeneratedPlayerTeamImportIssue(
                    generated_player_label=entry.generated_player_label,
                    generated_team_key="FREEAGENTS",
                    generated_team_label="Free Agents",
                    reason=f"Free Agent target reuses player index {target_player_index}",
                )
            )
            continue
        used_target_player_indices.add(target_player_index)
        assignments.append(
            GeneratedPlayerTeamAssignment(
                generated_player=entry.generated_player,
                generated_player_label=entry.generated_player_label,
                generated_team_key="FREEAGENTS",
                generated_team_label="Free Agents",
                team_source=entry.team_source,
                live_team_index=-1,
                live_team_address=0,
                live_team_label="Free Agents",
                target_player_index=target_player_index,
                target_player_label=_safe_label(target_player),
                team_slot=0,
                destination_kind="free_agent",
            )
        )

    return GeneratedPlayerTeamImportPlan(
        assignments=tuple(assignments),
        issues=tuple(issues),
        generated_count=len(generated_tuple),
        target_count=target_count,
        source_generated_count=cemented.source_generated_count,
        authored_count=cemented.authored_count,
        free_agent_count=cemented.free_agent_count,
    )


def _free_agent_target_items(model: Any) -> tuple[Any, ...]:
    prepare = getattr(model, "prepare_player_list_view", None)
    if not callable(prepare):
        raise ValueError("team import planning requires the model Free Agents filter")
    view = prepare("Free Agents")
    items = getattr(view, "items", ())
    if not isinstance(items, (list, tuple)):
        raise TypeError("model Free Agents filter returned a non-sequence")
    return tuple(items)


def _team_target_records_by_address(
    model: Any,
    teams: tuple[Any, ...],
) -> dict[int, tuple[tuple[Any, dict[str, Any]], ...]]:
    roster_reader = getattr(model, "player_roster_slot_items_for_team_items", None)
    if not callable(roster_reader):
        raise ValueError("team import planning requires the authored Team PLAYER-slot reader")
    grouped: dict[int, tuple[tuple[Any, dict[str, Any]], ...]] = {}
    for team in teams:
        raw_rows = roster_reader((team,))
        if not isinstance(raw_rows, (list, tuple)):
            raise TypeError("authored Team PLAYER-slot reader returned a non-sequence")
        rows = tuple(raw_rows)
        grouped[int(team.address)] = tuple(
            sorted(rows, key=lambda row: int(row[1]["team_slot"]))
        )
    return grouped



def _loaded_items(model: Any, domain: str) -> tuple[Any, ...]:
    loaded = getattr(model, "loaded_items", {})
    if isinstance(loaded, dict):
        domain_items = loaded.get(domain, {})
        if isinstance(domain_items, dict):
            return tuple(domain_items.values())
        if isinstance(domain_items, (list, tuple)):
            return tuple(domain_items)
    return ()


def _generated_team_order(generated_players: tuple[Any, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for generated in generated_players:
        key = _generated_team_key(generated)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


@dataclass(frozen=True)
class _TeamMatchProfile:
    team: Any
    address: int
    city_key: str
    name_key: str
    full_keys: tuple[str, ...]


def _team_match_profiles(model: Any, teams: tuple[Any, ...]) -> tuple[_TeamMatchProfile, ...]:
    profiles: list[_TeamMatchProfile] = []
    for team in teams:
        city = _read_team_value(model, team, ("CITYNAME", "CITY NAME"))
        name = _read_team_value(model, team, ("TEAMNAME", "TEAM NAME"))
        full_values = (
            getattr(team, "label", ""),
            getattr(team, "display_label", ""),
            f"{city} {name}",
        )
        profiles.append(
            _TeamMatchProfile(
                team=team,
                address=int(team.address),
                city_key=_identity(city),
                name_key=_identity(name),
                full_keys=tuple(dict.fromkeys(_identity(value) for value in full_values if _identity(value))),
            )
        )
    return tuple(profiles)


def _assign_generated_profiles_to_live_teams(
    model: Any,
    generated_team_order: tuple[str, ...],
    teams: tuple[Any, ...],
    generated_profiles: dict[str, _GeneratedTeamMatchProfile],
) -> dict[str, Any]:
    base_teams = tuple(teams[:_BASE_TEAM_COUNT])
    live_profiles = _team_match_profiles(model, base_teams)

    assigned: dict[str, Any] = {}
    used_addresses: set[int] = set()
    for generated_key in generated_team_order:
        generated_profile = generated_profiles.get(generated_key)
        if generated_profile is None:
            continue
        live_team = _match_live_team_by_city_then_name(generated_profile, live_profiles, used_addresses)
        if live_team is None:
            continue
        assigned[generated_key] = live_team
        used_addresses.add(int(live_team.address))
    return assigned


@dataclass(frozen=True)
class _GeneratedTeamMatchProfile:
    city_keys: tuple[str, ...]
    name_keys: tuple[str, ...]
    full_keys: tuple[str, ...]


@dataclass(frozen=True)
class _GeneratedTeamPlanIdentity:
    team_key: str
    team_label: str
    team_source: str
    profile: _GeneratedTeamMatchProfile | None
    exclude_reason: str | None = None
    blocking: bool = True


def _generated_team_plan_identity(generated: Any) -> _GeneratedTeamPlanIdentity:
    identity = getattr(generated, "identity", None)
    identity = identity if isinstance(identity, dict) else {}
    default_label = _generated_team_label(generated)
    default_key = _identity(default_label)
    default_profile = _generated_team_match_profile(generated)
    source_league = str(identity.get("source_league") or "").strip().upper()
    raw_source_leagues = identity.get("source_leagues")
    source_leagues = (
        tuple(str(league or "").strip().upper() for league in raw_source_leagues)
        if isinstance(raw_source_leagues, (list, tuple))
        else ()
    )
    if source_league == "NBL" or (source_leagues and set(source_leagues) == {"NBL"}):
        return _GeneratedTeamPlanIdentity(
            default_key,
            default_label,
            "generator source team (NBL; transaction files do not cover NBL)",
            default_profile,
        )

    from baa_nba_transactions import resolve_baa_nba_transaction_team

    resolution = resolve_baa_nba_transaction_team(
        season=int(getattr(generated, "season", 0) or 0),
        player_name=_generated_player_label(generated),
        source_league=source_league,
        source_leagues=source_leagues,
    )
    if not resolution.covered:
        return _GeneratedTeamPlanIdentity(default_key, default_label, "generator source team", default_profile)
    if resolution.ambiguous:
        return _GeneratedTeamPlanIdentity(
            default_key,
            default_label,
            "BAA/NBA transactions",
            default_profile,
            exclude_reason="BAA/NBA transaction player name is ambiguous",
        )
    if not resolution.matched:
        return _GeneratedTeamPlanIdentity(
            default_key,
            default_label,
            "generator source team (no exact BAA/NBA transaction match)",
            default_profile,
        )
    event = resolution.event
    event_label = (
        f"{event.event_type} {event.event_date.isoformat()}"
        if event is not None
        else "final transaction"
    )
    team_label = str(resolution.team_name or "").strip()
    team_key = _identity(team_label)
    return _GeneratedTeamPlanIdentity(
        team_key,
        team_label,
        f"BAA/NBA transactions: {event_label}",
        _GeneratedTeamMatchProfile(city_keys=(), name_keys=(), full_keys=(team_key,)),
    )


def _generated_team_match_profile(generated: Any) -> _GeneratedTeamMatchProfile:
    identity = getattr(generated, "identity", None)
    identity = identity if isinstance(identity, dict) else {}
    city_values = _generated_values(generated, identity, ("team_city", "city", "city_name"))
    name_values = _generated_values(generated, identity, ("team_name_only", "name", "franchise_name"))
    full_values = _generated_values(generated, identity, ("team_name", "team_full_name", "franchise", "team", "team_abbrev", "roster_team"))
    full_values += tuple(getattr(generated, attr, "") for attr in ("team", "team_abbrev", "roster_team", "team_name"))
    return _GeneratedTeamMatchProfile(
        city_keys=_identity_tuple(city_values),
        name_keys=_identity_tuple(name_values),
        full_keys=_identity_tuple(full_values),
    )


def _generated_values(generated: Any, identity: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, ...]:
    values: list[Any] = []
    for key in keys:
        value = identity.get(key)
        if value not in (None, ""):
            values.append(value)
    for key in keys:
        value = getattr(generated, key, None)
        if value not in (None, ""):
            values.append(value)
    return tuple(values)


def _identity_tuple(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(key for value in values if (key := _identity(value))))


def _match_live_team_by_city_then_name(
    generated: _GeneratedTeamMatchProfile,
    live_profiles: tuple[_TeamMatchProfile, ...],
    used_addresses: set[int],
) -> Any | None:
    available = tuple(profile for profile in live_profiles if profile.address not in used_addresses)
    city_matches = tuple(profile for profile in available if _generated_matches_live_city(generated, profile))
    if city_matches:
        name_matches = tuple(profile for profile in city_matches if _generated_matches_live_name(generated, profile))
        if name_matches:
            return name_matches[0].team

    name_matches = tuple(profile for profile in available if _generated_matches_live_name(generated, profile))
    if name_matches:
        return name_matches[0].team
    return None


def _generated_matches_live_city(generated: _GeneratedTeamMatchProfile, live: _TeamMatchProfile) -> bool:
    if not live.city_key:
        return False
    if live.city_key in generated.city_keys:
        return True
    return any(full_key.startswith(live.city_key) for full_key in generated.full_keys)


def _generated_matches_live_name(generated: _GeneratedTeamMatchProfile, live: _TeamMatchProfile) -> bool:
    if not live.name_key:
        return False
    if live.name_key in generated.name_keys:
        return True
    return any(full_key.endswith(live.name_key) or full_key in live.full_keys for full_key in generated.full_keys)


def _read_team_value(model: Any, team: Any, field_names: tuple[str, ...]) -> str:
    reader = getattr(model, "_read_named_value", None)
    if callable(reader):
        try:
            return str(reader("Teams", team, field_names))
        except Exception:
            return ""
    values = getattr(team, "values", None)
    if isinstance(values, dict):
        for name in field_names:
            value = values.get(name) or values.get(_identity(name))
            if value not in (None, ""):
                return str(value)
    return ""


def _generated_team_key(generated: Any) -> str:
    for attr in ("team", "team_abbrev", "roster_team"):
        value = getattr(generated, attr, None)
        key = _identity(value)
        if key:
            return key
    identity = getattr(generated, "identity", None)
    if isinstance(identity, dict):
        for key_name in ("team", "team_abbrev", "roster_team"):
            key = _identity(identity.get(key_name))
            if key:
                return key
    return ""


def _generated_team_label(generated: Any) -> str:
    identity = getattr(generated, "identity", None)
    identity = identity if isinstance(identity, dict) else {}
    for value in (
        identity.get("team_name"),
        getattr(generated, "team_name", None),
        getattr(generated, "team", None),
        identity.get("team"),
        getattr(generated, "roster_team", None),
        identity.get("roster_team"),
        getattr(generated, "team_abbrev", None),
        identity.get("team_abbrev"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return _generated_team_key(generated)


def _generated_player_label(generated: Any) -> str:
    for value in _generated_player_name_values(generated):
        text = _strip_record_index_prefix(value).strip()
        if text:
            return text
    return str(getattr(generated, "player_id", "")).strip()


def _identity(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", _ascii_name_text(value).upper())


def _ascii_name_text(value: object) -> str:
    text = str(value or "")
    # Some historic/current source rows contain UTF-8 names decoded as Windows
    # text (DonÄ\x8diÄ‡, BogdanoviÄ‡, DiabatÃ©). Repair the common cases before
    # stripping accents so generated names can match NBA 2K's plain-ASCII names.
    for bad, good in (
        ("\u00c4\u008d", "č"),
        ("\u00c4\u008c", "Č"),
        ("\u00c4i\u00c5\u00ab", "čiū"),
        ("\u00c5\u00ab", "ū"),
        ("\u00c4\u2021", "ć"),
        ("\u00c4\u2020", "Ć"),
        ("\u00c3\u00a9", "é"),
    ):
        text = text.replace(bad, good)
    text = text.replace("ё", "e").replace("Ё", "E")
    try:
        text = text.encode("cp1252").decode("utf-8")
    except Exception:
        pass
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _model_player_field_index(model: Any) -> dict[str, FieldEntry]:
    return {
        f"{entry.section}/{entry.normalized_name}": entry
        for groups in model.grouped_fields("Players").values()
        for entries in groups.values()
        for entry in entries
    }


def apply_generated_rows_to_game(
    model: Any,
    rows: Iterable[Any],
    *,
    player_index: int,
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
    stop_on_error: bool = False,
) -> GamePortResult:
    if player_index < 0:
        raise ValueError("player_index must be >= 0")
    authored = _model_player_field_index(model)
    results: list[GamePortFieldResult] = []
    for row in _ordered_generated_rows_for_game_write(rows):
        field_key = str(getattr(row, "field_key", "")).strip()
        attempted_value: int | str | None = None
        try:
            attempted_value = _row_value(row)
            entry = authored[field_key]
            readback = model.write_entry_value(entry, index=player_index, value=attempted_value)
            readback_value = readback.get("display_value") if isinstance(readback, dict) else readback
            results.append(
                GamePortFieldResult(
                    field_key=field_key,
                    section=entry.section,
                    group=entry.group,
                    normalized_name=entry.normalized_name,
                    display_name=entry.display_name,
                    attempted_value=attempted_value,
                    readback_value=readback_value,
                    ok=True,
                )
            )
        except Exception as exc:
            results.append(
                GamePortFieldResult(
                    field_key=field_key,
                    section=str(getattr(row, "section", "")),
                    group=str(getattr(row, "group", "")),
                    normalized_name=str(getattr(row, "normalized_name", _field_key_name(field_key))),
                    display_name=str(getattr(row, "field", field_key)),
                    attempted_value=attempted_value,
                    readback_value=None,
                    ok=False,
                    error=str(exc),
                )
            )
            if stop_on_error:
                break
    succeeded = sum(1 for result in results if result.ok)
    failed = len(results) - succeeded
    return GamePortResult(
        player_index=player_index,
        attempted=len(results),
        succeeded=succeeded,
        failed=failed,
        fields=tuple(results),
    )


def _ordered_generated_rows_for_game_write(rows: Iterable[Any]) -> tuple[Any, ...]:
    materialized = tuple(rows)
    return tuple(sorted(materialized, key=_game_write_order_key))


def _game_write_order_key(row: Any) -> tuple[int, str]:
    field_key = str(getattr(row, "field_key", "")).strip()
    # Main editor writes a single selected field. Generated import writes a packed
    # field batch; write Contest Shot after the surrounding defense tendency
    # package so the game-side visible T/CONTEST cell is the final write.
    if field_key == "Tendencies/CONTESTSHOT":
        return (1, field_key)
    return (0, field_key)


def _row_value(row: Any) -> int | str:
    if hasattr(row, "display_value"):
        return getattr(row, "display_value")
    if hasattr(row, "value"):
        return getattr(row, "value")
    raise AttributeError("generated row is missing display_value/value")


def _generated_rows_for_import(
    generated: Any,
    allowed_sections: frozenset[str] | None,
    allowed_field_keys: frozenset[str] | None = None,
) -> Iterable[Any]:
    for row in _generated_rows(generated):
        if allowed_sections is None and allowed_field_keys is None:
            yield row
            continue
        field_key = str(getattr(row, "field_key", ""))
        if allowed_field_keys is not None and field_key in allowed_field_keys:
            yield row
            continue
        section = str(getattr(row, "section", ""))
        if not section:
            section = field_key.split("/", 1)[0]
        if allowed_sections is not None and section in allowed_sections:
            yield row


def _generated_rows(generated: Any) -> Iterable[Any]:
    if hasattr(generated, "field_candidates"):
        return getattr(generated, "field_candidates")
    if hasattr(generated, "rows"):
        return getattr(generated, "rows")
    raise AttributeError("generated player is missing field_candidates/rows")


def _field_key_name(field_key: str) -> str:
    return field_key.split("/", 1)[-1] if "/" in field_key else field_key


__all__ = [
    "GamePortBatchResult",
    "GamePortFieldResult",
    "GamePortResult",
    "GeneratedPlayerGameImportResult",
    "active_loaded_players_not_in_generated_source",
    "apply_generated_players_to_game",
    "apply_generated_rows_to_game",
    "import_generated_players_to_game",
    "missing_generated_players_and_active_placeholder_indices",
    "validate_generated_player_names_match_offsets",
]







