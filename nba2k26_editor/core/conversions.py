"""
Rating, bitfield, and unit conversion helpers.

These functions are lifted from the original monolithic editor to keep math
utilities isolated from UI concerns.
"""
from __future__ import annotations

import struct
import re
from typing import Any

# Rating scaling constants
RATING_MIN = 25
RATING_MAX_DISPLAY = 99
RATING_MAX_TRUE = 110

# Badge levels (0..4)
BADGE_LEVEL_NAMES: list[str] = ["None", "Bronze", "Silver", "Gold", "Hall of Fame"]
BADGE_NAME_TO_VALUE: dict[str, int] = {name: idx for idx, name in enumerate(BADGE_LEVEL_NAMES)}

# Height constants (player record stores total inches * 254)
HEIGHT_UNIT_SCALE = 254
HEIGHT_MIN_INCHES = 48   # 4'0"
HEIGHT_MAX_INCHES = 120  # 10'0"


def convert_raw_to_rating(raw: int, length: int) -> int:
    """
    Convert a raw bitfield value into the 25-99 display rating scale using proportional mapping.
    """
    try:
        max_raw = (1 << length) - 1
        if max_raw <= 0:
            return RATING_MIN
        rating_true = RATING_MIN + (raw / max_raw) * (RATING_MAX_TRUE - RATING_MIN)
        if rating_true < RATING_MIN:
            rating_true = RATING_MIN
        elif rating_true > RATING_MAX_DISPLAY:
            rating_true = RATING_MAX_DISPLAY
        return int(round(rating_true))
    except Exception:
        return RATING_MIN


def convert_rating_to_raw(rating: float, length: int) -> int:
    """
    Convert a 25-99 rating back into a raw bitfield value using proportional mapping.
    """
    try:
        max_raw = (1 << length) - 1
        if max_raw <= 0:
            return 0
        r = float(rating)
        if r < RATING_MIN:
            r = RATING_MIN
        elif r > RATING_MAX_DISPLAY:
            r = RATING_MAX_DISPLAY
        fraction = (r - RATING_MIN) / (RATING_MAX_TRUE - RATING_MIN)
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0
        raw_val = round(fraction * max_raw)
        return max(0, min(int(raw_val), max_raw))
    except Exception:
        return 0


def convert_minmax_potential_to_raw(rating: float, length: int, minimum: float = 40.0, maximum: float = 99.0) -> int:
    """Convert Minimum/Maximum Potential display ratings into raw bitfield values."""
    try:
        clamped = max(minimum, min(maximum, float(rating)))
        max_raw = (1 << length) - 1
        return int(max(0, min(max_raw, round(clamped))))
    except Exception:
        return int(minimum)


def convert_raw_to_minmax_potential(raw: int, length: int, minimum: float = 40.0, maximum: float = 99.0) -> int:
    """Convert raw Minimum/Maximum Potential values back into the 40-99 range."""
    try:
        rating = int(raw)
        rating = max(int(minimum), rating)
        if rating > maximum:
            rating = int(maximum)
        return rating
    except Exception:
        return int(minimum)


def read_weight(mem, addr: int) -> float:
    """Read a weight value (float32 pounds) from memory."""
    try:
        b = mem.read_bytes(addr, 4)
        if len(b) == 4:
            return struct.unpack("<f", b)[0]
    except Exception:
        pass
    return 0.0


def write_weight(mem, addr: int, val: float) -> bool:
    """Write a weight value (float32 pounds) to memory."""
    try:
        raw = struct.pack("<f", float(val))
        mem.write_bytes(addr, raw)
        return True
    except Exception:
        return False


def raw_height_to_inches(raw_val: int) -> int:
    """Convert raw stored height (inches * 254) to inches."""
    try:
        inches = int(round(int(raw_val) / HEIGHT_UNIT_SCALE))
    except Exception:
        inches = 0
    return max(0, inches)


def height_inches_to_raw(inches: int) -> int:
    """Convert inches to raw stored height (inches * 254)."""
    try:
        raw_val = int(round(int(inches) * HEIGHT_UNIT_SCALE))
    except Exception:
        raw_val = 0
    return max(0, raw_val)


def format_height_inches(inches: int) -> str:
    """Format inches as feet/inches for display."""
    try:
        inches = int(inches)
    except Exception:
        return "--"
    feet = inches // 12
    remainder = inches % 12
    return f"{feet}'{remainder}\""


def convert_tendency_raw_to_rating(raw: int, length: int) -> int:
    """Convert a raw bitfield value into a 0-100 tendency rating."""
    try:
        value = int(raw)
    except Exception:
        value = 0
    if value < 0:
        value = 0
    elif value > 100:
        value = 100
    return value


def convert_rating_to_tendency_raw(rating: float, length: int) -> int:
    """Convert a 0-100 tendency rating into a raw bitfield value."""
    try:
        r = float(rating)
    except Exception:
        r = 0.0
    if r < 0.0:
        r = 0.0
    elif r > 100.0:
        r = 100.0
    return int(round(r))


def to_int(value: Any) -> int:
    """Convert strings or numeric values to an integer, accepting hex strings."""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return 0
        base = 16 if value.lower().startswith("0x") else 10
        try:
            return int(value, base)
        except ValueError:
            return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


NON_NUMERIC_RE = re.compile(r"[^0-9.-]")


__all__ = [
    "RATING_MIN",
    "RATING_MAX_DISPLAY",
    "RATING_MAX_TRUE",
    "BADGE_LEVEL_NAMES",
    "BADGE_NAME_TO_VALUE",
    "HEIGHT_UNIT_SCALE",
    "HEIGHT_MIN_INCHES",
    "HEIGHT_MAX_INCHES",
    "convert_raw_to_rating",
    "convert_rating_to_raw",
    "convert_minmax_potential_to_raw",
    "convert_raw_to_minmax_potential",
    "read_weight",
    "write_weight",
    "raw_height_to_inches",
    "height_inches_to_raw",
    "format_height_inches",
    "convert_tendency_raw_to_rating",
    "convert_rating_to_tendency_raw",
    "to_int",
    "NON_NUMERIC_RE",
]
