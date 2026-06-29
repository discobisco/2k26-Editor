from __future__ import annotations

import queue
import re
import threading
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

_DOMAIN_BASE_KEYS: dict[str, str] = {
    "Players": "Player",
    "Draft Class": "DraftClass",
    "Teams": "Team",
    "Staff": "Staff",
    "Stadiums": "Stadium",
    "Jerseys": "Jersey",
    "NBA History": "NBAHistory",
    "NBA Records": "Record",
    "Shoes": "Shoes",
}

EDITOR_DOMAINS: tuple[str, ...] = tuple(domain for domain in _DOMAIN_BASE_KEYS if domain != "Draft Class")
_MODEL_DOMAINS: tuple[str, ...] = tuple(_DOMAIN_BASE_KEYS)

_SPARSE_SCAN_INVALID_STREAKS: dict[str, int] = {
    "NBA Records": 12,
}

_LABEL_FIELD_NAMES: dict[str, tuple[str, ...]] = {
    "Players": ("FIRSTNAME", "LASTNAME"),
    "Draft Class": ("FIRSTNAME", "LASTNAME"),
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
PLAYER_TEAM_FILTER_DRAFT_CLASS = "Draft Class"


def _plausible_record_name_part(value: object) -> bool:
    text = str(value or "").strip()
    if len(text) < 2:
        return False
    return any(char.isalpha() for char in text) and all(char.isalpha() or char in " .'-" for char in text)


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
        self.loaded_items: dict[str, dict[str, RecordListItem]] = {domain: {} for domain in _MODEL_DOMAINS}
        self.selected_items: dict[str, RecordListItem | None] = {domain: None for domain in _MODEL_DOMAINS}
        self.domain_statuses: dict[str, str] = {domain: self.runtime_status_text() for domain in _MODEL_DOMAINS}
        self.refresh_events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.refresh_thread: threading.Thread | None = None
        self._history_screen_rows: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._record_screen_rows: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._layout_cache: dict[str, dict[str, Any]] = {}
        self._field_entries_cache: dict[str, tuple[FieldEntry, ...]] = {}
        self._field_context_cache: dict[str, dict[int, tuple[str, str]]] = {}
        self._field_lookup_cache: dict[str, dict[str, FieldEntry]] = {}
        self._player_team_pointer_cache: dict[int, int] = {}

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
        self.loaded_items = {domain: {} for domain in _MODEL_DOMAINS}
        self.selected_items = {domain: None for domain in _MODEL_DOMAINS}
        self.last_status = self.runtime_status_text()
        self.domain_statuses = {domain: self.last_status for domain in _MODEL_DOMAINS}

    def domain_status(self, domain: str) -> str:
        return self.domain_statuses.get(domain, self.runtime_status_text())

    def domain_item_labels(self, domain: str) -> list[str]:
        return list(self.loaded_items[domain])

    def domain_item_count(self, domain: str) -> int:
        return len(self.loaded_items[domain])

    def player_team_filter_options(self) -> tuple[str, ...]:
        return (PLAYER_TEAM_FILTER_ALL, PLAYER_TEAM_FILTER_BASE_TEAMS, PLAYER_TEAM_FILTER_DRAFT_CLASS, *self.domain_item_labels("Teams"))

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

    def _player_current_team_pointer(self, item: RecordListItem) -> int:
        if item.index not in self._player_team_pointer_cache:
            self._player_team_pointer_cache[item.index] = self._read_player_current_team_pointer(item)
        return self._player_team_pointer_cache[item.index]

    def _base_team_items(self) -> tuple[RecordListItem, ...]:
        return tuple(
            team
            for team in self.loaded_items.get("Teams", {}).values()
            if 0 <= int(team.index) <= 29
        )

    def _base_team_player_items(self) -> dict[str, RecordListItem]:
        rows = self.player_roster_slot_items_for_team_items(self._base_team_items())
        players: dict[str, RecordListItem] = {}
        for player, _placement in rows:
            players.setdefault(player.display_label, player)
        return players

    def _ensure_draft_class_items_loaded(self) -> None:
        if self.loaded_items.get("Draft Class"):
            return
        self.refresh_domain_items("Draft Class")

    def _player_filter_items(self, selected_team_label: str | None) -> dict[str, RecordListItem]:
        selected = str(selected_team_label or "").strip()
        if selected == PLAYER_TEAM_FILTER_BASE_TEAMS:
            return self._base_team_player_items()
        if selected == PLAYER_TEAM_FILTER_DRAFT_CLASS:
            self._ensure_draft_class_items_loaded()
            return self.loaded_items.get("Draft Class", {})
        return self.loaded_items.get("Players", {})

    def player_items_for_team_filter(self, selected_team_label: str | None) -> dict[str, RecordListItem]:
        return self._player_filter_items(selected_team_label)

    def player_item_labels_for_team_filter(self, selected_team_label: str | None, search_text: str | None = None) -> list[str]:
        selected = str(selected_team_label or "").strip()
        query = str(search_text or "").strip().lower()
        if selected in {PLAYER_TEAM_FILTER_BASE_TEAMS, PLAYER_TEAM_FILTER_DRAFT_CLASS}:
            labels = list(self._player_filter_items(selected))
        elif not selected or selected == PLAYER_TEAM_FILTER_ALL:
            labels = self.domain_item_labels("Players")
        else:
            team = self.loaded_items["Teams"].get(selected)
            if team is None:
                return []
            labels = [
                label
                for label, player in self.loaded_items["Players"].items()
                if self._player_current_team_pointer(player) == team.address
            ]
        if not query:
            return labels
        return [label for label in labels if query in label.lower()]

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

    def select_item_by_label(self, domain: str, selected_label: str | None) -> RecordListItem | None:
        selected = str(selected_label or "")
        if domain == "Players" and selected and selected not in self.loaded_items["Players"]:
            self._ensure_draft_class_items_loaded()
            draft_item = self.loaded_items.get("Draft Class", {}).get(selected)
            if draft_item is not None:
                self.selected_items[domain] = draft_item
                self.selected_items["Draft Class"] = draft_item
                return draft_item
        self.selected_items[domain] = self.loaded_items[domain].get(selected)
        return self.selected_items[domain]

    def refresh_domain_items(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:
        try:
            items = self.scan_records(domain, limit=limit)
            by_label = {item.display_label: item for item in items}
            self.loaded_items[domain] = by_label
            if domain == "Players":
                self._player_team_pointer_cache.clear()
            labels = list(by_label)
            if labels:
                current = self.selected_items.get(domain)
                selected_label = current.display_label if current is not None else labels[0]
                self.selected_items[domain] = by_label.get(selected_label, by_label[labels[0]])
                self.domain_statuses[domain] = f"loaded {len(labels)} {domain.lower()} records"
            else:
                self.selected_items[domain] = None
                self.domain_statuses[domain] = self.runtime_status_text()
            return items
        except Exception as exc:
            self.loaded_items[domain] = {}
            self.selected_items[domain] = None
            if domain == "Players":
                self._player_team_pointer_cache.clear()
            self.domain_statuses[domain] = self.runtime_status_text() if "not attached" in str(exc).lower() else f"scan failed: {exc}"
            return []

    def start_background_refresh(self, domains: tuple[str, ...]) -> bool:
        if self.refresh_thread is not None and self.refresh_thread.is_alive():
            return False
        self.refresh_thread = threading.Thread(target=self._background_refresh_worker, args=(domains,), name="nba2k-editor-model-refresh", daemon=True)
        self.refresh_thread.start()
        return True

    def _background_refresh_worker(self, domains: tuple[str, ...]) -> None:
        try:
            self.attach()
            self.refresh_events.put(("status", ""))
            for domain in domains:
                self.domain_statuses[domain] = "Loading records..."
                self.refresh_events.put(("start", domain))
                self.refresh_domain_items(domain)
                self.refresh_events.put(("domain", domain))
        except Exception as exc:
            self.refresh_events.put(("error", str(exc)))
        finally:
            self.refresh_events.put(("done", ""))

    def pop_refresh_events(self) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        while True:
            try:
                events.append(self.refresh_events.get_nowait())
            except queue.Empty:
                return events

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
    ) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        if domain == "NBA Records" and record_row_start is not None:
            max_rows = min(limit, int(record_row_count) if record_row_count is not None else limit)
            for offset in range(max_rows):
                record_addr = self.record_address(domain, int(record_row_start) + offset)
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

    def selected_player_detail_values(self) -> dict[str, str]:
        item = self.selected_items["Players"]
        read_domain = item.domain if item is not None and item.domain == "Draft Class" else "Players"
        return {label: self._read_named_value(read_domain, item, candidates) for label, candidates in PLAYER_DETAIL_FIELD_SPECS}

    def selected_team_summary_values(self) -> dict[str, str]:
        item = self.selected_items["Teams"]
        return {label: self._read_named_value("Teams", item, candidates) for label, candidates in TEAM_SUMMARY_FIELD_SPECS}

    def save_selected_team_summary(self, values: dict[str, str]) -> tuple[int, int]:
        item = self.selected_items["Teams"]
        if item is None:
            raise RuntimeError("select a team first")
        saved = 0
        failed = 0
        for label, candidates in TEAM_SUMMARY_FIELD_SPECS:
            entry = None
            for name in candidates:
                entry = self._field_by_normalized_name("Teams", name)
                if entry is not None:
                    break
            if entry is None:
                failed += 1
                continue
            try:
                self.write_entry_value(entry, index=item.index, value=values.get(label, ""))
                saved += 1
            except Exception:
                failed += 1
        return saved, failed

    def _record_data_entry(self) -> FieldEntry:
        entry = self._field_by_normalized_name("NBA Records", "DATA")
        if entry is None:
            raise KeyError("NBA Records DATA field is missing")
        return entry

    def save_record_data_values(self, values_by_index: dict[int, Any]) -> int:
        entry = self._record_data_entry()
        saved = 0
        for index, value in values_by_index.items():
            self.write_entry_value(entry, index=int(index), value=value)
            saved += 1
        return saved

    def zero_record_data_values(self, indexes: Iterable[int]) -> int:
        return self.save_record_data_values({int(index): 0 for index in indexes})

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
                return bool(labels)
            try:
                raw_type = int(self._read_field_at_record_address(domain, record_addr, type_entry.field)["raw_value"])
            except Exception:
                return False
            if raw_type <= 0:
                return False
            return any(_has_alpha_text(value) for value in values)
        return bool(labels)

    def _domain_record_count_limit(self, domain: str) -> int | None:
        try:
            count = int(self._base_pointer_entry(self._domain_base_key(domain)).get("record_count") or 0)
        except Exception:
            return None
        return count if count > 0 else None

    def scan_records(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:
        if not self.memory.hproc or not self.memory.base_addr:
            raise RuntimeError(f"not attached to {self.target_executable}")
        explicit_limit = int(limit) if limit is not None else self._domain_record_count_limit(domain)
        base = self.domain_base(domain)
        stride = self.domain_stride(domain)
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

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:
        if stat_selector is not None and _is_player_selected_stat_detail_entry(entry):
            return self._read_field_at_record_address(
                entry.domain,
                self._player_season_stat_detail_base_address(entry, index, stat_selector),
                entry.field,
            )
        return self.read_value(entry.domain, index=index, field=entry.field)

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any, stat_selector: object | None = None) -> None:
        if stat_selector is not None and _is_player_selected_stat_detail_entry(entry):
            record_addr = self._player_season_stat_detail_base_address(entry, index, stat_selector)
            self._write_field_at_record_address(entry.domain, record_addr, entry.field, value)
            return
        self.write_value(entry.domain, index=index, field=entry.field, value=value)

    def reset_player_editor_values(self, *, index: int, stat_selector: object | None = None) -> dict[str, int]:
        attempted = 0
        succeeded = 0
        failed = 0
        for groups in self.grouped_fields("Players").values():
            for entries in groups.values():
                for entry in entries:
                    value = self._player_editor_reset_value(entry)
                    if value is None:
                        continue
                    attempted += 1
                    try:
                        self.write_entry_value(entry, index=index, value=value, stat_selector=stat_selector)
                        succeeded += 1
                    except Exception:
                        failed += 1
        return {"attempted": attempted, "succeeded": succeeded, "failed": failed}

    def _player_editor_reset_value(self, entry: FieldEntry) -> int | str | None:
        if entry.domain != "Players":
            return None
        normalized = str(entry.normalized_name).upper()
        if normalized == "FIRSTNAME":
            return "A"
        if normalized == "LASTNAME":
            return "Z"
        if normalized == "BIRTHYEAR":
            return 2006
        if entry.section == "Attributes":
            return 25
        if entry.section == "Tendencies":
            return 0
        if entry.section == "Badges":
            return 0
        if _is_player_season_id_selector_entry(entry):
            return 65535
        return None

    def export_player_roster_snapshot(self, *, limit: int | None = None, progress_callback: Any | None = None) -> dict[str, Any]:
        return self.export_player_roster_snapshot_for_items(self.scan_records("Players", limit=limit), progress_callback=progress_callback)

    def _read_player_snapshot_entry_value(self, item: RecordListItem, entry: FieldEntry) -> dict[str, Any]:
        if item.domain == "Draft Class":
            return self._read_field_at_record_address("Draft Class", item.address, entry.field)
        return self.read_entry_value(entry, index=item.index)

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
            "domain": "Draft Class" if selected_items and all(item.domain == "Draft Class" for item in selected_items) else "Players",
            "mode": mode,
            "record_count": len(records),
            "records": records,
        }

    def _team_item_for_snapshot_row(self, row: dict[str, Any]) -> RecordListItem | None:
        team_index = row.get("team_index")
        if team_index is not None:
            try:
                wanted_index = int(team_index)
            except Exception:
                wanted_index = None
            if wanted_index is not None:
                for team in self.loaded_items.get("Teams", {}).values():
                    if int(team.index) == wanted_index:
                        return team
        team_label = str(row.get("team_label") or "").strip()
        if team_label:
            return self.loaded_items.get("Teams", {}).get(team_label)
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

    def apply_player_roster_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        limit: int | None = None,
        progress_callback: Any | None = None,
        target_items: Iterable[RecordListItem] | None = None,
    ) -> dict[str, int]:
        entries = {f"{entry.section}/{entry.normalized_name}": entry for entry in self._portable_player_roster_entries()}
        records = snapshot.get("records") if isinstance(snapshot, dict) else None
        if not isinstance(records, list):
            raise ValueError("player roster snapshot is missing records")
        target_records = records[:limit]
        target_item_tuple = tuple(target_items) if target_items is not None else None
        target_indices = tuple(item.index for item in target_item_tuple) if target_item_tuple is not None else None
        slot_target_indices: dict[tuple[object, str], int] = {}
        if target_indices is None:
            for player, placement in self.player_roster_slot_items_for_team_items(self.loaded_items.get("Teams", {}).values()):
                slot_key = _field_identity(str(placement.get("team_slot_field") or f"PLAYER{placement.get('team_slot')}"))
                slot_target_indices[(int(placement["team_index"]), slot_key)] = int(player.index)
                slot_target_indices[(str(placement["team_label"]), slot_key)] = int(player.index)
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
                target_domain = target_item.domain if target_item is not None else "Players"
                target_record_addr = target_item.address if target_item is not None else None
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
                    team_label = str(row.get("team_label") or "").strip()
                    if team_label:
                        index = slot_target_indices.get((team_label, slot_key))
                if index is None:
                    skipped += len(fields)
                    continue
                target_domain = "Players"
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
                target_domain = "Players"
                target_record_addr = None
            for key, payload in fields.items():
                entry = entries.get(str(key))
                if entry is None:
                    skipped += 1
                    continue
                value = self._snapshot_write_value(row, entry, payload)
                attempted += 1
                try:
                    if target_domain == "Draft Class" and target_record_addr is not None:
                        self._write_field_at_record_address("Draft Class", int(target_record_addr), entry.field, value)
                    else:
                        self.write_entry_value(entry, index=index, value=value)
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
