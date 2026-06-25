from __future__ import annotations

import re
import struct
from typing import Any

from nba2k_editor.core import offsets as offsets_mod
from nba2k_editor.core.conversions import (
    convert_body_scale_display_to_raw,
    convert_injury_duration_days_to_raw,
    convert_potential_to_raw,
    convert_rating_to_raw,
    convert_rating_to_tendency_raw,
    convert_raw_to_body_scale_display,
    convert_raw_to_injury_duration_days,
    convert_raw_to_potential,
    convert_raw_to_rating,
    convert_raw_to_year,
    convert_tendency_raw_to_rating,
    convert_year_to_raw,
    height_inches_to_raw,
    is_year_offset_field,
    normalize_weight_value,
    raw_height_to_inches,
    to_int,
)
from nba2k_editor.models.schema import _field_display_or_name, _field_identity


_IMPLEMENTATION_REQUIRED_FLAGS = {
    "from_address_dropdown",
    "offset2",
}

_ADDRESS_DROPDOWN_TYPES: dict[str, str] = {
    "team_address_dropdown": "Teams",
    "stadium_address_dropdown": "Stadiums",
    "uniform_dropdown": "Jerseys",
}

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

_PARENT_POINTER_TYPES = {"pointer", "address", "uint64", "ulonglong"}

_PLAYER_ZERO_TO_100_FIELD_IDS = {
    "MINPOTENTIAL",
    "MAXPOTENTIAL",
    "MINIMUMPOTENTIAL",
    "MAXIMUMPOTENTIAL",
    "AVGPERCENT",
    "AVERAGEPERCENT",
    "BUSTPERCENT",
    "BUSTPERCENTAGE",
    "BOOMPERCENT",
    "BOOMPERCENTAGE",
    "FINANCIALSECURITY",
    "LOYALTY",
    "PLAYFORWINNER",
}


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
        "int",
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


