"""
NBA 2K26 Live Memory Editor
---------------------------
This tool attaches to a running ``NBA2K26.exe`` process and uses the offsets
declared in ``2K26_Offsets.json`` to read, validate, and update roster data
directly in memory. Every read/write is persisted to ``logs/memory.log`` for
traceability. The editor requires the game to be running locally; no offline
fallbacks or synthetic data sources are used.
"""
import os
import sys
import threading
import struct
import ctypes
import logging
import time
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict, Sequence, Callable
import random
import tempfile
import urllib.request
import urllib.parse
import io
import json
import re
from pathlib import Path
from collections import Counter
# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------
class OffsetSchemaError(RuntimeError):
    """Raised when 2K26_Offsets.json is missing required definitions."""

# -----------------------------------------------------------------------------
# Memory logging
# -----------------------------------------------------------------------------
def _init_memory_logger() -> logging.Logger:
    logger = logging.getLogger("nba2k26.memory")
    if logger.handlers:
        return logger
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "memory.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)sZ | %(levelname)s | %(message)s", "%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime  # type: ignore[assignment]
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger

MEMORY_LOGGER = _init_memory_logger()

# -----------------------------------------------------------------------------
# Offset loading system for 2K26
# -----------------------------------------------------------------------------
OFFSET_FILE_CANDIDATES = (
    "2K26_Offsets.json",
    "2K26_offsets.json",
    "2k26_Offsets.json",
    "2k26_offsets.json",
    "2K26_Offsets.txt",
    "2k26_offsets.txt",
)
_offset_file_path: Path | None = None
_offset_config: dict | None = None
_offset_index: dict[tuple[str, str], dict] = {}
MODULE_NAME = "NBA2K26.exe"
ALLOWED_MODULE_NAMES = {
    "nba2k22.exe",
    "nba2k23.exe",
    "nba2k24.exe",
    "nba2k25.exe",
    "nba2k26.exe",
}
PLAYER_TABLE_RVA = 0
PLAYER_STRIDE = 0
PLAYER_PTR_CHAINS: list[dict[str, object]] = []
OFF_LAST_NAME = 0
OFF_FIRST_NAME = 0
OFF_TEAM_PTR = 0
OFF_TEAM_NAME = 0
MAX_PLAYERS = 4000
NAME_MAX_CHARS = 20
FIRST_NAME_ENCODING = "utf16"
LAST_NAME_ENCODING = "utf16"
TEAM_NAME_ENCODING = "utf16"
APP_VERSION = "v2K26.0.1"
TEAM_STRIDE = 0
TEAM_NAME_OFFSET = 0
TEAM_NAME_LENGTH = 0
TEAM_PLAYER_SLOT_COUNT = 30
FREE_AGENT_TEAM_ID = -1
MAX_TEAMS_SCAN = 300
TEAM_PTR_CHAINS: list[dict[str, object]] = []

# --------------------------------------------------------------------------
# UI color palette
# --------------------------------------------------------------------------
PRIMARY_BG = "#0F1C2E"
PANEL_BG = "#16213E"
INPUT_BG = "#1B263B"
ACCENT_BG = "#415A77"
BUTTON_BG = "#778DA9"
BUTTON_ACTIVE_BG = "#415A77"
TEXT_PRIMARY = "#E0E1DD"
TEXT_SECONDARY = "#9BA4B5"
BUTTON_TEXT = "#000000"
# -----------------------------------------------------------------------------
# 2K COY auto-import configuration
# -----------------------------------------------------------------------------
COY_SHEET_ID: str = "1pxWukEO6oOofSZdPKyu--R_8EyvHOflArT2tJFBzzzo"
COY_SHEET_TABS: dict[str, str] = {
    "Attributes": "Attributes",
    "Tendencies": "TEND",
    "Durability": "Durabilities",
    "Potential": "Potential",
}
# -----------------------------------------------------------------------------
# Rating scaling constants
#
# NBA 2K25 stores player attributes in bitfields that are later mapped to
# ratings shown to the user.  Through observation of the in‑game code it
# appears that the theoretical maximum rating used internally is 110 even
# though the UI caps values at 99.  To ensure that imported ratings map
# proportionally across the full bitfield range regardless of length, we
# expose two constants:
#
#   * RATING_MIN: the minimum rating shown in game.  Typically 25.
#   * RATING_MAX_DISPLAY: the maximum rating exposed in the UI (99).
#   * RATING_MAX_TRUE: the maximum rating used internally (110).  Raw
#     bitfield values corresponding to 110 will appear as 99 in the UI
#     but preserve the correct scale when computing intermediate values.

RATING_MIN = 25
RATING_MAX_DISPLAY = 99
RATING_MAX_TRUE = 110

# -----------------------------------------------------------------------------
# Badge level definitions
#
# Each badge stored in the player record occupies a three‑bit field (values
# 0–7).  In practice, NBA 2K uses only the lower five values: 0 = no
# badge, 1 = Bronze, 2 = Silver, 3 = Gold and 4 = Hall of Fame.  Values
# above 4 have no effect in game.  When presenting badges in the UI we
# expose only these five levels.  The lists below provide the names and
# corresponding integer values used throughout the code.
BADGE_LEVEL_NAMES: list[str] = [
    "None",
    "Bronze",
    "Silver",
    "Gold",
    "Hall of Fame",
]
# Reverse lookup from name to value for convenience
BADGE_NAME_TO_VALUE: dict[str, int] = {name: idx for idx, name in enumerate(BADGE_LEVEL_NAMES)}

# -----------------------------------------------------------------------------
# Rating conversion helpers
#
# The 2K25 game stores player ratings as raw bitfields of varying lengths.
# To present intuitive 25–99 scales to users and convert back when saving,
# we define helper functions below.  



def convert_raw_to_rating(raw: int, length: int) -> int:
    """
    Convert a raw bitfield value into the 25–99 display rating scale
    using proportional mapping. This is the old logic that matched
    in-game values correctly.
    """
    try:
        max_raw = (1 << length) - 1
        if max_raw <= 0:
            return RATING_MIN
        # Scale raw 0..max_raw proportionally onto 25..110
        rating_true = RATING_MIN + (raw / max_raw) * (RATING_MAX_TRUE - RATING_MIN)
        # Clamp to 25..99 for display
        if rating_true < RATING_MIN:
            rating_true = RATING_MIN
        elif rating_true > RATING_MAX_DISPLAY:
            rating_true = RATING_MAX_DISPLAY
        return int(round(rating_true))
    except Exception:
        return RATING_MIN


def convert_rating_to_raw(rating: float, length: int) -> int:
    """
    Convert a 25–99 rating back into a raw bitfield value using
    proportional mapping. Matches the old logic that lined up
    with game display values.
    """
    try:
        max_raw = (1 << length) - 1
        if max_raw <= 0:
            return 0
        r = float(rating)
        # Clamp input rating to 25..99
        if r < RATING_MIN:
            r = RATING_MIN
        elif r > RATING_MAX_DISPLAY:
            r = RATING_MAX_DISPLAY
        # Proportional mapping into 0..max_raw
        fraction = (r - RATING_MIN) / (RATING_MAX_TRUE - RATING_MIN)
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0
        raw_val = round(fraction * max_raw)
        return max(0, min(int(raw_val), max_raw))
    except Exception:
        return 0




# -----------------------------------------------------------------------------
# Weight conversion helpers (treat as 32-bit float in pounds)

def read_weight(mem, addr: int) -> float:
    try:
        b = mem.read_bytes(addr, 4)
        if len(b) == 4:
            return struct.unpack("<f", b)[0]
    except Exception:
        pass
    return 0.0

def write_weight(mem, addr: int, val: float) -> bool:
    try:
        raw = struct.pack("<f", float(val))
        mem.write_bytes(addr, raw)
        return True
    except Exception:
        return False
# -----------------------------------------------------------------------------
# Height conversion helpers (player record stores total inches * 254)
HEIGHT_UNIT_SCALE = 254
HEIGHT_MIN_INCHES = 48   # 4'0"
HEIGHT_MAX_INCHES = 120  # 10'0"

def raw_height_to_inches(raw_val: int) -> int:
    try:
        inches = int(round(int(raw_val) / HEIGHT_UNIT_SCALE))
    except Exception:
        inches = 0
    return max(0, inches)

def height_inches_to_raw(inches: int) -> int:
    try:
        raw_val = int(round(int(inches) * HEIGHT_UNIT_SCALE))
    except Exception:
        raw_val = 0
    return max(0, raw_val)

def format_height_inches(inches: int) -> str:
    try:
        inches = int(inches)
    except Exception:
        return "--"
    feet = inches // 12
    remainder = inches % 12
    return f"{feet}'{remainder}\""
# -----------------------------------------------------------------------------
# Tendency conversion helpers
#
# Tendencies in NBA 2K25 are displayed on a 0–100 scale in game.  Internally
# they are stored as unsigned bitfields of varying lengths.  To ensure that
# values imported from spreadsheets and those edited in the UI correspond to
# the familiar 0–100 range, we define separate conversion helpers for
# tendencies.  These functions map raw bitfield values to the 0–100 scale and
# vice versa using a simple proportional mapping.  No offset of 25 is
# applied.

def convert_tendency_raw_to_rating(raw: int, length: int) -> int:
    """
    Convert a raw bitfield value into a 0–100 tendency rating.  When the
    game stores tendency values in a bitfield of ``length`` bits, the
    minimum raw value represents a rating of 0 and the maximum raw value
    represents a rating of 100.  Intermediate values are scaled linearly.

    Parameters
    ----------
    raw : int
        The integer stored in the bit field.
    length : int
        Number of bits in the field; determines the maximum representable
        raw value.

    Returns
    -------
    int
        Rating on the 0–100 scale, rounded to the nearest integer and
        clamped to 0..100.
    """
    try:
        max_raw = (1 << length) - 1
        if max_raw <= 0:
            return 0
        # Proportional mapping: raw 0..max_raw maps to 0..100
        rating = (raw / max_raw) * 100.0
        if rating < 0.0:
            rating = 0.0
        elif rating > 100.0:
            rating = 100.0
        return int(round(rating))
    except Exception:
        return 0


def convert_rating_to_tendency_raw(rating: float, length: int) -> int:
    """
    Convert a 0–100 tendency rating into a raw bitfield value.  Tendency
    ratings may be specified by the user or imported from a file; this
    function clamps them to the valid 0..100 range and scales them into
    the 0..(2^length−1) raw range.

    Parameters
    ----------
    rating : float
        The desired rating on the 0–100 scale.
    length : int
        Number of bits in the field; determines the maximum representable
        raw value.

    Returns
    -------
    int
        Raw bitfield value corresponding to the rating.
    """
    try:
        max_raw = (1 << length) - 1
        if max_raw <= 0:
            return 0
        r = float(rating)
        if r < 0.0:
            r = 0.0
        elif r > 100.0:
            r = 100.0
        fraction = r / 100.0
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0
        raw_val = round(fraction * max_raw)
        if raw_val < 0:
            raw_val = 0
        elif raw_val > max_raw:
            raw_val = max_raw
        return int(raw_val)
    except Exception:
        return 0

def _to_int(value: object) -> int:
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
def _load_offset_config_file() -> tuple[Path | None, dict | None]:
    """Locate and parse the first available offset file."""
    base_dir = Path(__file__).resolve().parent
    for fname in OFFSET_FILE_CANDIDATES:
        path = base_dir / fname
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                return path, json.load(handle)
        except Exception as exc:
            print(f"Failed to load offsets from {path}: {exc}")
    return None, None
def _build_offset_index(offsets: list[dict]) -> None:
    """Create a lookup of offset entries by (category, name)."""
    _offset_index.clear()
    for entry in offsets:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category", "")).strip().lower()
        name = str(entry.get("name", "")).strip().lower()
        if not name:
            continue
        _offset_index[(category, name)] = entry
def _find_offset_entry(name: str, category: str | None = None) -> dict | None:
    """Return the offset entry matching the provided name and category."""
    lname = name.strip().lower()
    if category:
        key = (category.strip().lower(), lname)
        if key in _offset_index:
            return _offset_index[key]
    for (cat, entry_name), entry in _offset_index.items():
        if entry_name == lname and (category is None or cat == category.strip().lower()):
            return entry
    return None


def _collect_player_info_entries(player_info: object) -> list[dict]:
    """Convert nested Player_Info definitions into flat offset entries."""
    entries: list[dict] = []
    if not isinstance(player_info, dict):
        return entries
    for category, fields in player_info.items():
        if not isinstance(fields, dict):
            continue
        category_name = str(category)
        for name, definition in fields.items():
            if not isinstance(definition, dict):
                continue
            entry: dict[str, object] = {
                "category": category_name,
                "name": str(name),
            }
            # Carry over all fields, normalising offset/length keys for legacy logic.
            for key, value in definition.items():
                if key == "offset_from_base":
                    if not entry.get("address"):
                        entry["address"] = value
                else:
                    entry[key] = value
            if "address" not in entry and "offset_from_base" in definition:
                entry["address"] = definition["offset_from_base"]
            if "length" not in entry and "size" in definition:
                entry["length"] = definition["size"]
            entries.append(entry)
    return entries


def _normalize_chain_steps(chain_data: object) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    if not isinstance(chain_data, list):
        return steps
    for hop in chain_data:
        if isinstance(hop, dict):
            offset = _to_int(
                hop.get("offset")
                or hop.get("add")
                or hop.get("delta")
                or hop.get("value")
                or hop.get("rva")
            )
            post_add = _to_int(
                hop.get("post")
                or hop.get("postAdd")
                or hop.get("post_add")
                or hop.get("finalOffset")
                or hop.get("final_offset")
            )
            deref = False
            for key in ("dereference", "deref", "read", "pointer", "follow", "resolve", "resolvePointer", "resolve_pointer"):
                if hop.get(key):
                    deref = True
                    break
            hop_type = str(hop.get("type", "")).lower()
            if hop_type in {"read", "pointer", "deref"}:
                deref = True
            steps.append({
                "offset": offset,
                "post_add": post_add,
                "dereference": deref,
            })
        else:
            steps.append({
                "offset": _to_int(hop),
                "post_add": 0,
                "dereference": True,
            })
    return steps

def _parse_pointer_chain_config(base_cfg: dict | None) -> list[dict[str, object]]:
    chains: list[dict[str, object]] = []
    if not isinstance(base_cfg, dict):
        return chains
    base_addr = _to_int(base_cfg.get("address") or base_cfg.get("rva") or base_cfg.get("base"))
    if not base_addr:
        return chains
    final_offset = _to_int(base_cfg.get("finalOffset") or base_cfg.get("final_offset"))
    absolute_flag = base_cfg.get("absolute")
    if absolute_flag is None:
        absolute_flag = base_cfg.get("isAbsolute")
    is_absolute = bool(absolute_flag)
    chain_data = base_cfg.get("chain") or base_cfg.get("steps")
    if isinstance(chain_data, list) and chain_data:
        candidate_like = [
            item for item in chain_data
            if isinstance(item, dict) and any(key in item for key in ("address", "rva", "base"))
        ]
        if candidate_like and len(candidate_like) == len(chain_data):
            for candidate in chain_data:
                candidate_addr = candidate.get("address")
                if candidate_addr is None:
                    candidate_addr = candidate.get("rva", candidate.get("base"))
                candidate_absolute = candidate.get("absolute")
                if candidate_absolute is None:
                    candidate_absolute = candidate.get("isAbsolute")
                chains.extend(_parse_pointer_chain_config({
                    "address": candidate_addr if candidate_addr is not None else base_addr,
                    "chain": candidate.get("chain") or candidate.get("steps"),
                    "finalOffset": candidate.get("finalOffset") or candidate.get("final_offset") or final_offset,
                    "absolute": candidate_absolute if candidate_absolute is not None else is_absolute,
                }))
            if chains:
                return chains
    steps = _normalize_chain_steps(chain_data)
    chains.append({
        "rva": base_addr,
        "steps": steps,
        "final_offset": final_offset,
        "absolute": is_absolute,
    })
    return chains

def _apply_offset_config(data: dict | None) -> None:
    """Update module-level constants using the loaded offset data."""
    global MODULE_NAME, PLAYER_TABLE_RVA, PLAYER_STRIDE
    global PLAYER_PTR_CHAINS, OFF_LAST_NAME, OFF_FIRST_NAME
    global OFF_TEAM_PTR, OFF_TEAM_NAME, NAME_MAX_CHARS
    global FIRST_NAME_ENCODING, LAST_NAME_ENCODING, TEAM_NAME_ENCODING
    global TEAM_STRIDE, TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_PLAYER_SLOT_COUNT
    global TEAM_PTR_CHAINS, TEAM_RECORD_SIZE, TEAM_FIELD_DEFS
    if not data:
        raise OffsetSchemaError("2K26_Offsets.json is missing or empty.")
    combined_offsets: list[dict] = []
    offsets = data.get("offsets")
    if isinstance(offsets, list):
        combined_offsets.extend(offsets)
    player_info_entries = _collect_player_info_entries(data.get("Player_Info"))
    if player_info_entries:
        combined_offsets.extend(player_info_entries)
    team_offsets = data.get("Teams") or data.get("team_offsets")
    if isinstance(team_offsets, list):
        combined_offsets.extend(team_offsets)
    if not combined_offsets:
        _offset_index.clear()
        raise OffsetSchemaError("No offsets defined in 2K26_Offsets.json.")
    _build_offset_index(combined_offsets)
    errors: list[str] = []
    game_info = data.get("game_info") or {}
    if game_info.get("executable"):
        MODULE_NAME = str(game_info["executable"])
    player_stride_val = _to_int(game_info.get("playerSize"))
    if player_stride_val <= 0:
        errors.append("game_info.playerSize must be a positive integer.")
    else:
        PLAYER_STRIDE = player_stride_val
    team_stride_val = _to_int(game_info.get("teamSize"))
    if team_stride_val <= 0:
        errors.append("game_info.teamSize must be a positive integer.")
    else:
        TEAM_STRIDE = team_stride_val
        TEAM_RECORD_SIZE = TEAM_STRIDE
    base_pointers = data.get("base_pointers") or {}
    PLAYER_PTR_CHAINS.clear()
    player_base = base_pointers.get("Player")
    if not isinstance(player_base, dict):
        errors.append("base_pointers.Player definition missing.")
    else:
        addr = _to_int(player_base.get("address") or player_base.get("rva") or player_base.get("base"))
        if addr <= 0:
            errors.append("base_pointers.Player.address must be non-zero.")
        else:
            PLAYER_TABLE_RVA = addr
        chains = _parse_pointer_chain_config(player_base)
        if chains:
            PLAYER_PTR_CHAINS.extend(chains)
        else:
            errors.append("base_pointers.Player.chain produced no resolvable entries.")
    TEAM_PTR_CHAINS.clear()
    team_base = base_pointers.get("Team")
    if not isinstance(team_base, dict):
        errors.append("base_pointers.Team definition missing.")
    else:
        chains = _parse_pointer_chain_config(team_base)
        if chains:
            TEAM_PTR_CHAINS.extend(chains)
        else:
            errors.append("base_pointers.Team.chain produced no resolvable entries.")
    name_char_limit: int | None = None
    first_entry = _find_offset_entry("First Name", "Vitals")
    if not first_entry:
        errors.append("Player_Info.Vitals.First Name entry missing.")
    else:
        OFF_FIRST_NAME = _to_int(first_entry.get("address"))
        if OFF_FIRST_NAME < 0:
            errors.append("First Name address must be zero or positive.")
        first_type = str(first_entry.get("type", "")).lower()
        FIRST_NAME_ENCODING = "ascii" if first_type in ("string", "text") else "utf16"
        length_val = _to_int(first_entry.get("length"))
        char_capacity: int | None = None
        if length_val <= 0:
            errors.append("First Name length must be positive.")
        elif FIRST_NAME_ENCODING == "utf16" and length_val % 2 != 0:
            errors.append("First Name length must be even for UTF-16 data.")
        else:
            char_capacity = length_val // 2 if FIRST_NAME_ENCODING == "utf16" else length_val
            if char_capacity <= 0:
                errors.append("First Name character capacity must be positive.")
        if char_capacity is not None:
            name_char_limit = char_capacity if name_char_limit is None else max(name_char_limit, char_capacity)
    last_entry = _find_offset_entry("Last Name", "Vitals")
    if not last_entry:
        errors.append("Player_Info.Vitals.Last Name entry missing.")
    else:
        OFF_LAST_NAME = _to_int(last_entry.get("address"))
        if OFF_LAST_NAME < 0:
            errors.append("Last Name address must be zero or positive.")
        last_type = str(last_entry.get("type", "")).lower()
        LAST_NAME_ENCODING = "ascii" if last_type in ("string", "text") else "utf16"
        length_val = _to_int(last_entry.get("length"))
        char_capacity = None
        if length_val <= 0:
            errors.append("Last Name length must be positive.")
        elif LAST_NAME_ENCODING == "utf16" and length_val % 2 != 0:
            errors.append("Last Name length must be even for UTF-16 data.")
        else:
            char_capacity = length_val // 2 if LAST_NAME_ENCODING == "utf16" else length_val
            if char_capacity <= 0:
                errors.append("Last Name character capacity must be positive.")
        if char_capacity is not None:
            name_char_limit = char_capacity if name_char_limit is None else max(name_char_limit, char_capacity)
    if name_char_limit is None:
        errors.append("Unable to determine name character limit from schema.")
    else:
        NAME_MAX_CHARS = name_char_limit
    team_entry = _find_offset_entry("Current Team", "Vitals")
    if not team_entry:
        errors.append("Player_Info.Vitals.Current Team entry missing.")
    else:
        OFF_TEAM_PTR = _to_int(
            team_entry.get("dereferenceAddress")
            or team_entry.get("deref_offset")
            or team_entry.get("dereference_address")
        )
        if OFF_TEAM_PTR < 0:
            errors.append("Current Team dereference address must be zero or positive.")
    team_name_entry = _find_offset_entry("Team Name", "Teams")
    if not team_name_entry:
        errors.append("Teams.Team Name entry missing.")
    else:
        TEAM_NAME_OFFSET = _to_int(team_name_entry.get("address"))
        if TEAM_NAME_OFFSET < 0:
            errors.append("Team Name address must be zero or positive.")
        team_type = str(team_name_entry.get("type", "")).lower()
        TEAM_NAME_ENCODING = "ascii" if team_type in ("string", "text") else "utf16"
        TEAM_NAME_LENGTH = _to_int(team_name_entry.get("length"))
        if TEAM_NAME_LENGTH <= 0:
            errors.append("Team Name length must be positive.")
        OFF_TEAM_NAME = TEAM_NAME_OFFSET
    team_player_entries = [
        entry for (cat, _), entry in _offset_index.items() if cat == "team players"
    ]
    if not team_player_entries:
        errors.append("No Team Players entries found in schema.")
    else:
        TEAM_PLAYER_SLOT_COUNT = len(team_player_entries)
    TEAM_FIELD_DEFS.clear()
    for label, entry_name in TEAM_FIELD_SPECS:
        entry = _find_offset_entry(entry_name, "Teams")
        if not entry:
            continue
        offset = _to_int(entry.get("address"))
        length_val = _to_int(entry.get("length"))
        entry_type = str(entry.get("type", "")).lower()
        if offset <= 0 or length_val <= 0:
            continue
        if entry_type not in ("wstring", "string", "text"):
            continue
        encoding = "ascii" if entry_type in ("string", "text") else "utf16"
        TEAM_FIELD_DEFS[label] = (offset, length_val, encoding)
    if TEAM_STRIDE > 0:
        TEAM_RECORD_SIZE = TEAM_STRIDE
    if errors:
        raise OffsetSchemaError(" ; ".join(errors))

def initialize_offsets(force: bool = False) -> None:
    """Ensure offset data is loaded; raises OffsetSchemaError on failure."""
    global _offset_file_path, _offset_config
    if _offset_config is not None and not force:
        return
    path, data = _load_offset_config_file()
    if data is None:
        searched = ", ".join(OFFSET_FILE_CANDIDATES)
        raise OffsetSchemaError(f"Unable to locate 2K26 offset schema. Looked for: {searched}")
    _offset_file_path = path
    _offset_config = data
    _apply_offset_config(data)
# -----------------------------------------------------------------------------
# Team metadata (loaded from offsets)
# -----------------------------------------------------------------------------
TEAM_FIELD_SPECS: tuple[tuple[str, str], ...] = (
    ("Team Name", "Team Name"),
    ("City Name", "City Name"),
    ("City Abbrev", "City Abbrev"),
)
TEAM_FIELD_DEFS: dict[str, tuple[int, int, str]] = {}
TEAM_RECORD_SIZE = TEAM_STRIDE
# Player detail panel field mapping
PLAYER_PANEL_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("Position", "Vitals", "Position"),
    ("Number", "Vitals", "Jersey Number"),
    ("Height", "Body", "Height"),
    ("Weight", "Body", "Weight"),
    ("Face ID", "Vitals", "Face ID"),
    ("Unique ID", "Vitals", "Player Unique Signature ID"),
)
PLAYER_PANEL_OVR_FIELD: tuple[str, str] = ("Attributes", "Overall")
# -----------------------------------------------------------------------------
# Unified offsets support
# -----------------------------------------------------------------------------
#
# To simplify distribution of offset information and avoid conflicting names
# between internal 2K labels and editor UI labels, this editor supports
# loading a unified offsets file.  When present, a unified file contains
# ``Base`` definitions and category lists ("Body", "Vitals", "Attributes",
# "Badges" and "Tendencies").  Field names inside these categories may be
# customized (e.g. prefixed with ``mod_``) to avoid collisions with game
# internals.  The ``UNIFIED_FILES`` tuple references the default 2K26 offsets file for legacy fallbacks.
# The loader functions below attempt to read this file before falling back to legacy parsing.
# Legacy ``potion.txt`` and ``offsets.json`` files are no longer consulted.
# Unified offsets fallback: only consult the 2K26 offsets file.
UNIFIED_FILES = (
    "2K26_Offsets.json",
)
EXTRA_TEMPLATE_FILES: tuple[tuple[str, str, str | None], ...] = (
    ("JERSEY.json", "Jersey", "Jersey"),
    ("STADIUM.json", "Stadium", "Stadium"),
    ("STAFF.json", "Staff", "Staff"),
    ("TEAM.json", "Teams", "Team"),
    ("TEAM_RECORDS.json", "Teams", "Team Records"),
    ("TEAM_STATS.json", "Teams", "Team Stats"),
)
EXTRA_CATEGORY_FIELDS: dict[str, list[dict]] = {}
# -----------------------------------------------------------------------------
# Import table definitions
#
# The application supports importing player data from tab- or comma-delimited
# text files.  To align the UI with commonly used spreadsheets, we define
# canonical field orders for four tables: Attributes, Tendencies, Durability and
# Potential.  These lists specify the order in which fields should appear
# in the editor and the import files.  When loading the category definitions
# from a unified offsets file, the ``_load_categories`` helper
# reorders the fields to match these lists (where possible).  Unmatched
# fields remain at the end of the list.  Synonym matching is performed
# during import via simple string normalization (see ``_normalize_name``).
# Order for the Attributes table.  These names correspond to the column
# headers in user‑provided import files.  Note: ``PLAYER_NAME`` is not a
# field in the save data; it is used as a row identifier in import files.
ATTR_IMPORT_ORDER = [
    "LAYUP",
    "STDUNK",
    "DUNK",
    "CLOSE",
    "MID",
    "3PT",
    "FT",
    "PHOOK",
    "PFADE",
    "POSTC",
    "FOUL",
    "SHOTIQ",
    "BALL",
    "SPD/BALL",
    "HANDS",
    "PASS",
    "PASS_IQ",
    "VISION",
    "OCNST",
    "ID",
    "PD",
    "STEAL",
    "BLOCK",
    "OREB",
    "DREB",
    "HELPIQ",
    "PSPER",
    "DCNST",
    "SPEED",
    "AGIL",
    "STR",
    "VERT",
    "STAM",
    "INTNGBL",
    "HSTL",
    "DUR",
    "POT",
]
# Order for the Durability table.  These headers correspond to various
# body part durability ratings.  Not every header may map directly to a
# field in the offset map; unmatched entries will be ignored.
DUR_IMPORT_ORDER = [
    "Back",
    "Head",
    "Left Ankle",
    "Left Elbow",
    "Left Foot",
    "Left Hip",
    "Left Knee",
    "Left Shoulder",
    "Neck",
    "Right Ankle",
    "Right Elbow",
    "Right Foot",
    "Right Hip",
    "Right Knee",
    "Right Shoulder",
    "miscellaneous",
]
# Order for the Potential table.  These display names correspond to the
# trio of potential-related ratings used during imports.
POTENTIAL_IMPORT_ORDER = [
    "Minimum Potential",
    "Potential",
    "Maximum Potential",
]


def _col_to_index(col: str) -> int:
    """Convert a 1-based spreadsheet column label (e.g. 'B', 'AA') to a 0-based index."""
    col = (col or "").strip().upper()
    if not col:
        return 0
    acc = 0
    for ch in col:
        if not ("A" <= ch <= "Z"):
            continue
        acc = acc * 26 + (ord(ch) - ord("A") + 1)
    return max(acc - 1, 0)


COY_IMPORT_LAYOUTS: dict[str, dict[str, object]] = {
    # Player name column B. Value columns are detected dynamically using sheet headers.
    "Attributes": {
        "name_columns": [_col_to_index("B"), _col_to_index("A")],
        "skip_names": {"player_name"},
        "column_headers": ATTR_IMPORT_ORDER,
    },
    # Player name column B, data columns E..CY (99 values) matching TEND_IMPORT_ORDER length.
    "Tendencies": {
        "name_columns": [_col_to_index("B"), _col_to_index("A")],
        "value_columns": list(range(_col_to_index("E"), _col_to_index("CY") + 1)),
        "skip_names": {"player_name"},
    },
    # Player name column B, data columns D..S (16 values) matching DUR_IMPORT_ORDER length.
    "Durability": {
        "name_columns": [_col_to_index("B"), _col_to_index("A")],
        "value_columns": list(range(_col_to_index("D"), _col_to_index("S") + 1)),
        "skip_names": {"player_name"},
    },
    # Player name column B, data columns E..G (Rating min/avg/max). Probability columns are ignored.
    "Potential": {
        "name_columns": [_col_to_index("B"), _col_to_index("A")],
        "value_columns": list(range(_col_to_index("E"), _col_to_index("G") + 1)),
        "skip_names": {"player_name"},
    },
}

