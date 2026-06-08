from __future__ import annotations

import queue
import re
import struct
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable

from nba2k_editor.core import offsets as offsets_mod
from nba2k_editor.core.conversions import (
    convert_kilograms_to_pounds,
    convert_minmax_potential_to_raw,
    convert_pounds_to_kilograms,
    convert_rating_to_raw,
    convert_raw_to_minmax_potential,
    convert_raw_to_rating,
    convert_raw_to_year,
    convert_rating_to_tendency_raw,
    convert_tendency_raw_to_rating,
    convert_year_to_raw,
    height_inches_to_raw,
    is_year_offset_field,
    normalize_weight_value,
    raw_height_to_inches,
    to_int,
)
from nba2k_editor.memory.game_memory import GameMemory

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

_SPARSE_SCAN_INVALID_STREAKS: dict[str, int] = {
    "NBA Records": 12,
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


@dataclass(frozen=True)
class FieldEntry:
    domain: str
    section: str
    group: str
    ordinal: int
    field: dict[str, Any]

    @property
    def normalized_name(self) -> str:
        return str(self.field.get("normalized_name") or self.field.get("display_name") or self.ordinal)

    @property
    def display_name(self) -> str:
        return str(self.field.get("display_name") or self.normalized_name)


@dataclass(frozen=True)
class RecordListItem:
    domain: str
    index: int
    address: int
    label: str

    @property
    def display_label(self) -> str:
        return f"[{self.index}] {self.label}"


def _iter_layout_fields(domain: str, layout: dict[str, Any]) -> Iterable[FieldEntry]:
    ordinal = 0
    for section, groups in layout.items():
        if not isinstance(groups, dict):
            raise TypeError(f"layout section {domain}/{section} must contain groups")
        for group, fields in groups.items():
            if not isinstance(fields, list):
                raise TypeError(f"layout group {domain}/{section}/{group} must contain fields")
            for field in fields:
                if not isinstance(field, dict):
                    raise TypeError(f"layout field {domain}/{section}/{group}/{ordinal} must be an object")
                yield FieldEntry(domain=domain, section=str(section), group=str(group), ordinal=ordinal, field=field)
                ordinal += 1

_IMPLEMENTATION_REQUIRED_FLAGS = {
    "from_address_dropdown",
    "offset2",
}

_ADDRESS_DROPDOWN_TYPES: dict[str, str] = {
    "team_address_dropdown": "Teams",
    "stadium_address_dropdown": "Stadiums",
    "uniform_dropdown": "Jerseys",
}


def record_address(*, base: int, index: int, stride: int) -> int:
    """Return the absolute record address for a zero-based record number."""
    if index < 0:
        raise ValueError("index must be zero or greater")
    if stride <= 0:
        raise ValueError("stride must be greater than zero")
    return int(base) + int(index) * int(stride)


def _field_offset(payload: dict[str, Any]) -> int:
    if "address" not in payload:
        raise KeyError("authored payload is missing address")
    return to_int(payload["address"])


def _type_key(payload: dict[str, Any]) -> str:
    return str(payload.get("type") or "").strip().lower()


def _implemented_payload(payload: dict[str, Any]) -> bool:
    type_key = _type_key(payload)
    if type_key == "result_score":
        return "offset2" in payload
    if _IMPLEMENTATION_REQUIRED_FLAGS & set(payload):
        return False
    return type_key in {
        "uint",
        "number",
        "integer",
        "byte",
        "ubyte",
        "ushort",
        "uint64",
        "ulonglong",
        "pointer",
        "address",
        "combo",
        "dropdown",
        "slider",
        "bit",
        "bitfield",
        "float",
        "string",
        "wstring",
        "binary",
        "hex_bytes",
        "color",
        *_ADDRESS_DROPDOWN_TYPES,
    }


def _readable_payload(payload: dict[str, Any]) -> bool:
    if _implemented_payload(payload):
        return True
    return _type_key(payload) == "ptr_string" and "offset2" not in payload


_FIXED_NUMERIC_TYPE_WIDTHS: dict[str, int] = {
    "byte": 1,
    "ubyte": 1,
    "ushort": 2,
    "uint": 4,
    "uint64": 8,
    "ulonglong": 8,
    "pointer": 8,
    "address": 8,
    "team_address_dropdown": 8,
    "stadium_address_dropdown": 8,
    "uniform_dropdown": 8,
}


def _numeric_width(payload: dict[str, Any]) -> int:
    explicit_bytes = to_int(payload.get("byteLength"))
    if explicit_bytes > 0:
        return explicit_bytes
    authored_length = offsets_mod._resolved_length_bits(payload)
    if authored_length > 0:
        return authored_length
    type_width = _FIXED_NUMERIC_TYPE_WIDTHS.get(_type_key(payload))
    if type_width:
        return type_width
    raise KeyError("authored payload is missing length, bit_length, or byteLength")


def _bit_window(payload: dict[str, Any]) -> tuple[int, int, int]:
    bit_offset = to_int(payload.get("bit_offset")) or to_int(payload.get("startBit"))
    bit_length = offsets_mod._resolved_length_bits(payload)
    if bit_length <= 0:
        raise KeyError("authored bitfield payload is missing length, bit_length, or byteLength")
    width = _numeric_width(payload)
    return bit_offset, bit_length, width


def _read_bitfield(memory: Any, address: int, payload: dict[str, Any]) -> int:
    bit_offset, bit_length, width = _bit_window(payload)
    raw_int = int.from_bytes(memory.read_bytes(address, width), "little")
    mask = (1 << bit_length) - 1
    return (raw_int >> bit_offset) & mask


def _write_bitfield(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None:
    bit_offset, bit_length, width = _bit_window(payload)
    raw_int = int.from_bytes(memory.read_bytes(address, width), "little")
    mask = ((1 << bit_length) - 1) << bit_offset
    new_int = (raw_int & ~mask) | ((int(value) << bit_offset) & mask)
    memory.write_bytes(address, new_int.to_bytes(width, "little"))


def _field_identity(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _field_display_or_name(field: dict[str, Any]) -> str:
    return str(field.get("display_name") or field.get("normalized_name") or "")


def _uses_bitfield_io(payload: dict[str, Any]) -> bool:
    type_key = _type_key(payload)
    if type_key in {"bit", "bitfield"}:
        return True
    has_bit_offset = "bit_offset" in payload or "startBit" in payload
    return type_key in {"number", "integer", "binary"} and has_bit_offset and offsets_mod._resolved_length_bits(payload) > 0


def _list_mapping_value(raw_value: Any, options: object) -> Any | None:
    if not isinstance(options, list):
        return None
    try:
        index = int(raw_value)
    except Exception:
        return None
    if 0 <= index < len(options):
        return options[index]
    return None


def _reverse_list_mapping(value: Any, options: object) -> int | None:
    if not isinstance(options, list):
        return None
    text = str(value)
    for index, option in enumerate(options):
        if text == str(option):
            return index
    return None


def _mapped_display_value(payload: dict[str, Any], raw_value: Any) -> Any | None:
    values = payload.get("values")
    mapped = _list_mapping_value(raw_value, values)
    if mapped is not None:
        return mapped
    dropdown = payload.get("dropdown")
    mapped = _list_mapping_value(raw_value, dropdown)
    if mapped is not None:
        return mapped
    mapping = payload.get("value_mapping")
    if isinstance(mapping, dict):
        if raw_value in mapping:
            return mapping[raw_value]
        raw_key = str(raw_value)
        if raw_key in mapping:
            return mapping[raw_key]
    return None


def _mapped_raw_value(payload: dict[str, Any], value: Any) -> Any | None:
    mapped = _reverse_list_mapping(value, payload.get("values"))
    if mapped is not None:
        return mapped
    mapped = _reverse_list_mapping(value, payload.get("dropdown"))
    if mapped is not None:
        return mapped
    mapping = payload.get("value_mapping")
    if isinstance(mapping, dict):
        text = str(value)
        for raw_key, display in mapping.items():
            if text == str(display):
                return to_int(raw_key)
    return None


def _raw_to_display_value(section: str, field: dict[str, Any], payload: dict[str, Any], raw_value: Any) -> Any:
    type_key = _type_key(payload)
    if type_key == "color" and isinstance(raw_value, (bytes, bytearray)):
        return _color_hex(bytes(raw_value))
    if type_key == "result_score" and isinstance(raw_value, tuple) and len(raw_value) == 2:
        return _format_result_score(raw_value)
    mapped = _mapped_display_value(payload, raw_value)
    if mapped is not None:
        return mapped
    field_name = _field_display_or_name(field)
    field_id = _field_identity(field_name)
    length_bits = offsets_mod._resolved_length_bits(payload)
    if "season_year_base" in payload:
        start_year = to_int(payload.get("season_year_base")) + int(raw_value)
        if bool(payload.get("season_range")):
            return f"{start_year}-{start_year + 1}"
        return start_year
    if "year_map_base" in payload or is_year_offset_field(field_name):
        return convert_raw_to_year(int(raw_value), to_int(payload.get("year_map_base")) or 1900)
    if field_id == "HEIGHT":
        return raw_height_to_inches(int(raw_value))
    if bool(payload.get("div100")):
        return int(raw_value) / 100
    if bool(payload.get("from_pounds")):
        return convert_pounds_to_kilograms(raw_value)
    if "scale" in payload:
        return float(raw_value) * float(payload.get("scale") or 1)
    if section in {"Attributes", "Durability"}:
        return convert_raw_to_rating(int(raw_value), length_bits)
    if section == "Tendencies":
        return convert_tendency_raw_to_rating(int(raw_value), length_bits)
    if _field_identity(field_name) in {"MINPOTENTIAL", "MAXPOTENTIAL", "MINIMUMPOTENTIAL", "MAXIMUMPOTENTIAL"}:
        return convert_raw_to_minmax_potential(int(raw_value), length_bits)
    return raw_value


def _display_to_raw_value(section: str, field: dict[str, Any], payload: dict[str, Any], value: Any) -> Any:
    type_key = _type_key(payload)
    if type_key == "color":
        return _parse_color_value(value, _numeric_width(payload))
    if type_key == "result_score":
        return _parse_result_score(value)
    mapped = _mapped_raw_value(payload, value)
    if mapped is not None:
        return mapped
    field_name = _field_display_or_name(field)
    field_id = _field_identity(field_name)
    length_bits = offsets_mod._resolved_length_bits(payload)
    if "season_year_base" in payload:
        text = str(value)
        start_text = text.split("-", 1)[0].strip()
        return int(start_text) - to_int(payload.get("season_year_base"))
    if "year_map_base" in payload or is_year_offset_field(field_name):
        return convert_year_to_raw(int(value), to_int(payload.get("year_map_base")) or 1900)
    if field_id == "HEIGHT":
        return height_inches_to_raw(int(value))
    if field_id == "WEIGHT":
        normalized_weight = normalize_weight_value(value)
        return normalized_weight if normalized_weight is not None else value
    if bool(payload.get("div100")):
        return int(round(float(value) * 100))
    if bool(payload.get("from_pounds")):
        return convert_kilograms_to_pounds(value)
    if "scale" in payload:
        scale = float(payload.get("scale") or 1)
        return float(value) / scale if scale else value
    if section in {"Attributes", "Durability"}:
        return convert_rating_to_raw(float(value), length_bits)
    if section == "Tendencies":
        return convert_rating_to_tendency_raw(float(value), length_bits)
    if _field_identity(field_name) in {"MINPOTENTIAL", "MAXPOTENTIAL", "MINIMUMPOTENTIAL", "MAXIMUMPOTENTIAL"}:
        return convert_minmax_potential_to_raw(float(value), length_bits)
    return value



def _string_length(payload: dict[str, Any]) -> int:
    length = to_int(payload.get("length"))
    if length <= 0:
        raise KeyError("authored string payload is missing length")
    return length


def _read_string(memory: Any, address: int, payload: dict[str, Any]) -> str:
    max_chars = _string_length(payload)
    if _type_key(payload) == "wstring":
        return memory.read_wstring(address, max_chars)
    if hasattr(memory, "read_ascii"):
        return memory.read_ascii(address, max_chars)
    raw = memory.read_bytes(address, max_chars)
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore")


def _write_string(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None:
    max_chars = _string_length(payload)
    text = str(value)
    if _type_key(payload) == "wstring" and hasattr(memory, "write_wstring_fixed"):
        memory.write_wstring_fixed(address, text, max_chars)
        return
    if _type_key(payload) == "string" and hasattr(memory, "write_ascii_fixed"):
        memory.write_ascii_fixed(address, text, max_chars)
        return
    raw = text.encode("ascii", errors="ignore")[: max_chars - 1] + b"\x00"
    memory.write_bytes(address, raw.ljust(max_chars, b"\x00"))


def _read_ptr_string(memory: Any, address: int, payload: dict[str, Any]) -> str:
    pointer_size = int(getattr(memory, "pointer_size", 8) or 8)
    if pointer_size == 8 and hasattr(memory, "read_u64"):
        pointer = int(memory.read_u64(address))
    elif pointer_size == 4 and hasattr(memory, "read_uint32"):
        pointer = int(memory.read_uint32(address))
    else:
        pointer = int.from_bytes(memory.read_bytes(address, pointer_size), "little")
    if pointer <= 0:
        return ""
    string_payload = dict(payload)
    string_payload["type"] = "wstring" if bool(payload.get("unicode")) else "string"
    return _read_string(memory, pointer, string_payload)


def _result_score_addresses(address: int, payload: dict[str, Any]) -> tuple[int, int]:
    first_offset = _field_offset(payload)
    second_offset = to_int(payload.get("offset2"))
    if second_offset <= 0:
        raise KeyError("result_score payload is missing offset2")
    record_base = int(address) - first_offset
    return int(address), record_base + second_offset


def _coerce_result_component(value: float) -> int | float:
    rounded = round(float(value))
    return int(rounded) if abs(float(value) - rounded) < 0.0001 else float(value)


def _read_result_score(memory: Any, address: int, payload: dict[str, Any]) -> tuple[int | float, int | float]:
    first_address, second_address = _result_score_addresses(address, payload)
    first = struct.unpack("<f", memory.read_bytes(first_address, 4))[0]
    second = struct.unpack("<f", memory.read_bytes(second_address, 4))[0]
    return _coerce_result_component(first), _coerce_result_component(second)


def _parse_result_score(value: Any) -> tuple[float, float]:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return float(value[0]), float(value[1])
    text = str(value).strip()
    separator = "-" if "-" in text else ":" if ":" in text else None
    if separator is None:
        raise ValueError("result_score must be a two-part value like '1-0'")
    left, right = text.split(separator, 1)
    return float(left.strip()), float(right.strip())


def _format_result_component(value: int | float) -> str:
    numeric = float(value)
    rounded = round(numeric)
    return str(int(rounded)) if abs(numeric - rounded) < 0.0001 else f"{numeric:g}"


def _format_result_score(value: tuple[int | float, int | float]) -> str:
    return f"{_format_result_component(value[0])}-{_format_result_component(value[1])}"


def _color_hex(raw_value: bytes) -> str:
    return "#" + bytes(raw_value).hex().upper()


def _parse_color_value(value: Any, width: int) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    else:
        text = str(value).strip()
        if text.startswith("#"):
            text = text[1:]
        text = re.sub(r"[^0-9A-Fa-f]", "", text)
        raw = bytes.fromhex(text)
    if len(raw) != width:
        raise ValueError(f"color value must be exactly {width} bytes")
    return raw


def _read_authored_value(memory: Any, address: int, payload: dict[str, Any]) -> Any:
    if not _readable_payload(payload):
        raise NotImplementedError(f"authored type requires backend implementation: {payload.get('type')}")
    type_key = _type_key(payload)
    if _uses_bitfield_io(payload):
        return _read_bitfield(memory, address, payload)
    if type_key in {
        "uint",
        "number",
        "integer",
        "byte",
        "ubyte",
        "ushort",
        "uint64",
        "ulonglong",
        "pointer",
        "address",
        "combo",
        "dropdown",
        "slider",
        *_ADDRESS_DROPDOWN_TYPES,
    }:
        width = _numeric_width(payload)
        if width == 4 and hasattr(memory, "read_uint32"):
            return memory.read_uint32(address)
        if width == 8 and hasattr(memory, "read_u64"):
            return memory.read_u64(address)
        return int.from_bytes(memory.read_bytes(address, width), "little")
    if type_key == "float":
        return struct.unpack("<f", memory.read_bytes(address, 4))[0]
    if type_key in {"string", "wstring"}:
        return _read_string(memory, address, payload)
    if type_key == "ptr_string":
        return _read_ptr_string(memory, address, payload)
    if type_key == "result_score":
        return _read_result_score(memory, address, payload)
    if type_key == "color":
        return memory.read_bytes(address, _numeric_width(payload))
    if type_key in {"binary", "hex_bytes"}:
        return memory.read_bytes(address, _numeric_width(payload))
    raise NotImplementedError(f"authored type requires backend implementation: {payload.get('type')}")


def _write_authored_value(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None:
    if not _implemented_payload(payload):
        raise NotImplementedError(f"authored type requires backend implementation: {payload.get('type')}")
    type_key = _type_key(payload)
    if _uses_bitfield_io(payload):
        _write_bitfield(memory, address, payload, value)
    elif type_key in {
        "uint",
        "number",
        "integer",
        "byte",
        "ubyte",
        "ushort",
        "uint64",
        "ulonglong",
        "pointer",
        "address",
        "combo",
        "dropdown",
        "slider",
        *_ADDRESS_DROPDOWN_TYPES,
    }:
        width = _numeric_width(payload)
        if width == 4 and hasattr(memory, "write_uint32"):
            memory.write_uint32(address, int(value))
        else:
            memory.write_bytes(address, int(value).to_bytes(width, "little"))
    elif type_key == "float":
        memory.write_bytes(address, struct.pack("<f", float(value)))
    elif type_key in {"string", "wstring"}:
        _write_string(memory, address, payload, value)
    elif type_key == "result_score":
        first, second = _parse_result_score(value)
        first_address, second_address = _result_score_addresses(address, payload)
        memory.write_bytes(first_address, struct.pack("<f", first))
        memory.write_bytes(second_address, struct.pack("<f", second))
    elif type_key == "color":
        memory.write_bytes(address, _parse_color_value(value, _numeric_width(payload)))
    elif type_key in {"binary", "hex_bytes"}:
        width = _numeric_width(payload)
        raw = bytes(value)
        if len(raw) != width:
            raise ValueError(f"binary value must be exactly {width} bytes")
        memory.write_bytes(address, raw)
    else:
        raise NotImplementedError(f"authored type requires backend implementation: {payload.get('type')}")


class EditorDataModel:
    """Index-based backend model over offsets metadata and GameMemory reads/writes."""

    def __init__(
        self,
        *,
        memory: GameMemory | Any | None = None,
        offsets_api: Any = offsets_mod,
        target_executable: str | None = None,
    ) -> None:
        fallback_target = str(getattr(offsets_api, "MODULE_NAME", "NBA2K26.exe") or "NBA2K26.exe")
        if target_executable and target_executable != "auto":
            selected_target = target_executable
        else:
            selected_target = GameMemory.detect_running_module_name(fallback_target) or fallback_target
        self.memory = memory if memory is not None else GameMemory(selected_target)
        self.offsets = offsets_api
        self.target_executable = selected_target
        self.last_status = "not attached"
        self.loaded_items: dict[str, dict[str, RecordListItem]] = {domain: {} for domain in EDITOR_DOMAINS}
        self.selected_items: dict[str, RecordListItem | None] = {domain: None for domain in EDITOR_DOMAINS}
        self.domain_statuses: dict[str, str] = {domain: self.runtime_status_text() for domain in EDITOR_DOMAINS}
        self.refresh_events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.refresh_thread: threading.Thread | None = None
        self._layout_cache: dict[str, dict[str, Any]] = {}
        self._field_entries_cache: dict[str, tuple[FieldEntry, ...]] = {}
        self._field_context_cache: dict[str, dict[int, tuple[str, str]]] = {}
        self._field_lookup_cache: dict[str, dict[str, FieldEntry]] = {}
        self._player_team_pointer_cache: dict[int, int | None] = {}

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
        wanted_name = _field_identity(field.get("normalized_name") or field.get("display_name"))
        wanted_display = _field_identity(field.get("display_name") or field.get("normalized_name"))
        lookup = self._field_lookup(domain)
        for key in (wanted_name, wanted_display):
            entry = lookup.get(key)
            if entry is not None:
                return entry.section, entry.group
        return "", ""

    def _field_by_display_or_normalized_name(self, domain: str, name: object) -> FieldEntry | None:
        return self._field_lookup(domain).get(_field_identity(name))

    def _field_address(self, domain: str, record_addr: int, field: dict[str, Any], payload: dict[str, Any]) -> int:
        base_address = record_addr
        parent_name = payload.get("parent")
        if parent_name:
            parent_entry = self._field_by_display_or_normalized_name(domain, parent_name)
            if parent_entry is None:
                raise KeyError(f"missing parent field: {parent_name}")
            parent_payload = self._field_version_payload(parent_entry.field)
            base_address += _field_offset(parent_payload)
        address = base_address + _field_offset(payload)
        if bool(payload.get("requiresDereference")):
            pointer_size = int(getattr(self.memory, "pointer_size", 8) or 8)
            dereference_offset = to_int(payload.get("dereferenceAddress"))
            pointer_slot = base_address + dereference_offset if dereference_offset else address
            if pointer_size == 8 and hasattr(self.memory, "read_u64"):
                pointer = self.memory.read_u64(pointer_slot)
            elif pointer_size == 4 and hasattr(self.memory, "read_uint32"):
                pointer = self.memory.read_uint32(pointer_slot)
            else:
                pointer = int.from_bytes(self.memory.read_bytes(pointer_slot, pointer_size), "little")
            address = pointer + _field_offset(payload)
        return address

    def attach(self) -> bool:
        self.offsets.initialize_offsets(self.target_executable, force=False)
        opened = bool(self.memory.open_process()) if hasattr(self.memory, "open_process") else bool(getattr(self.memory, "hproc", None))
        if opened:
            base_addr = getattr(self.memory, "base_addr", None)
            self.last_status = f"attached to {self.target_executable} at 0x{int(base_addr):X}" if base_addr else f"attached to {self.target_executable}"
            return True
        self.last_status = f"not attached to {self.target_executable}"
        return False

    def runtime_status_text(self) -> str:
        label = target_display_label(self.target_executable)
        if getattr(self.memory, "hproc", None):
            return f"{label} is attached."
        return f"{label} is not running."

    def select_target_executable(self, executable: str) -> None:
        if executable != self.target_executable and hasattr(self.memory, "close"):
            self.memory.close()
        self.target_executable = executable
        if hasattr(self.memory, "module_name"):
            self.memory.module_name = executable
        self._layout_cache.clear()
        self._field_entries_cache.clear()
        self._field_context_cache.clear()
        self._field_lookup_cache.clear()
        self._player_team_pointer_cache.clear()
        self.loaded_items = {domain: {} for domain in EDITOR_DOMAINS}
        self.selected_items = {domain: None for domain in EDITOR_DOMAINS}
        self.last_status = self.runtime_status_text()
        self.domain_statuses = {domain: self.last_status for domain in EDITOR_DOMAINS}

    def domain_status(self, domain: str) -> str:
        return self.domain_statuses.get(domain, self.runtime_status_text())

    def domain_item_labels(self, domain: str) -> list[str]:
        return list(self.loaded_items[domain])

    def domain_item_count(self, domain: str) -> int:
        return len(self.loaded_items[domain])

    def player_team_filter_options(self) -> tuple[str, ...]:
        return (PLAYER_TEAM_FILTER_ALL, *self.domain_item_labels("Teams"))

    def _read_player_current_team_pointer(self, item: RecordListItem) -> int | None:
        entry = self._field_by_normalized_name("Players", "CURRENTTEAM")
        if entry is None:
            return None
        try:
            return int(self.read_entry_value(entry, index=item.index).get("raw_value"))
        except Exception:
            return None

    def _player_current_team_pointer(self, item: RecordListItem) -> int | None:
        if item.index not in self._player_team_pointer_cache:
            self._player_team_pointer_cache[item.index] = self._read_player_current_team_pointer(item)
        return self._player_team_pointer_cache[item.index]

    def _cache_player_team_pointers(self, items: list[RecordListItem]) -> None:
        self._player_team_pointer_cache = {item.index: self._read_player_current_team_pointer(item) for item in items}

    def player_item_labels_for_team_filter(self, selected_team_label: str | None) -> list[str]:
        selected = str(selected_team_label or "").strip()
        if not selected or selected == PLAYER_TEAM_FILTER_ALL:
            return self.domain_item_labels("Players")
        team = self.loaded_items["Teams"].get(selected)
        if team is None:
            return []
        labels: list[str] = []
        for label, player in self.loaded_items["Players"].items():
            if self._player_current_team_pointer(player) == team.address:
                labels.append(label)
        return labels

    def player_item_count_for_team_filter(self, selected_team_label: str | None) -> int:
        return len(self.player_item_labels_for_team_filter(selected_team_label))

    def selected_item(self, domain: str) -> RecordListItem | None:
        return self.selected_items[domain]

    def select_item_by_label(self, domain: str, selected_label: str | None) -> RecordListItem | None:
        selected = str(selected_label or "")
        self.selected_items[domain] = self.loaded_items[domain].get(selected)
        return self.selected_items[domain]

    def refresh_domain_items(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:
        try:
            items = self.scan_records(domain, limit=limit)
            by_label = {item.display_label: item for item in items}
            self.loaded_items[domain] = by_label
            if domain == "Players":
                self._cache_player_team_pointers(items)
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

    def record_summary_labels(self, domain: str) -> tuple[str, ...]:
        if domain == "NBA History":
            return tuple(label for label, _ in HISTORY_SUMMARY_FIELD_SPECS)
        if domain == "NBA Records":
            return tuple(label for label, _ in RECORD_SUMMARY_FIELD_SPECS)
        return ()

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

    def _packed_record_summary_stride(self, domain: str) -> int:
        max_end = 0
        for _label, candidates in self._record_summary_specs(domain):
            for name in candidates:
                entry = self._field_by_normalized_name(domain, name)
                if entry is None:
                    continue
                payload = self._field_version_payload(entry.field)
                offset = _field_offset(payload)
                type_key = _type_key(payload)
                if type_key in {"string", "wstring"}:
                    width = _string_length(payload)
                elif type_key == "float":
                    width = 4
                else:
                    width = _numeric_width(payload)
                max_end = max(max_end, offset + width)
                break
        return max(1, (max_end + 7) // 8 * 8)

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
            row_stride = int(record_row_stride) if record_row_stride is not None else self._packed_record_summary_stride(domain)
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
        return {label: self._read_named_value("Players", item, candidates) for label, candidates in PLAYER_DETAIL_FIELD_SPECS}

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
            target_base = self.domain_base(target_domain)
            target_stride = self.domain_stride(target_domain)
        except Exception:
            return None
        if pointer <= 0 or target_stride <= 0:
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
        return None

    def _read_field_at_record_address(self, domain: str, record_addr: int, field: dict[str, Any]) -> dict[str, Any]:
        payload = self._field_version_payload(field)
        address = self._field_address(domain, record_addr, field, payload)
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

    def _label_for_index(self, domain: str, index: int) -> str:
        return self._label_for_record_address(domain, index, self.record_address(domain, index), self._label_entries(domain))

    def scan_records(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:
        if not getattr(self.memory, "hproc", None) or not getattr(self.memory, "base_addr", None):
            raise RuntimeError(f"not attached to {self.target_executable}")
        explicit_limit = int(limit) if limit is not None else None
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

    def read_entry_value(self, entry: FieldEntry, *, index: int) -> dict[str, Any]:
        return self.read_value(entry.domain, index=index, field=entry.field)

    def write_entry_value(self, entry: FieldEntry, *, index: int, value: Any) -> dict[str, Any]:
        return self.write_and_readback(entry.domain, index=index, field=entry.field, value=value)

    def section_fields(self, domain: str, section: str, group: str) -> list[dict[str, Any]]:
        layout = self.editor_layout(domain)
        if section not in layout:
            raise KeyError(f"missing section: {section}")
        section_groups = layout[section]
        if not isinstance(section_groups, dict):
            raise TypeError(f"section {section} must contain authored groups")
        if group not in section_groups:
            available = ", ".join(str(key) for key in section_groups)
            raise KeyError(f"missing group path: {section}/{group}; available groups: {available}")
        fields = section_groups[group]
        if not isinstance(fields, list):
            raise TypeError(f"group {section}/{group} must contain authored field entries")
        return fields

    def domain_base(self, domain: str) -> int:
        config = self._active_config()
        base_key = self._domain_base_key(domain)
        base_pointers = config["base_pointers"]
        base_entry = base_pointers[base_key]
        if not isinstance(base_entry, dict):
            raise TypeError(f"base entry for {domain} must be an authored object")
        if "address" not in base_entry:
            raise KeyError(f"base entry for {domain} is missing address")
        authored_address = int(base_entry["address"])
        module_base = getattr(self.memory, "base_addr", None)
        if not module_base:
            return authored_address
        pointer_address = authored_address if bool(base_entry.get("absolute")) else int(module_base) + authored_address
        final_offset = int(base_entry.get("finalOffset") or 0)
        if bool(base_entry.get("direct_table")):
            return pointer_address + final_offset
        pointer_size = int(getattr(self.memory, "pointer_size", 8) or 8)
        if pointer_size == 8 and hasattr(self.memory, "read_u64"):
            return self.memory.read_u64(pointer_address) + final_offset
        if pointer_size == 4 and hasattr(self.memory, "read_uint32"):
            return self.memory.read_uint32(pointer_address) + final_offset
        raw = self.memory.read_bytes(pointer_address, pointer_size)
        return int.from_bytes(raw, "little") + final_offset

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

    def _field_offset(self, field: dict[str, Any]) -> int:
        return _field_offset(self._field_version_payload(field))

    def read_value(self, domain: str, *, index: int, field: dict[str, Any]) -> dict[str, Any]:
        payload = self._field_version_payload(field)
        address = self._field_address(domain, self.record_address(domain, index), field, payload)
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

    def write_value(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> None:
        payload = self._field_version_payload(field)
        if bool(payload.get("readonly")):
            raise PermissionError(f"field is readonly: {field.get('normalized_name') or field.get('display_name')}")
        address = self._field_address(domain, self.record_address(domain, index), field, payload)
        section, _group = self._field_context(domain, field)
        raw_value = _display_to_raw_value(section, field, payload, value)
        _write_authored_value(self.memory, address, payload, raw_value)
        if domain == "Players" and _field_identity(field.get("normalized_name") or field.get("display_name")) == "CURRENTTEAM":
            try:
                self._player_team_pointer_cache[index] = int(raw_value)
            except Exception:
                self._player_team_pointer_cache.pop(index, None)

    def write_and_readback(self, domain: str, *, index: int, field: dict[str, Any], value: Any) -> dict[str, Any]:
        self.write_value(domain, index=index, field=field, value=value)
        return self.read_value(domain, index=index, field=field)


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
        "attached": bool(getattr(model.memory, "hproc", None)),
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
