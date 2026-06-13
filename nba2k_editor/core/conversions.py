"""
Rating, bitfield, and unit conversion helpers.

These functions are lifted from the original monolithic editor to keep math
utilities isolated from UI concerns.
"""
from __future__ import annotations

import re
from typing import Any

# Rating scaling constants
RATING_MIN = 25
RATING_MAX_DISPLAY = 99
RATING_MAX_TRUE = 110

# Year offset conversion
YEAR_BASE = 1900
_YEAR_FIELD_CACHE: dict[str, bool] = {}
# Fields whose raw values are stored as offsets from YEAR_BASE (small ints) in some
# rosters, but may appear as absolute years in others. We guard in the converters.
_YEAR_FIELD_ALLOWLIST = {"DRAFTEDYEAR", "HISTORICYEAR", "BIRTHYEAR"}


def _normalize_year_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def parse_id_prefixed_option(value: Any) -> int | None:
    match = re.match(r"^\s*\[(\d+)\]", str(value or ""))
    return int(match.group(1)) if match else None


def is_year_offset_field(field_name: str) -> bool:
    """
    Return True if a field name should be treated as a year offset from YEAR_BASE.

    This targets names containing "year" while excluding common non-year counters
    like "years" and award labels such as "of the year".
    """
    if not field_name:
        return False
    if not field_name:
        return False
    key = _normalize_year_key(field_name)
    cached = _YEAR_FIELD_CACHE.get(key)
    if cached is not None:
        return cached
    allowed = key in _YEAR_FIELD_ALLOWLIST
    _YEAR_FIELD_CACHE[key] = allowed
    return allowed


def convert_raw_to_year(raw: int, base_year: int = YEAR_BASE) -> int:
    """Convert a stored year offset into a calendar year."""
    try:
        raw_val = int(raw)
    except Exception:
        raw_val = 0
    # If the value already looks like an absolute calendar year, return as-is.
    if raw_val >= base_year:
        return raw_val
    if raw_val < 0:
        raw_val = 0
    return int(base_year) + raw_val


def convert_year_to_raw(year: int, base_year: int = YEAR_BASE) -> int:
    """Convert a calendar year into its stored offset."""
    try:
        year_val = int(year)
    except Exception:
        return 0
    # If value is already a small offset, keep it.
    if 0 <= year_val < base_year:
        return year_val
    raw_val = year_val - int(base_year)
    if raw_val < 0:
        raw_val = 0
    return raw_val

# Height constants (player record stores total inches * 254)
HEIGHT_UNIT_SCALE = 254
HEIGHT_MIN_INCHES = 48   # 4'0"
HEIGHT_MAX_INCHES = 120  # 10'0"

# Weight constants (stored as float32 pounds)
WEIGHT_MIN_POUNDS = 115.0
WEIGHT_MAX_POUNDS = 350.0
POUNDS_TO_KILOGRAMS = 0.45359237


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


def convert_potential_to_raw(rating: float, length: int | None = None, minimum: float = 40.0, maximum: float = 99.0) -> int:
    """Convert Potential display ratings into raw values, bounded to the 40-99 display scale."""
    try:
        clamped = max(minimum, min(maximum, float(rating)))
    except Exception:
        clamped = minimum
    return convert_rating_to_raw(clamped, int(length or 0)) if length and length > 0 else int(round(clamped))


def convert_raw_to_potential(raw: int, length: int | None = None, minimum: float = 40.0, maximum: float = 99.0) -> int:
    """Convert raw Potential values through the rating curve, bounded to 40-99."""
    if length and length > 0:
        rating = convert_raw_to_rating(raw, int(length))
    else:
        try:
            rating = int(raw)
        except Exception:
            rating = int(minimum)
    return max(int(minimum), min(int(maximum), int(rating)))


def convert_minmax_potential_to_raw(rating: float, length: int, minimum: float = 0.0, maximum: float = 100.0) -> int:
    """Convert Min/Max/Average potential-like display values on the 0-100 scale into raw values."""
    return convert_rating_to_tendency_raw(rating, length)


def convert_raw_to_minmax_potential(raw: int, length: int, minimum: float = 0.0, maximum: float = 100.0) -> int:
    """Convert Min/Max/Average potential-like raw values into the 0-100 display scale."""
    return convert_tendency_raw_to_rating(raw, length)