NAME_SYNONYMS: dict[str, list[str]] = {
    "cam": ["Cameron"],
    "cameron": ["Cam"],
    "nic": ["Nicolas"],
    "nicolas": ["Nic"],
    "rob": ["Robert"],
    "robert": ["Rob"],
    "ron": ["Ronald"],
    "ronald": ["Ron"],
    "nate": ["Nathan"],
    "nathan": ["Nate"],
}
NAME_SUFFIXES: set[str] = {"jr", "sr", "ii", "iii", "iv", "v"}
# Order for the Tendencies table.  These column names are taken directly
# from the sample provided by the user.  They will be normalized and
# matched against the field names defined in the "Tendencies" category of
# the offset map.  Unmatched fields remain in their original order.
TEND_IMPORT_ORDER = [
    "T/SHOT",
    "T/TOUCH",
    "T/SCLOSE",
    "T/SUNDER",
    "T/SCL",
    "T/SCM",
    "T/SCR",
    "T/SMID",
    "T/SUSMID",
    "T/OSSMID",
    "T/SML",
    "T/SMLC",
    "T/SMC",
    "T/SMRC",
    "T/SMR",
    "T/S3PT",
    "T/SUS3PT",
    "T/OSS3PT",
    "T/S3L",
    "T/S3LC",
    "T/S3C",
    "T/S3RC",
    "T/S3R",
    "T/CONTMID",
    "T/CONT3PT",
    "T/SBMID",
    "T/SB3PT",
    "T/SPINJ",
    "T/TPU3PT",
    "T/DPUMID",
    "T/DPU3PT",
    "T/DRIVE",
    "T/SUDRIVE",
    "T/OSDRIVE",
    "T/GLASS",
    "T/STHRU",
    "T/DRLAYUP",
    "T/SPLAYUP",
    "T/EURO",
    "T/HOPSTEP",
    "T/FLOATER",
    "T/SDUNK",
    "T/DDUNK",
    "T/FDUNK",
    "T/AOOP",
    "T/PUTBACK",
    "T/CRASH",
    "T/DRIVE-R",
    "T/TTPFAKE",
    "T/JABSTEP",
    "T/TTIDLE",
    "T/TTSHOOT",
    "T/SIZEUP",
    "T/HSTTN",
    "T/NOSETUP",
    "T/XOVER",
    "T/2XOVER",
    "T/SPIN",
    "T/HSPIN",
    "T/SBACK",
    "T/BBACK",
    "T/DHSTTN",
    "T/INNOUT",
    "T/NODRIB",
    "T/FINISH",
    "T/DISH",
    "T/FLASHYP",
    "T/A-OOPP",
    "T/ROLLPOP",
    "T/SPOTCUT",
    "T/ISOVSE",
    "T/ISOVSG",
    "T/ISOVSA",
    "T/ISOVSP",
    "T/PLYDISC",
    "T/POSTUP",
    "T/PBDOWN",
    "T/PAGGBD",
    "T/PFACEUP",
    "T/PSPIN",
    "T/PDRIVE",
    "T/PDSTEP",
    "T/PHSTEP",
    "T/PSHOOT",
    "T/PHOOKL",
    "T/PHOOKR",
    "T/PFADEL",
    "T/PFADER",
    "T/PSHIMMY",
    "T/PHSHOT",
    "T/PSBSHOT",
    "T/PUPNUND",
    "T/TAKEC",
    "T/FOUL",
    "T/HFOUL",
    "T/PINTERC",
    "T/STEAL",
    "T/BLOCK",
    "T/CONTEST",
]
FIELD_NAME_ALIASES: dict[str, str] = {
    "SHOT": "SHOOT",
    "SHOTMIDRANGE": "SHOTMID",
    "SPOTUPSHOTMIDRANGE": "SPOTUPSHOTMID",
    "OFFSCREENSHOTMIDRANGE": "OFFSCREENSHOTMID",
    "SHOTTHREE": "SHOT3PT",
    "SPOTUPSHOTTHREE": "SPOTUPSHOT3PT",
    "OFFSCREENSHOTTHREE": "OFFSCREENSHOT3PT",
    "SHOTTHREELEFT": "SHOT3PTLEFT",
    "SHOTTHREELEFTCENTER": "SHOT3PTLEFTCENTER",
    "SHOTTHREECENTER": "SHOT3PTCENTER",
    "SHOTTHREERIGHTCENTER": "SHOT3PTRIGHTCENTER",
    "SHOTTHREERIGHT": "SHOT3PTRIGHT",
    "CONTESTEDJUMPERMIDRANGE": "CONTESTEDJUMPERMID",
    "CONTESTEDJUMPERTHREE": "CONTESTEDJUMPER3PT",
    "STEPBACKJUMPERMIDRANGE": "STEPBACKJUMPERMID",
    "STEPBACKJUMPERTHREE": "STEPBACKJUMPER3PT",
    "SPINJUMPER": "SPINJUMPERTENDENCY",
    "TRANSITIONPULLUPTHREE": "TRANSITIONPULLUP3PT",
    "DRIVEPULLUPMIDRANGE": "DRIVEPULLUPMID",
    "DRIVEPULLUPTHREE": "DRIVEPULLUP3PT",
    "DRIVINGLAYUP": "DRIVINGLAYUPTENDENCY",
    "EUROSTEPLAYUP": "EUROSTEP",
    "HOPSTEPLAYUP": "HOPSTEP",
    "STANDINGDUNK": "STANDINGDUNKTENDENCY",
    "DRIVINGDUNK": "DRIVINGDUNKTENDENCY",
    "FLASHYDUNK": "FLASHYDUNKTENDENCY",
    "DRIVINGBEHINDTHEBACK": "DRIVINGBEHINDBACK",
    "DRIVINGINANDOUT": "INANDOUT",
    "NODRIVINGDRIBBLEMOVE": "NODRIBBLE",
    "TRANSITIONSPOTUP": "SPOTUPCUT",
    "ISOVSELITEDEFENDER": "ISOVSE",
    "ISOVSGOODDEFENDER": "ISOVSG",
    "ISOVSAVERAGEDEFENDER": "ISOVSA",
    "ISOVSPOORDEFENDER": "ISOVSP",
    "SHOOTFROMPOST": "POSTSHOT",
    "POSTSHIMMYSHOT": "POSTSHIMMY",
    "ONBALLSTEAL": "STEAL",
    "BLOCKSHOT": "BLOCK",
    "CONTESTSHOT": "CONTEST",
}
# -----------------------------------------------------------------------------
# Attempt to override hard‑coded offsets from a configuration file.
#
# When a unified offsets file is present in the same directory (see
# ``UNIFIED_FILES`` above), it may contain a "Base" object with hex
# addresses used to override the default constants in this module.  This
# allows the tool to adapt to different game versions or user‑supplied
# offset maps without recompiling.  Legacy ``potion.txt`` and
# ``offsets.json`` files are no longer consulted.
import json as _json
import pathlib as _pathlib
# -----------------------------------------------------------------------------
# Helper to load category definitions from a unified offsets file.
#
# The cheat engine tables describe many fields (Body, Vitals, Attributes,
# Tendencies, Badges, etc.) with bit offsets and lengths.  When building
# a full editor we need to know which fields exist and how to read/write
# their values.  Unified offsets files encode this mapping in JSON format.
# The top‑level keys other than "Base" correspond to categories.  Each entry
# within a category is a dictionary with keys like ``name``, ``offset``,
# ``startBit`` and ``length``.  This helper reads the entire file and
# returns a dict mapping category names to lists of field definitions.
# If no unified file exists or it cannot be parsed, it returns an empty
# dictionary.
def _load_dropdowns_map() -> dict[str, dict[str, list[str]]]:
    "Return an empty dropdown map. Dropdowns.json support has been disabled."
    return {}
def _load_categories() -> dict[str, list[dict]]:
    """
    Load editor categories from a unified offsets file.
    The editor displays groups of fields under tabs such as "Body",
    "Vitals", "Attributes", "Badges" and "Tendencies".  These groups are
    defined in a JSON file.  To allow users to customize the field names
    and offsets without modifying the source code, the loader attempts to
    read a unified offsets JSON file listed in ``UNIFIED_FILES``.  The
    first file found is parsed and the categories returned.  Legacy
    ``potion.txt`` and ``offsets.json`` files are no longer consulted.
    Returns a dictionary mapping category names to lists of field
    definitions.  If parsing fails or no unified file is found, an empty
    dictionary is returned.
    """
    dropdowns = _load_dropdowns_map()
    def _finalize_field_metadata(
        field: dict[str, object],
        category_label: str,
        *,
        offset_val: int | None = None,
        start_bit_val: int | None = None,
        length_val: int | None = None,
        source_entry: dict | None = None,
    ) -> None:
        """Ensure each field dictionary carries core offset metadata."""
        if not isinstance(field, dict):
            return
        if category_label:
            field["category"] = category_label
        provided_hex = None
        if source_entry is not None and source_entry.get("hex"):
            provided_hex = str(source_entry.get("hex"))
        if offset_val is None:
            offset_val = _to_int(
                field.get("address")
                or field.get("offset")
                or field.get("hex")
            )
        if offset_val is not None and offset_val >= 0:
            offset_int = int(offset_val)
            field["address"] = offset_int
            field.setdefault("offset", hex(offset_int))
            if provided_hex is None:
                provided_hex = f"0x{offset_int:X}"
        if provided_hex is not None:
            field["hex"] = provided_hex
        start_val = start_bit_val
        if start_val is None:
            start_val = _to_int(field.get("startBit") or field.get("start_bit"))
        field["startBit"] = int(start_val or 0)
        if "start_bit" in field:
            field.pop("start_bit", None)
        length = length_val
        if length is None:
            length = _to_int(field.get("length") or field.get("size"))
        if length is not None and length > 0:
            field["length"] = int(length)
        if source_entry is not None and source_entry.get("type"):
            field["type"] = source_entry.get("type")
    def _entry_to_field(entry: dict, display_name: str, target_category: str | None = None) -> dict | None:
        offset_val = _to_int(entry.get("address"))
        length_val = _to_int(entry.get("length"))
        if offset_val <= 0 or length_val <= 0:
            return None
        start_bit = _to_int(entry.get("startBit"))
        field: dict[str, object] = {
            "name": display_name,
            "offset": hex(offset_val),
            "startBit": int(start_bit),
            "length": int(length_val),
        }
        if entry.get("requiresDereference"):
            field["requiresDereference"] = True
            field["dereferenceAddress"] = _to_int(entry.get("dereferenceAddress"))
        if "type" in entry:
            field["type"] = entry["type"]
        if "values" in entry and isinstance(entry["values"], list):
            field["values"] = entry["values"]
        category_label = target_category or str(entry.get("category", "")).strip()
        _finalize_field_metadata(
            field,
            category_label,
            offset_val=offset_val,
            start_bit_val=start_bit,
            length_val=length_val,
            source_entry=entry,
        )
        return field
    def _humanize_label(raw: object) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", text) if tok]
        if not tokens:
            return text
        words: list[str] = []
        for tok in tokens:
            if tok.isupper() and len(tok) <= 3:
                words.append(tok)
            else:
                words.append(tok.capitalize())
        return " ".join(words)
    def _template_entry_to_field(cat_label: str, entry: dict, name_prefix: str | None = None) -> dict | None:
        if not isinstance(entry, dict):
            return None
        display_name = str(entry.get("name", "")).strip()
        if not display_name:
            return None
        if name_prefix:
            prefix = name_prefix.strip()
            if prefix:
                if display_name:
                    display_name = f"{prefix} - {display_name}"
                else:
                    display_name = prefix
        entry_type = str(entry.get("type", "")).strip().lower()
        if entry_type in {"blank", "folder", "section", "class"}:
            return None
        if any(tag in entry_type for tag in ("string", "text")):
            return None
        offset_val = _to_int(entry.get("offset") or entry.get("address"))
        if offset_val < 0:
            return None
        info = entry.get("info") if isinstance(entry.get("info"), dict) else {}
        start_raw = entry.get("startBit") or entry.get("start_bit")
        if isinstance(info, dict):
            start_info = info.get("startbit") or info.get("startBit") or info.get("bit_start")
            if start_info is not None:
                start_raw = start_info
        explicit_start = start_raw is not None
        start_bit = _to_int(start_raw)
        if start_bit < 0:
            start_bit = 0
        length_bits = _to_int(entry.get("length"))
        if length_bits <= 0:
            size_val = _to_int(entry.get("size"))
            if entry_type in {"combo", "bitfield", "bool", "boolean"}:
                length_bits = size_val
            else:
                length_bits = size_val * 8
        if length_bits <= 0 and isinstance(info, dict):
            length_bits = _to_int(info.get("length") or info.get("bits"))
        if length_bits <= 0:
            return None
        if entry_type in {"combo", "bitfield", "bool", "boolean"} and not explicit_start:
            key = (cat_label, offset_val)
            start_bit = bit_cursor.get(key, 0)
        field: dict[str, object] = {
            "name": display_name,
            "offset": hex(offset_val),
            "startBit": int(start_bit),
            "length": int(length_bits),
        }
        if entry.get("type"):
            field["type"] = entry["type"]
        if isinstance(info, dict):
            options = info.get("options")
            if isinstance(options, list):
                values: list[str] = []
                for opt in options:
                    if isinstance(opt, dict):
                        label = str(opt.get("name") or opt.get("label") or opt.get("value") or "").strip()
                        if label:
                            values.append(label)
                    elif isinstance(opt, str):
                        label = opt.strip()
                        if label:
                            values.append(label)
                if values:
                    field.setdefault("values", values)
            if info.get("isptr"):
                deref = _to_int(info.get("offset") or info.get("deviation"))
                if deref > 0:
                    field["requiresDereference"] = True
                    field["dereferenceAddress"] = deref
        _finalize_field_metadata(
            field,
            cat_label,
            offset_val=offset_val,
            start_bit_val=field.get("startBit"),
            length_val=length_bits,
            source_entry=entry,
        )
        return field
    def _compose_field_prefix(base_label: str | None, subgroup: str | None) -> str | None:
        base_clean = _humanize_label(base_label) if base_label else ""
        sub_clean = _humanize_label(subgroup) if subgroup else ""
        if base_clean and sub_clean:
            if base_clean.lower() == sub_clean.lower():
                return base_clean
            return f"{base_clean} {sub_clean}"
        return base_clean or sub_clean or None
    def _convert_template_payload(target_category: str, base_prefix: str | None, payload: object) -> list[dict]:
        fields: list[dict] = []
        if isinstance(payload, list):
            prefix = _compose_field_prefix(base_prefix, None)
            for item in payload:
                field = _template_entry_to_field(target_category, item, prefix)
                if field:
                    fields.append(field)
            return fields
        if isinstance(payload, dict):
            for key, entries in payload.items():
                if not isinstance(entries, list):
                    continue
                prefix = _compose_field_prefix(base_prefix, key)
                for item in entries:
                    field = _template_entry_to_field(target_category, item, prefix)
                    if field:
                        fields.append(field)
        return fields
    def _merge_extra_template_files(cat_map: dict[str, list[dict]]) -> None:
        for fname, target_category, section_label in EXTRA_TEMPLATE_FILES:
            path = base_dir / fname
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = _json.load(handle)
            except Exception:
                continue
            collected_fields = _convert_template_payload(target_category, section_label, payload)
            if not collected_fields:
                continue
            seen = seen_fields_global.setdefault(target_category, set())
            bucket = cat_map.setdefault(target_category, [])
            for field in collected_fields:
                name = str(field.get("name", "")).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                bucket.append(field)
                offset_int = _to_int(field.get("offset"))
                start_val = _to_int(field.get("startBit") or field.get("start_bit"))
                length_val = _to_int(field.get("length"))
                key = (target_category, offset_int)
                bit_cursor[key] = max(bit_cursor.get(key, 0), start_val + max(length_val, 0))
    def _ensure_potential_category(cat_map: dict[str, list[dict]]) -> None:
        if cat_map.get("Potential"):
            return
        specs = [
            ("Minimum Potential", ("Minimum Potential", "Min Potential")),
            ("Potential", ("Potential",)),
            ("Maximum Potential", ("Maximum Potential", "Max Potential")),
        ]
        potential_fields: list[dict] = []
        for display_name, candidates in specs:
            entry = None
            for base in candidates:
                entry = _find_offset_entry(base, "Vitals")
                if entry:
                    break
                entry = _find_offset_entry(base, "Attributes")
                if entry:
                    break
            if not entry:
                continue
            field = _entry_to_field(entry, display_name, "Potential")
            if field is not None:
                potential_fields.append(field)
        if potential_fields:
            cat_map["Potential"] = potential_fields
    base_categories: dict[str, list[dict]] = {}
    if _offset_config is None:
        initialize_offsets()
    base_categories: dict[str, list[dict]] = {}
    bit_cursor: dict[tuple[str, int], int] = {}
    seen_fields_global: dict[str, set[str]] = {}
    if isinstance(_offset_config, dict):
        categories: dict[str, list[dict]] = {}
        combined_sections: list[dict] = []
        def _extend(section: object) -> None:
            if isinstance(section, list):
                combined_sections.extend(item for item in section if isinstance(item, dict))
        _extend(_offset_config.get("offsets"))
        for key, value in _offset_config.items():
            if key in {"offsets", "game_info", "base_pointers"}:
                continue
            _extend(value)
        seen_fields: set[tuple[str, str]] = set()
        for entry in combined_sections:
            cat_name = str(entry.get("category", "Misc")).strip() or "Misc"
            field_name = str(entry.get("name", "")).strip()
            if not field_name:
                continue
            key = (cat_name.lower(), field_name.lower())
            if key in seen_fields:
                continue
            seen_fields.add(key)
            offset_val = _to_int(entry.get("address"))
            if offset_val < 0:
                continue
            start_bit = _to_int(entry.get("startBit"))
            length_val = _to_int(entry.get("length"))
            size_val = _to_int(entry.get("size"))
            entry_type = str(entry.get("type", "")).lower()
            if any(tag in entry_type for tag in ("string", "text")):
                continue
            if length_val <= 0:
                if entry_type in ("bitfield", "bool", "boolean", "combo"):
                    length_val = size_val
                elif entry_type in ("number", "slider", "int", "uint", "pointer", "float"):
                    length_val = size_val * 8
            if length_val <= 0:
                continue
            field: dict[str, object] = {
                "name": field_name,
                "offset": hex(offset_val),
                "startBit": int(start_bit),
                "length": int(length_val),
            }
            if "type" in entry:
                field["type"] = entry["type"]
            if entry.get("requiresDereference"):
                field["requiresDereference"] = True
                field["dereferenceAddress"] = _to_int(entry.get("dereferenceAddress"))
            if "values" in entry and isinstance(entry["values"], list):
                field["values"] = entry["values"]
            try:
                dcat = dropdowns.get(cat_name) or dropdowns.get(cat_name.title()) or {}
                if field_name in dcat and isinstance(dcat[field_name], list):
                    field.setdefault("values", list(dcat[field_name]))
                elif field_name.upper().startswith("PLAYTYPE") and isinstance(dcat.get("PLAYTYPE"), list):
                    field.setdefault("values", list(dcat["PLAYTYPE"]))
            except Exception:
                pass
            _finalize_field_metadata(
                field,
                cat_name,
                offset_val=offset_val,
                start_bit_val=start_bit,
                length_val=length_val,
                source_entry=entry,
            )
            categories.setdefault(cat_name, []).append(field)
        if categories:
            base_categories = {key: list(value) for key, value in categories.items()}
            for cat_name, fields in base_categories.items():
                seen = seen_fields_global.setdefault(cat_name, set())
                for field in fields:
                    if not isinstance(field, dict):
                        continue
                    seen.add(str(field.get("name", "")))
                    offset_int = _to_int(field.get("offset"))
                    start_val = _to_int(field.get("startBit") or field.get("start_bit"))
                    length_val = _to_int(field.get("length"))
                    key = (cat_name, offset_int)
                    bit_cursor[key] = max(bit_cursor.get(key, 0), start_val + max(length_val, 0))
    base_dir = _pathlib.Path(__file__).resolve().parent
    # Try unified offsets files first
    for fname in UNIFIED_FILES:
        upath = base_dir / fname
        if not upath.is_file():
            continue
        try:
            with open(upath, "r", encoding="utf-8") as f:
                udata = _json.load(f)
            categories: dict[str, list[dict]] = {key: list(value) for key, value in base_categories.items()}
            for cat_name, fields in categories.items():
                seen = seen_fields_global.setdefault(cat_name, set())
                for field in fields:
                    if not isinstance(field, dict):
                        continue
                    seen.add(str(field.get("name", "")))
                    offset_int = _to_int(field.get("offset"))
                    start_val = _to_int(field.get("startBit") or field.get("start_bit"))
                    length_val = _to_int(field.get("length"))
                    key = (cat_name, offset_int)
                    bit_cursor[key] = max(bit_cursor.get(key, 0), start_val + max(length_val, 0))
            # Extract category lists from JSON (ignore "Base")
            if isinstance(udata, dict):
                # Case 1: unified format where categories are top-level lists of field definitions
                for key, value in udata.items():
                    key_lower = key.lower()
                    if key_lower in {"base", "offsets", "game_info", "base_pointers"}:
                        continue
                    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
                        normalized_fields: list[dict] = []
                        seen = seen_fields_global.setdefault(key, set())
                        for entry in value:
                            if not isinstance(entry, dict):
                                continue
                            _finalize_field_metadata(
                                entry,
                                key,
                                source_entry=entry,
                            )
                            normalized_fields.append(entry)
                            seen.add(str(entry.get("name", "")))
                            offset_int = _to_int(entry.get("offset"))
                            start_val = _to_int(entry.get("startBit") or entry.get("start_bit"))
                            length_val = _to_int(entry.get("length"))
                            bit_cursor[(key, offset_int)] = max(
                                bit_cursor.get((key, offset_int), 0),
                                start_val + max(length_val, 0),
                            )
                        categories[key] = normalized_fields
                # Case 2: extended offsets.json format with a nested Player_Info
                # The sanitized offsets JSON stores category dictionaries under
                # the "Player_Info" key.  Each category (e.g. "VITALS_offsets")
                # maps field names to definitions containing "offset_from_base",
                # "size" and "type" keys.  Convert these into the unified
                # list‑of‑dicts structure expected by the editor.  Map the
                # category names to a more human‑friendly form by stripping
                # the "_offsets" suffix and capitalising the remainder.
                pinf = udata.get("Player_Info")
                if isinstance(pinf, dict):
                    new_cats: dict[str, list[dict]] = {}
                    def _append_field(cat_label: str, field_name: str, prefix: str | None, fdef: dict) -> None:
                        display_name = field_name if prefix in (None, "") else f"{prefix} - {field_name}"
                        off_raw = (
                            fdef.get("address")
                            or fdef.get("offset_from_base")
                            or fdef.get("offset")
                        )
                        offset_int = _to_int(off_raw)
                        if offset_int < 0:
                            return
                        f_type = str(fdef.get("type", "")).lower()
                        if any(tag in f_type for tag in ("string", "text")):
                            return
                        start_raw = fdef.get("startBit") or fdef.get("start_bit") or fdef.get("bit_start")
                        explicit_start = start_raw is not None
                        start_bit = _to_int(start_raw)
                        size_int = _to_int(fdef.get("size"))
                        length_int = _to_int(fdef.get("length"))
                        if length_int <= 0:
                            if f_type in ("bitfield", "bool", "boolean", "combo"):
                                length_int = size_int
                            elif f_type in ("number", "slider", "int", "uint", "pointer"):
                                length_int = size_int * 8
                            elif f_type == "float":
                                length_int = 32 if size_int <= 0 else size_int * 8
                        if length_int <= 0:
                            return
                        if f_type in ("bitfield", "bool", "boolean", "combo") and not explicit_start:
                            key = (cat_label, offset_int)
                            start_bit = bit_cursor.get(key, 0)
                            bit_cursor[key] = start_bit + length_int
                        entry: dict[str, object] = {
                            "name": display_name,
                            "offset": hex(offset_int),
                            "startBit": int(start_bit),
                            "length": int(length_int),
                        }
                        if f_type:
                            entry["type"] = f_type
                        if f_type == "combo":
                            try:
                                value_count = min(1 << length_int, 64)
                                entry["values"] = [str(i) for i in range(max(value_count, 0))]
                            except Exception:
                                pass
                        try:
                            dcat = dropdowns.get(cat_label) or dropdowns.get(cat_label.title()) or {}
                            if display_name in dcat and isinstance(dcat[display_name], list):
                                entry.setdefault("values", list(dcat[display_name]))
                            elif field_name.upper().startswith("PLAYTYPE") and isinstance(dcat.get("PLAYTYPE"), list):
                                entry.setdefault("values", list(dcat["PLAYTYPE"]))
                        except Exception:
                            pass
                        seen_set = seen_fields_global.setdefault(cat_label, set())
                        if display_name in seen_set:
                            return
                        seen_set.add(display_name)
                        bit_cursor[(cat_label, offset_int)] = max(
                            bit_cursor.get((cat_label, offset_int), 0),
                            start_bit + length_int,
                        )
                        _finalize_field_metadata(
                            entry,
                            cat_label,
                            offset_val=offset_int,
                            start_bit_val=start_bit,
                            length_val=length_int,
                            source_entry=fdef,
                        )
                        new_cats.setdefault(cat_label, []).append(entry)
                    def _walk_field_map(base_label: str, mapping: dict, prefix: str | None = None) -> None:
                        for fname, fdef in mapping.items():
                            if not isinstance(fdef, dict):
                                continue
                            has_direct_keys = any(
                                key in fdef
                                for key in (
                                    "address",
                                    "offset_from_base",
                                    "offset",
                                    "startBit",
                                    "start_bit",
                                    "bit_start",
                                    "size",
                                    "length",
                                    "type",
                                )
                            )
                            if has_direct_keys:
                                cat_label = base_label
                                _append_field(cat_label, fname, prefix, fdef)
                            else:
                                next_prefix = fname if prefix is None else f"{prefix} - {fname}"
                                _walk_field_map(base_label, fdef, next_prefix)
                    for cat_key, field_map in pinf.items():
                        if not isinstance(field_map, dict):
                            continue
                        cat_name = cat_key[:-8] if cat_key.endswith("_offsets") else cat_key
                        cat_name = cat_name.title()
                        _walk_field_map(cat_name, field_map)
                    if new_cats:
                        for key, vals in new_cats.items():
                            if key in categories:
                                categories[key].extend(vals)
                            else:
                                categories[key] = vals
                if categories:
                    _merge_extra_template_files(categories)
                    _ensure_potential_category(categories)
                    return categories
        except Exception:
            # ignore errors and continue to next file
            pass
    if base_categories:
        categories = {key: list(value) for key, value in base_categories.items()}
        _merge_extra_template_files(categories)
        if categories:
            _ensure_potential_category(categories)
            return categories
    # Nothing found
    return {}
###############################################################################
# Windows API declarations
#
# Only a subset of the Win32 API is required: enumerating processes and
# modules, opening a process, and reading/writing its memory.  These
# declarations mirror those used in the earlier patcher example.  They are
# defined only on Windows. On other platforms the application exits before
# attempting any memory access.
if sys.platform == "win32":
    PROCESS_VM_READ      = 0x0010
    PROCESS_VM_WRITE     = 0x0020
    PROCESS_VM_OPERATION = 0x0008
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_QUERY_INFORMATION         = 0x0400
    PROCESS_ALL_ACCESS                = (
        PROCESS_VM_READ
        | PROCESS_VM_WRITE
        | PROCESS_VM_OPERATION
        | PROCESS_QUERY_INFORMATION
        | PROCESS_QUERY_LIMITED_INFORMATION
    )
    TH32CS_SNAPPROCESS  = 0x00000002
    TH32CS_SNAPMODULE   = 0x00000008
    TH32CS_SNAPMODULE32 = 0x00000010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # ---------------------------------------------------------------------
    # Handle potential API changes in ctypes.wintypes
    #
    # In Python 3.13 and later, `ctypes.wintypes` no longer defines
    # `ULONG_PTR`.  We define a compatible `ULONG_PTR` alias based on
    # pointer size so the structures below remain portable across Python
    # versions and architectures.
    try:
        _ULONG_PTR = wintypes.ULONG_PTR
    except AttributeError:
        # Choose 64‑bit or 32‑bit unsigned type depending on pointer size
        _ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD),
            ("modBaseAddr", wintypes.LPVOID),
            ("modBaseSize", wintypes.DWORD),
            ("hModule", wintypes.HMODULE),
            ("szModule", wintypes.WCHAR * 256),
            ("szExePath", wintypes.WCHAR * 260),
        ]
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            # Use our alias for `ULONG_PTR` to support Python versions where
            # `ctypes.wintypes.ULONG_PTR` is unavailable.
            ("th32DefaultHeapID", _ULONG_PTR),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]
    CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
    CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    CreateToolhelp32Snapshot.restype  = wintypes.HANDLE
    Module32FirstW = kernel32.Module32FirstW
    Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    Module32FirstW.restype  = wintypes.BOOL
    Module32NextW = kernel32.Module32NextW
    Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    Module32NextW.restype  = wintypes.BOOL
    Process32FirstW = kernel32.Process32FirstW
    Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    Process32FirstW.restype  = wintypes.BOOL
    Process32NextW = kernel32.Process32NextW
    Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    Process32NextW.restype  = wintypes.BOOL
    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    OpenProcess.restype  = wintypes.HANDLE
    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype  = wintypes.BOOL
    ReadProcessMemory = kernel32.ReadProcessMemory
    ReadProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.LPVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    ReadProcessMemory.restype = wintypes.BOOL
    WriteProcessMemory = kernel32.WriteProcessMemory
    WriteProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.LPCVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    WriteProcessMemory.restype = wintypes.BOOL
