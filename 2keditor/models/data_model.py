from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any, Iterable

from nba2k_editor.core import offsets as offsets_mod
from nba2k_editor.core.addressing import record_address, resolve_base_pointer_entry
from nba2k_editor.core.conversions import parse_id_prefixed_option
from nba2k_editor.core.field_io import (
    _ADDRESS_DROPDOWN_TYPES,
    _display_to_raw_value,
    _field_address,
    _id_prefixed_option,
    _implemented_payload,
    _raw_to_display_value,
    _read_authored_value,
    _type_key,
    _write_authored_value,
)
from nba2k_editor.memory.game_memory import GameMemory
from nba2k_editor.memory.read_buffer import ReadOnlyMemoryBuffer
from nba2k_editor.models.schema import (
    FieldEntry,
    RecordListItem,
    _field_identity,
    _is_player_season_id_selector_entry,
    _is_player_selected_stat_detail_entry,
    _iter_layout_fields,
    _player_season_id_identity_from_option,
    _player_season_id_option_label,
    _selected_record_source,
    _stat_role,
    _STAT_ROLE_SELECTOR,
)
from nba2k_editor.models.view_data import DomainRefreshView, PlayerListView

_DOMAIN_BASE_KEYS: dict[str, str] = {
    "Players": "Player",
    "Teams": "Team",
    "Staff": "Staff",
    "Stadiums": "Stadium",
    "Jerseys": "Jersey",
    "NBA History": "NBAHistory",
    "NBA Records": "Record",
    "Shoes": "Shoes",
}

EDITOR_DOMAINS: tuple[str, ...] = tuple(_DOMAIN_BASE_KEYS)
_MODEL_DOMAINS: tuple[str, ...] = EDITOR_DOMAINS

_SPARSE_SCAN_INVALID_STREAKS: dict[str, int] = {
    "NBA Records": 12,
    "Shoes": 256,
}

_LABEL_FIELD_NAMES: dict[str, tuple[str, ...]] = {
    "Players": ("FIRSTNAME", "LASTNAME"),
    "Teams": ("CITYNAME", "TEAMNAME"),
    "Staff": ("FIRSTNAME", "LASTNAME"),
    "Stadiums": ("ARENANAME", "CITYNAME"),
    "Jerseys": ("EDITIONNAME",),
    "Shoes": ("NAME",),
    "NBA History": ("TEAMCITY", "TEAMNAME", "FIRSTNAME", "LASTNAME", "DATA"),
    "NBA Records": ("FIRSTNAME", "LASTNAME", "DATA"),
}

PLAYER_TEAM_FILTER_ALL = "All Players"
PLAYER_TEAM_FILTER_BASE_TEAMS = "Teams 0-29"
PLAYER_TEAM_FILTER_FREE_AGENTS = "Free Agents"
PLAYER_TEAM_FILTER_DRAFT_CLASS = "Draft Class"
PLAYER_POSITION_FILTER_ALL = "All Positions"
PLAYER_PRIMARY_POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")
_DRAFT_CLASS_BASE_KEY = "DraftClass"
_PLAYER_EDITOR_RESET_SECTIONS: tuple[str, ...] = ("Vitals", "Attributes", "Tendencies", "Badges")



def _plausible_record_name_part(value: object) -> bool:
    text = str(value or "").strip()
    if len(text) < 2:
        return False
    return any(char.isalpha() for char in text) and all(char.isalpha() or char in " .'-" for char in text)


def _valid_record_list_label_part(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and any(char.isalpha() for char in text) and all(char.isalnum() or char in " .'-" for char in text)


def _valid_record_list_label_values(values: list[Any]) -> bool:
    parts = [value for value in values if str(value or "").strip()]
    return bool(parts) and all(_valid_record_list_label_part(value) for value in parts)


def _valid_nba_record_label_values(values: list[Any]) -> bool:
    if len(values) < 3:
        return False
    first_name, last_name, data_value = values[:3]
    if not (_plausible_record_name_part(first_name) and _plausible_record_name_part(last_name)):
        return False
    try:
        numeric_value = float(data_value)
    except Exception:
        return False
    return numeric_value == numeric_value and abs(numeric_value) <= 1_000_000


def _has_alpha_text(value: object) -> bool:
    return any(char.isalpha() for char in str(value or ""))


PLAYER_DETAIL_FIELD_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OVR", ("OVR", "OVERALL", "OVERALLRATING", "OVERALL RATING")),
    ("Team", ("CURRENTTEAM", "CURRENT TEAM")),
    ("Position", ("POSITION",)),
    ("Number", ("JERSEYNUM", "JERSEY NUMBER", "NUMBER")),
    ("Height", ("HEIGHT",)),
    ("Weight", ("WEIGHT",)),
    ("Face ID", ("FACEID", "FACE ID")),
    ("Unique ID", ("UNIQUEID", "UNIQUE ID", "PLAYERID")),
)

TEAM_SUMMARY_FIELD_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Team Name", ("TEAMNAME", "TEAM NAME")),
    ("City Name", ("CITYNAME", "CITY NAME")),
    ("City Abbrev", ("CITYABBREV", "CITY ABBREV", "ABBREVIATION")),
)

HISTORY_SUMMARY_FIELD_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Season", ("SEASON",)),
    ("Team Logo", ("TEAMLOGO", "TEAM LOGO")),
    ("Team City", ("TEAMCITY", "TEAM CITY", "WINNERTEAMCITY", "WINNER TEAM CITY")),
    ("Team Name", ("TEAMNAME", "TEAM NAME", "WINNERTEAMNAME", "WINNER TEAM NAME")),
    ("First Name", ("FIRSTNAME", "FIRST NAME")),
    ("Last Name", ("LASTNAME", "LAST NAME")),
    ("Data", ("DATA",)),
    ("Result", ("RESULT",)),
    ("Loser Team City", ("LOSERTEAMCITY", "LOSER TEAM CITY")),
    ("Loser Team Name", ("LOSERTEAMNAME", "LOSER TEAM NAME")),
)

RECORD_SUMMARY_FIELD_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Rank", ()),
    ("First Name", ("FIRSTNAME", "FIRST NAME")),
    ("Last Name", ("LASTNAME", "LAST NAME")),
    ("Signature ID", ("SIGNATUREID", "SIGNATURE ID")),
    ("Team Logo", ("TEAMLOGO", "TEAM LOGO")),
    ("Year", ("YEAR",)),
    ("Month", ("MONTH",)),
    ("Day", ("DAY",)),
    ("Data", ("DATA",)),
)


def target_display_label(executable: str | None) -> str:
    text = str(executable or "NBA2K26.exe")
    match = re.search(r"nba2k(\d{2})", text, flags=re.IGNORECASE)
    if not match:
        return "NBA 2K26"
    return f"NBA 2K{match.group(1)}"




