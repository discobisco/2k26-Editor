from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from nba2k_editor.models.schema import FieldEntry
from contracts import GeneratorInputContract, OutputTarget
from player_generator import (
    GeneratedPlayerProposal,
    authored_player_field_index,
    generate_player_proposals_from_index,
    season_context_index,
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


def import_generated_players_to_game(
    model: Any,
    contract: GeneratorInputContract,
    *,
    generated_players: Iterable[Any] | None = None,
    team_filter: str | None = None,
    player_indices: Iterable[int] | None = None,
    match_existing_player_names: bool = False,
    offsets_path: str | Path | None = None,
    stop_on_error: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> GeneratedPlayerGameImportResult:
    validated = contract.validate()
    if validated.output_target is not OutputTarget.OVERWRITE_CURRENT_ROSTER:
        raise ValueError("import to game requires overwrite_current_roster output target")

    if generated_players is None:
        context = season_context_index(validated, offsets_path=offsets_path)
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
        stop_on_error=stop_on_error,
        progress_callback=progress_callback,
    )
    return GeneratedPlayerGameImportResult(
        season=int(validated.season),
        roster_label=str(validated.roster_label or ""),
        team_filter=team_filter,
        apply_result=apply_result,
    )


def apply_generated_player_proposal_to_game(
    model: Any,
    proposal: GeneratedPlayerProposal,
    *,
    player_index: int,
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
    stop_on_error: bool = False,
) -> GamePortResult:
    return apply_generated_rows_to_game(
        model,
        proposal.field_candidates,
        player_index=player_index,
        field_index=field_index,
        offsets_path=offsets_path,
        stop_on_error=stop_on_error,
    )


def apply_generated_players_to_game(
    model: Any,
    generated_players: Iterable[Any],
    *,
    player_indices: Iterable[int] | None = None,
    field_index: dict[str, FieldEntry] | None = None,
    offsets_path: str | Path | None = None,
    extra_rows: Iterable[Any] = (),
    include_sections: Iterable[str] | None = None,
    stop_on_error: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> GamePortBatchResult:
    generated_tuple = tuple(generated_players)
    if player_indices is None:
        index_tuple, target_count = _player_team_slot_indices_for_generated(model, generated_tuple)
    else:
        index_tuple = tuple(int(index) for index in player_indices)
        target_count = len(index_tuple)
    player_results: list[GamePortResult] = []
    extra_row_tuple = tuple(extra_rows)
    allowed_sections = frozenset(str(section) for section in include_sections) if include_sections is not None else None
    total_players = len(generated_tuple)
    if progress_callback is not None:
        progress_callback(0, total_players, f"Preparing to import {total_players} generated players")
    for imported_count, (generated, player_index) in enumerate(zip(generated_tuple, index_tuple), start=1):
        player_results.append(
            apply_generated_rows_to_game(
                model,
                (*tuple(_generated_rows_for_import(generated, allowed_sections)), *extra_row_tuple),
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


def player_team_slot_indices_for_generated(model: Any, generated_players: Iterable[Any]) -> tuple[int, ...]:
    indices, _target_count = _player_team_slot_indices_for_generated(model, tuple(generated_players))
    return indices


def _player_indices_by_generated_names(model: Any, generated_players: Iterable[Any]) -> tuple[int, ...]:
    return tuple(index for _generated, index in _generated_player_name_matches(model, generated_players))


def _generated_player_name_matches(model: Any, generated_players: Iterable[Any]) -> tuple[tuple[Any, int], ...]:
    players_by_name = _loaded_players_by_name_key(model)
    used_indices: set[int] = set()
    matches: list[tuple[Any, int]] = []
    for generated in generated_players:
        try:
            keys = _generated_player_name_keys(generated)
        except Exception:
            continue
        for key in keys:
            for player in players_by_name.get(key, ()):
                try:
                    player_index = int(getattr(player, "index"))
                except Exception:
                    continue
                if player_index in used_indices:
                    continue
                matches.append((generated, player_index))
                used_indices.add(player_index)
                break
            else:
                continue
            break
    return tuple(matches)


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


def _loaded_players_by_name_key(model: Any) -> dict[str, tuple[Any, ...]]:
    raw: dict[str, list[Any]] = {}
    loaded = getattr(model, "loaded_items", {})
    players = loaded.get("Players", {}) if isinstance(loaded, dict) else {}
    if isinstance(players, dict):
        iterable = players.items()
    elif isinstance(players, (list, tuple)):
        iterable = ((_safe_label(item), item) for item in players)
    else:
        iterable = ()
    for label, item in iterable:
        for value in _loaded_player_name_values(label, item):
            try:
                keys = _person_name_keys(value)
            except Exception:
                keys = ()
            for key in keys:
                raw.setdefault(key, []).append(item)
    return {key: _unique_items_by_index(items) for key, items in raw.items()}


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
    return _person_name_keys(*values)


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
        if len(without_suffix) >= 2:
            first = without_suffix[0]
            last = without_suffix[-1]
            keys.append(first + last)
            for alias in _FIRST_NAME_ALIASES.get(first, ()):
                keys.append(alias + last)
    return tuple(dict.fromkeys(key for key in keys if key))


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
_TEAM_SLOT_LIMIT = 15


def _player_team_slot_indices_for_generated(model: Any, generated_players: tuple[Any, ...]) -> tuple[tuple[int, ...], int]:
    if not generated_players:
        return (), 0
    teams = _loaded_items(model, "Teams")
    players = _loaded_items(model, "Players")
    if not teams:
        raise ValueError("load Teams before applying generated players by team slots")
    if not players:
        raise ValueError("load Players before applying generated players by team slots")

    generated_team_order = _generated_team_order(generated_players)
    team_by_generated_key = _assign_generated_teams_to_live_teams(model, generated_team_order, teams, generated_players)
    player_indices_by_team_address = _player_indices_by_team_address(model, players)

    assigned_addresses = {int(team.address) for team in team_by_generated_key.values()}
    target_count = sum(min(len(player_indices_by_team_address.get(address, ())), _TEAM_SLOT_LIMIT) for address in assigned_addresses)
    used_offsets: dict[int, int] = {}
    used_player_indices: set[int] = set()
    indices: list[int] = []

    def take_slot(address: int, *, assigned: bool) -> int | None:
        team_player_indices = player_indices_by_team_address.get(address, ())
        limit = min(len(team_player_indices), _TEAM_SLOT_LIMIT) if assigned else len(team_player_indices)
        offset = used_offsets.get(address, 0)
        while offset < limit and team_player_indices[offset] in used_player_indices:
            offset += 1
        used_offsets[address] = offset
        if offset >= limit:
            return None
        player_index = team_player_indices[offset]
        used_offsets[address] = offset + 1
        used_player_indices.add(player_index)
        return player_index

    def take_spill_slot() -> int | None:
        for team in teams:
            address = int(team.address)
            if address in assigned_addresses:
                continue
            player_index = take_slot(address, assigned=False)
            if player_index is not None:
                return player_index
        return None

    for generated in generated_players:
        generated_key = _generated_team_key(generated)
        live_team = team_by_generated_key.get(generated_key)
        player_index: int | None = None

        for alternate_key in _generated_alternate_team_keys(generated):
            alternate_team = team_by_generated_key.get(alternate_key)
            if alternate_team is None:
                continue
            alternate_address = int(alternate_team.address)
            if alternate_address == int(getattr(live_team, "address", -1)):
                continue
            player_index = take_slot(alternate_address, assigned=True)
            if player_index is not None:
                break

        if player_index is None and live_team is not None:
            player_index = take_slot(int(live_team.address), assigned=True)
        if player_index is None:
            player_index = take_spill_slot()
        if player_index is not None:
            indices.append(player_index)
    return tuple(indices), target_count



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


def _assign_generated_teams_to_live_teams(model: Any, generated_team_order: tuple[str, ...], teams: tuple[Any, ...], generated_players: tuple[Any, ...]) -> dict[str, Any]:
    base_teams = tuple(teams[:_BASE_TEAM_COUNT])
    live_profiles = _team_match_profiles(model, base_teams)
    generated_profiles = _generated_team_profiles(generated_players)

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


def _generated_team_profiles(generated_players: tuple[Any, ...]) -> dict[str, _GeneratedTeamMatchProfile]:
    profiles: dict[str, _GeneratedTeamMatchProfile] = {}
    for generated in generated_players:
        generated_key = _generated_team_key(generated)
        if generated_key in profiles:
            continue
        profiles[generated_key] = _generated_team_match_profile(generated)
    return profiles


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
        if len(city_matches) == 1:
            return city_matches[0].team

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


def _live_team_keys(model: Any, team: Any) -> set[str]:
    values: set[str] = set()
    for value in (getattr(team, "label", ""), getattr(team, "display_label", "")):
        _add_team_key(values, value)
    for field_names in (
        ("CITYABBREV", "CITY ABBREV", "ABBREVIATION"),
        ("TEAMNAME", "TEAM NAME"),
        ("CITYNAME", "CITY NAME"),
    ):
        _add_team_key(values, _read_team_value(model, team, field_names))
    city = _read_team_value(model, team, ("CITYNAME", "CITY NAME"))
    name = _read_team_value(model, team, ("TEAMNAME", "TEAM NAME"))
    _add_team_key(values, f"{city} {name}")
    return values


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


def _add_team_key(values: set[str], value: object) -> None:
    key = _identity(value)
    if key and key not in {"--", "NONE", "NULL"}:
        values.add(key)


def _player_indices_by_team_address(model: Any, players: tuple[Any, ...]) -> dict[int, tuple[int, ...]]:
    grouped: dict[int, list[int]] = {}
    for player in players:
        team_address = _player_current_team_address(model, player)
        if team_address is None:
            continue
        grouped.setdefault(team_address, []).append(int(player.index))
    return {address: tuple(indices) for address, indices in grouped.items()}


def _player_current_team_address(model: Any, player: Any) -> int | None:
    pointer_reader = getattr(model, "_player_current_team_pointer", None)
    if callable(pointer_reader):
        try:
            value = pointer_reader(player)
            return int(str(value)) if value is not None else None
        except Exception:
            return None
    team_address = getattr(player, "team_address", None)
    if team_address is not None:
        try:
            return int(str(team_address))
        except Exception:
            return None
    cache = getattr(model, "_player_team_pointer_cache", None)
    if isinstance(cache, dict):
        value = cache.get(getattr(player, "index", None))
        try:
            return int(str(value)) if value is not None else None
        except Exception:
            return None
    return None


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


def _generated_alternate_team_keys(generated: Any) -> tuple[str, ...]:
    primary = _generated_team_key(generated)
    identity = getattr(generated, "identity", None)
    shares = identity.get("multi_team_stat_shares") if isinstance(identity, dict) else None
    if not isinstance(shares, (list, tuple)):
        return ()
    keys: list[str] = []
    for share in shares:
        if not isinstance(share, dict):
            continue
        key = _identity(share.get("team"))
        if key and key != primary and key not in keys:
            keys.append(key)
    return tuple(keys)


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


def _generated_rows_for_import(generated: Any, allowed_sections: frozenset[str] | None) -> Iterable[Any]:
    for row in _generated_rows(generated):
        if allowed_sections is None:
            yield row
            continue
        section = str(getattr(row, "section", ""))
        if not section:
            field_key = str(getattr(row, "field_key", ""))
            section = field_key.split("/", 1)[0]
        if section in allowed_sections:
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
    "apply_generated_player_proposal_to_game",
    "apply_generated_players_to_game",
    "apply_generated_rows_to_game",
    "import_generated_players_to_game",
    "player_team_slot_indices_for_generated",
    "validate_generated_player_names_match_offsets",
]