def _bits_to_bytes(bits: int) -> int:
    return max(1, (int(bits) + 7) // 8)


def _numeric_width(payload: dict[str, Any]) -> int:
    explicit_bytes = to_int(payload.get("byteLength"))
    if explicit_bytes > 0:
        return explicit_bytes
    type_key = _type_key(payload)
    authored_length_bits = offsets_mod._resolved_length_bits(payload)
    if type_key in {"color", "hex_bytes"}:
        authored_length = to_int(payload.get("length"))
        if authored_length > 0:
            return authored_length
    if type_key == "binary" and not ("bit_offset" in payload or "startBit" in payload):
        authored_length = to_int(payload.get("length"))
        if authored_length > 0:
            return authored_length
    type_width = _FIXED_NUMERIC_TYPE_WIDTHS.get(type_key)
    if type_width:
        return type_width
    if authored_length_bits > 0:
        return _bits_to_bytes(authored_length_bits)
    raise KeyError("authored payload is missing length, bit_length, or byteLength")


def _bit_window(payload: dict[str, Any]) -> tuple[int, int, int]:
    bit_offset = to_int(payload.get("bit_offset")) or to_int(payload.get("startBit"))
    bit_length = offsets_mod._resolved_length_bits(payload)
    if bit_length <= 0:
        raise KeyError("authored bitfield payload is missing length, bit_length, or byteLength")
    width = _bits_to_bytes(bit_offset + bit_length)
    return bit_offset, bit_length, width


def _read_pointer_value(memory: Any, address: int) -> int:
    pointer_size = int(memory.pointer_size or 8)
    if pointer_size == 8:
        return int(memory.read_u64(address))
    if pointer_size == 4:
        return int(memory.read_uint32(address))
    return int.from_bytes(memory.read_bytes(address, pointer_size), "little")


def _field_address(memory: Any, record_addr: int, payload: dict[str, Any], *, parent_payload: dict[str, Any] | None = None) -> int:
    base_address = int(record_addr)
    if parent_payload is not None:
        parent_address = base_address + _field_offset(parent_payload)
        if _type_key(parent_payload) in _PARENT_POINTER_TYPES:
            base_address = _read_pointer_value(memory, parent_address)
        else:
            base_address = parent_address
    address = base_address + _field_offset(payload)
    if bool(payload.get("requiresDereference")):
        dereference_offset = to_int(payload.get("dereferenceAddress"))
        pointer_slot = base_address + dereference_offset if dereference_offset else address
        pointer = _read_pointer_value(memory, pointer_slot)
        address = pointer + _field_offset(payload)
    return address


def _read_bitfield(memory: Any, address: int, payload: dict[str, Any]) -> int:
    bit_offset, bit_length, width = _bit_window(payload)
    raw_int = int.from_bytes(memory.read_bytes(address, width), "little")
    mask = (1 << bit_length) - 1
    value = (raw_int >> bit_offset) & mask
    if _type_key(payload) == "int" and value >= (1 << (bit_length - 1)):
        value -= 1 << bit_length
    return value


def _write_bitfield(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None:
    bit_offset, bit_length, width = _bit_window(payload)
    raw_int = int.from_bytes(memory.read_bytes(address, width), "little")
    mask = ((1 << bit_length) - 1) << bit_offset
    new_int = (raw_int & ~mask) | ((int(value) << bit_offset) & mask)
    memory.write_bytes(address, new_int.to_bytes(width, "little"))


def _uses_bitfield_io(payload: dict[str, Any]) -> bool:
    type_key = _type_key(payload)
    if type_key in {"bit", "bitfield"}:
        return True
    has_bit_offset = "bit_offset" in payload or "startBit" in payload
    return type_key in {"number", "integer", "int", "binary"} and has_bit_offset and offsets_mod._resolved_length_bits(payload) > 0


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


def _id_prefixed_option(raw_id: int, label: str) -> str:
    text = str(label).strip()
    return f"[{int(raw_id)}] {text}" if text else f"[{int(raw_id)}]"


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
    if field_id in {"HEIGHT", "WINGSPAN"}:
        return raw_height_to_inches(int(raw_value))
    if bool(payload.get("div100")):
        return int(raw_value) / 100
    if bool(payload.get("body_scale_0_100")) or bool(payload.get("body_scale_25_75")):
        return convert_raw_to_body_scale_display(raw_value, length_bits)
    if "scale" in payload:
        return float(raw_value) * float(payload.get("scale") or 1)
    if field_id == "POTENTIAL":
        return convert_raw_to_potential(to_int(raw_value), length_bits)
    if field_id in _PLAYER_ZERO_TO_100_FIELD_IDS:
        return convert_tendency_raw_to_rating(to_int(raw_value), length_bits)
    if bool(payload.get("injury_duration_days")) or field_id in {"INJURY1DURATION", "INJURY2DURATION"}:
        return convert_raw_to_injury_duration_days(to_int(raw_value))
    if section in {"Attributes", "Durability"}:
        return convert_raw_to_rating(int(raw_value), length_bits)
    if section == "Tendencies":
        return convert_tendency_raw_to_rating(int(raw_value), length_bits)
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
    if field_id in {"HEIGHT", "WINGSPAN"}:
        return height_inches_to_raw(int(value))
    if bool(payload.get("div100")):
        return int(round(float(value) * 100))
    if field_id == "WEIGHT":
        normalized_weight = normalize_weight_value(value)
        return normalized_weight if normalized_weight is not None else value
    if bool(payload.get("body_scale_0_100")) or bool(payload.get("body_scale_25_75")):
        return convert_body_scale_display_to_raw(value, length_bits)
    if "scale" in payload:
        scale = float(payload.get("scale") or 1)
        return float(value) / scale if scale else value
    if field_id == "POTENTIAL":
        return convert_potential_to_raw(float(value), length_bits)
    if field_id in _PLAYER_ZERO_TO_100_FIELD_IDS:
        return convert_rating_to_tendency_raw(float(value), length_bits)
    if bool(payload.get("injury_duration_days")) or field_id in {"INJURY1DURATION", "INJURY2DURATION"}:
        return convert_injury_duration_days_to_raw(float(value))
    if section in {"Attributes", "Durability"}:
        return convert_rating_to_raw(float(value), length_bits)
    if section == "Tendencies":
        return convert_rating_to_tendency_raw(float(value), length_bits)
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
    return memory.read_ascii(address, max_chars)


def _write_string(memory: Any, address: int, payload: dict[str, Any], value: Any) -> None:
    max_chars = _string_length(payload)
    text = str(value)
    if _type_key(payload) == "wstring":
        memory.write_wstring_fixed(address, text, max_chars)
        return
    if _type_key(payload) == "string":
        memory.write_ascii_fixed(address, text, max_chars)
        return


def _read_ptr_string(memory: Any, address: int, payload: dict[str, Any]) -> str:
    pointer = _read_pointer_value(memory, address)
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
        if width == 4:
            return memory.read_uint32(address)
        if width == 8:
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
        if width == 4:
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