class GameMemory:
    """Utility class encapsulating process lookup and memory access."""
    def __init__(self, module_name: str = MODULE_NAME):
        self.module_name = module_name
        self.pid: int | None = None
        self.hproc: wintypes.HANDLE | None = None
        self.base_addr: int | None = None
    def _log_event(self, level: int, op: str, addr: int, length: int, status: str, **extra: object) -> None:
        """Write a structured entry to the memory operation log."""
        try:
            parts: list[str] = [
                f"op={op}",
                f"addr=0x{int(addr):016X}",
                f"len={int(length)}",
                f"status={status}",
            ]
            if self.pid is not None:
                parts.append(f"pid={self.pid}")
            if self.base_addr is not None:
                rel = int(addr) - int(self.base_addr)
                sign = "-" if rel < 0 else ""
                parts.append(f"rva={sign}0x{abs(rel):X}")
            for key, value in extra.items():
                parts.append(f"{key}={value}")
            MEMORY_LOGGER.log(level, " | ".join(parts))
        except Exception:
            # Logging must never interfere with memory operations.
            pass
    # -------------------------------------------------------------------------
    # Process management
    # -------------------------------------------------------------------------
    def find_pid(self) -> int | None:
        """Return the PID of the target process, or None if not found."""
        # Use psutil when available for convenience
        try:
            import psutil  # type: ignore
            for proc in psutil.process_iter(['name']):
                name = (proc.info['name'] or '').lower()
                if name in ALLOWED_MODULE_NAMES:
                    self.module_name = proc.info['name'] or MODULE_NAME
                    return proc.pid
        except Exception:
            pass
        # Fallback to toolhelp snapshot on Windows
        if sys.platform != "win32":
            return None
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap:
            return None
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        try:
            success = Process32FirstW(snap, ctypes.byref(entry))
            while success:
                name = entry.szExeFile.lower()
                if name in ALLOWED_MODULE_NAMES:
                    self.module_name = entry.szExeFile
                    return entry.th32ProcessID
                success = Process32NextW(snap, ctypes.byref(entry))
        finally:
            CloseHandle(snap)
        return None
    def open_process(self) -> bool:
        """Open the game process and resolve its base address.
        Returns ``True`` on success and ``False`` on failure.  When the
        process is successfully opened, ``self.pid``, ``self.hproc`` and
        ``self.base_addr`` are set accordingly.
        """
        if sys.platform != "win32":
            # Non‑Windows platforms cannot attach to a process
            self.close()
            return False
        pid = self.find_pid()
        if pid is None:
            self.close()
            return False
        # If already open to the same PID, reuse existing handle
        if self.pid == pid and self.hproc:
            return True
        # Close any existing handle
        self.close()
        # Attempt to open with full access
        handle = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not handle:
            # Could fail due to insufficient privileges
            self.close()
            return False
        # Resolve module base
        base = self._get_module_base(pid, self.module_name)
        if base is None:
            CloseHandle(handle)
            self.close()
            return False
        # Populate fields
        self.pid = pid
        self.hproc = handle
        self.base_addr = base
        return True
    def close(self) -> None:
        """Close any open process handle and reset state."""
        if self.hproc:
            try:
                CloseHandle(self.hproc)
            except Exception:
                pass
        self.pid = None
        self.hproc = None
        self.base_addr = None
    def _get_module_base(self, pid: int, module_name: str) -> int | None:
        """Return the base address of ``module_name`` in the given process."""
        if sys.platform != "win32":
            return None
        # Take a snapshot of modules
        flags = TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
        snap = CreateToolhelp32Snapshot(flags, pid)
        if not snap:
            return None
        me32 = MODULEENTRY32W()
        me32.dwSize = ctypes.sizeof(MODULEENTRY32W)
        try:
            if not Module32FirstW(snap, ctypes.byref(me32)):
                return None
            while True:
                if me32.szModule.lower() == module_name.lower():
                    return ctypes.cast(me32.modBaseAddr, ctypes.c_void_p).value
                if not Module32NextW(snap, ctypes.byref(me32)):
                    break
        finally:
            CloseHandle(snap)
        return None
    # -------------------------------------------------------------------------
    # Memory access helpers
    # -------------------------------------------------------------------------
    def _check_open(self, op: str | None = None, addr: int | None = None, length: int | None = None) -> None:
        if self.hproc is None or self.base_addr is None:
            if op is not None and addr is not None and length is not None:
                self._log_event(logging.ERROR, op, addr, length, "process-closed", validation="not-open")
            raise RuntimeError("Game process not opened")
    def read_bytes(self, addr: int, length: int) -> bytes:
        """Read ``length`` bytes from absolute address ``addr``."""
        self._check_open("read", addr, length)
        buf = (ctypes.c_ubyte * length)()
        read_count = ctypes.c_size_t()
        try:
            ok = ReadProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(read_count))
        except Exception as exc:
            self._log_event(
                logging.ERROR,
                "read",
                addr,
                length,
                "exception",
                validation="exception",
                error=repr(exc),
            )
            raise
        if not ok:
            winerr = ctypes.get_last_error()
            self._log_event(
                logging.ERROR,
                "read",
                addr,
                length,
                "failed",
                validation=f"win32={winerr}",
            )
            raise RuntimeError(f"Failed to read memory at 0x{addr:X} (error {winerr})")
        if read_count.value != length:
            self._log_event(
                logging.ERROR,
                "read",
                addr,
                length,
                "failed",
                validation=f"bytes={read_count.value}",
            )
            raise RuntimeError(f"Partial read at 0x{addr:X}: {read_count.value}/{length} bytes")
        self._log_event(logging.INFO, "read", addr, length, "success", validation="exact")
        return bytes(buf)
    def write_bytes(self, addr: int, data: bytes) -> None:
        """Write ``data`` to absolute address ``addr``."""
        length = len(data)
        self._check_open("write", addr, length)
        buf = (ctypes.c_ubyte * length).from_buffer_copy(data)
        written = ctypes.c_size_t()
        try:
            ok = WriteProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(written))
        except Exception as exc:
            self._log_event(
                logging.ERROR,
                "write",
                addr,
                length,
                "exception",
                validation="exception",
                error=repr(exc),
            )
            raise
        if not ok:
            winerr = ctypes.get_last_error()
            self._log_event(
                logging.ERROR,
                "write",
                addr,
                length,
                "failed",
                validation=f"win32={winerr}",
            )
            raise RuntimeError(f"Failed to write memory at 0x{addr:X} (error {winerr})")
        if written.value != length:
            self._log_event(
                logging.ERROR,
                "write",
                addr,
                length,
                "failed",
                validation=f"bytes={written.value}",
            )
            raise RuntimeError(f"Partial write at 0x{addr:X}: {written.value}/{length} bytes")
        self._log_event(logging.INFO, "write", addr, length, "success", validation="exact")
    def read_uint32(self, addr: int) -> int:
        data = self.read_bytes(addr, 4)
        return struct.unpack('<I', data)[0]
    def write_uint32(self, addr: int, value: int) -> None:
        data = struct.pack('<I', value & 0xFFFFFFFF)
        self.write_bytes(addr, data)
    def read_uint64(self, addr: int) -> int:
        data = self.read_bytes(addr, 8)
        return struct.unpack('<Q', data)[0]
    def read_wstring(self, addr: int, max_chars: int) -> str:
        """Read a UTF‑16LE string of at most ``max_chars`` characters from ``addr``."""
        raw = self.read_bytes(addr, max_chars * 2)
        try:
            s = raw.decode('utf-16le', errors='ignore')
        except Exception:
            return ''
        end = s.find('\x00')
        if end != -1:
            s = s[:end]
        return s
    def write_wstring_fixed(self, addr: int, value: str, max_chars: int) -> None:
        """Write a fixed length null‑terminated UTF‑16LE string at ``addr``."""
        value = value[: max_chars - 1]
        encoded = value.encode('utf-16le') + b"\x00\x00"
        padded = encoded.ljust(max_chars * 2, b"\x00")
        self.write_bytes(addr, padded)
    # ---------------------------------------------------------------------
    # ASCII string helpers
    # ---------------------------------------------------------------------
    def read_ascii(self, addr: int, max_chars: int) -> str:
        """Read an ASCII string of up to ``max_chars`` bytes from ``addr``.
        This function reads a fixed number of bytes and decodes them as
        ASCII, stopping at the first null byte.  It is used for fields
        where the cheat table indicates ``Unicode=0`` (i.e. not UTF‑16).
        """
        raw = self.read_bytes(addr, max_chars)
        try:
            s = raw.decode('ascii', errors='ignore')
        except Exception:
            return ''
        end = s.find('\x00')
        if end != -1:
            s = s[:end]
        return s
    def write_ascii_fixed(self, addr: int, value: str, max_chars: int) -> None:
        """Write a fixed length null‑terminated ASCII string at ``addr``."""
        value = value[: max_chars - 1]
        encoded = value.encode('ascii', errors='ignore') + b"\x00"
        padded = encoded.ljust(max_chars, b"\x00")
        self.write_bytes(addr, padded)
class Player:
    """Container class representing basic player data."""
    def __init__(self, index: int, first_name: str, last_name: str, team: str, team_id: int | None = None):
        self.index = index
        self.first_name = first_name
        self.last_name = last_name
        self.team = team
        self.team_id = team_id
    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else f"Player {self.index}"
    def __repr__(self) -> str:
        return f"<Player index={self.index} name='{self.full_name}' team='{self.team}' team_id={self.team_id}>"