def convert_raw_to_body_scale_display(raw: object, length: int = 0) -> int:
    """Convert body scale raw float storage into the 0-100 editor display scale."""
    try:
        value = float(str(raw))
    except Exception:
        value = 0.0
    return convert_tendency_raw_to_rating(int(round(value * 50.0)), length)


def convert_body_scale_display_to_raw(display_value: object, length: int = 0) -> float:
    """Convert body scale 0-100 display values into raw float storage."""
    return convert_rating_to_tendency_raw(float(str(display_value)), length) / 50.0


def convert_raw_to_injury_duration_days(raw: int, maximum_days: int = 450) -> int:
    """Convert player injury duration storage into displayed days, ignoring high status flag bits."""
    try:
        duration_ticks = int(raw) & 0xFFFFF
    except Exception:
        duration_ticks = 0
    return max(0, min(int(maximum_days), duration_ticks // 1440))


def convert_injury_duration_days_to_raw(days: float, maximum_days: int = 450) -> int:
    """Convert displayed injury duration days into low duration ticks, clamped to the editor range."""
    try:
        value = int(round(float(days)))
    except Exception:
        value = 0
    value = max(0, min(int(maximum_days), value))
    return value * 1440


def normalize_weight_value(value: object) -> float | None:
    """Parse editor input into a supported weight value in pounds."""
    try:
        if isinstance(value, (int, float)):
            parsed = float(value)
        else:
            parsed = float(str(value).strip())
    except Exception:
        return None
    if parsed < WEIGHT_MIN_POUNDS:
        return WEIGHT_MIN_POUNDS
    if parsed > WEIGHT_MAX_POUNDS:
        return WEIGHT_MAX_POUNDS
    return parsed


def convert_pounds_to_kilograms(pounds: object) -> float:
    """Convert pounds to kilograms."""
    try:
        return float(pounds) * POUNDS_TO_KILOGRAMS
    except Exception:
        return 0.0


def convert_kilograms_to_pounds(kilograms: object) -> float:
    """Convert kilograms to pounds."""
    try:
        return float(kilograms) / POUNDS_TO_KILOGRAMS
    except Exception:
        return 0.0


def raw_height_to_inches(raw_val: int) -> int:
    """Convert raw stored height (inches * 254) to inches."""
    try:
        inches = int(round(int(raw_val) / HEIGHT_UNIT_SCALE))
    except Exception:
        inches = 0
    return max(0, inches)


def clamp_height_inches(inches: int) -> int:
    """Clamp a height value to the supported player-editor range."""
    try:
        value = int(inches)
    except Exception:
        value = 0
    if value < HEIGHT_MIN_INCHES:
        return HEIGHT_MIN_INCHES
    if value > HEIGHT_MAX_INCHES:
        return HEIGHT_MAX_INCHES
    return value


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


def player_numeric_bounds(category_name: str, field_name: str, length_bits: int) -> tuple[int, int]:
    category = str(category_name or '').strip()
    if category in ('Attributes', 'Durability'):
        return 25, 99
    if category == 'Tendencies':
        return 0, 100
    bits = int(length_bits) if int(length_bits) > 0 else 0
    field = str(field_name or '').strip().lower()
    if field == 'height':
        return HEIGHT_MIN_INCHES, HEIGHT_MAX_INCHES
    return 0, (1 << bits) - 1 if bits else 0


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
    "YEAR_BASE",
    "is_year_offset_field",
    "convert_raw_to_year",
    "convert_year_to_raw",
    "HEIGHT_UNIT_SCALE",
    "HEIGHT_MIN_INCHES",
    "HEIGHT_MAX_INCHES",
    "WEIGHT_MIN_POUNDS",
    "WEIGHT_MAX_POUNDS",
    "convert_raw_to_rating",
    "convert_rating_to_raw",
    "convert_potential_to_raw",
    "convert_raw_to_potential",
    "convert_raw_to_injury_duration_days",
    "convert_injury_duration_days_to_raw",
    "convert_raw_to_body_scale_display",
    "convert_body_scale_display_to_raw",
    "convert_minmax_potential_to_raw",
    "convert_raw_to_minmax_potential",
    "normalize_weight_value",
    "raw_height_to_inches",
    "clamp_height_inches",
    "height_inches_to_raw",
    "format_height_inches",
    "convert_tendency_raw_to_rating",
    "convert_rating_to_tendency_raw",
    "player_numeric_bounds",
    "to_int",
    "NON_NUMERIC_RE",
]