def _json_safe_roster_value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return list(bytes(value))
    if isinstance(value, tuple):
        return [_json_safe_roster_value(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_roster_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_roster_value(item) for key, item in value.items()}
    return value


def _json_safe_dataset_value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return list(bytes(value))
    if isinstance(value, tuple):
        return [_json_safe_dataset_value(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_dataset_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_dataset_value(item) for key, item in value.items()}
    return value

class EditorDataModel:

    """Index-based backend model over offsets metadata and GameMemory reads/writes."""

    def __init__(
        self,
        *,
        memory: GameMemory | Any | None = None,
        offsets_api: Any = offsets_mod,
        target_executable: str | None = None,
    ) -> None:
        if target_executable and target_executable != "auto":
            selected_target = target_executable
        else:
            fallback_target = str(offsets_api.MODULE_NAME or "NBA2K26.exe")
            selected_target = GameMemory.detect_running_module_name(fallback_target) or fallback_target
        self.memory = memory if memory is not None else GameMemory(selected_target)
        self.offsets = offsets_api
        self.target_executable = selected_target
        self.last_status = "not attached"
        self.loaded_items: dict[str, dict[int, RecordListItem]] = {domain: {} for domain in _MODEL_DOMAINS}
        self.selected_items: dict[str, RecordListItem | None] = {domain: None for domain in _MODEL_DOMAINS}
        self.domain_statuses: dict[str, str] = {domain: self.runtime_status_text() for domain in _MODEL_DOMAINS}
        self._data_version = 0
        self._history_screen_rows: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._record_screen_rows: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._layout_cache: dict[str, dict[str, Any]] = {}
        self._field_entries_cache: dict[str, tuple[FieldEntry, ...]] = {}
        self._field_context_cache: dict[str, dict[int, tuple[str, str]]] = {}
        self._field_lookup_cache: dict[str, dict[str, FieldEntry]] = {}
        self._player_team_pointer_cache: dict[int, int] = {}
        self._player_filter_items_by_key: dict[str | int, tuple[RecordListItem, ...]] = {}
        self._player_search_keys: dict[int, str] = {}
        self._player_primary_positions: dict[int, str] = {}
        self._player_filter_index_ready = False
        self._player_position_filter_ready = False
        self._player_free_agent_filter_ready = False

    def _active_config(self) -> dict[str, Any]:
        self.offsets.initialize_offsets(self.target_executable, force=False)
        return dict(self.offsets.get_active_offset_config(self.target_executable))

    def _domain_base_key(self, domain: str) -> str:
        if domain not in _DOMAIN_BASE_KEYS:
            raise KeyError(f"unsupported domain: {domain}")
        return _DOMAIN_BASE_KEYS[domain]

    def _domain_stride_key(self, domain: str) -> str:
        base_key = self._domain_base_key(domain)
        stride_key = offsets_mod.BASE_POINTER_SIZE_KEY_MAP.get(base_key)
        if not stride_key:
            raise KeyError(f"unsupported domain stride: {domain}")
        return str(stride_key)

    def editor_layout(self, domain: str) -> dict[str, Any]:
        if domain not in self._layout_cache:
            self.offsets.initialize_offsets(self.target_executable, force=False)
            self._layout_cache[domain] = self.offsets.get_editor_layout_for_super(domain)
        return self._layout_cache[domain]

    def _layout_entries(self, domain: str) -> tuple[FieldEntry, ...]:
        if domain not in self._field_entries_cache:
            self._field_entries_cache[domain] = tuple(_iter_layout_fields(domain, self.editor_layout(domain)))
        return self._field_entries_cache[domain]

    def _field_lookup(self, domain: str) -> dict[str, FieldEntry]:
        if domain not in self._field_lookup_cache:
            lookup: dict[str, FieldEntry] = {}
            for entry in self._layout_entries(domain):
                for key in (
                    _field_identity(entry.field.get("normalized_name")),
                    _field_identity(entry.field.get("display_name")),
                ):
                    if key and key not in lookup:
                        lookup[key] = entry
            self._field_lookup_cache[domain] = lookup
        return self._field_lookup_cache[domain]

    def _field_context_map(self, domain: str) -> dict[int, tuple[str, str]]:
        if domain not in self._field_context_cache:
            self._field_context_cache[domain] = {id(entry.field): (entry.section, entry.group) for entry in self._layout_entries(domain)}
        return self._field_context_cache[domain]

    def _field_context(self, domain: str, field: dict[str, Any]) -> tuple[str, str]:
        cached = self._field_context_map(domain).get(id(field))
        if cached is not None:
            return cached
        return "", ""

    def _parent_payload(self, domain: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        parent_name = payload.get("parent")
        if not parent_name:
            return None
        parent_entry = self._field_by_normalized_name(domain, parent_name)
        if parent_entry is None:
            raise KeyError(f"missing parent field: {parent_name}")
        return self._field_version_payload(parent_entry.field)

    def attach(self) -> bool:
        self.offsets.initialize_offsets(self.target_executable, force=False)
        opened = bool(self.memory.open_process())
        if opened:
            base_addr = self.memory.base_addr
            self.last_status = f"attached to {self.target_executable} at 0x{int(base_addr):X}" if base_addr else f"attached to {self.target_executable}"
            return True
        self.last_status = f"not attached to {self.target_executable}"
        return False

    def runtime_status_text(self) -> str:
        label = target_display_label(self.target_executable)
        if self.memory.hproc:
            return f"{label} is attached."
        return f"{label} is not running."

    def select_target_executable(self, executable: str) -> None:
        if executable != self.target_executable:
            self.memory.close()
        self.target_executable = executable
        self.memory.module_name = executable
        self._layout_cache.clear()
        self._field_entries_cache.clear()
        self._field_context_cache.clear()
        self._field_lookup_cache.clear()
        self._player_team_pointer_cache.clear()
        self._invalidate_player_filter_index()
        self.loaded_items = {domain: {} for domain in _MODEL_DOMAINS}
        self.selected_items = {domain: None for domain in _MODEL_DOMAINS}
        self.last_status = self.runtime_status_text()
        self.domain_statuses = {domain: self.last_status for domain in _MODEL_DOMAINS}

    def domain_status(self, domain: str) -> str:
        return self.domain_statuses.get(domain, self.runtime_status_text())

    def domain_item_labels(self, domain: str) -> list[str]:
        return [item.display_label for item in self.loaded_items[domain].values()]

    def domain_items(self, domain: str) -> list[RecordListItem]:
        return list(self.loaded_items[domain].values())

    def domain_item_count(self, domain: str) -> int:
        return len(self.loaded_items[domain])

    def app_dataset_snapshot(self, domains: Iterable[str] | None = None) -> dict[str, Any]:
        """Return the model-owned loaded app dataset for app-integrated consumers.

        This exposes the same loaded records and model-read field values that
        the editor screens use.
        """
        selected_domains = tuple(domains) if domains is not None else _MODEL_DOMAINS
        return {
            "target_executable": self.target_executable,
            "runtime_status": self.runtime_status_text(),
            "domains": {domain: self.domain_dataset_snapshot(domain) for domain in selected_domains},
        }

    def domain_dataset_snapshot(self, domain: str) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        items = tuple(self.loaded_items.get(domain, {}).values())
        if not items:
            return {"count": 0, "records": records}
        grouped = self.grouped_fields(domain)
        for item in items:
            sections: list[dict[str, Any]] = []
            for section, groups in grouped.items():
                section_groups: list[dict[str, Any]] = []
                for group, entries in groups.items():
                    fields: list[dict[str, Any]] = []
                    for entry in entries:
                        field_payload: dict[str, Any] = {
                            "section": entry.section,
                            "group": entry.group,
                            "normalized_name": entry.normalized_name,
                            "display_name": entry.display_name,
                        }
                        try:
                            value = self.read_entry_value(entry, index=item.index)
                        except Exception as exc:
                            field_payload.update({"available": False, "error": str(exc)})
                        else:
                            field_payload.update(
                                {
                                    "available": True,
                                    "display_value": _json_safe_dataset_value(value.get("display_value")),
                                    "raw_value": _json_safe_dataset_value(value.get("raw_value")),
                                    "writeable": bool(value.get("writeable")),
                                    "value_behavior": str(value.get("value_behavior") or ""),
                                }
                            )
                        fields.append(field_payload)
                    section_groups.append({"label": str(group), "fields": fields})
                sections.append({"label": str(section), "groups": section_groups})
            records.append(
                {
                    "domain": item.domain,
                    "index": int(item.index),
                    "address": int(item.address),
                    "label": str(item.label),
                    "display_label": item.display_label,
                    "sections": sections,
                }
            )
        return {"count": len(records), "records": records}

    def player_team_filter_options(self) -> tuple[tuple[str, str | int], ...]:
        fixed = (
            (PLAYER_TEAM_FILTER_ALL, PLAYER_TEAM_FILTER_ALL),
            (PLAYER_TEAM_FILTER_BASE_TEAMS, PLAYER_TEAM_FILTER_BASE_TEAMS),
            (PLAYER_TEAM_FILTER_FREE_AGENTS, PLAYER_TEAM_FILTER_FREE_AGENTS),
            (PLAYER_TEAM_FILTER_DRAFT_CLASS, PLAYER_TEAM_FILTER_DRAFT_CLASS),
        )
        teams = tuple((team.display_label, int(team.index)) for team in self.loaded_items["Teams"].values())
        return (*fixed, *teams)

    def player_position_filter_options(self) -> tuple[tuple[str, str], ...]:
        return ((PLAYER_POSITION_FILTER_ALL, PLAYER_POSITION_FILTER_ALL), *((position, position) for position in PLAYER_PRIMARY_POSITIONS))

    def _team_player_slot_entries(self) -> list[tuple[int, FieldEntry]]:
        entries: list[tuple[int, FieldEntry]] = []
        for entry in self.grouped_fields("Teams").get("Team Players", {}).get("Team Players", ()):
            normalized = str(entry.normalized_name).strip().upper()
            if not normalized.startswith("PLAYER"):
                continue
            suffix = normalized.replace("PLAYER", "", 1)
            if not suffix.isdigit():
                continue
            entries.append((int(suffix), entry))
        return sorted(entries, key=lambda item: item[0])[:15]

    def player_roster_slot_items_for_team_items(
        self,
        team_items: Iterable[RecordListItem],
    ) -> list[tuple[RecordListItem, dict[str, Any]]]:
        players_by_address = {int(player.address): player for player in self.loaded_items.get("Players", {}).values()}
        rows: list[tuple[RecordListItem, dict[str, Any]]] = []
        for team in team_items:
            for roster_slot, entry in self._team_player_slot_entries():
                try:
                    player_pointer = int(self.read_entry_value(entry, index=team.index).get("raw_value") or 0)
                except Exception:
                    continue
                if not player_pointer:
                    continue
                player = players_by_address.get(player_pointer)
                if player is None:
                    continue
                rows.append(
                    (
                        player,
                        {
                            "team_index": int(team.index),
                            "team_label": str(team.label),
                            "team_slot": int(roster_slot),
                            "team_slot_field": str(entry.normalized_name),
                        },
                    )
                )
        return rows

    def player_items_for_team_items(self, team_items: Iterable[RecordListItem]) -> list[RecordListItem]:
        return [player for player, _placement in self.player_roster_slot_items_for_team_items(team_items)]

    def _read_player_current_team_pointer(self, item: RecordListItem) -> int:
        entry = self._field_by_normalized_name("Players", "CURRENTTEAM")
        return int(self.read_entry_value(entry, index=item.index).get("raw_value"))

    def _read_player_is_active(self, item: RecordListItem) -> bool:
        entry = self._field_by_normalized_name("Players", "ISACTIVE")
        if entry is None:
            return False
        value = self.read_entry_value(entry, index=item.index).get("raw_value")
        return bool(int(value or 0))

    def _invalidate_player_filter_index(self) -> None:
        self._player_filter_items_by_key.clear()
        self._player_search_keys.clear()
        self._player_primary_positions.clear()
        self._player_filter_index_ready = False
        self._player_position_filter_ready = False
        self._player_free_agent_filter_ready = False

    def _field_invalidates_player_filter_index(self, domain: str, field: dict[str, Any]) -> bool:
        identity = _field_identity(field.get("normalized_name") or field.get("display_name"))
        return (domain == "Players" and identity in {"CURRENTTEAM", "ISACTIVE", "POSITION"}) or (
            domain == "Teams" and identity.startswith("PLAYER") and identity.removeprefix("PLAYER").isdigit()
        )

    def _player_primary_position_values(self, players: tuple[RecordListItem, ...]) -> dict[int, str]:
        if not players:
            return {}
        position_entry = self._field_by_normalized_name("Players", "POSITION")
        if position_entry is None:
            raise KeyError("Players position filter requires POSITION")
        payload = self._field_version_payload(position_entry.field)
        first_address = min(int(player.address) for player in players)
        last_address = max(int(player.address) for player in players)
        stride = self.domain_stride("Players")
        position_address = _field_address(
            self.memory,
            first_address,
            payload,
            parent_payload=self._parent_payload("Players", payload),
        )
        position_offset = int(position_address) - first_address
        if not 0 <= position_offset < stride:
            raise ValueError("Players POSITION must resolve inside the player record")
        memory = ReadOnlyMemoryBuffer.capture(
            self.memory,
            first_address,
            last_address - first_address + stride,
        )
        return {
            int(player.address): str(
                _raw_to_display_value(
                    position_entry.section,
                    position_entry.field,
                    payload,
                    _read_authored_value(memory, int(player.address) + position_offset, payload),
                )
            )
            for player in players
        }

    def _build_player_position_filter(self) -> None:
        primary_positions = self._player_primary_position_values(tuple(self.loaded_items.get("Players", {}).values()))
        primary_positions.update(
            self._player_primary_position_values(self._player_filter_items_by_key.get(PLAYER_TEAM_FILTER_DRAFT_CLASS, ()))
        )
        self._player_primary_positions = primary_positions
        self._player_position_filter_ready = True

    def _player_filter_source_values(
        self,
        players: tuple[RecordListItem, ...],
    ) -> dict[int, tuple[int, bool]]:
        if not players:
            return {}
        current_team_entry = self._field_by_normalized_name("Players", "CURRENTTEAM")
        active_entry = self._field_by_normalized_name("Players", "ISACTIVE")
        if current_team_entry is None or active_entry is None:
            raise KeyError("Players filter requires CURRENTTEAM and ISACTIVE")
        current_team_payload = self._field_version_payload(current_team_entry.field)
        active_payload = self._field_version_payload(active_entry.field)
        first_address = min(int(player.address) for player in players)
        last_address = max(int(player.address) for player in players)
        stride = self.domain_stride("Players")
        current_team_address = _field_address(
            self.memory,
            first_address,
            current_team_payload,
            parent_payload=self._parent_payload("Players", current_team_payload),
        )
        active_address = _field_address(
            self.memory,
            first_address,
            active_payload,
            parent_payload=self._parent_payload("Players", active_payload),
        )
        current_team_offset = int(current_team_address) - first_address
        active_offset = int(active_address) - first_address
        if not (0 <= current_team_offset < stride and 0 <= active_offset < stride):
            raise ValueError("Players filter fields must resolve inside the player record")
        memory = ReadOnlyMemoryBuffer.capture(
            self.memory,
            first_address,
            last_address - first_address + stride,
        )
        return {
            int(player.index): (
                int(_read_authored_value(memory, int(player.address) + current_team_offset, current_team_payload)),
                bool(int(_read_authored_value(memory, int(player.address) + active_offset, active_payload) or 0)),
            )
            for player in players
        }

    def _build_free_agent_filter(self, players: tuple[RecordListItem, ...]) -> tuple[RecordListItem, ...]:
        free_agents: list[RecordListItem] = []
        self._player_team_pointer_cache.clear()
        source_values = self._player_filter_source_values(players)
        for player in players:
            current_team, is_active = source_values[int(player.index)]
            self._player_team_pointer_cache[int(player.index)] = current_team
            if is_active and current_team == 0:
                free_agents.append(player)
        result = tuple(free_agents)
        self._player_filter_items_by_key[PLAYER_TEAM_FILTER_FREE_AGENTS] = result
        self._player_free_agent_filter_ready = True
        return result

    def build_player_filter_index(self, *, include_free_agents: bool = True) -> PlayerListView:
        players = tuple(self.loaded_items.get("Players", {}).values())
        players_by_address = {int(player.address): player for player in players}
        team_buckets: dict[int, list[RecordListItem]] = {
            int(team.index): [] for team in self.loaded_items.get("Teams", {}).values()
        }
        base_team_players: dict[int, RecordListItem] = {}
        slot_entries = self._team_player_slot_entries()

        for team in self.loaded_items.get("Teams", {}).values():
            bucket = team_buckets[int(team.index)]
            seen: set[int] = set()
            for _slot, entry in slot_entries:
                try:
                    player_pointer = int(self.read_entry_value(entry, index=team.index).get("raw_value") or 0)
                except Exception:
                    continue
                player = players_by_address.get(player_pointer)
                if player is None or int(player.index) in seen:
                    continue
                seen.add(int(player.index))
                bucket.append(player)
                if 0 <= int(team.index) <= 29:
                    base_team_players.setdefault(int(player.index), player)

        try:
            draft_class = tuple(self._scan_records_from_base_key("Players", _DRAFT_CLASS_BASE_KEY))
        except Exception:
            draft_class = ()

        indexes: dict[str | int, tuple[RecordListItem, ...]] = {
            PLAYER_TEAM_FILTER_ALL: players,
            PLAYER_TEAM_FILTER_BASE_TEAMS: tuple(base_team_players.values()),
            PLAYER_TEAM_FILTER_FREE_AGENTS: (),
            PLAYER_TEAM_FILTER_DRAFT_CLASS: draft_class,
        }
        indexes.update({team_index: tuple(items) for team_index, items in team_buckets.items()})
        self._player_filter_items_by_key = indexes
        self._player_primary_positions = {}
        self._player_position_filter_ready = False
        self._player_search_keys = {
            int(item.address): item.display_label.casefold()
            for items in indexes.values()
            for item in items
        }
        self._player_filter_index_ready = True
        self._player_free_agent_filter_ready = False
        if include_free_agents:
            self._build_free_agent_filter(players)
        self._data_version += 1
        return self.player_list_view(PLAYER_TEAM_FILTER_ALL)

    def prepare_player_list_view(
        self,
        selected_team: str | int | None,
        search_text: str | None = None,
        primary_position: str | None = None,
    ) -> PlayerListView:
        selected = selected_team if isinstance(selected_team, int) else str(selected_team or PLAYER_TEAM_FILTER_ALL).strip()
        if not self._player_filter_index_ready:
            self.build_player_filter_index(include_free_agents=selected == PLAYER_TEAM_FILTER_FREE_AGENTS)
        elif selected == PLAYER_TEAM_FILTER_FREE_AGENTS and not self._player_free_agent_filter_ready:
            self._build_free_agent_filter(tuple(self.loaded_items.get("Players", {}).values()))
        if str(primary_position or "").strip() in PLAYER_PRIMARY_POSITIONS and not self._player_position_filter_ready:
            self._build_player_position_filter()
        return self.player_list_view(selected, search_text, primary_position)

    def player_list_view(
        self,
        selected_team: str | int | None,
        search_text: str | None = None,
        primary_position: str | None = None,
    ) -> PlayerListView:
        selected = selected_team if isinstance(selected_team, int) else str(selected_team or PLAYER_TEAM_FILTER_ALL).strip()
        if not self._player_filter_index_ready:
            items = tuple(self.loaded_items.get("Players", {}).values()) if selected == PLAYER_TEAM_FILTER_ALL else ()
        else:
            items = self._player_filter_items_by_key.get(selected, ())
        position = str(primary_position or PLAYER_POSITION_FILTER_ALL).strip()
        if position in PLAYER_PRIMARY_POSITIONS:
            items = tuple(item for item in items if self._player_primary_positions.get(int(item.address)) == position)
        query = str(search_text or "").strip().casefold()
        if query:
            items = tuple(item for item in items if query in self._player_search_keys.get(int(item.address), item.display_label.casefold()))
        return PlayerListView(filter_key=selected, query=query, items=tuple(items), version=self._data_version)

    def _player_filter_items(self, selected_team: str | int | None) -> dict[int, RecordListItem]:
        return {int(item.index): item for item in self.player_list_view(selected_team).items}

    def player_items_for_team_filter(
        self,
        selected_team: str | int | None,
        search_text: str | None = None,
        primary_position: str | None = None,
    ) -> dict[int, RecordListItem]:
        return {int(item.index): item for item in self.player_list_view(selected_team, search_text, primary_position).items}

    def player_item_labels_for_team_filter(
        self,
        selected_team: str | int | None,
        search_text: str | None = None,
        primary_position: str | None = None,
    ) -> list[str]:
        return [item.display_label for item in self.player_list_view(selected_team, search_text, primary_position).items]

    def is_player_season_id_selector_entry(self, entry: FieldEntry) -> bool:
        return _is_player_season_id_selector_entry(entry)

    def is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool:
        return _is_player_selected_stat_detail_entry(entry)

    def player_season_stat_id_options(self, player_index: int) -> list[str]:
        options: list[str] = []
        for entry in self._player_season_id_selector_entries(_STAT_ROLE_SELECTOR):
            label = _player_season_id_option_label(entry)
            try:
                value = self.read_entry_value(entry, index=player_index)
                stat_id = int(value.get("raw_value") or 0)
            except Exception:
                options.append(f"-- {label} (unavailable)")
                continue
            if stat_id > 0 and stat_id != 0xFFFF:
                options.append(f"[{stat_id}] {label}")
            else:
                options.append(f"-- {label} ({stat_id})")
        return options

    def _player_season_id_selector_entries(self, selector_role: object) -> list[FieldEntry]:
        role = str(selector_role or _STAT_ROLE_SELECTOR).strip()
        entries: list[FieldEntry] = []
        for groups in self.grouped_fields("Players").values():
            for group_entries in groups.values():
                entries.extend(entry for entry in group_entries if _stat_role(entry.field) == role)
        return entries

    def _player_season_id_selector_entry_for_option(self, selected: object, *, selector_role: object = _STAT_ROLE_SELECTOR) -> FieldEntry:
        selected_identity = _player_season_id_identity_from_option(selected)
        if not selected_identity:
            raise ValueError("missing active Season Stat ID selector")
        for entry in self._player_season_id_selector_entries(selector_role):
            if selected_identity in {
                _field_identity(entry.normalized_name),
                _field_identity(_player_season_id_option_label(entry)),
            }:
                return entry
        raise KeyError(f"unknown Season Stat ID selector: {selected}")

    def _selected_record_source_for_entry(self, entry: FieldEntry) -> dict[str, Any]:
        source = _selected_record_source(entry.field)
        if source is None:
            raise KeyError(f"field is missing selected_record_source: {entry.display_name}")
        return source

    def _player_season_stat_detail_base_address(self, entry: FieldEntry, player_index: int, selected: object) -> int:
        source = self._selected_record_source_for_entry(entry)
        selector_entry = self._player_season_id_selector_entry_for_option(
            selected,
            selector_role=source.get("selector_role") or _STAT_ROLE_SELECTOR,
        )
        stat_id = int(self.read_entry_value(selector_entry, index=player_index).get("raw_value") or 0)
        invalid_ids = {int(value) for value in source.get("invalid_ids", []) if str(value).strip()}
        if stat_id <= 0 or stat_id in invalid_ids:
            raise ValueError(f"selected Season Stat ID has no stats row: {selected}")
        base_key = str(source.get("base_pointer") or "").strip()
        stride_key = str(source.get("stride") or "").strip()
        if not base_key or not stride_key:
            raise KeyError(f"selected_record_source for {entry.display_name} must include base_pointer and stride")
        return resolve_base_pointer_entry(self.memory, self._base_pointer_entry(base_key), label=base_key) + stat_id * self._stride_value(stride_key)

    def _base_pointer_entry(self, key: str) -> dict[str, Any]:
        config = self._active_config()
        base_pointers = config.get("base_pointers")
        if not isinstance(base_pointers, dict):
            raise KeyError("active config is missing base_pointers")
        base_entry = base_pointers.get(key)
        if not isinstance(base_entry, dict):
            raise KeyError(f"active config is missing {key} base pointer")
        return base_entry

    def _stride_value(self, key: str) -> int:
        config = self._active_config()
        game_info = config.get("game_info")
        if not isinstance(game_info, dict):
            raise KeyError("active config is missing game_info")
        stride = int(game_info.get(key) or 0)
        if stride <= 0:
            raise KeyError(f"game_info is missing {key}")
        return stride

    def _record_id_value(self, domain: str, item: RecordListItem, id_field_name: str) -> int | None:
        entry = self._field_by_normalized_name(domain, id_field_name)
        if entry is None:
            return None
        try:
            value = self.read_entry_value(entry, index=item.index).get("raw_value")
            return int(value) if value is not None else None
        except Exception:
            return None

    def _shoe_option_map(self) -> dict[int, str]:
        options: dict[int, str] = {}
        for item in self.loaded_items.get("Shoes", {}).values():
            shoe_id = self._record_id_value("Shoes", item, "ID")
            if shoe_id is not None:
                options[shoe_id] = _id_prefixed_option(shoe_id, item.label)
        return options

    def field_options(self, entry: FieldEntry) -> list[str]:
        payload = self._field_version_payload(entry.field)
        if bool(payload.get("shoe_dropdown")):
            return [option for _shoe_id, option in sorted(self._shoe_option_map().items())]
        raw_options = payload.get("dropdown") or payload.get("values")
        return [str(option) for option in raw_options] if isinstance(raw_options, list) else []

    def selected_item(self, domain: str) -> RecordListItem | None:
        return self.selected_items[domain]

    def select_item_by_index(
        self,
        domain: str,
        selected_index: int | None,
        *,
        player_team_filter: str | int | None = None,
    ) -> RecordListItem | None:
        if selected_index is None:
            self.selected_items[domain] = None
            return None
        items = self._player_filter_items(player_team_filter) if domain == "Players" else self.loaded_items[domain]
        self.selected_items[domain] = items.get(int(selected_index))
        return self.selected_items[domain]

    def refresh_domain_items(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:
        try:
            items = self.scan_records(domain, limit=limit)
            by_index = {int(item.index): item for item in items}
            self.loaded_items[domain] = by_index
            self._data_version += 1
            if domain == "Players":
                self._player_team_pointer_cache.clear()
            if domain in {"Players", "Teams"}:
                self._invalidate_player_filter_index()
            indices = list(by_index)
            if indices:
                current = self.selected_items.get(domain)
                selected_index = int(current.index) if current is not None else indices[0]
                self.selected_items[domain] = by_index.get(selected_index, by_index[indices[0]])
                self.domain_statuses[domain] = f"loaded {len(indices)} {domain.lower()} records"
            else:
                self.selected_items[domain] = None
                self.domain_statuses[domain] = self.runtime_status_text()
            return items
        except Exception as exc:
            self.loaded_items[domain] = {}
            self._data_version += 1
            self.selected_items[domain] = None
            if domain == "Players":
                self._player_team_pointer_cache.clear()
            if domain in {"Players", "Teams"}:
                self._invalidate_player_filter_index()
            self.domain_statuses[domain] = self.runtime_status_text() if "not attached" in str(exc).lower() else f"scan failed: {exc}"
            return []

    def refresh_domains(
        self,
        domains: tuple[str, ...],
        progress_callback: Any | None = None,
    ) -> tuple[DomainRefreshView, ...]:
        self.attach()
        views: list[DomainRefreshView] = []
        total = len(domains)
        for position, domain in enumerate(domains, start=1):
            self.domain_statuses[domain] = "Loading records..."
            items = tuple(self.refresh_domain_items(domain))
            views.append(
                DomainRefreshView(
                    domain=domain,
                    items=items,
                    status=self.domain_status(domain),
                    version=self._data_version,
                )
            )
            if progress_callback is not None:
                progress_callback(position, total, f"Loaded {domain}")
        if self.loaded_items.get("Players") and {"Players", "Teams"}.intersection(domains):
            self.build_player_filter_index(include_free_agents=False)
        return tuple(views)

    def player_detail_labels(self) -> tuple[str, ...]:
        return tuple(label for label, _ in PLAYER_DETAIL_FIELD_SPECS)

    def team_summary_labels(self) -> tuple[str, ...]:
        return tuple(label for label, _ in TEAM_SUMMARY_FIELD_SPECS)

    def _selected_item_rank_text(self, domain: str, item: RecordListItem | None) -> str:
        if item is None:
            return "--"
        for rank, candidate in enumerate(self.loaded_items.get(domain, {}).values(), start=1):
            if candidate == item:
                return str(rank)
        return "--"

    def _record_summary_specs(self, domain: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        if domain == "NBA History":
            return HISTORY_SUMMARY_FIELD_SPECS
        if domain == "NBA Records":
            return RECORD_SUMMARY_FIELD_SPECS
        return ()

    def _record_summary_values_for_item(self, domain: str, item: RecordListItem | None, rank: int | None = None) -> dict[str, str]:
        values: dict[str, str] = {}
        for label, candidates in self._record_summary_specs(domain):
            if label == "Rank":
                values[label] = str(rank) if rank is not None else self._selected_item_rank_text(domain, item)
            else:
                values[label] = self._read_named_value(domain, item, candidates)
        return values

    def _read_named_value_at_record_address(self, domain: str, record_addr: int, candidates: tuple[str, ...]) -> str:
        for name in candidates:
            try:
                entry = self._field_by_normalized_name(domain, name)
                if entry is None:
                    continue
                value = self._read_field_at_record_address(domain, record_addr, entry.field)
                return str(value.get("display_value", "--"))
            except Exception:
                continue
        return "--"

    def _record_summary_values_for_address(self, domain: str, record_addr: int, rank: int) -> dict[str, str]:
        values: dict[str, str] = {}
        for label, candidates in self._record_summary_specs(domain):
            if label == "Rank":
                values[label] = str(rank)
            else:
                values[label] = self._read_named_value_at_record_address(domain, record_addr, candidates)
        return values

    def selected_record_summary_values(self, domain: str) -> dict[str, str]:
        return self._record_summary_values_for_item(domain, self.selected_items[domain])

    def record_summary_rows(
        self,
        domain: str,
        *,
        limit: int | None,
        history_type: int | None = None,
        record_row_start: int | None = None,
        record_row_count: int | None = None,
        record_row_stride: int | None = None,
    ) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        if domain == "NBA Records" and record_row_start is not None:
            base = self.domain_base(domain)
            row_stride = int(record_row_stride) if record_row_stride is not None else self.domain_stride(domain)
            max_rows = min(limit, int(record_row_count) if record_row_count is not None else limit)
            for offset in range(max_rows):
                record_addr = base + (int(record_row_start) + offset) * row_stride
                rows.append(self._record_summary_values_for_address(domain, record_addr, offset + 1))
            return rows

        items = list(self.loaded_items.get(domain, {}).values())
        if domain == "NBA History":
            if history_type is not None:
                items = [item for item in items if self._read_named_raw_int(domain, item, "TYPE") == history_type]
            items = sorted(
                items,
                key=lambda item: self._read_named_raw_int(domain, item, "SEASON") or -1,
                reverse=True,
            )
        for rank, item in enumerate(items, start=1):
            if limit is not None and len(rows) >= limit:
                break
            rows.append(self._record_summary_values_for_item(domain, item, rank))
        return rows

    def clear_history_screen_rows(self) -> None:
        self._history_screen_rows.clear()

    def clear_record_screen_rows(self) -> None:
        self._record_screen_rows.clear()

    def refresh_history_screen_rows(self, section: str, tab: str, history_type: int | None) -> list[dict[str, str]]:
        rows = self.record_summary_rows("NBA History", limit=None, history_type=history_type)
        self._history_screen_rows[(section, tab)] = rows
        return rows

    def history_screen_rows(self, section: str, tab: str, history_type: int | None) -> list[dict[str, str]]:
        key = (section, tab)
        if key not in self._history_screen_rows:
            return self.refresh_history_screen_rows(section, tab, history_type)
        return self._history_screen_rows[key]

    def refresh_record_screen_rows(
        self,
        section: str,
        stat: str,
        *,
        record_row_start: int,
        record_row_count: int,
    ) -> list[dict[str, str]]:
        rows = self.record_summary_rows(
            "NBA Records",
            limit=record_row_count,
            record_row_start=record_row_start,
            record_row_count=record_row_count,
        )
        self._record_screen_rows[(section, stat)] = rows
        return rows

    def record_screen_rows(
        self,
        section: str,
        stat: str,
        *,
        record_row_start: int,
        record_row_count: int,
    ) -> list[dict[str, str]]:
        key = (section, stat)
        if key not in self._record_screen_rows:
            return self.refresh_record_screen_rows(
                section,
                stat,
                record_row_start=record_row_start,
                record_row_count=record_row_count,
            )
        return self._record_screen_rows[key]

    def _read_named_raw_int(self, domain: str, item: RecordListItem | None, name: str) -> int | None:
        if item is None:
            return None
        try:
            entry = self._field_by_normalized_name(domain, name)
            if entry is None:
                return None
            return int(self.read_entry_value(entry, index=item.index).get("raw_value"))
        except Exception:
            return None

    def _read_named_value(self, domain: str, item: RecordListItem | None, candidates: tuple[str, ...]) -> str:
        if item is None:
            return "--"
        for name in candidates:
            try:
                entry = self._field_by_normalized_name(domain, name)
                if entry is None:
                    continue
                value = self.read_entry_value(entry, index=item.index)
                return str(value.get("display_value", "--"))
            except Exception:
                continue
        return "--"

    def _read_named_value_for_item(self, domain: str, item: RecordListItem | None, candidates: tuple[str, ...]) -> str:
        if item is None:
            return "--"
        for name in candidates:
            try:
                entry = self._field_by_normalized_name(domain, name)
                if entry is None:
                    continue
                value = self._read_field_at_record_address(domain, item.address, entry.field)
                return str(value.get("display_value", "--"))
            except Exception:
                continue
        return "--"

    def selected_player_detail_values(self) -> dict[str, str]:
        item = self.selected_items["Players"]
        return {label: self._read_named_value_for_item("Players", item, candidates) for label, candidates in PLAYER_DETAIL_FIELD_SPECS}

    def selected_team_summary_values(self) -> dict[str, str]:
        item = self.selected_items["Teams"]
        return {label: self._read_named_value("Teams", item, candidates) for label, candidates in TEAM_SUMMARY_FIELD_SPECS}

    def save_selected_team_summary(self, values: dict[str, str]) -> tuple[int, int]:
        item = self.selected_items["Teams"]
        if item is None:
            raise RuntimeError("select a team first")
        fields: dict[str, dict[str, Any]] = {}
        missing = 0
        for label, candidates in TEAM_SUMMARY_FIELD_SPECS:
            entry = None
            for name in candidates:
                entry = self._field_by_normalized_name("Teams", name)
                if entry is not None:
                    break
            if entry is None:
                missing += 1
                continue
            fields[f"{entry.section}/{entry.normalized_name}"] = {"display_value": values.get(label, "")}
        result = self.apply_team_summary_snapshot({"records": [{"index": item.index, "fields": fields}]})
        return int(result["succeeded"]), int(result["failed"] + result["skipped"] + missing)

    def apply_team_summary_snapshot(self, snapshot: dict[str, Any]) -> dict[str, int]:
        entries: dict[str, FieldEntry] = {}
        for _label, candidates in TEAM_SUMMARY_FIELD_SPECS:
            for name in candidates:
                entry = self._field_by_normalized_name("Teams", name)
                if entry is not None:
                    entries[f"{entry.section}/{entry.normalized_name}"] = entry
                    break
        records = snapshot.get("records") if isinstance(snapshot, dict) else None
        if not isinstance(records, list):
            raise ValueError("team summary snapshot is missing records")
        attempted = 0
        succeeded = 0
        failed = 0
        skipped = 0
        for row in records:
            if not isinstance(row, dict):
                skipped += 1
                continue
            fields = row.get("fields")
            if not isinstance(fields, dict):
                skipped += 1
                continue
            try:
                index = int(row["index"])
            except Exception:
                skipped += len(fields)
                continue
            for key, payload in fields.items():
                entry = entries.get(str(key))
                if entry is None:
                    skipped += 1
                    continue
                value = payload.get("display_value") if isinstance(payload, dict) else payload
                attempted += 1
                try:
                    self.write_entry_value(entry, index=index, value=value)
                    succeeded += 1
                except Exception:
                    failed += 1
        return {"attempted": attempted, "succeeded": succeeded, "failed": failed, "skipped": skipped}

    def selected_detail_title(self, domain: str, label: str) -> str:
        item = self.selected_items[domain]
        return f"Select a {label.lower()}" if item is None else item.label

    def selected_record_address_text(self, domain: str) -> str:
        item = self.selected_items[domain]
        return "--" if item is None else f"0x{item.address:X}"

    def grouped_fields(self, domain: str) -> OrderedDict[str, OrderedDict[str, list[FieldEntry]]]:
        grouped: OrderedDict[str, OrderedDict[str, list[FieldEntry]]] = OrderedDict()
        for entry in self._layout_entries(domain):
            try:
                payload = self._field_version_payload(entry.field)
            except KeyError:
                continue
            if bool(payload.get("hidden")):
                continue
            grouped.setdefault(entry.section, OrderedDict()).setdefault(entry.group, []).append(entry)
        return grouped

    def _field_by_normalized_name(self, domain: str, name: str) -> FieldEntry | None:
        return self._field_lookup(domain).get(_field_identity(name))

    def _label_entries(self, domain: str) -> list[FieldEntry]:
        entries: list[FieldEntry] = []
        for name in _LABEL_FIELD_NAMES.get(domain, ()): 
            entry = self._field_by_normalized_name(domain, name)
            if entry is not None:
                entries.append(entry)
        if entries:
            return entries
        return []

    def _team_pointer_display(self, raw_value: Any) -> str | None:
        return self._record_pointer_display(raw_value, "Teams")

    def _record_pointer_display(self, raw_value: Any, target_domain: str) -> str | None:
        try:
            pointer = int(raw_value)
        except Exception:
            return None
        if pointer <= 0:
            return None
        for item in self.loaded_items.get(target_domain, {}).values():
            if item.address == pointer:
                text = str(item.label).strip()
                return text or None
        try:
            target_base = self.domain_base(target_domain)
            target_stride = self.domain_stride(target_domain)
        except Exception:
            return None
        if target_stride <= 0:
            return None
        delta = pointer - target_base
        if delta < 0 or delta % target_stride != 0:
            return None
        try:
            label = self._label_for_record_address(target_domain, delta // target_stride, pointer, self._label_entries(target_domain))
        except Exception:
            return None
        text = str(label).strip()
        return text or None

    def _pointer_display_for_payload(self, payload: dict[str, Any], raw_value: Any) -> str | None:
        target_domain = _ADDRESS_DROPDOWN_TYPES.get(_type_key(payload))
        if target_domain:
            return self._record_pointer_display(raw_value, target_domain)
        if bool(payload.get("team_dropdown")) or bool(payload.get("team_address_dropdown")):
            return self._team_pointer_display(raw_value)
        if bool(payload.get("shoe_dropdown")):
            try:
                return self._shoe_option_map().get(int(raw_value))
            except Exception:
                return None
        return None

    def _read_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any]) -> dict[str, Any]:
        payload = self._field_version_payload(field)
        address = _field_address(self.memory, record_addr, payload, parent_payload=self._parent_payload(domain, payload))
        raw_value = _read_authored_value(self.memory, address, payload)
        section, _group = self._field_context(domain, field)
        display_value = self._pointer_display_for_payload(payload, raw_value)
        if display_value is None:
            display_value = _raw_to_display_value(section, field, payload, raw_value)
        return {
            "field": field,
            "address": address,
            "raw_value": raw_value,
            "display_value": display_value,
            "writeable": not bool(payload.get("readonly")) and _implemented_payload(payload),
            "value_behavior": "implemented" if _implemented_payload(payload) else "implementation_required",
        }

    def _write_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any], value: Any) -> Any:
        payload = self._field_version_payload(field)
        if bool(payload.get("readonly")):
            raise PermissionError(f"field is readonly: {field.get('normalized_name') or field.get('display_name')}")
        address = _field_address(self.memory, record_addr, payload, parent_payload=self._parent_payload(domain, payload))
        section, _group = self._field_context(domain, field)
        raw_value = parse_id_prefixed_option(value) if bool(payload.get("shoe_dropdown")) else None
        if raw_value is None:
            raw_value = _display_to_raw_value(section, field, payload, value)
        _write_authored_value(self.memory, address, payload, raw_value)
        return raw_value

    def _label_for_record_address(self, domain: str, index: int, record_addr: int, label_entries: list[FieldEntry]) -> str:
        labels: list[str] = []
        values: list[Any] = []
        for entry in label_entries:
            value = self._read_field_at_record_address(domain, record_addr, entry.field)["display_value"]
            values.append(value)
            text = str(value).strip()
            if text:
                labels.append(text)
        if not self._valid_label_values(domain, record_addr, values, labels):
            return ""
        return " ".join(labels)

    def _valid_label_values(self, domain: str, record_addr: int, values: list[Any], labels: list[str]) -> bool:
        if domain == "NBA Records":
            return _valid_nba_record_label_values(values)
        if domain == "NBA History":
            type_entry = self._field_by_normalized_name(domain, "TYPE")
            if type_entry is None:
                return _valid_record_list_label_values(values)
            try:
                raw_type = int(self._read_field_at_record_address(domain, record_addr, type_entry.field)["raw_value"])
            except Exception:
                return False
            if raw_type <= 0:
                return False
            return any(_has_alpha_text(value) for value in values)
        return _valid_record_list_label_values(values)

    def _record_count_limit_for_base_key(self, base_key: str) -> int | None:
        try:
            count = int(self._base_pointer_entry(base_key).get("record_count") or 0)
        except Exception:
            return None
        return count if count > 0 else None

    def _domain_record_count_limit(self, domain: str) -> int | None:
        return self._record_count_limit_for_base_key(self._domain_base_key(domain))

    def _base_address_for_key(self, base_key: str) -> int:
        return resolve_base_pointer_entry(
            self.memory,
            self._base_pointer_entry(base_key),
            label=base_key,
            apply_final_offset_without_module_base=False,
            follow_chain=False,
        )

    def _scan_records_from_base_key(self, domain: str, base_key: str, *, limit: int | None = None) -> list[RecordListItem]:
        if not self.memory.hproc or not self.memory.base_addr:
            raise RuntimeError(f"not attached to {self.target_executable}")
        stride_key = offsets_mod.BASE_POINTER_SIZE_KEY_MAP.get(base_key)
        if not stride_key:
            raise KeyError(f"unsupported base stride: {base_key}")
        explicit_limit = int(limit) if limit is not None else self._record_count_limit_for_base_key(base_key)
        base = self._base_address_for_key(base_key)
        stride = self._stride_value(str(stride_key))
        label_entries = self._label_entries(domain)
        invalid_streak_stop = _SPARSE_SCAN_INVALID_STREAKS.get(domain, 1)
        invalid_streak = 0
        items: list[RecordListItem] = []
        index = 0
        while explicit_limit is None or index < explicit_limit:
            address = record_address(base=base, index=index, stride=stride)
            try:
                label = self._label_for_record_address(domain, index, address, label_entries)
            except Exception:
                if not items and index == 0:
                    raise
                label = ""
            if not label:
                if not items:
                    break
                invalid_streak += 1
                if invalid_streak >= invalid_streak_stop:
                    break
                index += 1
                continue
            invalid_streak = 0
            items.append(RecordListItem(domain=domain, index=index, address=address, label=label))
            index += 1
        return items

    def scan_records(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:
        return self._scan_records_from_base_key(domain, self._domain_base_key(domain), limit=limit)

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:
        if entry.domain == "Teams" and entry.section == "Team Stats Edit":
            return self._read_field_at_record_address(entry.domain, self._team_stats_edit_record_address(index), entry.field)
        if stat_selector is not None and _is_player_selected_stat_detail_entry(entry):
            return self._read_field_at_record_address(
                entry.domain,
                self._player_season_stat_detail_base_address(entry, index, stat_selector),
                entry.field,
            )
        return self.read_value(entry.domain, index=index, field=entry.field)

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object | None = None) -> None:
        if entry.domain == "Teams" and entry.section == "Team Stats Edit":
            self._write_field_at_record_address(entry.domain, self._team_stats_edit_record_address(index), entry.field, value)
            return
        if stat_selector is not None and _is_player_selected_stat_detail_entry(entry):
            record_addr = self._player_season_stat_detail_base_address(entry, index, stat_selector)
            self._write_field_at_record_address(entry.domain, record_addr, entry.field, value)
            return
        self.write_value(entry.domain, index=index, field=entry.field, value=value)

    def read_entry_value_for_item(self, entry: FieldEntry, item: RecordListItem, *, stat_selector: object | None = None) -> dict[str, Any]:
        if stat_selector is not None and _is_player_selected_stat_detail_entry(entry):
            return self.read_entry_value(entry, index=item.index, stat_selector=stat_selector)
        return self._read_field_at_record_address(entry.domain, item.address, entry.field)

    def write_entry_value_for_item(self, entry: FieldEntry, item: RecordListItem, *, value: Any, stat_selector: object | None = None) -> None:
        if stat_selector is not None and _is_player_selected_stat_detail_entry(entry):
            self.write_entry_value(entry, index=item.index, value=value, stat_selector=stat_selector)
            return
        raw_value = self._write_field_at_record_address(entry.domain, item.address, entry.field, value)
        self._data_version += 1
        if self._field_invalidates_player_filter_index(entry.domain, entry.field):
            self._invalidate_player_filter_index()
        if entry.domain == "Players" and _field_identity(entry.field.get("normalized_name") or entry.field.get("display_name")) == "CURRENTTEAM":
            try:
                self._player_team_pointer_cache[item.index] = int(raw_value)
            except Exception:
                self._player_team_pointer_cache.pop(item.index, None)

    def reset_player_editor_values(self, *, item: RecordListItem, stat_selector: object | None = None) -> dict[str, int]:
        attempted = 0
        succeeded = 0
        failed = 0
        grouped = self.grouped_fields("Players")
        for section in _PLAYER_EDITOR_RESET_SECTIONS:
            for entries in grouped.get(section, {}).values():
                for entry in entries:
                    value = self._player_editor_reset_value(entry)
                    if value is None:
                        continue
                    attempted += 1
                    try:
                        self.write_entry_value_for_item(entry, item, value=value, stat_selector=stat_selector)
                        succeeded += 1
                    except Exception:
                        failed += 1
        return {"attempted": attempted, "succeeded": succeeded, "failed": failed}

    def _player_editor_reset_value(self, entry: FieldEntry) -> int | float | str | None:
        if entry.domain != "Players":
            return None
        normalized = str(entry.normalized_name).upper()
        if normalized == "FIRSTNAME":
            return "A"
        if normalized == "LASTNAME":
            return "Z"
        if normalized == "BIRTHYEAR":
            return 2006
        if normalized == "HEIGHT":
            return 60
        if normalized == "WEIGHT":
            return 100
        if normalized == "WINGSPAN":
            return 60
        if normalized == "WINGSPANCM":
            return 152.4
        if normalized == "AGE":
            return 18
        if normalized in {"PLAYTYPE2", "PLAYTYPE3", "PLAYTYPE4"}:
            return "None"
        if normalized == "AVERAGEPERCENT":
            return 34
        if normalized in {"BUSTPERCENTAGE", "BOOMPERCENTAGE"}:
            return 33
        if normalized == "MAXIMUMPOTENTIAL":
            return 40
        if normalized == "MINIMUMPOTENTIAL":
            return 41
        if entry.section == "Attributes":
            return 25
        if entry.section == "Tendencies":
            return 0
        if entry.section == "Badges":
            return 0
        return None

    def set_all_players_stat_ids_to_no_stats(
        self,
        *,
        player_items: Iterable[RecordListItem] | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, int]:
        items = tuple(player_items) if player_items is not None else tuple(self.loaded_items.get("Players", {}).values())
        selector_entries = tuple(self._player_season_id_selector_entries(_STAT_ROLE_SELECTOR))
        fields = {f"{entry.section}/{entry.normalized_name}": {"display_value": 65535} for entry in selector_entries}
        total = len(items) * len(fields)

        def apply_progress(done: int, _total: int, _message: str) -> None:
            if progress_callback is not None:
                written = min(done * len(fields), total)
                progress_callback(written, total, f"Setting player stat IDs: {written}/{total}")

        result = self.apply_player_roster_snapshot(
            {"records": [{"fields": fields} for _item in items]},
            target_items=items,
            progress_callback=apply_progress,
            allow_stats=True,
        )
        return {"players": len(items), "stat_id_fields": len(selector_entries), "written": int(result["succeeded"])}

    def export_team_stats_snapshot_rows(self) -> list[dict[str, Any]]:
        teams = sorted(self.loaded_items.get("Teams", {}).values(), key=lambda item: int(item.index))
        entries = list(self.grouped_fields("Teams").get("Team Stats Edit", {}).get("Teams", ()))
        if not teams or not entries:
            return []
        rows: list[dict[str, Any]] = []
        for team_slot, team in enumerate(teams[:30]):
            row: dict[str, Any] = {
                "team_slot": int(team_slot),
                "team_index": int(team.index),
                "team_label": str(team.label),
            }
            for entry in entries:
                try:
                    value = self.read_entry_value(entry, index=team.index)
                except Exception:
                    display_value = ""
                else:
                    display_value = _json_safe_roster_value(value.get("display_value"))
                row[f"{entry.group} / {entry.display_name}"] = display_value
            rows.append(row)
        return rows

    def export_player_roster_snapshot(self, *, limit: int | None = None, progress_callback: Any | None = None) -> dict[str, Any]:
        return self.export_player_roster_snapshot_for_items(self.scan_records("Players", limit=limit), progress_callback=progress_callback)

    def _read_player_snapshot_entry_value(self, item: RecordListItem, entry: FieldEntry) -> dict[str, Any]:
        return self._read_field_at_record_address("Players", item.address, entry.field)

    def export_player_roster_snapshot_for_items(
        self,
        items: Iterable[RecordListItem],
        *,
        progress_callback: Any | None = None,
        mode: str = "custom",
        placements: Iterable[dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        entries = tuple(self._portable_player_roster_entries())
        records: list[dict[str, Any]] = []
        selected_items = tuple(items)
        selected_placements = tuple(placements) if placements is not None else tuple(None for _item in selected_items)
        if len(selected_placements) != len(selected_items):
            raise ValueError("player roster placements must match exported items")
        total = len(selected_items)
        if progress_callback is not None:
            progress_callback(0, total, "Exporting player roster...")
        for current, (item, placement) in enumerate(zip(selected_items, selected_placements), start=1):
            fields: dict[str, dict[str, Any]] = {}
            for entry in entries:
                value = self._read_player_snapshot_entry_value(item, entry)
                fields[f"{entry.section}/{entry.normalized_name}"] = {
                    "display_value": _json_safe_roster_value(value.get("display_value")),
                    "raw_value": _json_safe_roster_value(value.get("raw_value")),
                }
            record: dict[str, Any] = {"index": item.index, "label": item.label, "fields": fields}
            if placement:
                record.update({key: _json_safe_roster_value(value) for key, value in placement.items()})
            records.append(record)
            if progress_callback is not None:
                progress_callback(current, total, f"Exporting roster: {current}/{total} players")
        return {
            "target_executable": self.target_executable,
            "domain": "Players",
            "mode": mode,
            "record_count": len(records),
            "records": records,
        }

    def _team_item_for_snapshot_row(self, row: dict[str, Any]) -> RecordListItem | None:
        team_index = row.get("team_index")
        if team_index is None:
            return None
        try:
            return self.loaded_items.get("Teams", {}).get(int(team_index))
        except (TypeError, ValueError):
            return None

    def _is_team_address_entry(self, entry: FieldEntry) -> bool:
        payload = self._field_version_payload(entry.field)
        return _type_key(payload) == "team_address_dropdown" or bool(payload.get("team_address_dropdown"))

    def _snapshot_write_value(self, row: dict[str, Any], entry: FieldEntry, payload: Any) -> Any:
        if self._is_team_address_entry(entry):
            team = self._team_item_for_snapshot_row(row)
            if team is not None:
                return int(team.address)
        if isinstance(payload, dict):
            return payload.get("display_value")
        return payload

    def _write_player_roster_snapshot_value(
        self,
        *,
        target_record_addr: int | None,
        entry: FieldEntry,
        index: int,
        value: Any,
        stat_selector: object | None = None,
    ) -> None:
        if stat_selector is not None and _is_player_selected_stat_detail_entry(entry):
            self.write_entry_value(entry, index=index, value=value, stat_selector=stat_selector)
            return
        if target_record_addr is not None:
            raw_value = self._write_field_at_record_address(entry.domain, int(target_record_addr), entry.field, value)
            self._data_version += 1
            if self._field_invalidates_player_filter_index(entry.domain, entry.field):
                self._invalidate_player_filter_index()
            if entry.domain == "Players" and _field_identity(entry.field.get("normalized_name") or entry.field.get("display_name")) == "CURRENTTEAM":
                try:
                    self._player_team_pointer_cache[index] = int(raw_value)
                except Exception:
                    self._player_team_pointer_cache.pop(index, None)
            return
        self.write_entry_value(entry, index=index, value=value, stat_selector=stat_selector)

    def apply_player_roster_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        limit: int | None = None,
        progress_callback: Any | None = None,
        target_items: Iterable[RecordListItem] | None = None,
        stat_selector: object | None = None,
        allow_stats: bool = False,
    ) -> dict[str, int]:
        entries = {f"{entry.section}/{entry.normalized_name}": entry for entry in self._portable_player_roster_entries()}
        records = snapshot.get("records") if isinstance(snapshot, dict) else None
        if not isinstance(records, list):
            raise ValueError("player roster snapshot is missing records")
        target_records = records[:limit]
        snapshot_mode = str(snapshot.get("mode") or "") if isinstance(snapshot, dict) else ""
        use_target_item_addresses = "Draft Class" in snapshot_mode
        target_item_tuple = tuple(target_items) if target_items is not None else None
        target_indices = tuple(item.index for item in target_item_tuple) if target_item_tuple is not None else None
        slot_target_indices: dict[tuple[int, str], int] = {}
        if target_indices is None and getattr(self, "loaded_items", {}).get("Teams"):
            for player, placement in self.player_roster_slot_items_for_team_items(getattr(self, "loaded_items", {}).get("Teams", {}).values()):
                slot_key = _field_identity(str(placement.get("team_slot_field") or f"PLAYER{placement.get('team_slot')}"))
                slot_target_indices[(int(placement["team_index"]), slot_key)] = int(player.index)
        total = len(target_records) if target_indices is None else min(len(target_records), len(target_indices))
        if progress_callback is not None:
            progress_callback(0, total, "Applying player roster snapshot...")
        attempted = 0
        succeeded = 0
        failed = 0
        skipped = 0
        placement_attempted = 0
        placement_succeeded = 0
        placement_failed = 0
        for current, row in enumerate(target_records, start=1):
            if not isinstance(row, dict):
                skipped += 1
                continue
            fields = row.get("fields")
            if not isinstance(fields, dict):
                skipped += 1
                continue
            has_team_slot = row.get("team_slot") is not None or row.get("team_slot_field") is not None
            if target_indices is not None:
                if current > len(target_indices):
                    skipped += len(fields)
                    continue
                target_item = target_item_tuple[current - 1] if target_item_tuple is not None else None
                index = target_indices[current - 1]
                target_record_addr = target_item.address if use_target_item_addresses and target_item is not None else None
            elif has_team_slot:
                slot_key = _field_identity(str(row.get("team_slot_field") or f"PLAYER{row.get('team_slot')}"))
                index = None
                team_index = row.get("team_index")
                if team_index is not None:
                    try:
                        index = slot_target_indices.get((int(team_index), slot_key))
                    except Exception:
                        index = None
                if index is None:
                    skipped += len(fields)
                    continue
                target_record_addr = None
            else:
                index_value = row.get("index")
                if index_value is None:
                    skipped += 1
                    continue
                try:
                    index = int(index_value)
                except Exception:
                    skipped += 1
                    continue
                target_record_addr = None
            for key, payload in fields.items():
                entry = entries.get(str(key))
                if entry is None:
                    skipped += 1
                    continue
                if entry.section == "Stats" and not allow_stats:
                    skipped += 1
                    continue
                value = self._snapshot_write_value(row, entry, payload)
                attempted += 1
                try:
                    self._write_player_roster_snapshot_value(
                        target_record_addr=target_record_addr,
                        entry=entry,
                        index=index,
                        value=value,
                        stat_selector=stat_selector,
                    )
                    succeeded += 1
                except Exception:
                    failed += 1
            if progress_callback is not None:
                progress_callback(min(current, total), total, f"Applying roster: {min(current, total)}/{total} players")
        return {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "placement_attempted": placement_attempted,
            "placement_succeeded": placement_succeeded,
            "placement_failed": placement_failed,
        }

    def _portable_player_roster_entries(self) -> list[FieldEntry]:
        entries: list[FieldEntry] = []
        for groups in self.grouped_fields("Players").values():
            for group_entries in groups.values():
                for entry in group_entries:
                    try:
                        payload = self._field_version_payload(entry.field)
                    except Exception:
                        continue
                    if payload.get("readonly") or not _implemented_payload(payload):
                        continue
                    if _type_key(payload) in {"pointer", "address", *_ADDRESS_DROPDOWN_TYPES}:
                        continue
                    entries.append(entry)
        return entries

    def domain_base(self, domain: str) -> int:
        base_key = self._domain_base_key(domain)
        return resolve_base_pointer_entry(
            self.memory,
            self._base_pointer_entry(base_key),
            label=domain,
            apply_final_offset_without_module_base=False,
            follow_chain=False,
        )

    def domain_stride(self, domain: str) -> int:
        config = self._active_config()
        stride_key = self._domain_stride_key(domain)
        game_info = config["game_info"]
        if stride_key not in game_info:
            raise KeyError(f"game_info is missing {stride_key}")
        stride = int(game_info[stride_key])
        if stride <= 0:
            raise ValueError(f"stride for {domain} must be greater than zero")
        return stride

    def record_address(self, domain: str, index: int) -> int:
        return record_address(base=self.domain_base(domain), index=index, stride=self.domain_stride(domain))

    def _team_stats_edit_record_address(self, index: int) -> int:
        base = resolve_base_pointer_entry(
            self.memory,
            self._base_pointer_entry("TeamStatsEdit"),
            label="TeamStatsEdit",
            apply_final_offset_without_module_base=False,
            follow_chain=False,
        )
        return record_address(base=base, index=index, stride=self._stride_value("teamStatsEditSize"))

    def _field_version_payload(self, field: dict[str, Any]) -> dict[str, Any]:
        versions = field.get("versions")
        if not isinstance(versions, dict):
            raise KeyError("field is missing authored versions")
        try:
            target, _raw_key, payload = offsets_mod._select_active_version(versions, self.target_executable, require_hint=True)
        except StopIteration as exc:
            raise KeyError(f"field has no active version for {self.target_executable}") from exc
        if not isinstance(payload, dict):
            raise TypeError(f"selected payload for {target} must be an object")
        return payload

    def read_value(self, domain: str, *, index: int, field: dict[str, Any]) -> dict[str, Any]:
        return self._read_field_at_record_address(domain, self.record_address(domain, index), field)

    def write_value(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> None:
        raw_value = self._write_field_at_record_address(domain, self.record_address(domain, index), field, value)
        self._data_version += 1
        if self._field_invalidates_player_filter_index(domain, field):
            self._invalidate_player_filter_index()
        if domain == "Players" and _field_identity(field.get("normalized_name") or field.get("display_name")) == "CURRENTTEAM":
            try:
                self._player_team_pointer_cache[index] = int(raw_value)
            except Exception:
                self._player_team_pointer_cache.pop(index, None)


def verify_edits(*, target_executable: str | None = None) -> dict[str, Any]:
    model = EditorDataModel(target_executable=target_executable)
    domains: dict[str, dict[str, Any]] = {}
    for domain in EDITOR_DOMAINS:
        grouped = model.grouped_fields(domain)
        fields = [entry for groups in grouped.values() for entries in groups.values() for entry in entries]
        implemented = 0
        writable = 0
        implementation_required = 0
        readonly = 0
        for entry in fields:
            payload = model._field_version_payload(entry.field)
            if payload.get("readonly"):
                readonly += 1
            implemented_flag = _implemented_payload(payload)
            if implemented_flag:
                implemented += 1
                if not payload.get("readonly"):
                    writable += 1
            else:
                implementation_required += 1
        domains[domain] = {
            "sections": len(grouped),
            "groups": sum(len(groups) for groups in grouped.values()),
            "fields": len(fields),
            "implemented_fields": implemented,
            "writable_fields": writable,
            "readonly_fields": readonly,
            "implementation_required_fields": implementation_required,
        }
    return {
        "target_executable": model.target_executable,
        "attached": bool(model.memory.hproc),
        "domains": domains,
    }


__all__ = [
    "EDITOR_DOMAINS",
    "EditorDataModel",
    "FieldEntry",
    "RecordListItem",
    "record_address",
    "target_display_label",
    "verify_edits",
]