class PlayerDataModel:
    """High level API for scanning and editing NBA 2K26 player records."""
    def __init__(self, mem: GameMemory, max_players: int = MAX_PLAYERS):
        self.mem = mem
        self.max_players = max_players
        self.players: list[Player] = []
        # Mapping from normalized full names ("first last") to a list of
        # player indices.  This dictionary is rebuilt each time players are
        # scanned or loaded.  It allows for fast lookup of players by name
        # during imports and other operations.
        self.name_index_map: Dict[str, list[int]] = {}
        self.external_loaded = False  # reserved; offline roster loading is disabled
        # Optional mapping of team indices to names derived from CE table comments
        self.team_name_map: Dict[int, str] = {}
        # Current list of available teams represented as (index, name) tuples.
        # Populated exclusively from live memory scans.
        self.team_list: list[tuple[int, str]] = []
        # Cached list of free agent players derived from the most recent scan.
        self._cached_free_agents: list[Player] = []
        # Internal caches for resolved pointer chains.  During a successful
        # scan, these fields store the computed base addresses of the player
        # and team tables.  Subsequent operations reuse the cached values
        # to avoid repeatedly resolving pointers.  They reset whenever
        # ``refresh_players`` is called.
        self._resolved_player_base: int | None = None
        self._resolved_team_base: int | None = None
        # Attempt to load team names from cheat table comments for later use.  We
        # look for files matching "2K26 Team Data (10.18.24).txt" or
        # "2K26 Team Data.txt" in the current directory.  If found, we parse
        # the comments section to build a team index-to-name mapping that improves
        # display labels when live memory omits them.
        team_candidates = [
            "2K26 Team Data (10.18.24).txt",
            "2K26 Team Data.txt",
        ]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for name in team_candidates:
            path = os.path.join(base_dir, name)
            if os.path.isfile(path):
                mapping = self.parse_team_comments(path)
                if mapping:
                    self.team_name_map = mapping
                break
        # Load category definitions for advanced editing.  These definitions
        # describe where and how to read/write additional player attributes
        # (e.g. vitals, attributes, tendencies, badges).  They come from
        # unified offsets files if present.  If no unified file is found
        # ``categories`` will be empty and the full editor will display
        # placeholder text.
        try:
            self.categories: dict[str, list[dict]] = _load_categories()
        except Exception:
            self.categories = {}
        self._reorder_categories()
        # Stores per-category partial match suggestions collected during imports.
        self.import_partial_matches: dict[str, dict[str, list[str]]] = {}

    def _make_name_key(self, first: str, last: str, sanitize: bool = False) -> str:
        """Return a normalized lookup key for the given first/last name."""
        first_norm = (first or "").strip().lower()
        last_norm = (last or "").strip().lower()
        if sanitize:
            first_norm = re.sub(r"[^a-z0-9]", "", first_norm)
            last_norm = re.sub(r"[^a-z0-9]", "", last_norm)
        key = f"{first_norm} {last_norm}".strip()
        return key

    def _generate_name_keys(self, first: str, last: str) -> list[str]:
        """Generate lookup keys (original and sanitized) for a name pair."""
        keys: list[str] = []
        first_variants = [first]
        stripped_first = self._strip_suffix_string(first)
        if stripped_first and stripped_first.lower() != first.lower():
            first_variants.append(stripped_first)
        last_variants = [last]
        stripped_last = self._strip_suffix_string(last)
        if stripped_last and stripped_last.lower() != last.lower():
            last_variants.append(stripped_last)
        for first_variant in first_variants:
            for last_variant in last_variants:
                for sanitize in (False, True):
                    key = self._make_name_key(first_variant, last_variant, sanitize=sanitize)
                    if key and key not in keys:
                        keys.append(key)
        return keys
    def _get_import_fields(self, category_name: str) -> list[dict]:
        """Return the subset of fields that correspond to the import order for the given category."""
        fields = self.categories.get(category_name, [])
        order_map: dict[str, list[str]] = {
            "Attributes": ATTR_IMPORT_ORDER,
            "Tendencies": TEND_IMPORT_ORDER,
            "Durability": DUR_IMPORT_ORDER,
            "Potential": POTENTIAL_IMPORT_ORDER,
        }
        import_order = order_map.get(category_name)
        if not fields or not import_order:
            return list(fields)
        remaining = list(fields)
        selected: list[dict] = []
        for hdr in import_order:
            norm_hdr = self._normalize_header_name(hdr)
            match_idx = -1
            for idx, fdef in enumerate(remaining):
                norm_field = self._normalize_field_name(fdef.get("name", ""))
                if norm_hdr == norm_field or norm_hdr in norm_field or norm_field in norm_hdr:
                    match_idx = idx
                    break
            if match_idx >= 0:
                selected.append(remaining.pop(match_idx))
        return selected
    # ------------------------------------------------------------------
    # Internal string helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_encoding_tag(tag: str) -> str:
        enc = (tag or "utf16").lower()
        if enc in ("ascii", "string", "text"):
            return "ascii"
        return "utf16"
    def _read_string(self, addr: int, max_chars: int, encoding: str) -> str:
        enc = self._normalize_encoding_tag(encoding)
        max_len = int(max_chars)
        if max_len <= 0:
            raise ValueError("String length must be positive according to schema.")
        if enc == "ascii":
            return self.mem.read_ascii(addr, max_len)
        return self.mem.read_wstring(addr, max_len)
    def _write_string(self, addr: int, value: str, max_chars: int, encoding: str) -> None:
        enc = self._normalize_encoding_tag(encoding)
        max_len = int(max_chars)
        if max_len <= 0:
            raise ValueError("String length must be positive according to schema.")
        if enc == "ascii":
            self.mem.write_ascii_fixed(addr, value, max_len)
        else:
            self.mem.write_wstring_fixed(addr, value, max_len)
    # -------------------------------------------------------------------------
    # Offline data loading
    # -------------------------------------------------------------------------
    def _load_external_roster(self) -> list[Player] | None:
        """External roster loading disabled."""
        return None
    # -------------------------------------------------------------------------
    # Cheat Engine team table support
    # -------------------------------------------------------------------------
    def parse_team_comments(self, filepath: str) -> Dict[int, str]:
        """Parse the <Comments> section of a CE table to extract team names.
        The "Team Data" cheat table includes a <Comments> section with lines such as
        "0 - 76ers" or "A - Jazz".  This helper reads the file and returns
        a mapping from integer indices to team names.  Indices containing
        hexadecimal characters A–F are interpreted as hex; otherwise they
        are treated as decimal.
        Args:
            filepath: Full path to the CE table file.
        Returns:
            A dictionary mapping integer team indices to team names.
        """
        mapping: Dict[int, str] = {}
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            start = text.find("<Comments>")
            end = text.find("</Comments>", start + 1)
            if start == -1 or end == -1:
                return mapping
            comments = text[start + len("<Comments>"):end]
            for line in comments.strip().splitlines():
                line = line.strip()
                if not line or '-' not in line:
                    continue
                idx_str, name = line.split('-', 1)
                idx_str = idx_str.strip()
                name = name.strip()
                # Determine base: hex if contains letters A–F
                base = 16 if any(c in idx_str.upper() for c in "ABCDEF") else 10
                try:
                    idx = int(idx_str, base)
                    mapping[idx] = name
                except ValueError:
                    continue
        except Exception:
            pass
        return mapping
    # -------------------------------------------------------------------------
    # Category reordering and import helpers
    # -------------------------------------------------------------------------    # -------------------------------------------------------------------------
    # Name index map
    # -------------------------------------------------------------------------
    def _build_name_index_map(self) -> None:
        """Rebuild the internal mapping of normalized full names to player indices.
        The map helps locate players quickly during imports and other operations.
        """
        self.name_index_map.clear()
        for player in self.players:
            first = player.first_name or ""
            last = player.last_name or ""
            if not first and not last:
                continue
            for key in self._generate_name_keys(first, last):
                if key:
                    self.name_index_map.setdefault(key, []).append(player.index)


    def _normalize_header_name(self, name: str) -> str:
        """
        Normalize a column header name for matching against field names.
        This helper performs the following transformations:
        * Converts to uppercase.
        * Removes whitespace and punctuation.
        * Applies header‑specific synonyms (e.g. "LAYUP" becomes
          "DRIVINGLAYUP", "STDUNK" becomes "STANDINGDUNK", etc.).
        Args:
            name: Raw column header from the import file.
        Returns:
            A canonical string used for matching against field names.
        """
        import re as _re
        norm = _re.sub(r'[^A-Za-z0-9]', '', str(name).upper())
        if not norm:
            return ""
        # Apply known header synonyms; map abbreviations to canonical
        # attribute names.  Only a subset of synonyms is defined here; any
        # unknown name will fall back to its normalized form.
        header_synonyms = {
            "LAYUP": "DRIVINGLAYUP",
            "STDUNK": "STANDINGDUNK",
            "DUNK": "DRIVINGDUNK",
            "CLOSE": "CLOSESHOT",
            "MID": "MIDRANGESHOT",
            "3PT": "THREEPOINT",
            "FT": "FREETHROW",
            "PHOOK": "POSTHOOK",
            "PFADE": "POSTFADE",
            "POSTC": "POSTCONTROL",
            "FOUL": "DRAWFOUL",
            "BALL": "BALLCONTROL",
            "SPDBALL": "SPEEDWITHBALL",
            "PASSIQ": "PASSINGIQ",
            "PASS_IQ": "PASSINGIQ",
            "VISION": "PASSINGVISION",
            "OCNST": "OFFENSIVECONSISTENCY",
            "ID": "INTERIORDEFENSE",
            "PD": "PERIMETERDEFENSE",
            "STEAL": "STEAL",
            "BLOCK": "BLOCK",
            "OREB": "OFFENSIVEREBOUND",
            "DREB": "DEFENSIVEREBOUND",
            "HELPIQ": "HELPDEFENSEIQ",
            "PSPER": "PASSINGPERCEPTION",
            "DCNST": "DEFENSIVECONSISTENCY",
            "SPEED": "SPEED",
            "AGIL": "AGILITY",
            "STR": "STRENGTH",
            "VERT": "VERTICAL",
            "STAM": "STAMINA",
            "INTNGBL": "INTANGIBLES",
            "INTANG": "INTANGIBLES",
            "INTANGIBLE": "INTANGIBLES",
            "INTANGIBLES": "INTANGIBLES",
            "HSTL": "HUSTLE",
            "DUR": "MISCDURABILITY",
            "POT": "POTENTIAL",
            # Durability synonyms
            "BACK": "BACKDURABILITY",
            "HEAD": "HEADDURABILITY",
            "LEFTANKLE": "LEFTANKLEDURABILITY",
            "LEFTELBOW": "LEFTELBOWDURABILITY",
            "LEFTFOOT": "LEFTFOOTDURABILITY",
            "LEFTHIP": "LEFTHIPDURABILITY",
            "LEFTKNEE": "LEFTKNEEDURABILITY",
            "LEFTSHOULDER": "LEFTSHOULDERDURABILITY",
            "NECK": "NECKDURABILITY",
            "RIGHTANKLE": "RIGHTANKLEDURABILITY",
            "RIGHTELBOW": "RIGHTELBOWDURABILITY",
            "RIGHTFOOT": "RIGHTFOOTDURABILITY",
            "RIGHTHIP": "RIGHTHIPDURABILITY",
            "RIGHTKNEE": "RIGHTKNEEDURABILITY",
            "RIGHTSHOULDER": "RIGHTSHOULDERDURABILITY",
            "MISCELLANEOUS": "MISCELLANEOUSDURABILITY",
            "MISCELLANEOUSDURABILITY": "MISCELLANEOUSDURABILITY",
            # Tendencies abbreviations (T/ prefixed) mapped to canonical field names.
            # These mappings allow the importer to align columns from the
            # Tendencies spreadsheet with the corresponding field names in
            # the offset map.  Each key is the normalized abbreviation (no
            # punctuation); the value is the normalized field name
            # (uppercase, no spaces) used in the offset map.  This list
            # covers all abbreviations that appear in the user's sheet.
            # Abbreviation mappings for shooting/finishing
            "TSHOT": "SHOOT",  # generic Shot -> Shoot (from user: shot = shoot)
            "TTOUCH": "TOUCHES",
            "TSCLOSE": "SHOTCLOSE",
            "TSUNDER": "SHOTUNDERBASKET",
            "TSCL": "SHOTCLOSELEFT",
            "TSCM": "SHOTCLOSEMIDDLE",
            "TSCR": "SHOTCLOSERIGHT",
            "TSMID": "SHOTMID",
            "TSUSMID": "SPOTUPSHOTMID",
            "TOSSMID": "OFFSCREENSHOTMID",
            "TSML": "SHOTMIDLEFT",
            "TSMLC": "SHOTMIDLEFTCENTER",
            "TSMC": "SHOTMIDCENTER",
            "TSMRC": "SHOTMIDRIGHTCENTER",
            "TSMR": "SHOTMIDRIGHT",
            "TS3PT": "SHOT3PT",
            "TSUS3PT": "SPOTUPSHOT3PT",
            "TOSS3PT": "OFFSCREENSHOT3PT",
            "TS3L": "SHOT3PTLEFT",
            "TS3LC": "SHOT3PTLEFTCENTER",
            "TS3C": "SHOT3PTCENTER",
            "TS3RC": "SHOT3PTRIGHTCENTER",
            "TS3R": "SHOT3PTRIGHT",
            "TCONTMID": "CONTESTEDJUMPERMID",
            "TCONT3PT": "CONTESTEDJUMPER3PT",
            "TSBMID": "STEPBACKJUMPERMID",
            "TSB3PT": "STEPBACKJUMPER3PT",
            # Spin Jumper tendency abbreviation
            "TSPINJ": "SPINJUMPERTENDENCY",
            # Transition pull‑up 3pt (not drive)
            "TTPU3PT": "TRANSITIONPULLUP3PT",
            "TDPUMID": "DRIVEPULLUPMID",
            "TDPU3PT": "DRIVEPULLUP3PT",
            "TDRIVE": "DRIVE",
            "TSUDRIVE": "SPOTUPDRIVE",
            "TOSDRIVE": "OFFSCREENDRIVE",
            # Use Glass tendency; map to USEGLASS rather than Crash
            "TGLASS": "USEGLASS",
            "TSTHRU": "STEPTHROUGHSHOT",
            "TDRLAYUP": "DRIVINGLAYUPTENDENCY",
            "TSPLAYUP": "SPINLAYUP",
            "TEURO": "EUROSTEP",
            "THOPSTEP": "HOPSTEP",
            "TFLOATER": "FLOATER",
            "TSDUNK": "STANDINGDUNKTENDENCY",
            "TDDUNK": "DRIVINGDUNKTENDENCY",
            "TFDUNK": "FLASHYDUNKTENDENCY",
            # Alley‑oop dunk tendency
            "TAOOP": "ALLEYOOP",
            "TPUTBACK": "PUTBACK",
            "TCRASH": "CRASH",
            # Drive‑R abbreviation represents Drive Right
            "TDRIVER": "DRIVERIGHT",
            "TTTPFAKE": "TRIPLETHREATPUMPFAKE",
            "TJABSTEP": "TRIPLETHREATJABSTEP",
            "TTTIDLE": "TRIPLETHREATIDLE",
            "TTTSHOOT": "TRIPLETHREATSHOOT",
            # Setup moves (Sizeup and Hesitation) and no setup
            "TSIZEUP": "SETUPWITHSIZEUP",
            "THSTTN": "SETUPWITHHESITATION",
            "TNOSETUP": "NOSETUPDRIBBLE",
            # Dribble move abbreviations map to their driving variants
            "TXOVER": "DRIVINGCROSSOVER",
            "T2XOVER": "DRIVINGDOUBLECROSSOVER",
            # TSPIN abbreviation corresponds to the driving spin dribble move
            "TSPIN": "DRIVINGSPIN",
            # Half spin corresponds to driving half spin
            "THSPIN": "DRIVINGHALFSPIN",
            # Stepback corresponds to driving stepback
            "TSBACK": "DRIVINGSTEPBACK",
            # Behind‑the‑back corresponds to driving behind the back
            "TBBACK": "DRIVINGBEHINDBACK",
            # Double hesitation corresponds to driving dribble hesitation
            "TDHSTTN": "DRIVINGDRIBBLEHESITATION",
            "TINNOUT": "INANDOUT",
            "TNODRIB": "NODRIBBLE",
            "TFINISH": "ATTACKSTRONGONDRIVE",  # finish = attack strong on drive
            "TDISH": "DISHTOOPENMAN",  # dish = dish to open man
            "TFLASHYP": "FLASHYPASS",
            "TAOOPP": "ALLEYOOPPASS",
            # Roll vs Pop ratio (pick and roll) maps to RollVsPop
            "TROLLPOP": "ROLLVSPOP",
            "TSPOTCUT": "SPOTUPCUT",
            "TISOVSE": "ISOVSE",
            "TISOVSG": "ISOVSG",
            "TISOVSA": "ISOVSA",
            "TISOVSP": "ISOVSP",
            "TPLYDISC": "PLAYDISCIPLINE",
            "TPOSTUP": "POSTUP",
            "TPBDOWN": "POSTBACKDOWN",
            "TPAGGBD": "POSTAGGRESSIVEBACKDOWN",
            "TPFACEUP": "POSTFACEUP",
            "TPSPIN": "POSTSPIN",
            "TPDRIVE": "POSTDRIVE",
            "TPDSTEP": "POSTDROPSTEP",
            "TPHSTEP": "POSTHOPSTEP",
            "TPSHOOT": "POSTSHOT",
            "TPHOOKL": "POSTHOOKLEFT",
            "TPHOOKR": "POSTHOOKRIGHT",
            "TPFADEL": "POSTFADELEFT",
            "TPFADER": "POSTFADERIGHT",
            "TPSHIMMY": "POSTSHIMMY",
            "TPHSHOT": "POSTHOPSHOT",
            "TPSBSHOT": "POSTSTEPBACKSHOT",
            "TPUPNUND": "POSTUPANDUNDER",
            "TTAKEC": "TAKECHARGE",
            # General foul tendency
            "TFOUL": "FOUL",
            "THFOUL": "HARDFOUL",
            # Pass Interception tendency
            "TPINTERC": "PASSINTERCEPTION",
            "TSTEAL": "STEAL",
            "TBLOCK": "BLOCK",
            "TCONTEST": "CONTEST",
        }
        # Replace slashes in SPD/BALL etc.
        # Normalize specific patterns
        # Example: SPD/BALL -> SPDBALL, PASS_IQ -> PASSIQ
        if norm in header_synonyms:
            return header_synonyms[norm]
        summary_tokens = (
            "TOTAL",
            "TOTALS",
            "TOTALATTRIBUTES",
            "ATTRIBUTESTOTAL",
            "TOTALPOINTS",
            "ATTRIBUTESPOINTS",
            "TOTALCOUNT",
            "COUNTTOTAL",
        )
        if any(norm == token or norm.startswith(token) or norm.endswith(token) for token in summary_tokens):
            return ""
        return norm
    def _normalize_field_name(self, name: str) -> str:
        """
        Normalize a field name from the offset map for matching.
        This helper performs uppercase conversion and removal of
        non-alphanumeric characters, then applies aliases so descriptive
        labels align with the abbreviated headers used by imports.
        """
        import re as _re
        norm = _re.sub(r'[^A-Za-z0-9]', '', str(name).upper())
        return FIELD_NAME_ALIASES.get(norm, norm)
    def _reorder_categories(self) -> None:
        """
        Reorder the categories and fields based on predefined import orders
        and group durability fields into their own category.
        This method modifies ``self.categories`` in place.  It does the
        following:
        * Moves any attribute whose name contains ``Durability`` (case
          insensitive) into a new category called ``Durability``.
        * Reorders the ``Attributes`` category according to
          ``ATTR_IMPORT_ORDER`` using normalized names to match.  Any
          fields not listed in the import order remain at the end in
          their original order.
        * Reorders the ``Tendencies`` category according to
          ``TEND_IMPORT_ORDER`` using a fuzzy matching on normalized
          header names and field names.  Unmatched fields remain at the
          end.
        * Reorders the ``Durability`` category according to
          ``DUR_IMPORT_ORDER`` (if the category exists) using normalized
          header names.  Unmatched fields remain at the end.
        """
        # Ensure the categories dict exists
        cats = self.categories or {}
        # Categories that come from the offsets file but are not relevant for the
        # player-focused editor UI (they relate to team tables instead).  Drop
        # them so they do not appear as extra tabs in the player editor.
        for skip in ("Teams", "Team Players"):
            cats.pop(skip, None)
        # ------------------------------------------------------------------
        # Extract durability fields from Attributes
        if 'Attributes' in cats:
            attr_fields = cats.get('Attributes', [])
            new_attr = []
            dura_fields = cats.get('Durability', [])  # if already exists
            for fld in attr_fields:
                name = fld.get('name', '')
                norm = self._normalize_field_name(name)
                if (
                    'DURABILITY' in norm
                    and norm not in ('MISCDURABILITY',)
                ):
                    dura_fields.append(fld)
                else:
                    new_attr.append(fld)
            cats['Attributes'] = new_attr
            if dura_fields:
                cats['Durability'] = dura_fields
        # ------------------------------------------------------------------
        # Helper to reorder a category based on an import order list
        def reorder(cat_name: str, import_order: list[str]):
            if cat_name not in cats:
                return
            fields = cats[cat_name]
            # Build a list of remaining fields
            remaining = list(fields)
            reordered: list[dict] = []
            for hdr in import_order:
                norm_hdr = self._normalize_header_name(hdr)
                if not norm_hdr:
                    continue
                best_idx = -1
                best_score = 3  # 0 = exact, 1 = header in field, 2 = field in header
                for idx, f in enumerate(remaining):
                    norm_field = self._normalize_field_name(f.get('name', ''))
                    if not norm_field:
                        continue
                    score = None
                    if norm_hdr == norm_field:
                        score = 0
                    elif norm_hdr in norm_field:
                        score = 1
                    elif norm_field in norm_hdr:
                        score = 2
                    if score is None:
                        continue
                    if score < best_score:
                        best_idx = idx
                        best_score = score
                        if score == 0:
                            break
                if best_idx >= 0:
                    reordered.append(remaining.pop(best_idx))
            # Append any unmatched fields at the end
            reordered.extend(remaining)
            cats[cat_name] = reordered
        # Reorder attributes, tendencies, durability, potential
        reorder('Attributes', ATTR_IMPORT_ORDER)
        reorder('Tendencies', TEND_IMPORT_ORDER)
        reorder('Durability', DUR_IMPORT_ORDER)
        reorder('Potential', POTENTIAL_IMPORT_ORDER)
        # Save back in a deterministic order.  We prefer to display
        # categories in a consistent order matching the import tables.
        ordered = {}
        preferred = [
            'Body',
            'Vitals',
            'Attributes',
            'Durability',
            'Potential',
            'Tendencies',
            'Badges',
        ]
        for name in preferred:
            if name in cats:
                ordered[name] = cats[name]
        # Append any remaining categories not listed above
        for name, fields in cats.items():
            if name not in ordered:
                ordered[name] = fields
        self.categories = ordered
    def find_player_indices_by_name(self, name: str) -> list[int]:
        """
        Find player indices matching a given full name.
        Args:
            name: Full name as appearing in import files (e.g. "LeBron James").
        Returns:
            A list of integer indices of players whose first and last names
            match the given name (case‑insensitive).  If no match is found
            returns an empty list.
        """
        name = str(name or '').strip()
        if not name:
            return []
        parts = name.split()
        if not parts:
            return []
        first = parts[0].strip()
        last = ' '.join(parts[1:]).strip() if len(parts) > 1 else ''
        # Use the name_index_map for efficient lookup if available
        if self.name_index_map:
            for key in self._generate_name_keys(first, last):
                if key and key in self.name_index_map:
                    return self.name_index_map[key]
        # Fallback: linear scan over players with sanitized comparison
        target_keys = set(self._generate_name_keys(first, last))
        indices: list[int] = []
        for p in self.players:
            player_keys = self._generate_name_keys(p.first_name, p.last_name)
            if target_keys.intersection(player_keys):
                indices.append(p.index)
        return indices

    def _name_variants(self, raw_name: str) -> list[str]:
        """Return plausible player name variants derived from an import cell."""
        text = str(raw_name or "").strip()
        if not text:
            return []
        base = " ".join(text.replace("\u00a0", " ").split())
        variants: list[str] = []
        if base:
            variants.append(base)
            stripped = re.sub(r"[^A-Za-z0-9 ]", "", base)
            if stripped and stripped != base:
                variants.append(" ".join(stripped.split()))
        parts = base.split()
        if "," in base:
            parts = [p.strip() for p in base.split(",", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                variants.append(f"{parts[1]} {parts[0]}")
        elif len(parts) >= 2:
            first = parts[-1]
            last = " ".join(parts[:-1])
            variants.append(f"{first} {last}".strip())
            stripped_parts = re.sub(r"[^A-Za-z0-9 ]", "", base).split()
            if stripped_parts and len(stripped_parts) >= 2:
                stripped_first = stripped_parts[-1]
                stripped_last = " ".join(stripped_parts[:-1])
                variants.append(f"{stripped_first} {stripped_last}".strip())
        expanded_variants: list[str] = []
        for candidate in variants:
            expanded_variants.append(candidate)
            # Add variant with trailing suffix tokens removed
            stripped_words = self._strip_suffix_words(candidate.split())
            if stripped_words:
                stripped_variant = " ".join(stripped_words).strip()
                if stripped_variant and stripped_variant.lower() != candidate.lower():
                    expanded_variants.append(stripped_variant)
            words = candidate.split()
            for idx, word in enumerate(words):
                stripped_word = re.sub(r"[^A-Za-z]", "", word)
                if not stripped_word:
                    continue
                key = stripped_word.lower()
                synonyms = NAME_SYNONYMS.get(key)
                if not synonyms:
                    continue
                pattern = re.compile(re.escape(stripped_word), re.IGNORECASE)
                for repl in synonyms:
                    new_word = pattern.sub(repl, word, count=1)
                    new_words = list(words)
                    new_words[idx] = new_word
                    expanded_variants.append(" ".join(new_words).strip())
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in expanded_variants:
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(candidate)
        return ordered

    def _match_player_indices(self, raw_name: str) -> list[int]:
        """Try matching a raw name against the roster using common variants."""
        for candidate in self._name_variants(raw_name):
            idxs = self.find_player_indices_by_name(candidate)
            if idxs:
                return idxs
        return []

    @staticmethod
    def _sanitize_name_token(token: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (token or "").lower())

    @staticmethod
    def _strip_suffix_words(words: list[str]) -> list[str]:
        if not words:
            return []
        trimmed = list(words)
        while trimmed:
            suffix_token = re.sub(r"[^a-z0-9]", "", trimmed[-1].lower())
            if suffix_token in NAME_SUFFIXES:
                trimmed.pop()
                continue
            break
        return trimmed

    @staticmethod
    def _strip_suffix_string(text: str) -> str:
        words = PlayerDataModel._strip_suffix_words(text.split())
        return " ".join(words).strip()

    @staticmethod
    def _normalize_family_token(token: str) -> str:
        sanitized = PlayerDataModel._sanitize_name_token(token)
        for suffix in sorted(NAME_SUFFIXES, key=len, reverse=True):
            if sanitized.endswith(suffix):
                sanitized = sanitized[: -len(suffix)]
                break
        return sanitized

    def _partial_name_candidates(self, raw_name: str) -> list[str]:
        variants = self._name_variants(raw_name)
        first_tokens: set[str] = set()
        last_tokens: set[str] = set()
        norm_first_tokens: set[str] = set()
        norm_last_tokens: set[str] = set()
        for variant in variants:
            parts = variant.split()
            if len(parts) >= 2:
                first = parts[0]
                last = " ".join(parts[1:])
                sf = self._sanitize_name_token(first)
                sl = self._sanitize_name_token(last)
                if sf:
                    first_tokens.add(sf)
                    norm_first_tokens.add(self._normalize_family_token(first))
                if sl:
                    last_tokens.add(sl)
                    norm_last_tokens.add(self._normalize_family_token(last))
        if not first_tokens and not last_tokens:
            return []
        candidates: list[str] = []
        seen: set[str] = set()
        for player in self.players:
            pf = self._sanitize_name_token(player.first_name)
            pl = self._sanitize_name_token(player.last_name)
            pf_norm = self._normalize_family_token(player.first_name)
            pl_norm = self._normalize_family_token(player.last_name)
            strict_first = pf in first_tokens
            strict_last = pl in last_tokens
            fuzzy_first = pf_norm in norm_first_tokens
            fuzzy_last = pl_norm in norm_last_tokens
            strong_match = strict_first and strict_last
            partial = False
            if strict_first != strict_last:
                partial = True
            elif not strong_match:
                if (strict_first and fuzzy_last) or (strict_last and fuzzy_first):
                    partial = True
                elif fuzzy_first != fuzzy_last:
                    partial = True
            if partial and (strict_first or strict_last or fuzzy_first or fuzzy_last):
                full_name = player.full_name
                if full_name not in seen:
                    seen.add(full_name)
                    candidates.append(full_name)
        return candidates

    def _get_import_order(self, category_name: str) -> list[str]:
        name = (category_name or "").strip().lower()
        if name == "attributes":
            return ATTR_IMPORT_ORDER
        if name == "tendencies":
            return TEND_IMPORT_ORDER
        if name == "durability":
            return DUR_IMPORT_ORDER
        if name == "potential":
            return POTENTIAL_IMPORT_ORDER
        return []

    def prepare_import_rows(self, category_name: str, rows: Sequence[Sequence[str]]) -> dict[str, object] | None:
        if not rows:
            return None
        layout = COY_IMPORT_LAYOUTS.get(category_name)
        if layout:
            value_columns = list(layout.get("value_columns", []))
            column_headers = list(layout.get("column_headers", []))
            skip_names = {str(s).strip().lower() for s in layout.get("skip_names", set())}
            name_columns_raw = layout.get("name_columns")
            if name_columns_raw is None:
                name_columns = [int(layout.get("name_col", 0))]
            else:
                name_columns = [int(col) for col in name_columns_raw]
            header_lookup: dict[str, int] = {}
            if column_headers and rows:
                header_row = rows[0]
                for idx, cell in enumerate(header_row):
                    norm_cell = self._normalize_header_name(cell)
                    if norm_cell and norm_cell not in header_lookup:
                        header_lookup[norm_cell] = idx
            resolved_value_indices: list[int] = []
            if column_headers:
                for hdr in column_headers:
                    norm_hdr = self._normalize_header_name(hdr)
                    if norm_hdr and norm_hdr in header_lookup:
                        resolved_value_indices.append(header_lookup[norm_hdr])

            def _is_valid_name(cell: str) -> bool:
                normalized = (cell or "").strip()
                if not normalized:
                    return False
                if normalized.lower() in skip_names:
                    return False
                return any(ch.isalpha() for ch in normalized)

            def _row_has_numeric(row: Sequence[str]) -> bool:
                target_columns = resolved_value_indices or value_columns
                if not target_columns and column_headers:
                    # If columns are derived from headers but none were resolved, fall back to scanning entire row.
                    target_columns = [i for i in range(len(row)) if i not in name_columns]
                for idx in target_columns:
                    if idx >= len(row):
                        continue
                    cell = str(row[idx]).strip()
                    if not cell:
                        continue
                    if any(ch.isdigit() for ch in cell) and not any(ch.isalpha() for ch in cell):
                        return True
                return False

            data_rows: list[list[str]] = []
            for row in rows:
                name_value: str | None = None
                for col in name_columns:
                    if col >= len(row):
                        continue
                    candidate = str(row[col]).strip()
                    if _is_valid_name(candidate):
                        name_value = candidate
                        break
                if not name_value:
                    continue
                if not _row_has_numeric(row):
                    continue
                if column_headers:
                    values: list[str] = []
                    for hdr in column_headers:
                        norm_hdr = self._normalize_header_name(hdr)
                        col_idx = header_lookup.get(norm_hdr)
                        if col_idx is None or col_idx >= len(row):
                            values.append("")
                        else:
                            values.append(row[col_idx])
                else:
                    values = [row[idx] if idx < len(row) else "" for idx in value_columns]
                data_rows.append([name_value, *values])
            if not data_rows:
                return None
            order_headers: list[str] = []
            if category_name == "Attributes":
                order_headers = ["Player Name", *ATTR_IMPORT_ORDER]
            elif category_name == "Tendencies":
                order_headers = ["Player Name", *TEND_IMPORT_ORDER]
            elif category_name == "Durability":
                order_headers = ["Player Name", *DUR_IMPORT_ORDER]
            elif category_name == "Potential":
                order_headers = ["Player Name", *POTENTIAL_IMPORT_ORDER]
            else:
                order_headers = []
            return {
                "header": order_headers,
                "data_rows": data_rows,
                "name_col": 0,
                "value_columns": list(range(1, len(order_headers))),
            }
        header = rows[0]
        if not header:
            return None
        name_col = 0
        value_columns = list(range(1, len(header)))
        data_rows = [row for row in rows[1:] if any(str(cell).strip() for cell in row)]
        if not value_columns or not data_rows:
            return None
        return {
            "header": header,
            "data_rows": data_rows,
            "name_col": name_col,
            "value_columns": value_columns,
        }

    def import_table(self, category_name: str, filepath: str) -> int:
        """
        Import player data from a tab- or comma-delimited file for a single category.
        The first column is assumed to contain player names unless a fixed layout overrides it.
        Subsequent columns are read in order and applied to the category's field definitions.
        Values are converted to raw bitfield representations as required.
        Args:
            category_name: Name of the category to import (e.g. "Attributes",
                "Tendencies", "Durability", "Potential").
            filepath: Path to the import file.
        Returns:
            The number of players successfully updated.
        """
        import csv as _csv
        # Ensure category exists
        if category_name not in self.categories:
            return 0
        # Open file
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # Try to detect delimiter: prefer tab, then comma, semicolon
                sample = f.readline()
                delim = '\t' if '\t' in sample else ',' if ',' in sample else ';'
                # Reset file pointer
                f.seek(0)
                reader = _csv.reader(f, delimiter=delim)
                rows = list(reader)
        except Exception:
            return 0
        if not rows:
            return 0
        info = self.prepare_import_rows(category_name, rows)
        if not info:
            return 0
        header = info["header"]
        data_rows = info["data_rows"]
        name_col = info["name_col"]
        value_columns = info["value_columns"]
        field_defs = self._get_import_fields(category_name) or self.categories.get(category_name, [])
        if not field_defs:
            return 0
        fixed_mapping = bool(info.get("fixed_mapping"))
        header = info.get("header") or []
        selected_columns: list[int] = []
        mappings: list[dict] = []
        if header and not fixed_mapping:
            normalized_headers = [
                self._normalize_header_name(h) if idx != name_col else ""
                for idx, h in enumerate(header)
            ]
            remaining_fields = list(field_defs)
            for idx, norm_hdr in enumerate(normalized_headers):
                if idx == name_col or not norm_hdr:
                    continue
                match_idx = -1
                for j, fdef in enumerate(remaining_fields):
                    norm_field = self._normalize_field_name(fdef.get("name", ""))
                    if norm_hdr == norm_field or norm_hdr in norm_field or norm_field in norm_hdr:
                        match_idx = j
                        break
                if match_idx >= 0:
                    mappings.append(remaining_fields.pop(match_idx))
                    selected_columns.append(idx)
        else:
            selected_columns = value_columns[:len(field_defs)]
            mappings = list(field_defs[:len(selected_columns)])
        if not data_rows or not selected_columns:
            return 0
        players_updated = 0
        partial_matches: dict[str, list[str]] = {}
        for row in data_rows:
            if not row:
                continue
            if len(row) <= name_col:
                continue
            raw_name = str(row[name_col]).strip()
            if not raw_name:
                continue
            idxs = self._match_player_indices(raw_name)
            if not idxs:
                candidates = self._partial_name_candidates(raw_name)
                if candidates:
                    partial_matches.setdefault(raw_name, [])
                    for cand in candidates:
                        if cand not in partial_matches[raw_name]:
                            partial_matches[raw_name].append(cand)
                continue
            # Apply values to each matching player
            for idx in idxs:
                any_set = False
                for col_idx, meta in zip(selected_columns, mappings):
                    if meta is None or col_idx >= len(row):
                        continue
                    val = row[col_idx]
                    if meta is None:
                        continue
                    # Retrieve offset, start_bit and length.  Offsets in
                    # the offset map may be strings (e.g. "0x392"), so
                    # handle hex prefixes gracefully.  If the offset
                    # cannot be parsed, default to zero.
                    off_raw = meta.get('offset')
                    try:
                        if isinstance(off_raw, str):
                            off_str = off_raw.strip()
                            # Allow hex prefixes (0x...) and decimal
                            if off_str.lower().startswith('0x'):
                                offset = int(off_str, 16)
                            else:
                                offset = int(off_str)
                        else:
                            offset = int(off_raw)
                    except Exception:
                        offset = 0
                    start_bit = int(meta.get('startBit', meta.get('start_bit')))
                    length = int(meta.get('length'))
                    # Convert string value to integer; ignore non‑numeric
                    try:
                        # Remove percentage signs or other non-digits
                        import re as _re
                        v = _re.sub(r'[^0-9.-]', '', str(val))
                        if not v:
                            continue
                        num = float(v)
                    except Exception:
                        continue
                    requires_deref = bool(meta.get("requiresDereference") or meta.get("requires_deref"))
                    deref_offset = _to_int(meta.get("dereferenceAddress") or meta.get("deref_offset"))
                    max_raw = (1 << length) - 1
                    if category_name in ('Attributes', 'Durability', 'Potential'):
                        # Interpret the imported value directly as a rating on
                        # the 25-99 scale and convert to raw.  Values
                        # outside the expected range are clamped internally.
                        raw = convert_rating_to_raw(num, length)
                    elif category_name == 'Tendencies':
                        # Tendencies are 0-100 scale; convert accordingly
                        raw = convert_rating_to_tendency_raw(num, length)
                    else:
                        # Other categories (if any) are assumed to be
                        # percentages ranging 0..100.  Map linearly to the
                        # raw bitfield range.
                        if max_raw > 0:
                            pct = min(max(num, 0.0), 100.0) / 100.0
                            raw = int(round(pct * max_raw))
                        else:
                            raw = 0
                    # Write value
                    if self.set_field_value(
                        idx,
                        offset,
                        start_bit,
                        length,
                        raw,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                    ):
                        any_set = True
                if any_set:
                    players_updated += 1
        if partial_matches:
            self.import_partial_matches[category_name] = partial_matches
        else:
            self.import_partial_matches[category_name] = {}
        return players_updated
    def import_all(self, file_map: dict[str, str]) -> dict[str, int]:
        """
        Import multiple tables from a mapping of category names to file paths.
        Args:
            file_map: A mapping of category names ("Attributes", "Tendencies",
                "Durability", "Potential") to file paths.  If a file path is an
                empty string or does not exist, that category will be skipped.
        Returns:
            A dictionary mapping category names to the number of players
            updated for each category.
        """
        results: dict[str, int] = {}
        self.import_partial_matches = {}
        for cat, path in file_map.items():
            self.import_partial_matches.setdefault(cat, {})
            if not path or not os.path.isfile(path):
                results[cat] = 0
                continue
            results[cat] = self.import_table(cat, path)
        return results
    # -----------------------------------------------------------------
    # Pointer resolution helpers
    # -----------------------------------------------------------------
    def _resolve_pointer_from_chain(self, chain_entry: object) -> int | None:
        """Resolve a pointer chain entry produced by the offsets loader.
        Returns the computed absolute address or ``None`` if the chain
        cannot be resolved."""
        if not self.mem.hproc or self.mem.base_addr is None:
            return None
        if isinstance(chain_entry, dict):
            base_rva = _to_int(chain_entry.get("rva"))
            if base_rva == 0:
                return None
            absolute = bool(chain_entry.get("absolute"))
            try:
                base_addr = base_rva if absolute else self.mem.base_addr + base_rva
                ptr = self.mem.read_uint64(base_addr)
            except Exception:
                return None
            steps = chain_entry.get("steps") or []
            try:
                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    offset = _to_int(step.get("offset"))
                    if offset:
                        ptr += offset
                    if step.get("dereference"):
                        if ptr == 0:
                            return None
                        ptr = self.mem.read_uint64(ptr)
                    extra = _to_int(
                        step.get("post_add")
                        or step.get("postAdd")
                        or step.get("post")
                        or step.get("post_offset")
                        or step.get("postOffset")
                        or step.get("final_offset")
                        or step.get("finalOffset")
                    )
                    if extra:
                        ptr += extra
            except Exception:
                return None
            final_offset = _to_int(chain_entry.get("final_offset") or chain_entry.get("finalOffset"))
            if final_offset:
                ptr += final_offset
            return ptr
        if isinstance(chain_entry, tuple) and len(chain_entry) == 3:
            try:
                rva_off, final_off, extra_deref = chain_entry
                p0_addr = self.mem.base_addr + rva_off
                p = self.mem.read_uint64(p0_addr)
                if extra_deref:
                    if p == 0:
                        return None
                    p = self.mem.read_uint64(p)
                return p + final_off
            except Exception:
                return None
        return None

    def _resolve_player_table_base(self) -> int | None:
        """Resolve and cache the base pointer of the player table.
        Player records live in a contiguous array of fixed-size structures.
        Pointer chains supplied via ``PLAYER_PTR_CHAINS`` describe how to
        reach that array.  Each entry is a dictionary produced by
        ``_parse_pointer_chain_config`` containing the module-relative
        ``rva``, optional ``steps`` (lists of ``offset``/``dereference`` hops)
        and a trailing ``final_offset``.  Each candidate chain is applied
        until one yields readable player names.  Successful results are
        cached; ``None`` is returned when no candidate resolves to a
        plausible address."""
        if self._resolved_player_base is not None:
            return self._resolved_player_base
        if not self.mem.hproc or self.mem.base_addr is None:
            return None
        for chain_entry in PLAYER_PTR_CHAINS:
            table_base = self._resolve_pointer_from_chain(chain_entry)
            if table_base is None:
                continue
            try:
                ln = self._read_string(table_base + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()
                fn = self._read_string(table_base + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
                if ln or fn:
                    self._resolved_player_base = table_base
                    return table_base
            except Exception:
                continue
        return None

    def _resolve_team_base_ptr(self) -> int | None:
        """Resolve and cache the base pointer of the team records.
        ``TEAM_PTR_CHAINS`` entries follow the same dictionary format as the
        player chains.  Each candidate is evaluated until a printable team
        name is located; the first success is cached and returned.  ``None``
        is returned when every chain fails."""
        if self._resolved_team_base is not None:
            return self._resolved_team_base
        if not self.mem.hproc or self.mem.base_addr is None:
            return None
        for chain_entry in TEAM_PTR_CHAINS:
            team_base = self._resolve_pointer_from_chain(chain_entry)
            if team_base is None:
                continue
            try:
                name = self._read_string(team_base + TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
                if name and all(32 <= ord(ch) <= 126 for ch in name):
                    self._resolved_team_base = team_base
                    return team_base
            except Exception:
                continue
        return None

    # ---------------------------------------------------------------------
    # In‑memory team and player scanning
    # ---------------------------------------------------------------------
    def _scan_team_names(self) -> list[tuple[int, str]]:
        """Read the list of team names from the running game process.
        This helper uses the pointer chain defined in the Cheat Engine
        "Team Data" table to locate the base of the team records.  It then
        iterates over the first several teams, reading the team name string
        from each record.  If successful, it returns a list of (index,
        name) tuples.  On failure, it returns an empty list.
        """
        # Require an open process and a base address
        if not self.mem.hproc or self.mem.base_addr is None:
            return []
        # Resolve the base of the team table via candidate pointer chains
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return []
        teams: list[tuple[int, str]] = []
        # Scan up to MAX_TEAMS_SCAN teams.  This covers NBA teams, All‑Time
        # teams, Draft Class teams and G‑League teams.  Stop when an
        # empty or non‑ASCII name is encountered.
        for i in range(MAX_TEAMS_SCAN):
            try:
                rec_addr = team_base_ptr + i * TEAM_STRIDE
                name = self._read_string(rec_addr + TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
            except Exception:
                break
            # Stop if the name is empty
            if not name:
                break
            # If the name contains mostly non‑printable characters, assume
            # we've gone past the valid list and stop.
            if any(ord(ch) < 32 or ord(ch) > 126 for ch in name):
                break
            teams.append((i, name))
        return teams
    def scan_team_players(self, team_idx: int) -> list[Player]:
        """Retrieve the list of players on a given team.
        This function reads the roster pointers for the specified team and
        returns a list of ``Player`` objects.  It does **not** update
        ``self.players``; instead it always returns a fresh list.
        Args:
            team_idx: Zero‑based team index (0 for 76ers, 1 for Bucks, etc.).
        Returns:
            A list of ``Player`` instances for the specified team, or an
            empty list if reading fails.
        """
        if not self.mem.hproc or self.mem.base_addr is None:
            return []
        # Resolve player and team base pointers using dynamic resolution
        player_table_base = self._resolve_player_table_base()
        if player_table_base is None:
            return []
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return []
        rec_addr = team_base_ptr + team_idx * TEAM_STRIDE
        players: list[Player] = []
        for slot in range(TEAM_PLAYER_SLOT_COUNT):
            try:
                ptr = self.mem.read_uint64(rec_addr + slot * 8)
            except Exception:
                # Skip this slot if pointer read fails
                continue
            # Skip null pointers
            if not ptr:
                continue
            try:
                # Compute index relative to player table
                idx = int((ptr - player_table_base) // PLAYER_STRIDE)
            except Exception:
                idx = -1
            try:
                last_name = self._read_string(ptr + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()
                first_name = self._read_string(ptr + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
            except Exception:
                # Skip this player if any field cannot be read
                continue
            if not first_name and not last_name:
                continue
            team_name = self._get_team_display_name(team_idx)
            players.append(Player(idx if idx >= 0 else len(players), first_name, last_name, team_name, team_idx))
        return players
    # -----------------------------------------------------------------
    # Team editing API
    # -----------------------------------------------------------------
    def get_team_fields(self, team_idx: int) -> Dict[str, str] | None:
        """Return the editable fields for the specified team.
        This method reads the team record for the given index and
        extracts each field defined in ``TEAM_FIELD_DEFS``.  The return
        value is a mapping from field label to its current string
        value.  If the game process is not open, or the team table
        cannot be resolved, ``None`` is returned.
        Args:
            team_idx: The zero‑based index of the team (0 = 76ers).
        Returns:
            A dictionary mapping field names to their current values,
            or ``None`` if reading fails.
        """
        if not self.mem.hproc or self.mem.base_addr is None:
            return None
        if TEAM_RECORD_SIZE <= 0 or not TEAM_FIELD_DEFS:
            return None
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return None
        rec_addr = team_base_ptr + team_idx * TEAM_RECORD_SIZE
        fields: Dict[str, str] = {}
        for label, (offset, max_chars, encoding) in TEAM_FIELD_DEFS.items():
            try:
                val = self._read_string(rec_addr + offset, max_chars, encoding).rstrip("\x00")
            except Exception:
                val = ""
            fields[label] = val
        return fields
    def set_team_fields(self, team_idx: int, values: Dict[str, str]) -> bool:
        """Write the given values into the specified team record.
        Given a mapping of field names to strings, this method writes
        each value back into the corresponding location of the team
        record.  Only fields defined in ``TEAM_FIELD_DEFS`` will be
        updated; extra keys in ``values`` are ignored.  Strings are
        truncated to fit within the maximum character length of their
        fields.  The function returns ``True`` if the write succeeds
        for all fields and ``False`` if any errors occur.
        Args:
            team_idx: Zero‑based index of the team.
            values: Mapping from field label to new value.
        Returns:
            ``True`` if all writes succeeded, ``False`` otherwise.
        """
        if not self.mem.hproc or self.mem.base_addr is None:
            return False
        if TEAM_RECORD_SIZE <= 0 or not TEAM_FIELD_DEFS:
            return False
        team_base_ptr = self._resolve_team_base_ptr()
        if team_base_ptr is None:
            return False
        rec_addr = team_base_ptr + team_idx * TEAM_RECORD_SIZE
        success = True
        for label, (offset, max_chars, encoding) in TEAM_FIELD_DEFS.items():
            if label not in values:
                continue
            val = values[label]
            try:
                self._write_string(rec_addr + offset, val, max_chars, encoding)
            except Exception:
                success = False
        return success
    def _scan_all_players(self, max_scan: int = 1024) -> list[Player]:
        """Enumerate player records sequentially from memory.
        This method reads every player record from the player table in the
        running game up to ``max_scan`` entries.  Each record is
        interpreted using the offsets defined at the top of this file.
        Team names are resolved via the ``OFF_TEAM_PTR`` and
        ``OFF_TEAM_NAME`` offsets.  If any read fails, scanning stops.
        Args:
            max_scan: Maximum number of players to read to avoid long loops.
        Returns:
            A list of ``Player`` instances.  If scanning fails or yields
            suspiciously corrupted names (e.g. mostly non‑ASCII), an empty
            list is returned.
        """
        if not self.mem.hproc or self.mem.base_addr is None:
            return []
        # Determine player table base pointer using dynamic resolution
        table_base = self._resolve_player_table_base()
        if table_base is None:
            return []
        team_base_ptr = self._resolve_team_base_ptr()
        team_stride = TEAM_STRIDE
        players: list[Player] = []
        for i in range(max_scan):
            # Compute address of the i-th player record
            p_addr = table_base + i * PLAYER_STRIDE
            try:
                # Read essential fields; skip this record on failure
                last_name = self._read_string(p_addr + OFF_LAST_NAME, NAME_MAX_CHARS, LAST_NAME_ENCODING).strip()
                first_name = self._read_string(p_addr + OFF_FIRST_NAME, NAME_MAX_CHARS, FIRST_NAME_ENCODING).strip()
            except Exception:
                # Skip invalid or unreadable records instead of aborting the scan
                continue
            # Attempt to resolve the team name; default to Unknown on failure
            team_name = "Unknown"
            team_id: int | None = None
            try:
                team_ptr = self.mem.read_uint64(p_addr + OFF_TEAM_PTR)
                if team_ptr == 0:
                    team_name = "Free Agents"
                    team_id = FREE_AGENT_TEAM_ID
                else:
                    tn = self._read_string(team_ptr + OFF_TEAM_NAME, TEAM_NAME_LENGTH, TEAM_NAME_ENCODING).strip()
                    team_name = tn or "Unknown"
                    if team_base_ptr and team_stride > 0:
                        try:
                            rel = team_ptr - team_base_ptr
                            if rel >= 0 and rel % team_stride == 0:
                                team_id = int(rel // team_stride)
                        except Exception:
                            team_id = None
            except Exception:
                pass
            # Skip completely blank name records
            if not first_name and not last_name:
                continue
            players.append(Player(i, first_name, last_name, team_name, team_id))
        # Heuristic: if the scanned names appear mostly non‑ASCII, return []
        if players:
            non_ascii_count = 0
            allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ -'")
            for p in players:
                name = p.first_name + p.last_name
                if any(ch not in allowed for ch in name):
                    non_ascii_count += 1
            if non_ascii_count > len(players) * 0.5:
                return []
        return players
    def refresh_players(self) -> None:
        """Populate team and player information from live memory only."""
        self.team_list = []
        self.players = []
        self.external_loaded = False
        self._resolved_player_base = None
        self._resolved_team_base = None
        self._cached_free_agents = []
        self.name_index_map.clear()

        if not self.mem.open_process():
            return

        team_base = self._resolve_team_base_ptr()
        if team_base is None:
            return

        teams = self._scan_team_names()
        if not teams:
            return

        def _team_sort_key_pair(item: tuple[int, str]) -> tuple[int, str]:
            idx, name = item
            return (1 if name.strip().lower().startswith("team ") else 0, name)

        ordered_teams = sorted(teams, key=_team_sort_key_pair)
        self.team_list = self._build_team_display_list(ordered_teams)

        players_all = self._scan_all_players(self.max_players)
        if not players_all:
            return

        if any(p.team_id == FREE_AGENT_TEAM_ID for p in players_all):
            self._ensure_team_entry(FREE_AGENT_TEAM_ID, "Free Agents", front=True)
        self.players = players_all
        self._cached_free_agents = [p for p in self.players if p.team_id == FREE_AGENT_TEAM_ID]
        self._apply_team_display_to_players(self.players)
        self._build_name_index_map()

    def _build_team_display_list(self, teams: list[tuple[int, str]]) -> list[tuple[int, str]]:
        """Return a list of (team_id, display_name) with duplicate names disambiguated."""
        if not teams:
            return []
        normalized: list[tuple[int, str]] = []
        for idx, name in teams:
            base = (name or f"Team {idx}").strip() or f"Team {idx}"
            normalized.append((idx, base))
        counts = Counter(base.lower() for _, base in normalized)
        display_list: list[tuple[int, str]] = []
        for idx, base in normalized:
            display = base if counts[base.lower()] <= 1 else f"{base} (ID {idx})"
            display_list.append((idx, display))
        return display_list

    def _build_team_list_from_players(self, players: list[Player]) -> list[tuple[int, str]]:
        """Construct a team list using data available on the supplied players."""
        entries: list[tuple[int, str]] = []
        seen_ids: set[int] = set()
        name_to_temp: dict[str, int] = {}
        next_temp_id = -2
        for player in players:
            if player.team_id == FREE_AGENT_TEAM_ID:
                if FREE_AGENT_TEAM_ID not in seen_ids:
                    entries.append((FREE_AGENT_TEAM_ID, "Free Agents"))
                    seen_ids.add(FREE_AGENT_TEAM_ID)
            elif player.team_id is not None:
                if player.team_id not in seen_ids:
                    base = (player.team or f"Team {player.team_id}").strip() or f"Team {player.team_id}"
                    entries.append((player.team_id, base))
                    seen_ids.add(player.team_id)
            else:
                base = (player.team or "Unknown").strip() or "Unknown"
                if base not in name_to_temp:
                    while next_temp_id in seen_ids or next_temp_id == FREE_AGENT_TEAM_ID:
                        next_temp_id -= 1
                    temp_id = next_temp_id
                    name_to_temp[base] = temp_id
                    entries.append((temp_id, base))
                    seen_ids.add(temp_id)
                    next_temp_id -= 1
        return self._build_team_display_list(entries)

    def _apply_team_display_to_players(self, players: list[Player]) -> None:
        """Update ``player.team`` to use the display names defined by ``team_list``."""
        mapping = self._team_display_map()
        for player in players:
            if player.team_id == FREE_AGENT_TEAM_ID:
                player.team = "Free Agents"
            elif player.team_id is not None and player.team_id in mapping:
                player.team = mapping[player.team_id]
    def _read_panel_entry(self, record_addr: int, entry: dict) -> object | None:
        """Read a raw field value for the detail panel based on a schema entry."""
        try:
            offset = _to_int(
                entry.get("address")
                or entry.get("offset")
                or entry.get("offset_from_base")
            )
            if offset < 0:
                return None
            requires_deref = bool(entry.get("requiresDereference") or entry.get("requires_deref"))
            deref_offset = _to_int(entry.get("dereferenceAddress") or entry.get("deref_offset"))
            target_addr = record_addr + offset
            if requires_deref and deref_offset:
                ptr = self.mem.read_uint64(record_addr + deref_offset)
                if not ptr:
                    return None
                target_addr = ptr + offset
            entry_type = str(entry.get("type", "")).lower()
            start_bit = _to_int(entry.get("startBit") or entry.get("start_bit") or 0)
            size_val = _to_int(entry.get("size"))
            length_val = _to_int(entry.get("length"))
            if entry_type in {"string_utf16", "wstring"}:
                if size_val <= 0:
                    return None
                max_chars = size_val // 2
                return self.mem.read_wstring(target_addr, max_chars).strip("\x00")
            if entry_type in {"string", "text", "cstring", "ascii"}:
                if size_val <= 0:
                    return None
                return self.mem.read_ascii(target_addr, size_val).strip("\x00")
            if entry_type == "float":
                byte_len = size_val if size_val > 0 else ((length_val + 7) // 8 if length_val > 0 else 0)
                if byte_len <= 0:
                    return None
                raw = self.mem.read_bytes(target_addr, byte_len)
                if byte_len == 4:
                    return struct.unpack("<f", raw)[0]
                if byte_len == 8:
                    return struct.unpack("<d", raw)[0]
                return None
            if entry_type == "bitfield":
                bit_length = length_val if length_val > 0 else size_val
                if bit_length <= 0:
                    return None
                bits_needed = start_bit + bit_length
                byte_len = (bits_needed + 7) // 8
                raw = self.mem.read_bytes(target_addr, byte_len)
                value = int.from_bytes(raw, "little")
                value >>= start_bit
                mask = (1 << bit_length) - 1
                return value & mask
            byte_len = size_val if size_val > 0 else ((length_val + 7) // 8 if length_val > 0 else 0)
            if byte_len <= 0:
                return None
            raw = self.mem.read_bytes(target_addr, byte_len)
            return int.from_bytes(raw, "little")
        except Exception:
            return None
    def get_player_panel_snapshot(self, player: Player) -> dict[str, object]:
        """Return field values required for the player detail panel."""
        snapshot: dict[str, object] = {}
        if not player:
            return snapshot
        if not self.mem.open_process():
            return snapshot
        base = self._resolve_player_table_base()
        if base is None:
            return snapshot
        if PLAYER_STRIDE <= 0:
            return snapshot
        try:
            record_addr = base + player.index * PLAYER_STRIDE
        except Exception:
            return snapshot
        for label, category, entry_name in PLAYER_PANEL_FIELDS:
            entry = _find_offset_entry(entry_name, category)
            if not entry:
                continue
            value = self._read_panel_entry(record_addr, entry)
            if value is None:
                continue
            values_list = entry.get("values")
            if isinstance(values_list, list) and isinstance(value, int) and 0 <= value < len(values_list):
                value = values_list[value]
            snapshot[label] = value
        ovr_entry = _find_offset_entry(PLAYER_PANEL_OVR_FIELD[1], PLAYER_PANEL_OVR_FIELD[0])
        if ovr_entry:
            overall_val = self._read_panel_entry(record_addr, ovr_entry)
            if overall_val is not None:
                snapshot["Overall"] = overall_val
        return snapshot

    def _ensure_team_entry(self, team_id: int, display_name: str, front: bool = False) -> None:
        """Ensure ``team_list`` contains the provided entry."""
        for idx, name in self.team_list:
            if idx == team_id or name == display_name:
                return
        if front:
            self.team_list.insert(0, (team_id, display_name))
        else:
            self.team_list.append((team_id, display_name))

    def _collect_assigned_player_indexes(self) -> set[int]:
        """Return the set of player indices currently assigned to team rosters."""
        assigned: set[int] = set()
        if not self.team_list:
            return assigned
        if not self.mem.hproc or self.mem.base_addr is None:
            return assigned
        player_base = self._resolve_player_table_base()
        team_base_ptr = self._resolve_team_base_ptr()
        if player_base is None or team_base_ptr is None or TEAM_STRIDE <= 0:
            return assigned
        stride = PLAYER_STRIDE or 1
        for team_idx, _ in self.team_list:
            if team_idx is None or team_idx < 0:
                continue
            try:
                rec_addr = team_base_ptr + team_idx * TEAM_STRIDE
            except Exception:
                continue
            for slot in range(TEAM_PLAYER_SLOT_COUNT):
                try:
                    ptr = self.mem.read_uint64(rec_addr + slot * 8)
                except Exception:
                    ptr = 0
                if not ptr:
                    continue
                try:
                    idx = int((ptr - player_base) // stride)
                except Exception:
                    continue
                if 0 <= idx < self.max_players:
                    assigned.add(idx)
        return assigned

    def _get_free_agents(self) -> list[Player]:
        """Return cached free agent list, recomputing if necessary."""
        if self._cached_free_agents:
            return list(self._cached_free_agents)
        if not self.players:
            players = self._scan_all_players(self.max_players)
            if players:
                self.players = players
                self._apply_team_display_to_players(self.players)
                self._build_name_index_map()
        if not self.players:
            return []
        free_agents = [p for p in self.players if p.team_id == FREE_AGENT_TEAM_ID]
        if free_agents:
            self._cached_free_agents = list(free_agents)
            return list(free_agents)
        assigned = self._collect_assigned_player_indexes()
        if assigned:
            free_agents = [p for p in self.players if p.index not in assigned]
        else:
            free_agents = [
                p for p in self.players
                if (p.team or "").strip().lower().startswith("free")
            ]
        self._cached_free_agents = list(free_agents)
        return list(free_agents)

    def _team_display_map(self) -> dict[int, str]:
        """Return a mapping of team_id to display name."""
        return {idx: name for idx, name in self.team_list}

    def _team_index_for_display_name(self, display_name: str) -> int | None:
        """Resolve a display name back to its team index."""
        for idx, name in self.team_list:
            if name == display_name:
                return idx
        return None

    def _get_team_display_name(self, team_idx: int) -> str:
        """Return the display name for a team index."""
        return self._team_display_map().get(team_idx, f"Team {team_idx}")

    def get_teams(self) -> list[str]:
        """Return the list of team names in a logical order.
        This method returns a list of team names that has been
        categorised and reordered to improve usability.  When team
        information has been scanned from memory, the underlying
        ``team_list`` remains in its original order (to preserve
        pointer indices), but the returned list groups teams as
        follows:
          1. Free agency / Free Agents entries
          2. Draft Class (if present)
          3. Standard NBA teams
          4. All-Time teams (names containing "All Time" or "All-Time")
          5. G-League teams (names containing "G League", "G-League" or "GLeague")
        Within each category the original order is preserved.  If team
        data cannot be resolved from live memory the method returns an
        empty list instead of synthesising entries.
        """
        if not self.team_list:
            return []

        def _classify(entry: tuple[int, str]) -> str:
            tid, name = entry
            lname = name.lower()
            if tid == FREE_AGENT_TEAM_ID or "free" in lname:
                return "free_agents"
            if "draft" in lname:
                return "draft_class"
            return "normal"

        free_agents: list[str] = []
        draft_class: list[str] = []
        remaining: list[tuple[int, str]] = []
        for entry in self.team_list:
            category = _classify(entry)
            if category == "free_agents":
                free_agents.append(entry[1])
            elif category == "draft_class":
                draft_class.append(entry[1])
            else:
                remaining.append(entry)
        remaining_sorted = [name for _, name in sorted(remaining, key=lambda item: item[0])]
        ordered: list[str] = []
        ordered.extend(free_agents)
        ordered.extend(draft_class)
        ordered.extend(remaining_sorted)
        return ordered
    def get_players_by_team(self, team: str) -> list[Player]:
        """Return players for the specified team using live memory access."""
        team_name = (team or "").strip()
        if not team_name:
            return []
        team_lower = team_name.lower()

        if team_lower == "all players":
            if not self.players:
                players = self._scan_all_players(self.max_players)
                if players:
                    self.players = players
                    self._apply_team_display_to_players(self.players)
                    self._build_name_index_map()
            return list(self.players)

        if team_lower.startswith("free"):
            return self._get_free_agents()

        team_idx = self._team_index_for_display_name(team_name)
        if team_idx == FREE_AGENT_TEAM_ID:
            return self._get_free_agents()
        if team_idx is not None and team_idx >= 0:
            live_players = self.scan_team_players(team_idx)
            if live_players:
                return live_players

        # Use cached roster data (still sourced from live memory) if available
        if self.players:
            if team_idx is not None:
                return [p for p in self.players if p.team_id == team_idx]
            return [p for p in self.players if p.team == team_name]
        return []
    def update_player(self, player: Player) -> None:
        """Write changes to a player back to memory if connected."""
        if not self.mem.hproc or self.mem.base_addr is None or self.external_loaded:
            # Do nothing if not connected or if loaded from external files
            return
        # Resolve dynamic player table base pointer
        table_base = self._resolve_player_table_base()
        if table_base is None:
            return
        p_addr = table_base + player.index * PLAYER_STRIDE
        # Write names (fixed length strings)
        self._write_string(p_addr + OFF_LAST_NAME, player.last_name, NAME_MAX_CHARS, LAST_NAME_ENCODING)
        self._write_string(p_addr + OFF_FIRST_NAME, player.first_name, NAME_MAX_CHARS, FIRST_NAME_ENCODING)
    # ---------------------------------------------------------------------
    # Bulk copy operations
    # ---------------------------------------------------------------------
    def copy_player_data(self, src_index: int, dst_index: int, categories: list[str]) -> bool:
        """Copy selected data categories from one player to another."""
        if not self.mem.hproc or self.mem.base_addr is None or self.external_loaded:
            return False
        table_base = self._resolve_player_table_base()
        if table_base is None:
            return False
        if src_index < 0 or dst_index < 0 or src_index >= len(self.players) or dst_index >= len(self.players):
            return False
        lower_cats = [c.lower() for c in categories]
        if not lower_cats:
            return False
        src_addr = table_base + src_index * PLAYER_STRIDE
        dst_addr = table_base + dst_index * PLAYER_STRIDE
        if "full" in lower_cats:
            try:
                data = self.mem.read_bytes(src_addr, PLAYER_STRIDE)
                self.mem.write_bytes(dst_addr, data)
                return True
            except Exception:
                return False
        copied_any = False
        for name in lower_cats:
            matched_key = next((cat_name for cat_name in self.categories.keys() if cat_name.lower() == name), None)
            if not matched_key:
                continue
            field_defs = self.categories.get(matched_key, [])
            for field in field_defs:
                if not isinstance(field, dict):
                    continue
                raw_offset = field.get("offset")
                if raw_offset in (None, ""):
                    continue
                offset_int = _to_int(raw_offset)
                start_bit = _to_int(field.get("startBit", field.get("start_bit", 0)))
                length = _to_int(field.get("length", 0))
                if length <= 0:
                    continue
                requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
                deref_offset = _to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
                raw_val = self.get_field_value(
                    src_index,
                    offset_int,
                    start_bit,
                    length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                )
                if raw_val is None:
                    continue
                if self.set_field_value(
                    dst_index,
                    offset_int,
                    start_bit,
                    length,
                    raw_val,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                ):
                    copied_any = True
        return copied_any

    def get_field_value(
        self,
        player_index: int,
        offset: int,
        start_bit: int,
        length: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
    ) -> int | None:
        try:
            if not self.mem.open_process():
                return None
            base = self._resolve_player_table_base()
            if base is None:
                return None
            record_addr = base + player_index * PLAYER_STRIDE
            if requires_deref and deref_offset:
                try:
                    struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                except Exception:
                    return None
                if not struct_ptr:
                    return None
                addr = struct_ptr + offset
            else:
                addr = record_addr + offset
            bits_needed = start_bit + length
            bytes_needed = (bits_needed + 7) // 8
            raw = self.mem.read_bytes(addr, bytes_needed)
            value = int.from_bytes(raw, "little")
            value >>= start_bit
            mask = (1 << length) - 1
            return value & mask
        except Exception:
            return None

    def set_field_value(
        self,
        player_index: int,
        offset: int,
        start_bit: int,
        length: int,
        value: int,
        requires_deref: bool = False,
        deref_offset: int = 0,
    ) -> bool:
        try:
            if not self.mem.open_process():
                return False
            base = self._resolve_player_table_base()
            if base is None:
                return False
            record_addr = base + player_index * PLAYER_STRIDE
            if requires_deref and deref_offset:
                try:
                    struct_ptr = self.mem.read_uint64(record_addr + deref_offset)
                except Exception:
                    return False
                if not struct_ptr:
                    return False
                addr = struct_ptr + offset
            else:
                addr = record_addr + offset
            max_val = (1 << length) - 1
            value = max(0, min(max_val, int(value)))
            bits_needed = start_bit + length
            bytes_needed = (bits_needed + 7) // 8
            data = bytearray(self.mem.read_bytes(addr, bytes_needed))
            current = int.from_bytes(data, "little")
            mask = ((1 << length) - 1) << start_bit
            current &= ~mask
            current |= (value << start_bit) & mask
            new_bytes = current.to_bytes(bytes_needed, "little")
            self.mem.write_bytes(addr, new_bytes)
            return True
        except Exception:
            return False

class PlayerEditorApp(tk.Tk):
    def _read_team_field_bits(self, base_addr, offset, size_bytes=1, bit_start=0, bit_length=None):
        raw = self._read_bytes(base_addr + offset, size_bytes)
        if not raw:
            return 0
        val = int.from_bytes(raw, "little")
        if bit_length is not None:
            mask = (1 << bit_length) - 1
            val = (val >> bit_start) & mask
        return val
    """The main Tkinter application for editing player data."""
    def __init__(self, model: PlayerDataModel):
        super().__init__()
        self.model = model
        self.title("2K26 Offline Player Data Editor")
        self.geometry("1280x760")
        self.minsize(1024, 640)
        self.style = ttk.Style(self)
        try:
            current_theme = self.style.theme_use()
            self.style.theme_use(current_theme)
        except Exception:
            pass
        try:
            self.style.configure(
                "App.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=TEXT_PRIMARY,
                bordercolor=ACCENT_BG,
                arrowcolor=TEXT_PRIMARY,
            )
        except tk.TclError:
            self.style.configure(
                "App.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=TEXT_PRIMARY,
            )
        self.style.map(
            "App.TCombobox",
            fieldbackground=[("readonly", INPUT_BG)],
            foreground=[("readonly", TEXT_PRIMARY)],
            arrowcolor=[("readonly", TEXT_PRIMARY)],
        )
        # State variables
        self.selected_team: str | None = None
        self.selected_player: Player | None = None
        self.scanning = False
        # Maintain a list of players for the currently selected team.  This
        # list is filtered by the search bar on the players screen.
        # ``current_players`` holds the Player objects for the selected team,
        # while ``filtered_player_indices`` maps the visible listbox rows
        # back to the indices within ``current_players``.  ``player_search_var``
        # tracks the current search text.
        self.current_players: list[Player] = []
        self.filtered_player_indices: list[int] = []
        self.player_search_var = tk.StringVar()
        self.team_players_lookup: list[Player] = []
        self.team_players_listbox: tk.Listbox | None = None
        # Build UI elements
        self._build_sidebar()
        self._build_home_screen()
        self._build_players_screen()
        self._build_teams_screen()
        # Show home by default
        self.show_home()
    # ---------------------------------------------------------------------
    # Sidebar and navigation
    # ---------------------------------------------------------------------
    def _build_sidebar(self):
        self.sidebar = tk.Frame(self, width=200, bg=PRIMARY_BG)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        # Buttons
        self.btn_home = tk.Button(
            self.sidebar,
            text="Home",
            command=self.show_home,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_home.pack(fill=tk.X, padx=10, pady=(20, 5))
        self.btn_players = tk.Button(
            self.sidebar,
            text="Players",
            command=self.show_players,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_players.pack(fill=tk.X, padx=10, pady=5)
        # Teams button
        self.btn_teams = tk.Button(
            self.sidebar,
            text="Teams",
            command=self.show_teams,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_teams.pack(fill=tk.X, padx=10, pady=5)
        # Stadiums button (disabled for now).
        # Originally this button opened a Stadiums editor, but that feature
        # has been disabled to prevent issues.  To restore it later, you
        # can re‑enable the button by pointing the command at a real
        #     self.sidebar,
        #     text="Stadiums",
        #     bg="#354F52",
        #     fg="white",
        #     relief=tk.FLAT,
        #     activebackground="#52796F",
        #     activeforeground="white",
        # )
        # Randomizer button
        self.btn_randomizer = tk.Button(
            self.sidebar,
            text="Randomize",
            command=self._open_randomizer,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_randomizer.pack(fill=tk.X, padx=10, pady=5)
        # 2K COY button
        # This button imports player data from external tables (e.g. Google
        # Sheets export) and applies it to the roster.  It expects the
        # import files to follow the same column ordering as the batch
        # import functionality already implemented.  When complete it
        # displays a summary of how many players were updated and
        # lists any players that could not be found.  See
        # ``_open_2kcoy`` for details.
        self.btn_coy = tk.Button(
            self.sidebar,
            text="2K COY",
            command=self._open_2kcoy,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_coy.pack(fill=tk.X, padx=10, pady=5)
        # Load Excel button
        # This button imports player data from a user-selected Excel workbook.
        # It prompts the user to choose the workbook first, then asks which
        # categories (Attributes, Tendencies, Durability, Potential) should be applied.  A
        # loading dialog is displayed while processing to discourage
        # interaction.  See ``_open_load_excel`` for details.
        self.btn_load_excel = tk.Button(
            self.sidebar,
            text="Load Excel",
            command=self._open_load_excel,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_load_excel.pack(fill=tk.X, padx=10, pady=5)
        # Team Shuffle button
        self.btn_shuffle = tk.Button(
            self.sidebar,
            text="Shuffle Teams",
            command=self._open_team_shuffle,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_shuffle.pack(fill=tk.X, padx=10, pady=5)
        # Batch Edit button
        self.btn_batch_edit = tk.Button(
            self.sidebar,
            text="Batch Edit",
            command=self._open_batch_edit,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        )
        self.btn_batch_edit.pack(fill=tk.X, padx=10, pady=5)
    # ---------------------------------------------------------------------
    # Home screen
    # ---------------------------------------------------------------------
    def _build_home_screen(self):
        self.home_frame = tk.Frame(self, bg=PRIMARY_BG)
        # Title
        tk.Label(
            self.home_frame,
            text="2K26 Offline Player Editor",
            font=("Segoe UI", 20, "bold"),
            bg=PRIMARY_BG,
            fg=TEXT_PRIMARY,
        ).pack(pady=(40, 10))
        content = tk.Frame(self.home_frame, bg=PANEL_BG, padx=30, pady=25)
        content.pack(pady=(0, 30), padx=40)
        # Status
        self.status_var = tk.StringVar()
        self.status_label = tk.Label(
            content,
            textvariable=self.status_var,
            font=("Segoe UI", 12),
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
        )
        self.status_label.pack(pady=(0, 15))
        # Refresh button
        tk.Button(
            content,
            text="Refresh",
            command=self._update_status,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
        ).pack()
        # Version label
        tk.Label(
            self.home_frame,
            text=f"Version {APP_VERSION}",
            font=("Segoe UI", 9, "italic"),
            bg=PRIMARY_BG,
            fg=TEXT_SECONDARY,
        ).pack(side=tk.BOTTOM, pady=20)
    # ---------------------------------------------------------------------
    # Players screen
    # ---------------------------------------------------------------------
    def _build_players_screen(self):
        self.players_frame = tk.Frame(self, bg="#0F1C2E")
        controls = tk.Frame(self.players_frame, bg="#0F1C2E")
        controls.pack(fill=tk.X, padx=20, pady=15)
        tk.Label(
            controls,
            text="Search",
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=0, sticky="w")
        self.player_search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            controls,
            textvariable=self.player_search_var,
            width=30,
            font=("Segoe UI", 11),
            relief=tk.FLAT,
        )
        self.search_entry.grid(row=0, column=1, padx=(8, 20), sticky="w")
        self.search_entry.insert(0, "Search players.")
        self.search_entry.configure(fg="#8E8E8E")
        def _on_search_focus_in(_event):
            if self.search_entry.get() == "Search players.":
                self.search_entry.delete(0, tk.END)
                self.search_entry.configure(fg="#E0E1DD")
        def _on_search_focus_out(_event):
            if not self.search_entry.get():
                self.search_entry.insert(0, "Search players.")
                self.search_entry.configure(fg="#8E8E8E")
        self.search_entry.bind("<FocusIn>", _on_search_focus_in)
        self.search_entry.bind("<FocusOut>", _on_search_focus_out)
        refresh_btn = tk.Button(
            controls,
            text="Refresh",
            command=self._start_scan,
            bg="#778DA9",
            fg=BUTTON_TEXT,
            relief=tk.FLAT,
            activebackground="#415A77",
            activeforeground=BUTTON_TEXT,
            padx=16,
            pady=4,
        )
        refresh_btn.grid(row=0, column=2, padx=(0, 20))
        tk.Label(
            controls,
            text="Player Dataset",
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=3, sticky="w")
        self.dataset_var = tk.StringVar(value="All Data")
        dataset_combo = ttk.Combobox(
            controls,
            textvariable=self.dataset_var,
            values=["All Data"],
            state="readonly",
            width=15,
            style="App.TCombobox",
        )
        dataset_combo.grid(row=0, column=4, padx=(8, 0), sticky="w")
        controls.columnconfigure(5, weight=1)
        self.player_count_var = tk.StringVar(value="Players: 0")
        tk.Label(
            controls,
            textvariable=self.player_count_var,
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=0, column=5, sticky="e")
        tk.Label(
            controls,
            text="Team",
            font=("Segoe UI", 11, "bold"),
            bg="#0F1C2E",
            fg="#E0E1DD",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.team_var = tk.StringVar()
        self.team_dropdown = ttk.Combobox(
            controls,
            textvariable=self.team_var,
            state="readonly",
            width=25,
            style="App.TCombobox",
        )
        self.team_dropdown.grid(row=1, column=1, padx=(8, 0), pady=(10, 0), sticky="w")
        self.team_dropdown.bind("<<ComboboxSelected>>", self._on_team_selected)
        self.scan_status_var = tk.StringVar(value="")
        self.scan_status_label = tk.Label(
            controls,
            textvariable=self.scan_status_var,
            font=("Segoe UI", 10, "italic"),
            bg="#0F1C2E",
            fg="#9BA4B5",
        )
        self.scan_status_label.grid(row=1, column=2, columnspan=3, sticky="w", pady=(10, 0))
        content = tk.Frame(self.players_frame, bg="#0F1C2E")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        list_container = tk.Frame(content, bg="#0F1C2E")
        list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.player_listbox = tk.Listbox(
            list_container,
            selectmode=tk.SINGLE,
            exportselection=False,
            font=("Segoe UI", 11),
            bg="#0F1C2E",
            fg="#E0E1DD",
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.player_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.player_listbox.bind("<<ListboxSelect>>", self._on_player_selected)
        self.player_listbox.bind("<Double-Button-1>", lambda _e: self._open_full_editor())
        self.player_listbox.bind("<MouseWheel>", self._on_player_list_mousewheel)
        list_scroll = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.player_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.player_listbox.configure(yscrollcommand=list_scroll.set)
        detail_container = tk.Frame(content, bg="#16213E", width=420)
        detail_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(20, 0))
        detail_container.pack_propagate(False)
        self.player_portrait = tk.Canvas(detail_container, width=150, height=150, bg="#16213E", highlightthickness=0)
        self.player_portrait.pack(pady=(30, 15))
        self.player_portrait_circle = self.player_portrait.create_oval(25, 25, 125, 125, fill="#415A77", outline="")
        self.player_portrait_text = self.player_portrait.create_text(75, 75, text="", fill="#E0E1DD", font=("Segoe UI", 24, "bold"))
        self.player_name_var = tk.StringVar(value="Select a player")
        tk.Label(
            detail_container,
            textvariable=self.player_name_var,
            font=("Segoe UI", 18, "bold"),
            bg="#16213E",
            fg="#E0E1DD",
        ).pack()
        self.player_ovr_var = tk.StringVar(value="OVR --")
        tk.Label(
            detail_container,
            textvariable=self.player_ovr_var,
            font=("Segoe UI", 14),
            bg="#16213E",
            fg="#E63946",
        ).pack(pady=(0, 20))
        info_grid = tk.Frame(detail_container, bg="#16213E")
        info_grid.pack(padx=35, pady=10, fill=tk.X)
        self.player_detail_fields: dict[str, tk.StringVar] = {}
        detail_fields = [
            ("Position", "--"),
            ("Number", "--"),
            ("Height", "--"),
            ("Weight", "--"),
            ("Face ID", "--"),
            ("Unique ID", "--"),
        ]
        for idx, (label, default) in enumerate(detail_fields):
            row = idx // 2
            col = (idx % 2) * 2
            tk.Label(
                info_grid,
                text=label,
                bg="#16213E",
                fg="#E0E1DD",
                font=("Segoe UI", 11),
            ).grid(row=row, column=col, sticky="w", pady=4, padx=(0, 12))
            var = tk.StringVar(value=default)
            tk.Label(
                info_grid,
                textvariable=var,
                bg="#16213E",
                fg="#9BA4B5",
                font=("Segoe UI", 11, "bold"),
            ).grid(row=row, column=col + 1, sticky="w", pady=4, padx=(0, 20))
            self.player_detail_fields[label] = var
        info_grid.columnconfigure(1, weight=1)
        info_grid.columnconfigure(3, weight=1)
        form = tk.Frame(detail_container, bg="#16213E")
        form.pack(padx=35, pady=(10, 0), fill=tk.X)
        tk.Label(form, text="First Name", bg="#16213E", fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w", pady=4)
        self.var_first = tk.StringVar()
        tk.Entry(form, textvariable=self.var_first, relief=tk.FLAT, width=20).grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))
        tk.Label(form, text="Last Name", bg="#16213E", fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w", pady=4)
        self.var_last = tk.StringVar()
        tk.Entry(form, textvariable=self.var_last, relief=tk.FLAT, width=20).grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        tk.Label(form, text="Team", bg="#16213E", fg="#E0E1DD", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w", pady=4)
        self.var_player_team = tk.StringVar()
        tk.Label(form, textvariable=self.var_player_team, bg="#16213E", fg="#9BA4B5", font=("Segoe UI", 11, "bold")).grid(row=2, column=1, sticky="w", pady=4, padx=(8, 0))
        form.columnconfigure(1, weight=1)
        btn_row = tk.Frame(detail_container, bg="#16213E")
        btn_row.pack(pady=(20, 0))
        self.btn_save = tk.Button(
            btn_row,
            text="Save",
            command=self._save_player,
            bg="#84A98C",
            fg="white",
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=16,
            pady=6,
        )
        self.btn_save.pack(side=tk.LEFT, padx=5)
        self.btn_edit = tk.Button(
            btn_row,
            text="Full Editor",
            command=self._open_full_editor,
            bg="#E63946",
            fg="white",
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=16,
            pady=6,
        )
        self.btn_edit.pack(side=tk.LEFT, padx=5)
        self.btn_copy = tk.Button(
            btn_row,
            text="Copy Player",
            command=self._open_copy_dialog,
            bg="#52796F",
            fg="white",
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=16,
            pady=6,
        )
        self.btn_copy.pack(side=tk.LEFT, padx=5)
        self.btn_import = tk.Button(
            btn_row,
            text="Import Data",
            command=self._open_import_dialog,
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            padx=16,
            pady=6,
        )
        self.btn_import.pack(side=tk.LEFT, padx=5)
        self.current_players = []
        self.filtered_player_indices = []
        self.selected_player = None
        self.player_listbox.delete(0, tk.END)
        self.player_count_var.set("Players: 0")
        self.player_listbox.insert(tk.END, "No players available.")
        self.player_search_var.trace_add("write", lambda *_: self._filter_player_list())
    # ---------------------------------------------------------------------
    # Navigation methods
    # ---------------------------------------------------------------------
    def show_home(self):
        """
        Display the Home screen and hide any other visible panes.
        If the Teams or Stadiums panes were previously shown, they are
        explicitly hidden here.  Without forgetting those frames, their
        widgets could remain visible atop the Home screen after navigation.
        """
        # Hide other screens if they were previously packed
        try:
            self.players_frame.pack_forget()
        except Exception:
            pass
        # Also hide the Teams pane if it exists
        try:
            self.teams_frame.pack_forget()
        except Exception:
            pass
        # Show the home screen
        self.home_frame.pack(fill=tk.BOTH, expand=True)
        self._update_status()
    def show_players(self):
        """
        Display the Players screen and hide other panes.
        Prior to packing the Players frame, explicitly hide the Home,
        Teams and Stadiums panes.  This prevents UI elements from
        overlapping when switching between tabs.
        """
        # Hide other screens
        try:
            self.home_frame.pack_forget()
        except Exception:
            pass
        try:
            self.teams_frame.pack_forget()
        except Exception:
            pass
        # Show the players screen
        self.players_frame.pack(fill=tk.BOTH, expand=True)
        # Kick off a background scan to load players and teams
        self._start_scan()
    def show_teams(self):
        """Display the Teams screen and start scanning if necessary."""
        self.home_frame.pack_forget()
        self.players_frame.pack_forget()
        self.teams_frame.pack(fill=tk.BOTH, expand=True)
        # Kick off a scan if we don't have team names yet
        if not self.model.get_teams():
            # Use the same scanning logic as players
            if not self.scanning:
                self.scanning = True
                # Show scanning message in team screen
                self.team_scan_status_var.set("Scanning... please wait")
                threading.Thread(target=self._scan_teams_thread, daemon=True).start()
        else:
            # Update dropdown immediately
            teams = self.model.get_teams()
            self._update_team_dropdown(teams)
            # Auto‑select first team if none selected
            if teams and not self.team_edit_var.get():
                self.team_edit_var.set(teams[0])
                self._on_team_edit_selected()
    # -----------------------------------------------------------------
    # Randomizer
    # -----------------------------------------------------------------
    def _open_randomizer(self):
        """Open the Randomizer window for mass randomizing player values."""
        try:
            # Ensure we have up-to-date player and team lists
            self.model.refresh_players()
        except Exception:
            pass
        # Launch the randomizer window.  The RandomizerWindow class is
        # defined below.  It will build its own UI and handle
        # randomization logic.
        RandomizerWindow(self, self.model)
    def _open_team_shuffle(self) -> None:
        """Open the Team Shuffle window to shuffle players across selected teams."""
        try:
            # Refresh player list to ensure team assignments are current
            self.model.refresh_players()
        except Exception:
            pass
        TeamShuffleWindow(self, self.model)
    def _open_batch_edit(self) -> None:
        """
        Open the Batch Edit window to set a specific field across
        multiple players.  The BatchEditWindow allows selection of
        one or more teams, a category (Attributes, Tendencies,
        Durability, Vitals, Body, Badges, Contract, etc.), a field
        within that category, and a new value.  When executed, the
        specified value is written to the selected field for every
        player on the chosen teams.  Only live memory editing is
        supported; if the game process is not attached the user will
        be notified and no changes will occur.
        """
        try:
            # Refresh player and team lists; ignore errors if scanning fails
            self.model.refresh_players()
        except Exception:
            pass
        # Launch the batch edit window.  Any exceptions raised during
        # creation will be reported via a messagebox.
        try:
            BatchEditWindow(self, self.model)
        except Exception as exc:
            import traceback
            messagebox.showerror("Batch Edit", f"Failed to open batch edit window: {exc}")
            traceback.print_exc()
    def _open_2kcoy(self) -> None:
        """
        Automatically import player ratings from a fixed Google Sheet and apply
        them to the roster.  If ``COY_SHEET_ID`` is defined, this method
        downloads the CSV exports of the configured tabs and performs the
        import without prompting the user.  If downloading fails or the
        sheet ID is empty, the user will be prompted to select files
        manually.  A summary of updates and any players not found is
        displayed at the end.
        """
        # Refresh players to ensure we have up-to-date indices
        try:
            self.model.refresh_players()
        except Exception:
            pass
        # Require the game to be running
        if not self.model.mem.hproc:
            messagebox.showinfo(
                "2K COY Import",
                "NBA 2K26 does not appear to be running. Please launch the game and "
                "load a roster before importing."
            )
            return
        # Ask the user which categories to import.  Present a simple
        # checkbox dialog so they can choose between Attributes,
        # Tendencies, Durability, and Potential.  If they cancel or uncheck all
        # boxes, no import is performed.
        # ------------------------------------------------------------------
        categories_to_ask = ["Attributes", "Tendencies", "Durability", "Potential"]
        try:
            dlg = CategorySelectionDialog(self, categories_to_ask)
            # Wait for the dialog to close before proceeding
            self.wait_window(dlg)
            selected_categories = dlg.selected
        except Exception:
            selected_categories = None
        # If the user cancelled (None) or selected nothing, abort
        if not selected_categories:
            return
        # Show a loading dialog to discourage clicking during processing
        loading_win = tk.Toplevel(self)
        loading_win.title("Loading")
        loading_win.geometry("350x120")
        loading_win.resizable(False, False)
        tk.Label(
            loading_win,
            text="Loading data... Please wait and do not click the updater.",
            wraplength=320,
            justify="left"
        ).pack(padx=20, pady=20)
        loading_win.update_idletasks()
        # Determine whether to auto-download or prompt for files
        auto_download = bool(COY_SHEET_ID)
        file_map: dict[str, str] = {}
        not_found: set[str] = set()
        category_tables: dict[str, dict[str, object]] = {}
        results: dict[str, int] = {}
        if auto_download:
            # Attempt to fetch each configured sheet for the selected categories
            for cat, sheet_name in COY_SHEET_TABS.items():
                # Skip categories the user did not select
                if cat not in selected_categories:
                    continue
                try:
                    # Build CSV export URL for the given sheet
                    url = (
                        f"https://docs.google.com/spreadsheets/d/{COY_SHEET_ID}/"
                        f"gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}"
                    )
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        csv_text = resp.read().decode('utf-8')
                except Exception:
                    csv_text = ''
                if not csv_text:
                    # Could not fetch this sheet; skip it
                    continue
                # Write the CSV text to a temporary file
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8")
                tmp.write(csv_text)
                tmp.close()
                file_map[cat] = tmp.name
                # Parse names to identify missing players
                try:
                    import csv as _csv
                    rows = list(_csv.reader(io.StringIO(csv_text)))
                    category_tables[cat] = {"rows": rows, "delimiter": ","}
                    info = self.model.prepare_import_rows(cat, rows) if rows else None
                    if info:
                        name_col = info["name_col"]
                        for row in info["data_rows"]:
                            if len(row) <= name_col:
                                continue
                            name = str(row[name_col]).strip()
                            if not name:
                                continue
                            if not self.model._match_player_indices(name):
                                not_found.add(name)
                except Exception:
                    pass
        # If no files were downloaded or auto-download disabled, prompt the user
        if not file_map:
            # Ask for the Attributes file
            # For manual selection, prompt only for the categories chosen
            import tkinter.simpledialog as _simpledialog  # delayed import
            # Helper to open a file dialog for a given category
            def prompt_file(cat_name: str) -> str:
                return filedialog.askopenfilename(
                    title=f"Select {cat_name} Import File",
                    filetypes=[("Delimited files", "*.csv *.tsv *.txt"), ("All files", "*.*")],
                )
            # For each selected category ask the user to select a file.  If
            # they cancel on the first mandatory category (Attributes) then
            # abort.
            for cat in categories_to_ask:
                if cat not in selected_categories:
                    continue
                path = prompt_file(cat)
                if not path:
                    # User cancelled; abort the entire import
                    # Remove any previously selected files
                    file_map.clear()
                    return
                file_map[cat] = path
            # Collect names from selected files
            def collect_missing_names(cat_name: str, path: str) -> None:
                import csv as _csv
                if not path or not os.path.isfile(path):
                    return
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        sample = f.readline()
                        delim = '\t' if '\t' in sample else ',' if ',' in sample else ';'
                        f.seek(0)
                        rows = list(_csv.reader(f, delimiter=delim))
                    category_tables[cat_name] = {"rows": rows, "delimiter": delim}
                    info = self.model.prepare_import_rows(cat_name, rows) if rows else None
                    if info:
                        name_col = info["name_col"]
                        for row in info["data_rows"]:
                            if len(row) <= name_col:
                                continue
                            name = str(row[name_col]).strip()
                            if not name:
                                continue
                            if not self.model._match_player_indices(name):
                                not_found.add(name)
                except Exception:
                    pass
            for cat_name, path in file_map.items():
                collect_missing_names(cat_name, path)
        # Compute the size of the Attributes player pool (number of names in the
        # attributes file).  We track this to inform the user if some
        # players were not updated.  It is computed before imports so
        # that ``import_all`` does not need to be changed.
        attr_pool_size = 0
        attr_names_set: set[str] = set()
        if 'Attributes' in file_map:
            try:
                import csv as _csv
                path = file_map['Attributes']
                # Read the file (auto‑determine delimiter similar to import_table)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    sample = f.readline()
                    delim = '\t' if '\t' in sample else ',' if ',' in sample else ';'
                    f.seek(0)
                    reader = _csv.reader(f, delimiter=delim)
                    rows = list(reader)
                info = self.model.prepare_import_rows('Attributes', rows) if rows else None
                if info:
                    name_col = info['name_col']
                    for row in info['data_rows']:
                        if not row or len(row) <= name_col:
                            continue
                        cell = str(row[name_col]).strip()
                        if not cell:
                            continue
                        attr_names_set.add(cell)
                    attr_pool_size = len(attr_names_set)
            except Exception:
                attr_pool_size = 0
        # Perform imports only for the selected categories
        results = self.model.import_all(file_map)
        # Refresh players to reflect changes
        try:
            self.model.refresh_players()
        except Exception:
            pass
        # Remove any temporary files created during auto-download
        if auto_download:
            for p in file_map.values():
                try:
                    if p and os.path.isfile(p):
                        os.remove(p)
                except Exception:
                    pass
        # Build summary
        msg_lines = ["2K COY import completed."]
        # If any players were updated, list counts per category
        if results:
            msg_lines.append("\nPlayers updated:")
            for cat, cnt in results.items():
                if file_map.get(cat):
                    msg_lines.append(f"  {cat}: {cnt}")
        partial_info = getattr(self.model, "import_partial_matches", {}) or {}
        had_partial = False
        for cat, mapping in partial_info.items():
            if not mapping:
                continue
            if not had_partial:
                msg_lines.append("\nPlayers requiring confirmation (skipped):")
                had_partial = True
            msg_lines.append(f"  {cat}:")
            for raw_name, candidates in mapping.items():
                display = ", ".join(candidates[:5]) if candidates else "Possible roster match"
                msg_lines.append(f"    {raw_name} -> {display}")
                not_found.add(raw_name)
        # Compute number of attributes pool entries that were not updated
        if attr_pool_size:
            updated_attr = results.get('Attributes')
            # Count only those not_found names that originated from the
            # attributes file
            if attr_names_set and not_found:
                not_matched = len(attr_names_set.intersection(not_found))
            else:
                not_matched = 0
            not_updated = attr_pool_size - updated_attr - not_matched
            if not_updated > 0:
                msg_lines.append(
                    f"\n{not_updated} player{'s' if not_updated != 1 else ''} in the Attributes pool "
                    f"could not be updated (blank values or no matching fields)."
                )
        # List any players that were not found in the roster
        if not_found:
            msg_lines.append(f"\nPlayers not found (no matches in roster): {len(not_found)}")
        else:
            msg_lines.append("\nAll players were found in the roster.")
        # Destroy the loading dialog before showing the summary
        try:
            loading_win.destroy()
        except Exception:
            pass
        apply_cb = None
        if not_found and category_tables:
            def _apply(mapping, tables=category_tables):
                self._apply_manual_import(mapping, tables, title="2K COY Manual Import")
            apply_cb = _apply
        self._show_import_summary(
            title="2K COY Import",
            summary_lines=msg_lines,
            missing_players=sorted(not_found),
            apply_callback=apply_cb,
        )
    def _open_load_excel(self) -> None:
        """
        Prompt the user to import player updates from a single Excel workbook.
        This method first asks the user to select an Excel (.xlsx/.xls) file.
        After selecting the file, it presents a category selection dialog
        allowing the user to choose which types of data to import (Attributes,
        Tendencies and/or Durability).  For each selected category, the
        corresponding sheet is extracted from the workbook (matching the
        category name if it exists, otherwise falling back to the first sheet).
        The sheet is converted to a temporary CSV file and passed through
        ``import_all`` for processing.  A modal loading dialog is displayed
        during the import to discourage further clicks.
        """
        # Refresh players to ensure we have up-to-date indices
        try:
            self.model.refresh_players()
        except Exception:
            pass
        # Require the game to be running
        if not self.model.mem.hproc:
            messagebox.showinfo(
                "Excel Import",
                "NBA 2K26 does not appear to be running. Please launch the game and "
                "load a roster before importing."
            )
            return
        # Prompt for the Excel workbook first
        workbook_path = filedialog.askopenfilename(
            title="Select Excel Workbook",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if not workbook_path:
            return
        # Ask the user which categories to import
        categories_to_ask = ["Attributes", "Tendencies", "Durability", "Potential"]
        try:
            dlg = CategorySelectionDialog(self, categories_to_ask)
            self.wait_window(dlg)
            selected_categories = dlg.selected
        except Exception:
            selected_categories = None
        if not selected_categories:
            return
        # Show a loading dialog to discourage clicking during processing
        loading_win = tk.Toplevel(self)
        loading_win.title("Loading")
        loading_win.geometry("350x120")
        loading_win.resizable(False, False)
        tk.Label(
            loading_win,
            text="Loading data... Please wait and do not click the updater.",
            wraplength=320,
            justify="left"
        ).pack(padx=20, pady=20)
        loading_win.update_idletasks()
        file_map: dict[str, str] = {}
        not_found: set[str] = set()
        category_tables: dict[str, dict[str, object]] = {}
        try:
            import pandas as _pd
        except Exception:
            messagebox.showerror('Excel Import', 'Pandas is required. Install with: pip install pandas openpyxl')
            loading_win.destroy()
            return
        # Helper to collect missing names from a DataFrame
        def collect_missing_names_df(cat_name: str, df) -> None:
            if df is None or df.empty:
                return
            try:
                data = df.fillna('').astype(str)
            except Exception:
                data = df.astype(str)
            header = [str(col) for col in data.columns]
            rows = [header]
            rows.extend([list(row) for row in data.values.tolist()])
            if not rows:
                return
            category_tables[cat_name] = {"rows": rows, "delimiter": ","}
            info = self.model.prepare_import_rows(cat_name, rows)
            if not info:
                return
            name_col = info['name_col']
            for row in info['data_rows']:
                if len(row) <= name_col:
                    continue
                name = str(row[name_col]).strip()
                if not name:
                    continue
                if not self.model._match_player_indices(name):
                    not_found.add(name)
        try:
            # Read the workbook once to obtain the list of sheet names
            try:
                xls = _pd.ExcelFile(workbook_path)
            except Exception:
                messagebox.showerror("Excel Import", f"Failed to read {os.path.basename(workbook_path)}")
                loading_win.destroy()
                return
            for cat in categories_to_ask:
                if cat not in selected_categories:
                    continue
                # Determine which sheet to read: prefer exact match of category name
                sheet_to_use = None
                for sheet_name in xls.sheet_names:
                    if sheet_name.strip().lower() == cat.lower():
                        sheet_to_use = sheet_name
                        break
                # If no exact match, use the first sheet
                if sheet_to_use is None:
                    sheet_to_use = xls.sheet_names[0] if xls.sheet_names else None
                if sheet_to_use is None:
                    continue
                # Read the sheet into a DataFrame
                try:
                    df = xls.parse(sheet_to_use)
                except Exception:
                    # Attempt to read via pandas.read_excel fallback
                    try:
                        df = _pd.read_excel(workbook_path, sheet_name=sheet_to_use)
                    except Exception:
                        df = None
                if df is None:
                    continue
                # Write DataFrame to a temporary CSV file
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8")
                df.to_csv(tmp.name, index=False)
                tmp.close()
                file_map[cat] = tmp.name
                collect_missing_names_df(cat, df)
            # Perform the import
            results = self.model.import_all(file_map)
            # Refresh players to reflect changes
            try:
                self.model.refresh_players()
            except Exception:
                pass
        finally:
            # Destroy the loading dialog
            try:
                loading_win.destroy()
            except Exception:
                pass
            # Clean up temporary files
            for p in file_map.values():
                try:
                    if p and os.path.isfile(p):
                        os.remove(p)
                except Exception:
                    pass
        # Build summary message
        msg_lines = ["Excel import completed."]
        if results:
            msg_lines.append("\nPlayers updated:")
            for cat, cnt in results.items():
                if file_map.get(cat):
                    msg_lines.append(f"  {cat}: {cnt}")
        # Inform about missing players
        if not_found:
            msg_lines.append(f"\nPlayers not found: {len(not_found)}")
        else:
            msg_lines.append("\nAll players were found in the roster.")
        apply_cb = None
        if not_found and category_tables:
            def _apply(mapping, tables=category_tables):
                self._apply_manual_import(mapping, tables, title="Excel Manual Import")
            apply_cb = _apply
        self._show_import_summary(
            title="Excel Import",
            summary_lines=msg_lines,
            missing_players=sorted(not_found),
            apply_callback=apply_cb,
        )
    def _show_import_summary(
        self,
        title: str,
        summary_lines: list[str],
        missing_players: list[str],
        apply_callback: Callable[[dict[str, str]], None] | None = None,
    ) -> None:
        """Display an import summary with optional lookup helpers for missing players."""
        summary_text = "\n".join(summary_lines)
        roster_names = [p.full_name for p in self.model.players if (p.first_name or p.last_name)]
        if not missing_players or not roster_names:
            messagebox.showinfo(title, summary_text)
            return
        ImportSummaryDialog(self, title, summary_text, missing_players, roster_names, apply_callback=apply_callback)
    def _apply_manual_import(self, mapping: dict[str, str], category_tables: dict[str, dict[str, object]], title: str) -> None:
        if not mapping:
            messagebox.showinfo(title, "No player matches were selected.")
            return
        import csv as _csv
        map_lookup = {str(k or "").strip().lower(): v for k, v in mapping.items() if v}
        if not map_lookup:
            messagebox.showinfo(title, "No valid player matches were provided.")
            return
        temp_files: dict[str, str] = {}
        try:
            for cat, table in category_tables.items():
                rows = list(table.get("rows") or [])
                if len(rows) < 2:
                    continue
                header = rows[0]
                filtered = [header]
                for row in rows[1:]:
                    if not row:
                        continue
                    sheet_name = str(row[0]).strip()
                    mapped = map_lookup.get(sheet_name.lower())
                    if not mapped:
                        continue
                    new_row = list(row)
                    new_row[0] = mapped
                    filtered.append(new_row)
                if len(filtered) <= 1:
                    continue
                delimiter = table.get("delimiter") or ","
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline='', encoding='utf-8')
                writer = _csv.writer(tmp, delimiter=delimiter)
                writer.writerows(filtered)
                tmp.close()
                temp_files[cat] = tmp.name
            if not temp_files:
                messagebox.showinfo(title, "No matching rows were found for the selected players.")
                return
            results = self.model.import_all(temp_files)
            try:
                self.model.refresh_players()
            except Exception:
                pass
            msg_lines = [f"{title} completed."]
            if results:
                msg_lines.append("\nPlayers updated:")
                for cat, cnt in results.items():
                    msg_lines.append(f"  {cat}: {cnt}")
            messagebox.showinfo(title, "\n".join(msg_lines))
        finally:
            for path in temp_files.values():
                try:
                    os.remove(path)
                except Exception:
                    pass
    # ---------------------------------------------------------------------
    # Teams screen
    # ---------------------------------------------------------------------
    def _build_teams_screen(self):
        """Construct the Teams editing screen."""
        self.teams_frame = tk.Frame(self, bg=PANEL_BG)
        # Top bar with team selection
        top = tk.Frame(self.teams_frame, bg=PANEL_BG)
        top.pack(side=tk.TOP, fill=tk.X, pady=10, padx=10)
        tk.Label(top, text="Team:", font=("Segoe UI", 12), bg=PANEL_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT)
        self.team_edit_var = tk.StringVar()
        self.team_edit_dropdown = ttk.Combobox(
            top,
            textvariable=self.team_edit_var,
            state="readonly",
            style="App.TCombobox",
        )
        self.team_edit_dropdown.bind("<<ComboboxSelected>>", self._on_team_edit_selected)
        self.team_edit_dropdown.pack(side=tk.LEFT, padx=5)
        # Scan status label for teams
        self.team_scan_status_var = tk.StringVar()
        self.team_scan_status_label = tk.Label(
            top,
            textvariable=self.team_scan_status_var,
            font=("Segoe UI", 10, "italic"),
            bg=PANEL_BG,
            fg=TEXT_SECONDARY,
        )
        self.team_scan_status_label.pack(side=tk.LEFT, padx=10)
        # Detail pane for team fields
        detail = tk.Frame(self.teams_frame, bg=PANEL_BG, relief=tk.FLAT, bd=0)
        detail.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        tk.Label(
            detail,
            text="Team Details",
            font=("Segoe UI", 14, "bold"),
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
        ).pack(pady=(5, 10))
        # Form for each team field
        self.team_field_vars: Dict[str, tk.StringVar] = {}
        form = tk.Frame(detail, bg=PANEL_BG)
        form.pack(fill=tk.X, padx=10, pady=5)
        row = 0
        if TEAM_FIELD_DEFS:
            for label in TEAM_FIELD_DEFS.keys():
                tk.Label(form, text=f"{label}:", bg=PANEL_BG, fg=TEXT_SECONDARY).grid(row=row, column=0, sticky=tk.W, pady=2)
                var = tk.StringVar()
                entry = tk.Entry(
                    form,
                    textvariable=var,
                    bg=INPUT_BG,
                    fg=TEXT_PRIMARY,
                    relief=tk.FLAT,
                    insertbackground=TEXT_PRIMARY,
                    highlightthickness=1,
                    highlightbackground=ACCENT_BG,
                    highlightcolor=ACCENT_BG,
                )
                entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
                self.team_field_vars[label] = var
                row += 1
            form.columnconfigure(1, weight=1)
        else:
            tk.Label(
                form,
                text="No team field offsets found. Update 2K26_Offsets.json to enable editing.",
                bg=PANEL_BG,
                fg="#B0413E",
                wraplength=360,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=4)
        players_section = tk.Frame(detail, bg=PANEL_BG)
        players_section.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        tk.Label(
            players_section,
            text="Team Players",
            font=("Segoe UI", 12, "bold"),
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
        ).pack(anchor=tk.W)
        list_container = tk.Frame(players_section, bg=PANEL_BG)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        scrollbar = tk.Scrollbar(list_container, orient="vertical")
        self.team_players_listbox = tk.Listbox(
            list_container,
            height=12,
            yscrollcommand=scrollbar.set,
            bg=INPUT_BG,
            fg=TEXT_PRIMARY,
            selectbackground=ACCENT_BG,
            selectforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
        )
        self.team_players_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.team_players_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.team_players_listbox.bind("<Double-Button-1>", self._open_team_player_editor)

        # Save button
        self.btn_team_save = tk.Button(
            detail,
            text="Save",
            command=self._save_team,
            bg=BUTTON_BG,
            fg=TEXT_PRIMARY,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        self.btn_team_save.pack(pady=10)
    def _scan_teams_thread(self):
        """Background thread to refresh players and teams for the Teams screen."""
        # Use the same refresh mechanism as players
        self.model.refresh_players()
        teams = self.model.get_teams()
        def update_ui():
            self.scanning = False
            self.team_scan_status_var.set("")
            self._update_team_dropdown(teams)
            # Auto‑select first team if available
            if teams:
                self.team_edit_var.set(teams[0])
                self._on_team_edit_selected()
        self.after(0, update_ui)
    def _update_team_dropdown(self, teams: list[str]):
        """Helper to update both team dropdowns (players and teams screens)."""
        # Update players screen dropdown if it exists
        if hasattr(self, "team_dropdown"):
            player_list = ["All Players"] + list(teams)
            self.team_dropdown['values'] = player_list
            if player_list:
                self.team_var.set(player_list[0])
        # Update teams screen dropdown
        self.team_edit_dropdown['values'] = teams
    def _on_team_edit_selected(self, event=None):
        """Load team field values when a team is selected."""
        team_name = self.team_edit_var.get()
        if not team_name:
            self.btn_team_save.config(state=tk.DISABLED)
            for var in self.team_field_vars.values():
                var.set("")
            self._update_team_players(None)
            return
        # Find team index
        teams = self.model.get_teams()
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                self.btn_team_save.config(state=tk.DISABLED)
                self._update_team_players(None)
                return
        fields = self.model.get_team_fields(team_idx)
        if fields is None:
            # Not connected or cannot read
            for var in self.team_field_vars.values():
                var.set("")
            self.btn_team_save.config(state=tk.DISABLED)
            self._update_team_players(None)
            return
        # Populate fields
        for label, var in self.team_field_vars.items():
            val = fields.get(label, "")
            var.set(val)
        self._update_team_players(team_idx)
        # Enable save if process open
        self.btn_team_save.config(state=tk.NORMAL if self.model.mem.hproc else tk.DISABLED)
    def _save_team(self):
        """Save the edited team fields back to memory."""
        team_name = self.team_edit_var.get()
        if not team_name:
            return
        teams = self.model.get_teams()
        team_idx = self.model._team_index_for_display_name(team_name)
        if team_idx is None:
            try:
                team_idx = teams.index(team_name)
            except ValueError:
                return
        values = {label: var.get() for label, var in self.team_field_vars.items()}
        ok = self.model.set_team_fields(team_idx, values)
        if ok:
            messagebox.showinfo("Success", f"Updated {team_name} successfully.")
            # Refresh team list to reflect potential name change
            self.model.refresh_players()
            teams = self.model.get_teams()
            self._update_team_dropdown(teams)
            # Reselect the updated team name if changed
            new_name = values.get("Team Name")
            if new_name:
                self.team_edit_var.set(new_name)
            self._update_team_players(team_idx)
            return
        else:
            messagebox.showerror("Error", "Failed to write team data. Make sure the game is running and try again.")

    def _update_team_players(self, team_idx: int | None) -> None:
        if not hasattr(self, 'team_players_listbox') or self.team_players_listbox is None:
            return
        self.team_players_listbox.delete(0, tk.END)
        self.team_players_lookup = []
        if team_idx is None:
            return
        players: list[Player] = []
        try:
            if self.model.mem.hproc and self.model.mem.base_addr and not self.model.external_loaded:
                players = self.model.scan_team_players(team_idx)
        except Exception:
            players = []
        if not players:
            teams = self.model.get_teams()
            if 0 <= team_idx < len(teams):
                team_name = teams[team_idx]
                players = self.model.get_players_by_team(team_name)
        self.team_players_lookup = players
        if players:
            for player in players:
                self.team_players_listbox.insert(tk.END, player.full_name)
        else:
            self.team_players_listbox.insert(tk.END, "(No players found)")

    def _open_team_player_editor(self, _event=None) -> None:
        if not getattr(self, 'team_players_listbox', None):
            return
        selection = self.team_players_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.team_players_lookup):
            return
        player = self.team_players_lookup[idx]
        try:
            self.model.mem.open_process()
        except Exception:
            pass
        editor = FullPlayerEditor(self, player, self.model)
        editor.grab_set()


    # ---------------------------------------------------------------------
    # Home helpers
    # ---------------------------------------------------------------------
    def _update_status(self):
        if self.model.mem.open_process():
            pid = self.model.mem.pid
            self.status_var.set(f"NBA2K26 is running (PID {pid})")
        else:
            self.status_var.set("NBA2K26 not detected - launch the game to enable editing")
    # ---------------------------------------------------------------------
    # Scanning players
    # ---------------------------------------------------------------------
    def _start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.player_listbox.delete(0, tk.END)
        self.player_listbox.insert(tk.END, "Scanning players...")
        self.scan_status_var.set("Scanning... please wait")
        # Launch in a separate thread to avoid blocking UI
        threading.Thread(target=self._scan_thread, daemon=True).start()
    def _scan_thread(self):
        self.model.refresh_players()
        teams = self.model.get_teams()
        def update_ui():
            self.scanning = False
            # Update both dropdowns via helper
            self._update_team_dropdown(teams)
            if teams:
                self.team_var.set(teams[0])
            else:
                self.team_var.set("")
            self._refresh_player_list()
            if not self.model.mem.hproc:
                self.scan_status_var.set("NBA 2K26 is not running.")
            elif not teams:
                self.scan_status_var.set("No teams available.")
            else:
                self.scan_status_var.set("")
        self.after(0, update_ui)
    # ---------------------------------------------------------------------
    # UI update helpers
    # ---------------------------------------------------------------------
    def _refresh_player_list(self):
        team = self.team_var.get()
        # Get the players for the selected team.  Store them in
        # ``current_players`` so the search filter can operate on
        # a stable list without hitting the model repeatedly.
        self.current_players = self.model.get_players_by_team(team) if team else []
        # Apply search filtering.  This will rebuild the listbox and
        # update ``filtered_player_indices``.  If no search term is set
        # (i.e. placeholder text), all players are displayed.
        self._filter_player_list()
        # Reset selection and detail fields
        self.selected_player = None
        self._update_detail_fields()
    def _clear_player_cards(self, message: str = "") -> None:
        self.player_listbox.delete(0, tk.END)
        if message:
            self.player_listbox.insert(tk.END, message)
        self.player_name_var.set("Select a player")
        self.player_ovr_var.set("OVR --")
        self.var_first.set("")
        self.var_last.set("")
        self.var_player_team.set("")
        for var in self.player_detail_fields.values():
            var.set("--")
        try:
            self.player_portrait.itemconfig(self.player_portrait_text, text="")
        except Exception:
            pass
        self.player_count_var.set("Players: 0")
        self.btn_save.config(state=tk.DISABLED)
        self.btn_edit.config(state=tk.DISABLED)
        self.btn_copy.config(state=tk.DISABLED)
    def _filter_player_list(self) -> None:
        """Filter the player list based on the search entry and repopulate."""
        search = (self.player_search_var.get() or "").strip().lower()
        if search == "search players.":
            search = ""
        self.player_listbox.delete(0, tk.END)
        self.filtered_player_indices = []
        if not self.current_players:
            if not self.model.mem.hproc:
                self.player_listbox.insert(tk.END, "NBA 2K26 is not running.")
            else:
                self.player_listbox.insert(tk.END, "No players available.")
            self.player_count_var.set("Players: 0")
            return
        for idx, player in enumerate(self.current_players):
            name = (player.full_name or "").lower()
            if not search or search in name:
                self.filtered_player_indices.append(idx)
                self.player_listbox.insert(tk.END, player.full_name)
        if not self.filtered_player_indices:
            if self.current_players:
                self.player_listbox.insert(tk.END, "No players match the current filter.")
            else:
                self.player_listbox.insert(tk.END, "No players available.")
        self.player_count_var.set("Players: 0")
    def _on_player_list_mousewheel(self, event):
        try:
            delta = int(-1 * (event.delta / 120))
        except Exception:
            delta = -1 if getattr(event, 'delta', 0) > 0 else 1
        self.player_listbox.yview_scroll(delta, "units")
        return "break"
    def _on_team_selected(self, event=None):
        self._refresh_player_list()
    def _on_player_selected(self, event=None):
        selection = self.player_listbox.curselection()
        if not selection:
            self.selected_player = None
        else:
            idx = selection[0]
            # Map the visible index back to the index within
            # ``current_players`` using ``filtered_player_indices``.  If the
            # mapping is out of range, clear the selection.
            if idx < len(self.filtered_player_indices):
                p_idx = self.filtered_player_indices[idx]
                if p_idx < len(self.current_players):
                    self.selected_player = self.current_players[p_idx]
                else:
                    self.selected_player = None
            else:
                self.selected_player = None
        self._update_detail_fields()
    def _update_detail_fields(self):
        p = self.selected_player
        if not p:
            # Clear fields
            self.player_name_var.set("Select a player")
            self.player_ovr_var.set("OVR --")
            self.var_first.set("")
            self.var_last.set("")
            self.var_player_team.set("")
            self.btn_save.config(state=tk.DISABLED)
            self.btn_edit.config(state=tk.DISABLED)
            self.btn_copy.config(state=tk.DISABLED)
            for var in self.player_detail_fields.values():
                var.set("--")
            try:
                self.player_portrait.itemconfig(self.player_portrait_text, text="")
            except Exception:
                pass
        else:
            display_name = p.full_name or f"Player {p.index}"
            self.player_name_var.set(display_name)
            initials = "".join(part[0].upper() for part in (p.first_name, p.last_name) if part) or "?"
            try:
                self.player_portrait.itemconfig(self.player_portrait_text, text=initials[:2])
            except Exception:
                pass
            self.var_first.set(p.first_name)
            self.var_last.set(p.last_name)
            self.var_player_team.set(p.team)
            snapshot: dict[str, object] = {}
            try:
                snapshot = self.model.get_player_panel_snapshot(p)
            except Exception:
                snapshot = {}
            overall_val = snapshot.get("Overall")
            if isinstance(overall_val, (int, float)):
                self.player_ovr_var.set(f"OVR {int(overall_val)}")
            else:
                self.player_ovr_var.set("OVR --")
            def _format_detail(label: str, value: object) -> str:
                if label == "Height" and isinstance(value, (int, float)):
                    inches_val = raw_height_to_inches(int(value))
                    inches_val = max(HEIGHT_MIN_INCHES, min(HEIGHT_MAX_INCHES, inches_val))
                    return format_height_inches(inches_val)
                if value is None:
                    return "--"
                if isinstance(value, float):
                    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"
                return str(value)
            for label, var in self.player_detail_fields.items():
                var.set(_format_detail(label, snapshot.get(label)))
            # Save button enabled only if connected to game and not loaded from files
            enable_save = self.model.mem.hproc is not None and not self.model.external_loaded
            self.btn_save.config(state=tk.NORMAL if enable_save else tk.DISABLED)
            self.btn_edit.config(state=tk.NORMAL)
            # Copy button enabled if connected and not loaded from files.  We
            # defer determining actual destination availability until the
            # copy dialog is opened.
            enable_copy = enable_save and p is not None
            self.btn_copy.config(state=tk.NORMAL if enable_copy else tk.DISABLED)
    # ---------------------------------------------------------------------
    # Saving and editing
    # ---------------------------------------------------------------------
    def _save_player(self):
        p = self.selected_player
        if not p:
            return
        # Update from entry fields
        p.first_name = self.var_first.get().strip()
        p.last_name = self.var_last.get().strip()
        try:
            self.model.update_player(p)
            messagebox.showinfo("Success", "Player updated successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save changes:\n{e}")
        # Refresh list to reflect potential name changes
        self._refresh_player_list()
    def _open_full_editor(self):
        p = self.selected_player
        if not p:
            return
        editor = FullPlayerEditor(self, p, self.model)
        editor.grab_set()
    def _open_copy_dialog(self):
        """Open a dialog allowing the user to copy data from the selected player to another."""
        src = self.selected_player
        if not src:
            return
        # Prepare list of destination players (exclude source)
        dest_players: list[Player] = []
        if self.model.players:
            dest_players = [p for p in self.model.players if p.index != src.index]
        elif self.model.team_list:
            for idx, _ in self.model.team_list:
                players = self.model.scan_team_players(idx)
                for p in players:
                    if p.index != src.index:
                        dest_players.append(p)
        # Remove duplicate names (based on index) while preserving order
        seen = set()
        uniq_dest = []
        for p in dest_players:
            if p.index not in seen:
                seen.add(p.index)
                uniq_dest.append(p)
        dest_players = uniq_dest
        if not dest_players:
            messagebox.showinfo("Copy Player Data", "No other players are available to copy to.")
            return
        # Create dialog window
        win = tk.Toplevel(self)
        win.title("Copy Player Data")
        win.geometry("400x320")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        # Source label
        tk.Label(win, text=f"Copy from: {src.full_name}", font=("Segoe UI", 12, "bold")).pack(pady=(10, 5))
        # Destination dropdown
        dest_var = tk.StringVar()
        dest_names = [p.full_name for p in dest_players]
        dest_map = {p.full_name: p for p in dest_players}
        dest_frame = tk.Frame(win)
        dest_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        tk.Label(dest_frame, text="Copy to:", font=("Segoe UI", 10)).pack(side=tk.LEFT)
        dest_combo = ttk.Combobox(dest_frame, textvariable=dest_var, values=dest_names, state="readonly")
        dest_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5))
        if dest_names:
            dest_var.set(dest_names[0])
        # Category checkboxes
        chk_frame = tk.Frame(win)
        chk_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        tk.Label(chk_frame, text="Data to copy:", font=("Segoe UI", 10)).pack(anchor=tk.W)
        var_full = tk.IntVar(value=0)
        var_attributes = tk.IntVar(value=0)
        var_tendencies = tk.IntVar(value=0)
        var_badges = tk.IntVar(value=0)
        cb1 = tk.Checkbutton(chk_frame, text="Full Player", variable=var_full)
        cb3 = tk.Checkbutton(chk_frame, text="Attributes", variable=var_attributes)
        cb4 = tk.Checkbutton(chk_frame, text="Tendencies", variable=var_tendencies)
        cb5 = tk.Checkbutton(chk_frame, text="Badges", variable=var_badges)
        cb1.pack(anchor=tk.W)
        cb3.pack(anchor=tk.W)
        cb4.pack(anchor=tk.W)
        cb5.pack(anchor=tk.W)
        # Buttons for copy/cancel
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        def do_copy():
            dest_name = dest_var.get()
            dest_player = dest_map.get(dest_name)
            if not dest_player:
                messagebox.showerror("Copy Player Data", "No destination player selected.")
                return
            categories = []
            if var_full.get():
                categories = ["full"]
            else:
                if var_attributes.get():
                    categories.append("attributes")
                if var_tendencies.get():
                    categories.append("tendencies")
                if var_badges.get():
                    categories.append("badges")
            if not categories:
                messagebox.showwarning("Copy Player Data", "Please select at least one data category to copy.")
                return
            success = self.model.copy_player_data(src.index, dest_player.index, categories)
            if success:
                messagebox.showinfo("Copy Player Data", "Data copied successfully.")
                # Refresh the player list to reflect any changes
                self._start_scan()
            else:
                messagebox.showerror("Copy Player Data", "Failed to copy data. Make sure the game is running and try again.")
            win.destroy()
        tk.Button(btn_frame, text="Copy", command=do_copy, bg="#84A98C", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=win.destroy, bg="#B0413E", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
    def _open_import_dialog(self):
        """Prompt the user to select one or more import files and apply them to the roster.
        The user can select up to three files corresponding to Attributes,
        Tendencies, and Durability tables.  The method attempts to
        auto‑detect the category of each selected file based on the
        column headers.  If no recognizable category is detected, the
        file is ignored.  After importing, the player list is refreshed.
        """
        # Prompt for files; allow multiple selection.  If the user cancels,
        # return immediately.
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Select Import Files",
            filetypes=[("Data files", "*.txt *.csv *.tsv"), ("All files", "*.*")],
        )
        if not paths:
            return
        # Precompute normalized header names for each known category
        attr_norms = [self.model._normalize_header_name(h) for h in ATTR_IMPORT_ORDER]
        tend_norms = [self.model._normalize_header_name(h) for h in TEND_IMPORT_ORDER]
        dur_norms = [self.model._normalize_header_name(h) for h in DUR_IMPORT_ORDER]
        file_map: dict[str, str] = {}
        for path in paths:
            # Read the first line of the file to inspect headers
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    first_line = f.readline()
            except Exception:
                continue
            # Detect delimiter: prioritize tab, then comma, then semicolon
            delim = '\t' if '\t' in first_line else ',' if ',' in first_line else ';'
            header = [h.strip() for h in first_line.strip().split(delim)]
            # Normalize all headers except the first (player name)
            headers_norm = [self.model._normalize_header_name(h) for h in header[1:]] if len(header) > 1 else []
            # Compute match scores for each category
            score_attr = sum(1 for h in headers_norm if any(nf == h or nf in h or h in nf for nf in attr_norms))
            score_tend = sum(1 for h in headers_norm if any(nf == h or nf in h or h in nf for nf in tend_norms))
            score_dur = sum(1 for h in headers_norm if any(nf == h or nf in h or h in nf for nf in dur_norms))
            # Determine category with the highest score
            if score_attr >= score_tend and score_attr >= score_dur and score_attr > 0:
                cat = 'Attributes'
            elif score_tend >= score_attr and score_tend >= score_dur and score_tend > 0:
                cat = 'Tendencies'
            elif score_dur >= score_attr and score_dur >= score_tend and score_dur > 0:
                cat = 'Durability'
            else:
                # Could not determine category; skip this file
                continue
            # If this category is not yet mapped, assign the file path
            if cat not in file_map:
                file_map[cat] = path
        if not file_map:
            messagebox.showerror("Import Data", "The selected file(s) do not match any known data category.")
            return
        # Invoke the import for all detected categories
        results = self.model.import_all(file_map)
        # Compose a summary message
        messages = []
        for cat in ['Attributes', 'Tendencies', 'Durability']:
            if cat in file_map:
                count = results.get(cat)
                basename = os.path.basename(file_map[cat])
                messages.append(f"Imported {count} players for {cat} from {basename}.")
        msg = "\n".join(messages) if messages else "No data was imported."
        messagebox.showinfo("Import Data", msg)
        # Refresh players to reflect imported values (works only when process is open)
        self._start_scan()
class FullPlayerEditor(tk.Toplevel):
    """A tabbed editor window for advanced player attributes."""
    def __init__(self, parent: tk.Tk, player: Player, model: PlayerDataModel):
        super().__init__(parent)
        self.player = player
        self.model = model
        self.title(f"Editing: {player.full_name}")
        # Dimensions: slightly larger for many fields
        self.geometry("700x500")
        self.configure(bg=PANEL_BG)
        style = ttk.Style(self)
        try:
            current_theme = style.theme_use()
            style.theme_use(current_theme)
        except Exception:
            pass
        style.configure("FullEditor.TNotebook", background=PANEL_BG, borderwidth=0)
        style.configure(
            "FullEditor.TNotebook.Tab",
            background=PANEL_BG,
            foreground=TEXT_SECONDARY,
            padding=(12, 6),
        )
        style.map(
            "FullEditor.TNotebook.Tab",
            background=[("selected", BUTTON_BG), ("active", ACCENT_BG)],
            foreground=[("selected", TEXT_PRIMARY), ("active", TEXT_PRIMARY)],
        )
        style.configure("FullEditor.TFrame", background=PANEL_BG)
        try:
            style.configure(
                "FullEditor.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=TEXT_PRIMARY,
                bordercolor=ACCENT_BG,
                arrowcolor=TEXT_PRIMARY,
            )
        except tk.TclError:
            style.configure(
                "FullEditor.TCombobox",
                fieldbackground=INPUT_BG,
                background=INPUT_BG,
                foreground=TEXT_PRIMARY,
            )
        style.map(
            "FullEditor.TCombobox",
            fieldbackground=[("readonly", INPUT_BG)],
            foreground=[("readonly", TEXT_PRIMARY)],
        )
        # Dictionary mapping category names to a mapping of field names to
        # Tkinter variables.  This allows us to load and save values easily.
        self.field_vars: dict[str, dict[str, tk.Variable]] = {}
        # Dictionary mapping (category_name, field_name) -> metadata dict
        # describing offset, start bit and bit length.  Using the tuple
        # avoids using unhashable Tkinter variables as keys.
        self.field_meta: dict[tuple[str, str], dict[str, int]] = {}
        # Dictionary to hold Spinbox widgets for each field.  The key is
        # (category_name, field_name) and the value is the Spinbox
        # instance.  Storing these allows us to compute min/max values
        # dynamically based on the widget's configuration (e.g. range)
        # when adjusting entire categories via buttons.
        self.spin_widgets: dict[tuple[str, str], tk.Spinbox] = {}
        # Track fields edited since last save
        self._unsaved_changes: set[tuple[str, str]] = set()
        # Suppress change-trace callbacks while populating initial values
        self._initializing = True
        # Notebook for category tabs
        notebook = ttk.Notebook(self, style="FullEditor.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True)
        # Determine which categories are available from the model.  If
        # categories are missing, we still display the tab with a placeholder.
        # Determine tab order.  Start with the common categories defined in
        # the offset map.  Then append any additional categories found in
        # the model that are not already listed.  Finally include
        # placeholder tabs for future extensions (Accessories, Contract).
        categories = []
        for name in ["Body", "Vitals", "Attributes", "Tendencies", "Badges"]:
            categories.append(name)
        # Append any additional category names defined in the model
        for name in self.model.categories.keys():
            if name not in categories:
                categories.append(name)
        # Append placeholder categories for unimplemented sections
        if "Contract" not in categories:
            categories.append("Contract")
            if name not in categories:
                categories.append(name)
        exclude_for_player = {
            "pointers",
            "offsets",
            "teams",
            "team business",
            "team jersey",
            "team stats",
            "team stats edit",
            "team vitals",
            "staff",
            "stadium",
            "jersey",
        }
        filtered_categories: list[str] = []
        for cat in categories:
            if cat.strip().lower() in exclude_for_player:
                continue
            filtered_categories.append(cat)
        for cat in filtered_categories:
            frame = tk.Frame(notebook, bg=PANEL_BG, highlightthickness=0, bd=0)
            notebook.add(frame, text=cat)
            self._build_category_tab(frame, cat)
        # Action buttons at bottom
        btn_frame = tk.Frame(self, bg=PANEL_BG)
        btn_frame.pack(fill=tk.X, pady=5)
        save_btn = tk.Button(
            btn_frame,
            text="Save",
            command=self._save_all,
            bg=BUTTON_BG,
            fg=BUTTON_TEXT,
            activebackground=BUTTON_ACTIVE_BG,
            activeforeground=BUTTON_TEXT,
            relief=tk.FLAT,
        )
        save_btn.pack(side=tk.LEFT, padx=10)
        close_btn = tk.Button(
            btn_frame,
            text="Close",
            command=self.destroy,
            bg="#B0413E",
            fg="white",
            activebackground="#8D2C29",
            activeforeground="white",
            relief=tk.FLAT,
        )
        close_btn.pack(side=tk.LEFT)
        # Populate field values from memory
        self._load_all_values()
        self._initializing = False
    def _build_category_tab(self, parent: tk.Frame, category_name: str) -> None:
        """
        Build the UI for a specific category.  If field definitions are
        available for the category, create a grid of labels and spinboxes
        for each field.  Otherwise, display a placeholder message.
        """
        fields = self.model.categories.get(category_name, [])
        # Add category-level adjustment buttons for Attributes, Durability, and Tendencies
        if category_name in ("Attributes", "Durability", "Tendencies"):
            btn_frame = tk.Frame(parent, bg=PANEL_BG)
            btn_frame.pack(fill=tk.X, padx=10, pady=(5))
            actions = [
                ("Min", "min"),
                ("+5", "plus5"),
                ("+10", "plus10"),
                ("-5", "minus5"),
                ("-10", "minus10"),
                ("Max", "max"),
            ]
            for label, action in actions:
                tk.Button(
                    btn_frame,
                    text=label,
                    command=lambda act=action, cat=category_name: self._adjust_category(cat, act),
                    bg=BUTTON_BG,
                    fg=BUTTON_TEXT,
                    activebackground=BUTTON_ACTIVE_BG,
                    activeforeground=BUTTON_TEXT,
                    relief=tk.FLAT,
                    width=5,
                ).pack(side=tk.LEFT, padx=2)
        # Container for scrolled view if many fields
        canvas = tk.Canvas(parent, bg=PANEL_BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        try:
            scrollbar.configure(bg=PANEL_BG, troughcolor=PANEL_BG, activebackground=ACCENT_BG)
        except tk.TclError:
            pass
        scroll_frame = tk.Frame(canvas, bg=PANEL_BG)
        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set, bg=PANEL_BG)
        # Pack canvas and scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Save variables mapping
        self.field_vars.setdefault(category_name, {})
        if not fields:
            # No definitions found
            tk.Label(
                scroll_frame,
                text=f"{category_name} editing not available.",
                bg=PANEL_BG,
                fg=TEXT_SECONDARY,
            ).pack(padx=10, pady=10)
            return
        # Build rows for each field
        for row, field in enumerate(fields):
            name = field.get("name", f"Field {row}")
            offset_val = _to_int(field.get("offset"))
            start_bit = _to_int(field.get("startBit", field.get("start_bit", 0)))
            length = _to_int(field.get("length", 8))
            requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
            deref_offset = _to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
            # Label
            lbl = tk.Label(scroll_frame, text=name + ":", bg=PANEL_BG, fg=TEXT_PRIMARY)
            lbl.grid(row=row, column=0, sticky=tk.W, padx=(10, 5), pady=2)
            # Variable and spinbox
            var = tk.IntVar(value=0)
            # Determine raw maximum value for the bitfield
            max_raw = (1 << length) - 1
            # Compute the range shown in the spinbox.  For Attributes
            # categories we convert the raw 0..max_raw values to the 2K
            # rating scale of 25..99.  This mapping is handled in
            # _load_all_values/_save_all; here we restrict the spinbox
            # range to reflect the rating bounds.  For all other
            # categories we use the raw bit range.
            # Determine the displayed range of the Spinbox.  For
            # Attributes, Durability and Tendencies we display the
            # familiar 25..99 rating scale.  Conversion to/from raw
            # bitfield values is handled in the load/save methods.  For
            # all other categories, use the raw bit range.
            if category_name in ("Attributes", "Durability"):
                # Attributes and Durability use the familiar 25-99 rating scale
                spin_from = 25
                spin_to = 99
            elif category_name == "Tendencies":
                # Tendencies are displayed on a 0-100 scale
                spin_from = 0
                spin_to = 100
            elif name.lower() == "height":
                spin_from = HEIGHT_MIN_INCHES
                spin_to = HEIGHT_MAX_INCHES
            else:
                spin_from = 0
                spin_to = max_raw
            # Determine if this field has an enumeration of values defined.
            # If the field contains a "values" list, we use a combobox
            # populated with those values.  Otherwise we fall back to
            # category‑specific handling (badges) or a numeric spinbox.
            values_list = field.get("values") if isinstance(field, dict) else None
            if values_list:
                # Create an IntVar to store the selected index
                var = tk.IntVar(value=0)
                combo = ttk.Combobox(
                    scroll_frame,
                    values=values_list,
                    state="readonly",
                    width=16,
                    style="FullEditor.TCombobox",
                )
                combo.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                # When user picks an entry, update the IntVar accordingly
                def on_enum_selected(event, v=var, c=combo, vals=values_list):
                    try:
                        v.set(vals.index(c.get()))
                    except Exception:
                        v.set(0)
                combo.bind("<<ComboboxSelected>>", on_enum_selected)
                # Store variable
                self.field_vars[category_name][name] = var
                # Record metadata; keep reference to combobox and values list
                self.field_meta[(category_name, name)] = {
                    "offset": offset_val,
                    "start_bit": start_bit,
                    "length": length,
                    "widget": combo,
                    "values": values_list,
                    "requires_deref": requires_deref,
                    "deref_offset": deref_offset,
                }
                # Flag unsaved changes
                def on_enum_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_enum_change)
            elif category_name == "Badges":
                # Special handling for badge levels: expose a human‑readable
                # combobox instead of a numeric spinbox.  Each badge uses a
                # 3‑bit field (0–7) but the game recognises only 0..4.
                var = tk.IntVar(value=0)
                combo = ttk.Combobox(
                    scroll_frame,
                    values=BADGE_LEVEL_NAMES,
                    state="readonly",
                    width=12,
                    style="FullEditor.TCombobox",
                )
                combo.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                # When the user picks a level, update the IntVar
                def on_combo_selected(event, v=var, c=combo):
                    val_name = c.get()
                    v.set(BADGE_NAME_TO_VALUE.get(val_name))
                combo.bind("<<ComboboxSelected>>", on_combo_selected)
                # Store variable for this field
                self.field_vars[category_name][name] = var
                # Record metadata; also keep reference to combobox for later update
                self.field_meta[(category_name, name)] = {
                    "offset": offset_val,
                    "start_bit": start_bit,
                    "length": length,
                    "widget": combo,
                    "requires_deref": requires_deref,
                    "deref_offset": deref_offset,
                }
                # Flag unsaved changes
                def on_badge_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_badge_change)
            else:
                # Use Spinbox for numeric values; large ranges may be unwieldy
                spin = tk.Spinbox(
                    scroll_frame,
                    from_=spin_from,
                    to=spin_to,
                    textvariable=var,
                    width=10,
                    bg=INPUT_BG,
                    fg=TEXT_PRIMARY,
                    highlightbackground=ACCENT_BG,
                    highlightthickness=1,
                    relief=tk.FLAT,
                    insertbackground=TEXT_PRIMARY,
                )
                spin.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
                spin.configure(selectbackground=ACCENT_BG, selectforeground=TEXT_PRIMARY)
                # Store variable by name for this category
                self.field_vars[category_name][name] = var
                # Record metadata keyed by (category, field_name)
                self.field_meta[(category_name, name)] = {
                    "offset": offset_val,
                    "start_bit": start_bit,
                    "length": length,
                    "widget": spin,
                    "requires_deref": requires_deref,
                    "deref_offset": deref_offset,
                }
                # Save the Spinbox widget for later category-wide adjustments
                self.spin_widgets[(category_name, name)] = spin
                # Flag unsaved changes when the value changes
                def on_spin_change(*args, cat=category_name, field_name=name):
                    if getattr(self, '_initializing', False):
                        return
                    self._unsaved_changes.add((cat, field_name))
                var.trace_add("write", on_spin_change)
    def _load_all_values(self) -> None:
        """
        Populate all spinboxes with current values from memory.  This
        iterates over the categories and fields stored in
        ``self.field_vars`` and calls ``model.get_field_value`` for
        each one.
        """
        # Iterate over each category and field to load values using stored
        # metadata.  The metadata is stored in ``self.field_meta`` keyed by
        # (category, field_name).  We then set the associated variable.
        for category, fields in self.field_vars.items():
            for field_name, var in fields.items():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                offset = meta.get('offset')
                start_bit = meta.get('start_bit')
                length = meta.get('length')
                requires_deref = bool(meta.get('requires_deref'))
                deref_offset = _to_int(meta.get('deref_offset'))
                value = self.model.get_field_value(
                    self.player.index,
                    offset,
                    start_bit,
                    length,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                )
                if value is not None:
                    try:
                        # Convert raw bitfield values to user‑friendly values
                        field_name_lower = field_name.lower()
                        if field_name_lower == "height":
                            inches_val = raw_height_to_inches(int(value))
                            inches_val = max(HEIGHT_MIN_INCHES, min(HEIGHT_MAX_INCHES, inches_val))
                            var.set(inches_val)
                        elif field_name_lower == "weight":
                            try:
                                self.model.mem.open_process()
                            except Exception:
                                pass
                            base_addr = self.model._resolve_player_table_base()
                            if base_addr is not None:
                                addr = base_addr + self.player.index * PLAYER_STRIDE + offset
                                wval = read_weight(self.model.mem, addr)
                                var.set(int(round(wval)))
                            else:
                                var.set(0)
                        elif category in ("Attributes", "Durability"):  # Map the raw bitfield value into the 25-99 rating scale
                            rating = convert_raw_to_rating(int(value), length)
                            var.set(int(rating))
                        elif category == "Tendencies":
                            # Tendencies use a 0–100 scale
                            rating = convert_tendency_raw_to_rating(int(value), length)
                            var.set(int(rating))
                        elif category == "Badges":
                            # Badges are stored as 3‑bit fields; clamp to 0–4
                            lvl = int(value)
                            if lvl < 0:
                                lvl = 0
                            elif lvl > 4:
                                lvl = 4
                            var.set(lvl)
                            # Update combobox display if present
                            widget = meta.get("widget") if meta else None
                            if widget is not None:
                                try:
                                    widget.set(BADGE_LEVEL_NAMES[lvl])
                                except Exception:
                                    pass
                        elif meta and isinstance(meta.get("values"), list):
                            # Enumerated field: clamp the raw value to the index range
                            vals = meta.get("values")
                            idx = int(value)
                            if idx < 0:
                                idx = 0
                            elif idx >= len(vals):
                                idx = len(vals) - 1
                            var.set(idx)
                            # Update combobox display
                            widget = meta.get("widget")
                            if widget is not None:
                                try:
                                    widget.set(vals[idx])
                                except Exception:
                                    pass
                        else:
                            # Other categories are shown as their raw integer values
                            var.set(int(value))
                    except Exception:
                        pass
    def _save_all(self) -> None:
        """
        Iterate over all fields and write the current values back to the
        player's record in memory.
        """
        # Iterate similar to load
        any_error = False
        for category, fields in self.field_vars.items():
            for field_name, var in fields.items():
                meta = self.field_meta.get((category, field_name))
                if not meta:
                    continue
                try:
                    offset = meta.get('offset')
                    start_bit = meta.get('start_bit')
                    length = meta.get('length')
                    requires_deref = bool(meta.get('requires_deref'))
                    deref_offset = _to_int(meta.get('deref_offset'))
                    # Retrieve the value from the UI
                    ui_value = var.get()
                    # Convert rating back to raw bitfield for Attributes,
                    # Durability and Tendencies.  Observations indicate
                    # that ratings are stored with an offset of 10 (i.e., a
                    # rating of 25 corresponds to raw 15 and a rating of 99
                    # corresponds to raw 89).  Therefore we simply
                    # subtract 10 from the rating and clamp the result to
                    # the valid bitfield range.  Other categories are
                    # written as-is.
                    field_name_lower = field_name.lower()
                    if field_name_lower == "height":
                        try:
                            inches_val = int(ui_value)
                        except Exception:
                            inches_val = HEIGHT_MIN_INCHES
                        if inches_val < HEIGHT_MIN_INCHES:
                            inches_val = HEIGHT_MIN_INCHES
                        elif inches_val > HEIGHT_MAX_INCHES:
                            inches_val = HEIGHT_MAX_INCHES
                        value_to_write = height_inches_to_raw(inches_val)
                    elif field_name_lower == "weight":
                        try:
                            wval = float(ui_value)
                        except Exception:
                            wval = 0.0
                        try:
                            self.model.mem.open_process()
                        except Exception:
                            pass
                        base_addr = self.model._resolve_player_table_base()
                        if base_addr is not None:
                            addr = base_addr + self.player.index * PLAYER_STRIDE + offset
                            write_weight(self.model.mem, addr, wval)
                        continue
                    elif category in ("Attributes", "Durability"):  # Convert the UI rating back into a raw bitfield value.
                        try:
                            rating_val = int(ui_value)
                        except Exception:
                            rating_val = 25
                        value_to_write = convert_rating_to_raw(rating_val, length)
                    elif category == "Tendencies":
                        # Tendencies: convert the 0–100 rating back to raw bitfield
                        try:
                            rating_val = float(ui_value)
                        except Exception:
                            rating_val = 0.0
                        value_to_write = convert_rating_to_tendency_raw(rating_val, length)
                    elif category == "Badges":
                        # Badges: clamp UI value (0–4) to the underlying bitfield
                        try:
                            lvl = int(ui_value)
                        except Exception:
                            lvl = 0
                        if lvl < 0:
                            lvl = 0
                        max_raw = (1 << length) - 1
                        if lvl > max_raw:
                            lvl = max_raw
                        value_to_write = lvl
                    elif meta and isinstance(meta.get("values"), list):
                        # Enumerated field: clamp UI value to the bitfield range
                        try:
                            idx_val = int(ui_value)
                        except Exception:
                            idx_val = 0
                        if idx_val < 0:
                            idx_val = 0
                        max_raw = (1 << length) - 1
                        if idx_val > max_raw:
                            idx_val = max_raw
                        value_to_write = idx_val
                    else:
                        # For other categories, write the raw value directly
                        value_to_write = ui_value
                    if not self.model.set_field_value(
                        self.player.index,
                        offset,
                        start_bit,
                        length,
                        value_to_write,
                        requires_deref=requires_deref,
                        deref_offset=deref_offset,
                    ):
                        any_error = True
                except Exception:
                    any_error = True
        if any_error:
            messagebox.showerror("Save Error", "One or more fields could not be saved.")
        else:
            messagebox.showinfo("Save Successful", "All fields saved successfully.")
    def _adjust_category(self, category_name: str, action: str) -> None:
        """
        Adjust all values within a category according to the specified action.
        Actions can be one of: 'min', 'max', 'plus5', 'plus10', 'minus5', 'minus10'.
        For Attributes, Durability and Tendencies categories, values are clamped
        to the 25..99 scale.  For other categories, values are clamped to the
        raw bitfield range (0..(2^length - 1)).
        """
        # Ensure the category exists
        fields = self.field_vars.get(category_name)
        if not fields:
            return
        for field_name, var in fields.items():
            # Retrieve bit length from metadata
            meta = self.field_meta.get((category_name, field_name))
            if not meta:
                continue
            length = meta.get("length", 8)
            # Determine min and max values based on category
            if category_name in ("Attributes", "Durability"):
                # Attributes and Durability: clamp to 25..99
                min_val = 25
                max_val = 99
            elif category_name == "Tendencies":
                # Tendencies: clamp to 0..100
                min_val = 0
                max_val = 100
            else:
                min_val = 0
                max_val = (1 << int(length)) - 1
            current = var.get()
            new_val = current
            if action == "min":
                new_val = min_val
            elif action == "max":
                new_val = max_val
            elif action == "plus5":
                new_val = current + 5
            elif action == "plus10":
                new_val = current + 10
            elif action == "minus5":
                new_val = current - 5
            elif action == "minus10":
                new_val = current - 10
            # Clamp to allowed range
            if new_val < min_val:
                new_val = min_val
            if new_val > max_val:
                new_val = max_val
            var.set(int(new_val))
# ---------------------------------------------------------------------
# Randomizer window
# ---------------------------------------------------------------------
class RandomizerWindow(tk.Toplevel):
    """
    A modal window for randomizing player attributes, tendencies and
    durability values for selected teams.  It presents three tabs
    (Attributes, Tendencies, Durability) where minimum and maximum
    rating bounds can be specified per field, and a fourth tab for
    selecting which teams or pools should be affected.  When the
    "Randomize Selected" button is clicked, random ratings are
    applied to all players on the selected teams.
    Parameters
    ----------
    parent : PlayerEditorApp
        The parent window.  The randomizer window will be centered
        over this window and is modal relative to it.
    model : PlayerDataModel
        The data model used to access players, teams and field
        definitions.
    """
    def __init__(self, parent: "PlayerEditorApp", model: PlayerDataModel) -> None:
        super().__init__(parent)
        self.title("Randomizer")
        self.model = model
        # Dictionaries to hold IntVars for min and max values per field
        self.min_vars: dict[tuple[str, str], tk.IntVar] = {}
        self.max_vars: dict[tuple[str, str], tk.IntVar] = {}
        # BooleanVars for team selection
        self.team_vars: dict[str, tk.BooleanVar] = {}
        # Configure basic appearance
        self.configure(bg="#F5F5F5")
        # Make window modal
        self.transient(parent)
        self.grab_set()
        # Build the user interface
        self._build_ui()
        # Center the window relative to parent
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
    def _build_ui(self) -> None:
        """Construct the notebook with category and team tabs, plus a close button."""
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Categories to randomize
        categories = ["Attributes", "Tendencies", "Durability"]
        for cat in categories:
            frame = tk.Frame(notebook, bg="#F5F5F5")
            notebook.add(frame, text=cat)
            self._build_category_page(frame, cat)
        # Teams tab
        team_frame = tk.Frame(notebook, bg="#F5F5F5")
        notebook.add(team_frame, text="Teams")
        self._build_team_page(team_frame)
        # Close button at bottom
        tk.Button(self, text="Close", command=self.destroy, bg="#B0413E", fg="white", relief=tk.FLAT).pack(pady=(0, 10))
    def _build_category_page(self, parent: tk.Frame, category: str) -> None:
        """
        Build a page for a single category (Attributes, Tendencies, Durability).
        Each field has two Spinboxes for specifying minimum and maximum
        ratings.  Default values are 25 and 99.
        """
        canvas = tk.Canvas(parent, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Header row
        tk.Label(scroll_frame, text="Field", bg="#F5F5F5", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky=tk.W, padx=(10, 5), pady=2)
        tk.Label(scroll_frame, text="Min", bg="#F5F5F5", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, padx=5, pady=2)
        tk.Label(scroll_frame, text="Max", bg="#F5F5F5", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, padx=5, pady=2)
        fields = self.model.categories.get(category, [])
        for idx, field in enumerate(fields, start=1):
            name = field.get("name", f"Field {idx}")
            tk.Label(scroll_frame, text=name, bg="#F5F5F5").grid(row=idx, column=0, sticky=tk.W, padx=(10, 5), pady=2)
            # Set default min/max based on category
            if category in ("Attributes", "Durability"):
                default_min = 25
                default_max = 99
                spin_from = 25
                spin_to = 99
            elif category == "Tendencies":
                default_min = 0
                default_max = 100
                spin_from = 0
                spin_to = 100
            else:
                # Default branch; not expected for randomizer categories
                default_min = 0
                default_max = (1 << int(field.get("length", 8))) - 1
                spin_from = 0
                spin_to = default_max
            min_var = tk.IntVar(value=default_min)
            max_var = tk.IntVar(value=default_max)
            self.min_vars[(category, name)] = min_var
            self.max_vars[(category, name)] = max_var
            tk.Spinbox(scroll_frame, from_=spin_from, to=spin_to, textvariable=min_var, width=5).grid(row=idx, column=1, padx=2, pady=2)
            tk.Spinbox(scroll_frame, from_=spin_from, to=spin_to, textvariable=max_var, width=5).grid(row=idx, column=2, padx=2, pady=2)
    def _build_team_page(self, parent: tk.Frame) -> None:
        """
        Build the team selection page.  Contains a button to trigger
        randomization and a list of checkboxes for each team/pool.
        """
        btn_randomize = tk.Button(parent, text="Randomize Selected", command=self._randomize_selected, bg="#52796F", fg="white", relief=tk.FLAT)
        btn_randomize.pack(pady=(5, 10))
        canvas = tk.Canvas(parent, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Obtain team names: prefer get_teams' ordering, otherwise use the raw team_list
        team_names = []
        try:
            team_names = self.model.get_teams()
        except Exception:
            team_names = []
        if not team_names:
            team_names = [name for _, name in self.model.team_list]
        # Build checkbuttons for each team
        for idx, team_name in enumerate(team_names):
            var = tk.BooleanVar(value=False)
            self.team_vars[team_name] = var
            chk = tk.Checkbutton(scroll_frame, text=team_name, variable=var, bg="#F5F5F5")
            chk.grid(row=idx, column=0, sticky=tk.W, padx=10, pady=2)
    def _randomize_selected(self) -> None:
        """
        Randomize all player values for selected teams using the specified
        bounds.  The ratings are converted from the 25–99 scale into
        raw bitfield values before writing to memory.  After
        randomization, the player list is refreshed and a summary
        message is displayed.
        """
        import tkinter.messagebox as mb
        # Determine which teams are selected
        selected = [team for team, var in self.team_vars.items() if var.get()]
        if not selected:
            mb.showinfo("Randomizer", "No teams selected for randomization.")
            return
        # Categories we randomize
        categories = ["Attributes", "Tendencies", "Durability"]
        updated_players = 0
        for team_name in selected:
            players = self.model.get_players_by_team(team_name)
            if not players:
                continue
            for player in players:
                player_updated = False
                for cat in categories:
                    fields = self.model.categories.get(cat, [])
                    for field in fields:
                        fname = field.get("name")
                        # Check that we have min/max variables for this field
                        key = (cat, fname)
                        if key not in self.min_vars or key not in self.max_vars:
                            continue
                        # Retrieve offset info
                        offset_raw = field.get("offset")
                        if offset_raw in (None, ""):
                            continue
                        offset_val = _to_int(offset_raw)
                        start_bit = _to_int(field.get("startBit", field.get("start_bit", 0)))
                        length = _to_int(field.get("length", 8))
                        requires_deref = bool(field.get("requiresDereference") or field.get("requires_deref"))
                        deref_offset = _to_int(field.get("dereferenceAddress") or field.get("deref_offset"))
                        min_val = self.min_vars[key].get()
                        max_val = self.max_vars[key].get()
                        if min_val > max_val:
                            min_val, max_val = max_val, min_val
                        # Pick a random rating within the user‑specified bounds
                        rating = random.randint(min_val, max_val)
                        # Convert the rating into a raw bitfield value using
                        # the appropriate conversion based on category
                        if cat == "Tendencies":
                            raw_val = convert_rating_to_tendency_raw(rating, length)
                        else:
                            raw_val = convert_rating_to_raw(rating, length)
                        if self.model.set_field_value(
                            player.index,
                            offset_val,
                            start_bit,
                            length,
                            raw_val,
                            requires_deref=requires_deref,
                            deref_offset=deref_offset,
                        ):
                            player_updated = True
                if player_updated:
                    updated_players += 1
        # Refresh player list to reflect updated values
        try:
            self.model.refresh_players()
        except Exception:
            pass
        mb.showinfo("Randomizer", f"Randomization complete. {updated_players} players updated.")
# ---------------------------------------------------------------------
# Team Shuffle window
# ---------------------------------------------------------------------
class TeamShuffleWindow(tk.Toplevel):
    """
    A modal window that lets the user select one or more teams and then
    shuffle the players among those teams.  The shuffle maintains the
    original roster sizes (players per team) and will not proceed if
    any selected team has more than 15 players.  After shuffling, the
    team pointers in each player record are updated to reflect their
    new teams and the player list is refreshed.
    Parameters
    ----------
    parent : PlayerEditorApp
        The parent window; the shuffle window will be modal over this.
    model : PlayerDataModel
        The data model used to access players and memory addresses.
    """
    MAX_ROSTER_SIZE = 15
    def __init__(self, parent: "PlayerEditorApp", model: PlayerDataModel) -> None:
        super().__init__(parent)
        self.title("Team Shuffle")
        self.model = model
        self.team_vars: dict[str, tk.BooleanVar] = {}
        # Modal setup
        self.configure(bg="#F5F5F5")
        self.transient(parent)
        self.grab_set()
        # Build UI
        self._build_ui()
        # Center relative to parent
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
    def _build_ui(self) -> None:
        """Construct the UI for selecting teams and initiating the shuffle."""
        # Instruction label
        tk.Label(self, text="Select teams to shuffle players among them:", bg="#F5F5F5", font=("Segoe UI", 11)).pack(pady=(10, 5))
        # Scrollable list of teams
        frame = tk.Frame(self, bg="#F5F5F5")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        canvas = tk.Canvas(frame, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Fetch team names: prefer get_teams' ordering, otherwise use team_list directly
        team_names = []
        try:
            team_names = self.model.get_teams()
        except Exception:
            team_names = []
        if not team_names:
            team_names = [name for _, name in self.model.team_list]
        # Build checkboxes
        for idx, team_name in enumerate(team_names):
            var = tk.BooleanVar(value=False)
            self.team_vars[team_name] = var
            chk = tk.Checkbutton(scroll_frame, text=team_name, variable=var, bg="#F5F5F5")
            chk.grid(row=idx, column=0, sticky=tk.W, padx=10, pady=2)
        # Shuffle button
        btn = tk.Button(self, text="Shuffle Selected", command=self._shuffle_selected, bg="#52796F", fg="white", relief=tk.FLAT)
        btn.pack(pady=(0, 10))
        # Close button
        tk.Button(self, text="Close", command=self.destroy, bg="#B0413E", fg="white", relief=tk.FLAT).pack(pady=(0, 10))
    def _shuffle_selected(self) -> None:
        """
        Shuffle players across the selected teams.
        The updated shuffling logic first dumps all players from the
        selected teams into the Free Agents pool, then randomly
        assigns exactly 15 players back to each selected team.  Any
        leftover players remain in Free Agents.  The shuffle operates
        against live memory when pointer chains are available and
        otherwise mutates the sequential scan cache.
        """
        import tkinter.messagebox as mb
        import random as _random
        selected = [team for team, var in self.team_vars.items() if var.get()]
        if not selected:
            mb.showinfo("Shuffle Teams", "No teams selected.")
            return
        # Gather all players from the selected teams
        players_to_pool: list[Player] = []
        for team in selected:
            plist = self.model.get_players_by_team(team)
            if plist:
                players_to_pool.extend(plist)
        if not players_to_pool:
            mb.showinfo("Shuffle Teams", "No players to shuffle.")
            return
        name_to_idx = {name: idx for idx, name in self.model.team_list}
        free_agent_idx = name_to_idx.get("Free Agents", FREE_AGENT_TEAM_ID)
        # Determine whether we are in live memory mode.  Shuffling in
        # live memory writes directly to the game process; otherwise it
        # only updates the in-memory cache.
        live_mode = (
            not self.model.external_loaded
            and self.model.mem.hproc is not None
            and self.model.mem.base_addr is not None
        )
        total_assigned = 0
        if live_mode:
            # Resolve base pointers
            team_base = self.model._resolve_team_base_ptr()
            player_base = self.model._resolve_player_table_base()
            if team_base is None or player_base is None:
                mb.showerror("Shuffle Teams", "Failed to resolve team or player table pointers.")
                return
            # Find the Free Agents team pointer
            free_ptr = None
            for idx, name in self.model.team_list:
                if name and 'free' in name.lower():
                    free_ptr = team_base + idx * TEAM_RECORD_SIZE
                    break
            if free_ptr is None:
                mb.showerror("Shuffle Teams", "Free Agents team could not be located.")
                return
            # Build mapping of selected team name -> team pointer
            team_ptrs: dict[str, int] = {}
            for idx, name in self.model.team_list:
                if name in selected:
                    team_ptrs[name] = team_base + idx * TEAM_RECORD_SIZE
            # Dump all selected players to Free Agents
            for p in players_to_pool:
                try:
                    p_addr = player_base + p.index * PLAYER_STRIDE
                    self.model.mem.write_bytes(p_addr + OFF_TEAM_PTR, struct.pack('<Q', free_ptr))
                    p.team = "Free Agents"
                    p.team_id = free_agent_idx
                except Exception:
                    # Ignore write failures for individual players
                    pass
            # Shuffle the pooled players
            _random.shuffle(players_to_pool)
            pos = 0
            # Assign up to 15 players back to each selected team
            for team in selected:
                ptr = team_ptrs.get(team)
                if ptr is None:
                    continue
                for i in range(15):
                    if pos >= len(players_to_pool):
                        break
                    player = players_to_pool[pos]
                    pos += 1
                    try:
                        p_addr = player_base + player.index * PLAYER_STRIDE
                        self.model.mem.write_bytes(p_addr + OFF_TEAM_PTR, struct.pack('<Q', ptr))
                        player.team = team
                        player.team_id = name_to_idx.get(team, player.team_id)
                        total_assigned += 1
                    except Exception:
                        pass
            # Refresh the player list so the UI reflects new assignments
            try:
                self.model.refresh_players()
            except Exception:
                pass
        else:
            # Offline mode: update the player objects only
            # Dump all selected players to Free Agents
            for p in players_to_pool:
                p.team = "Free Agents"
                p.team_id = free_agent_idx
            # Shuffle the pool and assign 15 players back to each team
            _random.shuffle(players_to_pool)
            pos = 0
            for team in selected:
                for i in range(15):
                    if pos >= len(players_to_pool):
                        break
                    p = players_to_pool[pos]
                    pos += 1
                    p.team = team
                    p.team_id = name_to_idx.get(team, p.team_id)
                    total_assigned += 1
            # Rebuild the name index map after in-memory cache changes
            self.model._build_name_index_map()
        # Report summary
        mb.showinfo("Shuffle Teams", f"Shuffle complete. {total_assigned} players reassigned. Remaining players are Free Agents.")
# ---------------------------------------------------------------------
# Batch Edit window
# ---------------------------------------------------------------------
class BatchEditWindow(tk.Toplevel):
    """
    A modal window for applying a single value to a field across many players.
    Users select one or more teams, choose a category, select a field in
    that category and then specify a new value.  When the Apply button is
    clicked, the chosen value is written to the selected field for every
    player on the selected teams via PlayerDataModel.set_field_value.
    Only live memory editing is supported; if the game is not running or the
    player table cannot be resolved, no changes will be made.  The editor
    supports both numeric fields and enumerated fields (via combobox).
    Parameters
    ----------
    parent : PlayerEditorApp
        The parent window; the batch edit window will be modal over it.
    model : PlayerDataModel
        The data model used to access players, teams and field definitions.
    """
    def __init__(self, parent: "PlayerEditorApp", model: PlayerDataModel) -> None:
        super().__init__(parent)
        self.title("Batch Edit")
        self.model = model
        # Mapping of team name to selection variable
        self.team_vars: dict[str, tk.BooleanVar] = {}
        # Variables for selected category and field
        self.category_var = tk.StringVar()
        self.field_var = tk.StringVar()
        # The input widget and associated variable for the value
        self.value_widget: tk.Widget | None = None
        self.value_var: tk.Variable | None = None
        # Configure window appearance and modality
        self.configure(bg="#F5F5F5")
        self.transient(parent)
        self.grab_set()
        # Build the UI
        self._build_ui()
        # Center relative to parent
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
    def _build_ui(self) -> None:
        """Construct the user interface for selecting teams, category, field and value."""
        # Instruction label
        tk.Label(self, text="Select teams, choose a field and enter a value:", bg="#F5F5F5", font=("Segoe UI", 11)).pack(pady=(10, 5))
        # Selection frame for category and field
        sel_frame = tk.Frame(self, bg="#F5F5F5")
        sel_frame.pack(fill=tk.X, padx=10)
        tk.Label(sel_frame, text="Category:", bg="#F5F5F5").grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        categories = list(self.model.categories.keys())
        self.category_combo = ttk.Combobox(sel_frame, textvariable=self.category_var, state="readonly", values=categories)
        self.category_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        self.category_combo.bind("<<ComboboxSelected>>", self._on_category_selected)
        tk.Label(sel_frame, text="Field:", bg="#F5F5F5").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=2)
        self.field_combo = ttk.Combobox(sel_frame, textvariable=self.field_var, state="readonly", values=[])
        self.field_combo.grid(row=1, column=1, sticky=tk.W, pady=2)
        self.field_combo.bind("<<ComboboxSelected>>", self._on_field_selected)
        # Input frame for value widget
        self.input_frame = tk.Frame(self, bg="#F5F5F5")
        self.input_frame.pack(fill=tk.X, padx=10, pady=(5, 5))
        # Team selection area
        teams_frame = tk.Frame(self, bg="#F5F5F5")
        teams_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        canvas = tk.Canvas(teams_frame, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(teams_frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Populate team checkboxes
        try:
            team_names = self.model.get_teams()
        except Exception:
            team_names = []
        if not team_names:
            team_names = [name for _, name in self.model.team_list]
        for idx, name in enumerate(team_names):
            var = tk.BooleanVar(value=False)
            self.team_vars[name] = var
            chk = tk.Checkbutton(scroll_frame, text=name, variable=var, bg="#F5F5F5")
            chk.grid(row=idx, column=0, sticky=tk.W, padx=5, pady=2)
        # Buttons for apply and close
        btn_frame = tk.Frame(self, bg="#F5F5F5")
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        apply_btn = tk.Button(btn_frame, text="Apply", command=self._apply_changes, bg="#52796F", fg="white", relief=tk.FLAT)
        apply_btn.pack(side=tk.LEFT, padx=(0, 5))
        close_btn = tk.Button(btn_frame, text="Close", command=self.destroy, bg="#B0413E", fg="white", relief=tk.FLAT)
        close_btn.pack(side=tk.RIGHT)
    def _on_category_selected(self, event: tk.Event | None = None) -> None:
        """Update the field dropdown when a new category is selected."""
        category = self.category_var.get()
        self.field_var.set("")
        # Remove any existing input widget
        if self.value_widget is not None:
            self.value_widget.destroy()
            self.value_widget = None
            self.value_var = None
        # Populate field names for this category
        fields = self.model.categories.get(category, [])
        names = [f.get("name", "") for f in fields]
        self.field_combo.config(values=names)
        self.field_combo.set("")
    def _on_field_selected(self, event: tk.Event | None = None) -> None:
        """Create the appropriate input control for the selected field."""
        category = self.category_var.get()
        field_name = self.field_var.get()
        # Remove existing value widget
        if self.value_widget is not None:
            self.value_widget.destroy()
            self.value_widget = None
            self.value_var = None
        # Find field definition
        field_def = None
        for fd in self.model.categories.get(category, []):
            if fd.get("name") == field_name:
                field_def = fd
                break
        if not field_def:
            return
        values_list = field_def.get("values")
        length = int(field_def.get("length"))
        if values_list:
            # Enumerated field: use combobox
            self.value_var = tk.IntVar()
            disp_vals = list(values_list)
            combo = ttk.Combobox(self.input_frame, state="readonly", values=disp_vals, width=25)
            combo.pack(fill=tk.X, pady=(0, 5))
            self.value_widget = combo
            if disp_vals:
                combo.current(0)
        else:
            # Numeric field: use spinbox
            if category in ("Attributes", "Tendencies", "Durability"):
                min_val = 25
                max_val = 99
            else:
                min_val = 0
                max_val = (1 << length) - 1 if length else 255
            self.value_var = tk.IntVar(value=min_val)
            spin = tk.Spinbox(
                self.input_frame,
                from_=min_val,
                to=max_val,
                textvariable=self.value_var,
                width=10,
                increment=1,
                justify=tk.LEFT,
            )
            spin.pack(fill=tk.X, pady=(0, 5))
            self.value_widget = spin
    def _apply_changes(self) -> None:
        """Write the specified value to the selected field for all players on the selected teams."""
        import tkinter.messagebox as mb
        category = self.category_var.get()
        field_name = self.field_var.get()
        if not category or not field_name:
            mb.showinfo("Batch Edit", "Please select a category and field.")
            return
        # Collect selected teams
        selected_teams = [name for name, var in self.team_vars.items() if var.get()]
        if not selected_teams:
            mb.showinfo("Batch Edit", "Please select one or more teams.")
            return
        # Find the field definition
        field_def = None
        for fd in self.model.categories.get(category, []):
            if fd.get("name") == field_name:
                field_def = fd
                break
        if not field_def:
            mb.showerror("Batch Edit", "Field definition not found.")
            return
        # Parse offset and bit positions
        offset_val = _to_int(field_def.get("offset"))
        start_bit = _to_int(field_def.get("startBit", field_def.get("start_bit", 0)))
        length = _to_int(field_def.get("length", 0))
        requires_deref = bool(field_def.get("requiresDereference") or field_def.get("requires_deref"))
        deref_offset = _to_int(field_def.get("dereferenceAddress") or field_def.get("deref_offset"))
        if length <= 0:
            mb.showerror("Batch Edit", f"Invalid length for field '{field_name}'.")
            return
        values_list = field_def.get("values")
        # Determine value to write
        if values_list:
            # Enumerated: index corresponds to stored value
            combo = self.value_widget  # type: ignore
            if hasattr(combo, "current"):
                sel_idx = combo.current()
            else:
                sel_idx = 0
            if sel_idx < 0:
                mb.showinfo("Batch Edit", "Please select a value.")
                return
            value_to_write = sel_idx
            max_val = (1 << length) - 1 if length else len(values_list) - 1
            if value_to_write > max_val:
                value_to_write = max_val
        else:
            # Numeric value
            try:
                numeric_val = float(self.value_var.get()) if self.value_var else 0
            except Exception:
                numeric_val = 0
            if category in ("Attributes", "Durability"):
                value_to_write = convert_rating_to_raw(numeric_val, length)
            elif category == "Tendencies":
                value_to_write = convert_rating_to_tendency_raw(numeric_val, length)
            else:
                max_val = (1 << length) - 1 if length else 255
                value_to_write = int(max(0, min(max_val, numeric_val)))
        # Verify connection to the game
        if not self.model.mem.hproc or self.model.external_loaded:
            mb.showinfo("Batch Edit", "NBA 2K26 is not running or roster loaded from external files. Cannot apply changes.")
            return
        # Apply changes for each player on each selected team
        total_changed = 0
        for team_name in selected_teams:
            players = self.model.get_players_by_team(team_name)
            for player in players:
                success = self.model.set_field_value(
                    player.index,
                    offset_val,
                    start_bit,
                    length,
                    value_to_write,
                    requires_deref=requires_deref,
                    deref_offset=deref_offset,
                )
                if success:
                    total_changed += 1
        mb.showinfo("Batch Edit", f"Applied value to {total_changed} players.")
        # Refresh players to update the UI
        try:
            self.model.refresh_players()
        except Exception:
            pass
        # Close the window
        self.destroy()
# -----------------------------------------------------------------------------
# Category selection dialog for COY imports
#
# When invoking the COY import from the side bar, the user can choose which
# categories (Attributes, Tendencies, Durability, Potential) they wish to import.  This
# dialog presents a list of checkboxes and returns the selected categories
# when the user clicks OK.  If the dialog is cancelled or no categories are
# selected, ``selected`` is set to None.
class ImportSummaryDialog(tk.Toplevel):
    """Dialog displaying import results and providing quick player lookup."""
    MAX_SUGGESTIONS = 200
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        summary_text: str,
        missing_players: list[str],
        roster_names: list[str],
        apply_callback: Callable[[dict[str, str]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)
        self.configure(bg=PANEL_BG)
        self.apply_callback = apply_callback
        self.missing_players = list(missing_players)
        self.mapping: dict[str, str] = {}
        # Summary section
        summary_frame = tk.Frame(self, bg=PANEL_BG)
        summary_frame.pack(fill=tk.X, padx=16, pady=(16, 8))
        tk.Label(
            summary_frame,
            text="Import summary:",
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        summary_lines_count = summary_text.count("\n") + 1
        summary_box = tk.Text(
            summary_frame,
            height=max(3, min(12, summary_lines_count)),
            wrap="word",
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            relief=tk.FLAT,
            state="normal",
            padx=0,
            pady=0,
            highlightthickness=0,
        )
        summary_box.insert("1.0", summary_text)
        summary_box.config(state="disabled")
        summary_box.pack(fill=tk.X, pady=(4, 0))
        if missing_players:
            missing_frame = tk.LabelFrame(
                self,
                text="Players not found – type to search the current roster",
                bg=PANEL_BG,
                fg=TEXT_PRIMARY,
                labelanchor="n",
                padx=8,
                pady=8,
            )
            missing_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
            canvas = tk.Canvas(missing_frame, highlightthickness=0, bg=PANEL_BG)
            scrollbar = tk.Scrollbar(missing_frame, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            rows_frame = tk.Frame(canvas, bg=PANEL_BG)
            canvas.create_window((0, 0), window=rows_frame, anchor="nw")
            def _on_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))
            rows_frame.bind("<Configure>", _on_configure)
            header_fg = TEXT_PRIMARY
            tk.Label(
                rows_frame,
                text="Sheet Name",
                bg=PANEL_BG,
                fg=header_fg,
                font=("Segoe UI", 10, "bold"),
            ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 4))
            tk.Label(
                rows_frame,
                text="Search roster",
                bg=PANEL_BG,
                fg=header_fg,
                font=("Segoe UI", 10, "bold"),
            ).grid(row=0, column=1, sticky="w", pady=(0, 4))
            roster_sorted = sorted(set(roster_names), key=lambda n: n.lower())
            for idx, name in enumerate(missing_players, start=1):
                tk.Label(
                    rows_frame,
                    text=name,
                    bg=PANEL_BG,
                    fg=TEXT_PRIMARY,
                ).grid(row=idx, column=0, sticky="w", padx=(0, 10), pady=2)
                combo = SearchEntry(rows_frame, roster_sorted, width=32)
                combo.grid(row=idx, column=1, sticky="ew", pady=2)
                combo.set_match_callback(lambda value, source=name, self=self: self._set_mapping(source, value))
            rows_frame.columnconfigure(1, weight=1)
        btn_frame = tk.Frame(self, bg=PANEL_BG)
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 16))
        if missing_players and apply_callback:
            tk.Button(
                btn_frame,
                text="Apply Matches",
                command=self._on_apply,
                width=14,
                bg=ACCENT_BG,
                activebackground=BUTTON_ACTIVE_BG,
                fg=TEXT_PRIMARY,
            ).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(
            btn_frame,
            text="Close",
            command=self.destroy,
            width=12,
            bg=BUTTON_BG,
            activebackground=BUTTON_ACTIVE_BG,
            fg=BUTTON_TEXT,
        ).pack(side=tk.RIGHT)

    def _set_mapping(self, sheet_name: str, roster_value: str) -> None:
        value = roster_value.strip()
        if value:
            self.mapping[sheet_name] = value
        elif sheet_name in self.mapping:
            self.mapping.pop(sheet_name, None)

    def _on_apply(self) -> None:
        if self.apply_callback:
            self.apply_callback(dict(self.mapping))
        self.destroy()

class SearchEntry(ttk.Entry):
    """Entry with dropdown suggestion list that stays open while typing."""
    def __init__(self, parent: tk.Misc, values: list[str], width: int = 30):
        self._all_values = values
        self._popup = None
        self._listbox = None
        super().__init__(parent, width=width)
        self._match_callback: Callable[[str], None] | None = None
        self.bind("<KeyRelease>", self._on_keyrelease, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Down>", self._move_focus_to_list, add="+")
        self.bind("<Return>", self._commit_current, add="+")

    def set_match_callback(self, callback: Callable[[str], None]) -> None:
        self._match_callback = callback

    def _move_focus_to_list(self, event=None) -> None:
        if self._listbox:
            self._listbox.focus_set()
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(0)
            self._listbox.activate(0)

    def _commit_current(self, event=None) -> None:
        value = self.get().strip()
        if self._listbox and self._listbox.curselection():
            value = self._listbox.get(self._listbox.curselection()[0])
            self.delete(0, tk.END)
            self.insert(0, value)
        if self._match_callback:
            self._match_callback(value)
        self._hide_popup()

    def _on_keyrelease(self, event) -> None:
        if event.keysym in ("Return", "Escape", "Tab"):
            return
        term = self.get().strip().lower()
        if not term:
            filtered = self._all_values[:ImportSummaryDialog.MAX_SUGGESTIONS]
        else:
            filtered = [v for v in self._all_values if term in v.lower()]
            filtered = filtered[:ImportSummaryDialog.MAX_SUGGESTIONS]
        if not filtered:
            self._hide_popup()
            return
        self._show_popup(filtered)

    def _on_focus_out(self, event) -> None:
        widget = event.widget
        if self._popup and widget not in (self, self._listbox):
            self.after(100, self._hide_popup)

    def _show_popup(self, values: list[str]) -> None:
        if self._popup and not self._popup.winfo_exists():
            self._popup = None
        if not self._popup:
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            self._popup.configure(bg="#2C3E50")
            self._listbox = tk.Listbox(
                self._popup,
                selectmode=tk.SINGLE,
                activestyle="dotbox",
                bg="#2C3E50",
                fg="#ECF0F1",
                highlightthickness=0,
                relief=tk.FLAT,
            )
            self._listbox.pack(fill=tk.BOTH, expand=True)
            self._listbox.bind("<ButtonRelease-1>", self._on_list_click, add="+")
            self._listbox.bind("<Return>", self._commit_current, add="+")
            self._listbox.bind("<Escape>", lambda _e: self._hide_popup(), add="+")
        assert self._popup and self._listbox
        self._listbox.delete(0, tk.END)
        for item in values:
            self._listbox.insert(tk.END, item)
        self._popup.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        width = max(self.winfo_width(), 240)
        height = min(200, self._popup.winfo_reqheight())
        self._popup.geometry(f"{width}x{height}+{x}+{y}")
        self._popup.deiconify()

    def _on_list_click(self, _event) -> None:
        if self._listbox and self._listbox.curselection():
            value = self._listbox.get(self._listbox.curselection()[0])
            self.delete(0, tk.END)
            self.insert(0, value)
            if self._match_callback:
                self._match_callback(value)
        self._hide_popup()

    def _hide_popup(self) -> None:
        if self._popup:
            self._popup.destroy()
            self._popup = None
            self._listbox = None

class CategorySelectionDialog(tk.Toplevel):
    """
    Simple modal dialog that allows the user to select one or more categories
    for the COY import.  Categories are presented as checkboxes.  The
    selected categories are stored in the ``selected`` attribute after
    ``OK`` is pressed; if cancelled, ``selected`` is ``None``.
    """
    def __init__(self, parent: tk.Misc, categories: list[str]) -> None:
        super().__init__(parent)
        self.title("Select categories to import")
        self.resizable(False, False)
        # Ensure the dialog appears above its parent
        self.transient(parent)
        self.grab_set()
        # Internal storage for selected categories; None until closed
        self.selected: list[str] | None = []
        # Create a label
        tk.Label(self, text="Import the following categories:").pack(padx=10, pady=(10, 5))
        # Create a frame to hold the checkboxes
        frame = tk.Frame(self)
        frame.pack(padx=10, pady=5)
        # Dictionary mapping category names to BooleanVars
        self.var_map: dict[str, tk.BooleanVar] = {}
        for cat in categories:
            var = tk.BooleanVar(value=True)
            chk = tk.Checkbutton(frame, text=cat, variable=var)
            chk.pack(anchor=tk.W)
            self.var_map[cat] = var
        # OK and Cancel buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(5, 10))
        tk.Button(btn_frame, text="OK", width=10, command=self._on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", width=10, command=self._on_cancel).pack(side=tk.LEFT, padx=5)
    def _on_ok(self) -> None:
        """Gather selected categories and close the dialog."""
        selected: list[str] = []
        for cat, var in self.var_map.items():
            try:
                if var.get():
                    selected.append(cat)
            except Exception:
                pass
        # If no categories selected, set None to indicate cancel
        if not selected:
            self.selected = None
        else:
            self.selected = selected
        self.destroy()
    def _on_cancel(self) -> None:
        """Cancel the dialog without selecting any categories."""
        self.selected = None
        self.destroy()
def main() -> None:
    # Only run on Windows; bail early otherwise
    if sys.platform != "win32":
        messagebox.showerror("Unsupported platform", "This application can only run on Windows.")
        return
    try:
        initialize_offsets(force=True)
    except OffsetSchemaError as exc:
        messagebox.showerror("Offset schema error", str(exc))
        return
    if _offset_file_path:
        print(f"Loaded 2K26 offsets from {_offset_file_path.name}")
    else:
        print("Loaded 2K26 offsets from defaults")
    mem = GameMemory(MODULE_NAME)
    model = PlayerDataModel(mem, max_players=MAX_PLAYERS)
    app = PlayerEditorApp(model)
    app.mainloop()
if __name__ == '__main__':
    main()
