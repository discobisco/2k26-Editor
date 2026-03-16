"""Typed definitions and schema metadata for imports and exports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, NotRequired, TypedDict

from ..core.conversions import (
    BADGE_LEVEL_NAMES,
    HEIGHT_MAX_INCHES,
    HEIGHT_MIN_INCHES,
    convert_raw_to_minmax_potential,
    convert_raw_to_rating,
    convert_raw_to_year,
    convert_tendency_raw_to_rating,
    is_year_offset_field,
    raw_height_to_inches,
    to_int,
)


class PreparedImportRows(TypedDict):
    header: list[str]
    data_rows: list[list[str]]
    name_col: int
    value_columns: list[int]
    first_name_col: NotRequired[int | None]
    last_name_col: NotRequired[int | None]
    fixed_mapping: NotRequired[bool]
    allow_missing_names: NotRequired[bool]


@dataclass
class FieldMetadata:
    offset: int
    start_bit: int
    length: int
    requires_deref: bool = False
    deref_offset: int = 0
    widget: object | None = None
    values: tuple[str, ...] | None = None
    data_type: str | None = None
    byte_length: int = 0


FieldSpecInput = FieldMetadata | dict[str, object]


@dataclass(frozen=True)
class FieldParts:
    offset: int = 0
    start_bit: int = 0
    length: int = 0
    requires_deref: bool = False
    deref_offset: int = 0
    field_type: str = ""
    byte_length: int = 0
    values: tuple[str, ...] | None = None

    def as_tuple(self) -> tuple[int, int, int, bool, int, str, int, tuple[str, ...] | None]:
        return (
            self.offset,
            self.start_bit,
            self.length,
            self.requires_deref,
            self.deref_offset,
            self.field_type,
            self.byte_length,
            self.values,
        )


FieldWriteSpec = tuple[int, int, int, int, bool, int]


class ExportFieldSpec(TypedDict):
    category: str
    name: str
    offset: int
    hex: str
    length: int
    start_bit: int
    requires_deref: bool
    deref_offset: int
    type: str | None
    meta: dict[str, object]


BUFFER_CODEC_FALLBACK = object()


@dataclass(frozen=True)
class BufferDecodeConfig:
    entity_type: str
    category: str
    field_name: str
    name_max_chars: int = 64
    clamp_badges: bool = True
    clamp_height: bool = True
    clamp_enum_index: Callable[[int, tuple[str, ...], int], int] | None = None
    format_hex_value: Callable[[int, int, int], str] | None = None
    team_pointer_to_display_name: Callable[[int], str | None] | None = None


def normalize_field_parts(meta: FieldSpecInput) -> FieldParts:
    if isinstance(meta, FieldMetadata):
        return FieldParts(
            offset=meta.offset,
            start_bit=meta.start_bit,
            length=meta.length,
            requires_deref=bool(meta.requires_deref),
            deref_offset=meta.deref_offset,
            field_type=meta.data_type or "",
            byte_length=meta.byte_length,
            values=meta.values,
        )
    if isinstance(meta, dict):
        values_raw = meta.get("values")
        values = None
        if isinstance(values_raw, (list, tuple)):
            values = tuple(str(v) for v in values_raw)
        return FieldParts(
            offset=to_int(meta.get("offset") or meta.get("address") or meta.get("offset_from_base") or meta.get("hex")),
            start_bit=to_int(meta.get("startBit") or meta.get("start_bit") or 0),
            length=to_int(meta.get("length") or meta.get("size") or meta.get("bitLength") or meta.get("bits")),
            requires_deref=bool(meta.get("requiresDereference") or meta.get("requires_deref")),
            deref_offset=to_int(meta.get("dereferenceAddress") or meta.get("deref_offset")),
            field_type=str(meta.get("type") or ""),
            byte_length=to_int(
                meta.get("byte_length")
                or meta.get("byteLength")
                or meta.get("lengthBytes")
                or meta.get("size")
                or 0
            ),
            values=values,
        )
    return FieldParts()


def normalize_field_type(field_type: str | None) -> str:
    return str(field_type or "").strip().lower()


def is_string_type(field_type: str | None) -> bool:
    ftype = normalize_field_type(field_type)
    return any(tag in ftype for tag in ("string", "text", "wstring", "wstr", "utf16", "wide", "char"))


def string_encoding_for_type(field_type: str | None) -> str:
    ftype = normalize_field_type(field_type)
    if any(tag in ftype for tag in ("wstring", "wstr", "utf16", "wide")):
        return "utf16"
    if any(tag in ftype for tag in ("ascii", "string", "text", "char")):
        return "ascii"
    return "utf16"


def is_float_type(field_type: str | None) -> bool:
    ftype = normalize_field_type(field_type)
    return "float" in ftype or "double" in ftype


def is_pointer_type(field_type: str | None) -> bool:
    ftype = normalize_field_type(field_type)
    return "pointer" in ftype or "ptr" in ftype


def is_color_type(field_type: str | None) -> bool:
    return "color" in normalize_field_type(field_type)


def effective_byte_length(byte_length_hint: int, length_bits: int, default: int = 4) -> int:
    if byte_length_hint and byte_length_hint > 0:
        if byte_length_hint > 8 and byte_length_hint % 8 == 0:
            return max(1, byte_length_hint // 8)
        return max(1, byte_length_hint)
    if length_bits and length_bits > 0:
        return max(1, (int(length_bits) + 7) // 8)
    return max(1, default)


def decode_field_value_from_buffer(
    meta: FieldSpecInput | FieldParts,
    record_buffer: bytes | bytearray | memoryview,
    *,
    config: BufferDecodeConfig,
) -> object:
    parts = meta if isinstance(meta, FieldParts) else normalize_field_parts(meta)
    (
        offset,
        start_bit,
        length_bits,
        requires_deref,
        deref_offset,
        field_type,
        byte_length,
        values,
    ) = parts.as_tuple()
    if requires_deref and deref_offset:
        return BUFFER_CODEC_FALLBACK

    field_type_norm = normalize_field_type(field_type)
    entity_key = (config.entity_type or "").strip().lower()
    name_lower = str(config.field_name or "").strip().lower()
    category_lower = str(config.category or "").strip().lower()
    length_raw = length_bits
    if length_bits <= 0 and byte_length > 0:
        length_bits = byte_length * 8

    buf = memoryview(record_buffer)

    if is_string_type(field_type_norm):
        max_chars = length_raw if length_raw > 0 else byte_length
        if max_chars <= 0:
            max_chars = config.name_max_chars if "name" in name_lower and config.name_max_chars > 0 else 64
        enc = string_encoding_for_type(field_type_norm)
        if offset < 0 or max_chars <= 0:
            return BUFFER_CODEC_FALLBACK
        if enc == "ascii":
            byte_len = max_chars
        else:
            byte_len = max_chars * 2
        end = offset + byte_len
        if end > len(buf):
            return BUFFER_CODEC_FALLBACK
        raw = buf[offset:end].tobytes()
        try:
            text = raw.decode("ascii" if enc == "ascii" else "utf-16le", errors="ignore")
        except Exception:
            return BUFFER_CODEC_FALLBACK
        zero = text.find("\x00")
        if zero != -1:
            text = text[:zero]
        return text

    if entity_key == "player" and name_lower == "weight":
        end = offset + 4
        if offset < 0 or end > len(buf):
            return BUFFER_CODEC_FALLBACK
        import struct
        try:
            return int(round(struct.unpack("<f", buf[offset:end].tobytes())[0]))
        except Exception:
            return BUFFER_CODEC_FALLBACK

    if is_float_type(field_type_norm):
        import struct
        byte_len = effective_byte_length(byte_length, length_bits, default=4)
        need = 8 if byte_len >= 8 else 4
        end = offset + need
        if offset < 0 or end > len(buf):
            return BUFFER_CODEC_FALLBACK
        try:
            return struct.unpack("<d" if byte_len >= 8 else "<f", buf[offset:end].tobytes())[0]
        except Exception:
            return BUFFER_CODEC_FALLBACK

    if length_bits <= 0:
        return BUFFER_CODEC_FALLBACK
    bits_needed = start_bit + length_bits
    bytes_needed = (bits_needed + 7) // 8
    end = offset + bytes_needed
    if offset < 0 or end > len(buf):
        return BUFFER_CODEC_FALLBACK
    try:
        raw_int = int.from_bytes(buf[offset:end], "little")
        raw_int >>= start_bit
        raw_int &= (1 << length_bits) - 1
    except Exception:
        return BUFFER_CODEC_FALLBACK

    if values:
        if config.clamp_enum_index is not None:
            return config.clamp_enum_index(raw_int, values, length_bits)
        return raw_int

    if is_pointer_type(field_type_norm) or is_color_type(field_type_norm):
        if entity_key == "player" and "team" in f"{config.category} {config.field_name}".strip().lower() and ("address" in name_lower or "pointer" in name_lower):
            resolver = config.team_pointer_to_display_name
            if resolver is not None:
                team_name = resolver(raw_int)
                if team_name:
                    return team_name
        if config.format_hex_value is None:
            return raw_int
        return config.format_hex_value(raw_int, length_bits, byte_length)

    if entity_key == "player" and name_lower == "height":
        inches = raw_height_to_inches(raw_int)
        if config.clamp_height:
            if inches < HEIGHT_MIN_INCHES:
                inches = HEIGHT_MIN_INCHES
            if inches > HEIGHT_MAX_INCHES:
                inches = HEIGHT_MAX_INCHES
            return inches
        if HEIGHT_MIN_INCHES <= inches <= HEIGHT_MAX_INCHES:
            return inches
        return raw_int

    if category_lower in ("attributes", "durability"):
        return convert_raw_to_rating(raw_int, length_bits or 8)
    if category_lower == "potential":
        if "min" in name_lower or "max" in name_lower:
            return convert_raw_to_minmax_potential(raw_int, length_bits or 8)
        return convert_raw_to_rating(raw_int, length_bits or 8)
    if category_lower == "tendencies":
        return convert_tendency_raw_to_rating(raw_int, length_bits or 8)
    if is_year_offset_field(config.field_name):
        return convert_raw_to_year(raw_int)
    if category_lower == "badges":
        if not config.clamp_badges:
            return raw_int
        max_lvl = max(0, len(BADGE_LEVEL_NAMES) - 1)
        if raw_int < 0:
            return 0
        if raw_int > max_lvl:
            return max_lvl
        return raw_int
    return raw_int


__all__ = [
    "PreparedImportRows",
    "FieldMetadata",
    "FieldSpecInput",
    "FieldParts",
    "FieldWriteSpec",
    "ExportFieldSpec",
    "BUFFER_CODEC_FALLBACK",
    "BufferDecodeConfig",
    "decode_field_value_from_buffer",
    "effective_byte_length",
    "normalize_field_parts",
    "normalize_field_type",
    "is_string_type",
    "string_encoding_for_type",
    "is_float_type",
    "is_pointer_type",
    "is_color_type",
]
