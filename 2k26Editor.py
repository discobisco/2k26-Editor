"""
2K26 Offline Player Patcher GUI
--------------------------------
This script implements a simple offline editor for NBA 2K26 player data.  It
leverages Windows API calls via `ctypes` to locate the running game,
enumerate player records in memory and edit all fields off of
an offset json.
**Disclaimer**: This tool is intended for offline use only.  EAC will kick you from game
if ran together!
Example usage:
```cmd
python 2k25_player_patcher_gui.py
```
You will be presented with a window containing a side bar with “Home” and
“Players” options.  The Home page displays whether NBA 2K26 is currently
running and the application version.  The Players page scans for players
in memory (or loads them from files if the game is not running), groups
them by team and allows editing of names and core attributes.  A full editor
window with placeholder tabs is available for future extensions.
"""
import os
import sys
import threading
import struct
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict
import random
import tempfile
import urllib.request
import urllib.parse
import io
import json
from pathlib import Path
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
PLAYER_TABLE_RVA = 0
PLAYER_STRIDE = 0
PLAYER_PTR_CHAINS: list[dict[str, object]] = []
OFF_LAST_NAME = 0
OFF_FIRST_NAME = 0
OFF_TEAM_PTR = 0
OFF_TEAM_NAME = 0
MAX_PLAYERS = 6000
NAME_MAX_CHARS = 20
APP_VERSION = "v2K26.0.1"
TEAM_STRIDE = 0
TEAM_NAME_OFFSET = 0
TEAM_NAME_LENGTH = 0
TEAM_PLAYER_SLOT_COUNT = 30
MAX_TEAMS_SCAN = 200
TEAM_PTR_CHAINS: list[dict[str, object]] = []
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
import struct

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
    global TEAM_STRIDE, TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_PLAYER_SLOT_COUNT
    global TEAM_PTR_CHAINS, TEAM_RECORD_SIZE, TEAM_FIELD_DEFS
    if not data:
        print("Warning: no 2K26 offset configuration found.")
        return
    offsets = data.get("offsets")
    if isinstance(offsets, list):
        _build_offset_index(offsets)
    else:
        _offset_index.clear()
    game_info = data.get("game_info") or {}
    if game_info.get("executable"):
        MODULE_NAME = str(game_info["executable"])
    if "playerSize" in game_info:
        PLAYER_STRIDE = _to_int(game_info["playerSize"])
    if "teamSize" in game_info:
        TEAM_STRIDE = _to_int(game_info["teamSize"])
        TEAM_RECORD_SIZE = TEAM_STRIDE
    base_pointers = data.get("base_pointers") or {}
    PLAYER_PTR_CHAINS.clear()
    player_base = base_pointers.get("Player")
    if isinstance(player_base, dict):
        addr = _to_int(player_base.get("address") or player_base.get("rva") or player_base.get("base"))
        if addr:
            PLAYER_TABLE_RVA = addr
        PLAYER_PTR_CHAINS.extend(_parse_pointer_chain_config(player_base))
    TEAM_PTR_CHAINS.clear()
    team_base = base_pointers.get("Team")
    if isinstance(team_base, dict):
        TEAM_PTR_CHAINS.extend(_parse_pointer_chain_config(team_base))
    first_entry = _find_offset_entry("First Name", "Vitals")
    if first_entry:
        OFF_FIRST_NAME = _to_int(first_entry.get("address"))
        length_val = _to_int(first_entry.get("length"))
        if str(first_entry.get("type", "")).lower() == "wstring":
            NAME_MAX_CHARS = max(1, (length_val // 2) or NAME_MAX_CHARS)
        elif length_val:
            NAME_MAX_CHARS = length_val
    last_entry = _find_offset_entry("Last Name", "Vitals")
    if last_entry:
        OFF_LAST_NAME = _to_int(last_entry.get("address"))
    team_entry = _find_offset_entry("Current Team", "Vitals")
    if team_entry:
        OFF_TEAM_PTR = _to_int(team_entry.get("dereferenceAddress"))
    elif OFF_TEAM_PTR == 0:
        print("Warning: Team pointer offset not provided in 2K26_Offsets.json.")
    team_name_entry = _find_offset_entry("Team Name", "Teams")
    if team_name_entry:
        TEAM_NAME_OFFSET = _to_int(team_name_entry.get("address"))
        TEAM_NAME_LENGTH = _to_int(team_name_entry.get("length")) or TEAM_NAME_LENGTH
        OFF_TEAM_NAME = TEAM_NAME_OFFSET
    if TEAM_NAME_LENGTH <= 0:
        TEAM_NAME_LENGTH = 24
    team_player_entries = [
        entry for (cat, _), entry in _offset_index.items() if cat == "team players"
    ]
    if team_player_entries:
        TEAM_PLAYER_SLOT_COUNT = max(TEAM_PLAYER_SLOT_COUNT, len(team_player_entries))
    TEAM_FIELD_DEFS.clear()
    for label, entry_name in TEAM_FIELD_SPECS:
        entry = _find_offset_entry(entry_name, "Teams")
        if not entry:
            continue
        offset = _to_int(entry.get("address"))
        length_val = _to_int(entry.get("length", 0))
        entry_type = str(entry.get("type", "")).lower()
        if not offset or not length_val:
            continue
        if entry_type not in ("wstring", "string", "text"):
            continue
        TEAM_FIELD_DEFS[label] = (offset, length_val)
    if TEAM_STRIDE:
        TEAM_RECORD_SIZE = TEAM_STRIDE
def initialize_offsets(force: bool = False) -> bool:
    """Ensure offset data is loaded; returns True on success."""
    global _offset_file_path, _offset_config
    if _offset_config is not None and not force:
        return True
    path, data = _load_offset_config_file()
    _offset_file_path = path
    _offset_config = data
    _apply_offset_config(data)
    return data is not None
# -----------------------------------------------------------------------------
# Team metadata (loaded from offsets)
# -----------------------------------------------------------------------------
TEAM_FIELD_SPECS: tuple[tuple[str, str], ...] = (
    ("Team Name", "Team Name"),
    ("City Name", "City Name"),
    ("City Abbrev", "City Abbrev"),
)
TEAM_FIELD_DEFS: dict[str, tuple[int, int]] = {}
TEAM_RECORD_SIZE = TEAM_STRIDE
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
# -----------------------------------------------------------------------------
# Import table definitions
#
# The application supports importing player data from tab- or comma-delimited
# text files.  To align the UI with commonly used spreadsheets, we define
# canonical field orders for three tables: Attributes, Tendencies and
# Durability.  These lists specify the order in which fields should appear
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
    if _offset_config is None:
        initialize_offsets()
    if _offset_config and isinstance(_offset_config.get("offsets"), list):
        categories: dict[str, list[dict]] = {}
        for entry in _offset_config["offsets"]:
            if not isinstance(entry, dict):
                continue
            cat_name = str(entry.get("category", "Misc")).strip() or "Misc"
            field_name = str(entry.get("name", "")).strip()
            if not field_name:
                continue
            offset_val = _to_int(entry.get("address"))
            start_bit = _to_int(entry.get("startBit"))
            length_val = _to_int(entry.get("length"))
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
            categories.setdefault(cat_name, []).append(field)
        return categories
    base_dir = _pathlib.Path(__file__).resolve().parent
    # Try unified offsets files first
    for fname in UNIFIED_FILES:
        upath = base_dir / fname
        if not upath.is_file():
            continue
        try:
            with open(upath, "r", encoding="utf-8") as f:
                udata = _json.load(f)
            categories: dict[str, list[dict]] = {}
            # Extract category lists from JSON (ignore "Base")
            if isinstance(udata, dict):
                # Case 1: unified format where categories are top‑level lists of field definitions
                for key, value in udata.items():
                    if key.lower() == "base":
                        continue
                    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
                        categories[key] = value
                # If categories were found in unified format return them immediately
                if categories:
                    return categories
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
                    for cat_key, field_map in pinf.items():
                        if not isinstance(field_map, dict):
                            continue
                        # Derive a user‑friendly category name
                        cat_name = cat_key
                        if cat_name.endswith("_offsets"):
                            cat_name = cat_name[:-8]
                        # Normalise case (e.g. VITALS -> Vitals)
                        cat_name = cat_name.title()
                        entries: list[dict] = []
                        for fname, fdef in field_map.items():
                            if not isinstance(fdef, dict):
                                continue
                            off_str = fdef.get("offset_from_base") or fdef.get("offset")
                            if not off_str:
                                continue
                            try:
                                off_int = int(str(off_str), 16)
                            except Exception:
                                continue
                            # Determine bit length based on the field type.
                            f_type = str(fdef.get("type", "")).lower()
                            size_val = fdef.get("size", 1)
                            try:
                                size_int = int(size_val)
                            except Exception:
                                size_int = 1
                            # Numeric/slider fields occupy whole bytes; others use bit count directly
                            if f_type in ("number", "slider"):
                                bit_length = size_int * 8
                            else:
                                bit_length = size_int
                            entry: dict[str, object] = {
                                "name": fname,
                                "offset": hex(off_int),
                                "startBit": 0,
                                "length": bit_length,
                            }
                            # Provide a simple enumeration for combo fields
                            if f_type == "combo":
                                try:
                                    max_val = 2 ** bit_length
                                    entry["values"] = [str(i) for i in range(max_val)]
                                except Exception:
                                    pass
                            try:
                                dcat = dropdowns.get(cat_name) or dropdowns.get(cat_name.title()) or {}
                                if fname in dcat and isinstance(dcat[fname], list):
                                    entry.setdefault("values", list(dcat[fname]))
                                elif fname.upper().startswith("PLAYTYPE") and isinstance(dcat.get("PLAYTYPE"), list):
                                    entry.setdefault("values", list(dcat["PLAYTYPE"]))
                            except Exception:
                                pass
                            entries.append(entry)
                        if entries:
                            new_cats[cat_name] = entries
                    if new_cats:
                        return new_cats
        except Exception:
            # ignore errors and continue to next file
            pass
    # Nothing found
    return {}
###############################################################################
# Windows API declarations
#
# Only a subset of the Win32 API is required: enumerating processes and
# modules, opening a process, and reading/writing its memory.  These
# declarations mirror those used in the earlier patcher example.  They are
# defined only on Windows; on other platforms the memory access functions
# will remain unused and the tool will operate purely on offline data.
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
    # -------------------------------------------------------------------------
    # Process management
    # -------------------------------------------------------------------------
    def find_pid(self) -> int | None:
        """Return the PID of the target process, or None if not found."""
        # Use psutil when available for convenience
        try:
            import psutil  # type: ignore
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and proc.info['name'].lower() == self.module_name.lower():
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
                if entry.szExeFile.lower() == self.module_name.lower():
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
    def _check_open(self):
        if self.hproc is None or self.base_addr is None:
            raise RuntimeError("Game process not opened")
    def read_bytes(self, addr: int, length: int) -> bytes:
        """Read ``length`` bytes from absolute address ``addr``."""
        self._check_open()
        buf = (ctypes.c_ubyte * length)()
        read_count = ctypes.c_size_t()
        ok = ReadProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(read_count))
        if not ok or read_count.value != length:
            raise RuntimeError(f"Failed to read memory at 0x{addr:X}")
        return bytes(buf)
    def write_bytes(self, addr: int, data: bytes) -> None:
        """Write ``data`` to absolute address ``addr``."""
        self._check_open()
        length = len(data)
        buf = (ctypes.c_ubyte * length).from_buffer_copy(data)
        written = ctypes.c_size_t()
        ok = WriteProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, length, ctypes.byref(written))
        if not ok or written.value != length:
            raise RuntimeError(f"Failed to write memory at 0x{addr:X}")
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
    def __init__(self, index: int, first_name: str, last_name: str, team: str):
        self.index = index
        self.first_name = first_name
        self.last_name = last_name
        self.team = team
    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else f"Player {self.index}"
    def __repr__(self) -> str:
        return f"<Player index={self.index} name='{self.full_name}' team='{self.team}'>"
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
        self.external_loaded = False  # indicates if offline data was loaded from files
        # Optional mapping of team indices to names derived from CE table comments
        self.team_name_map: Dict[int, str] = {}
        # Current list of available teams represented as (index, name) tuples.
        # This will be populated by scanning memory or via offline files.
        self.team_list: list[tuple[int, str]] = []
        # Flag indicating that ``self.players`` was populated by scanning all
        # player records rather than via per‑team scanning.  When true,
        # ``get_players_by_team`` will filter ``self.players`` by team name
        # instead of using roster pointers.
        self.fallback_players: bool = False
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
        # the comments section to build a team index→name mapping.  This
        # mapping can be useful for offline lookups or when scanning memory.
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
    # -------------------------------------------------------------------------
    # Offline data loading
    # -------------------------------------------------------------------------
    def _load_external_roster(self) -> list[Player] | None:
        """Attempt to load players and teams from uploaded text files.
        This method tries to populate the player list and team names from
        the text files distributed with the Cheat Engine tables.  It looks
        for files named ``"2K26 Team Data (10.18.24).txt"`` (or
        ``"2K26 Team Data.txt"``) and ``"2K26 Player Data (10.18.24).txt"`` (or
        ``"2K26 Player Data.txt"``) in the same directory as this script.  If
        both files exist, it will attempt to extract team names from the
        <Comments> section of the team table and player names from the
        trailing mapping appended to the player table.  In the absence of
        these files or if parsing fails, ``None`` is returned so that the
        caller can fall back to the built‑in demo roster.
        The player data files distributed with Cheat Engine are not
        conventional CSVs; instead they consist of an XML cheat table
        followed by a list of lines like ``"4425:Stanley Johnson"`` or
        ``"0 - Maxey"`` that map an index to a player name.  We parse these
        lines by splitting on ':' or '-' and interpreting the index as
        either decimal or hexadecimal (when letters A–F are present).  The
        team ID column is unavailable in this mapping, so all players are
        assigned to a generic team called "Free Agents" unless a team
        mapping can be inferred from the team table.
        """
        # Candidate filenames for team and player data; allow shorter names
        team_file_candidates = [
            "2K26 Team Data (10.18.24).txt",
            "2K26 Team Data.txt",
        ]
        player_file_candidates = [
            "2K26 Player Data (10.18.24).txt",
            "2K26 Player Data.txt",
        ]
        # Determine base directory (where this script resides)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Locate the first existing team file
        team_file: str | None = None
        for name in team_file_candidates:
            path = os.path.join(base_dir, name)
            if os.path.isfile(path):
                team_file = path
                break
        # Locate the first existing player file
        player_file: str | None = None
        for name in player_file_candidates:
            path = os.path.join(base_dir, name)
            if os.path.isfile(path):
                player_file = path
                break
        # If either file is missing, bail out
        if not team_file or not player_file:
            return None
        # ------------------------------------------------------------------
        # Parse team names
        # ------------------------------------------------------------------
        team_lookup: dict[str, str] = {}
        # First, attempt to parse team names from the <Comments> section
        ce_map = self.parse_team_comments(team_file)
        for idx, name in ce_map.items():
            team_lookup[str(idx)] = name
        # If no entries were found, also try reading simple delimiter lines
        if not team_lookup:
            try:
                with open(team_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        s = line.strip()
                        if not s or s.startswith("#"):
                            continue
                        # Try splitting on common delimiters
                        for delim in ('\t', '|', ';', ',', ':', ' - '):
                            if delim in s:
                                parts = [p.strip() for p in s.split(delim)]
                                if len(parts) >= 2:
                                    team_id, team_name = parts[0], parts[1]
                                    if team_id:
                                        team_lookup[team_id] = team_name
                                    break
            except Exception:
                pass
        # ------------------------------------------------------------------
        # Parse player names
        # ------------------------------------------------------------------
        players: list[Player] = []
        try:
            with open(player_file, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except Exception:
            return None
        # Scan the entire file for simple mapping lines of the form "index - name"
        # or "index:name".  Ignore any lines containing angle brackets (< or >)
        # which denote XML tags.  This captures player mappings regardless of
        # their location in the file.
        index_counter = 0
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            # Skip XML tags and other markup lines
            if '<' in s or '>' in s:
                continue
            # Identify separator: try ':' then ' - ' then '-' (without spaces)
            sep = None
            if ':' in s:
                sep = ':'
            elif ' - ' in s:
                sep = ' - '
            elif '-' in s:
                sep = '-'
            if sep:
                left, right = s.split(sep, 1)
            else:
                # Could be just a name with no index
                left, right = '', s
            idx_str = left.strip()
            name = right.strip()
            if not name:
                continue
            # Determine numeric index; treat empty as auto
            try:
                # If contains letters A–F, treat as hex
                base = 16 if any(c in idx_str.upper() for c in "ABCDEF") else 10
                idx = int(idx_str, base) if idx_str else index_counter
            except Exception:
                idx = index_counter
            index_counter += 1
            # Split full name into first and last names (take first token as first name)
            parts = name.split()
            if not parts:
                continue
            first = parts[0]
            last = " ".join(parts[1:]) if len(parts) > 1 else ""
            # Assign all offline players to the Free Agents team because
            # the CE tables do not include a reliable team ID mapping.
            team_name = "Free Agents"
            players.append(Player(idx, first, last, team_name))
        # Ensure we loaded a reasonable number of players; if not, abort
        return players if players else None
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
            first = player.first_name.strip().lower()
            last = player.last_name.strip().lower()
            if not first and not last:
                continue
            key = f"{first} {last}".strip()
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
        # Apply known header synonyms; map abbreviations to canonical
        # attribute names.  Only a subset of synonyms is defined here; any
        # unknown name will fall back to its normalized form.
        header_synonyms = {
            "LAYUP": "DRIVINGLAYUP",
            "STDUNK": "STANDINGDUNK",
            "DUNK": "DRIVINGDUNK",
            "CLOSE": "CLOSESHOT",
            "MID": "MIDRANGESHOT",
            "3PT": "3PTSHOT",
            "FT": "FREETHROW",
            "PHOOK": "POSTHOOK",
            "PFADE": "POSTFADE",
            "POSTC": "POSTMOVES",
            "FOUL": "DRAWFOUL",
            "BALL": "BALLCONTROL",
            "SPDBALL": "SPEEDWITHBALL",
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
            "HSTL": "HUSTLE",
            "DUR": "MISCELLANEOUSDURABILITY",
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
            "TSPLAYUP": "STANDINGLAYUPTENDENCY",
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
        return norm
    def _normalize_field_name(self, name: str) -> str:
        """
        Normalize a field name from the offset map for matching.
        This helper performs uppercase conversion and removal of
        non‑alphanumeric characters.  No synonyms are applied here since
        the field names are already descriptive.
        """
        import re as _re
        return _re.sub(r'[^A-Za-z0-9]', '', str(name).upper())
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
        # ------------------------------------------------------------------
        # Extract durability fields from Attributes
        if 'Attributes' in cats:
            attr_fields = cats.get('Attributes', [])
            new_attr = []
            dura_fields = cats.get('Durability', [])  # if already exists
            for fld in attr_fields:
                name = fld.get('name', '')
                norm = self._normalize_field_name(name)
                if 'DURABILITY' in norm:
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
                match_idx = -1
                # Find the first field whose normalized name matches or
                # contains the normalized header name.
                for i, f in enumerate(remaining):
                    norm_field = self._normalize_field_name(f.get('name', ''))
                    # Exact or partial match
                    if norm_hdr == norm_field or norm_hdr in norm_field or norm_field in norm_hdr:
                        match_idx = i
                        break
                if match_idx >= 0:
                    reordered.append(remaining.pop(match_idx))
            # Append any unmatched fields at the end
            reordered.extend(remaining)
            cats[cat_name] = reordered
        # Reorder attributes, tendencies, durability
        reorder('Attributes', ATTR_IMPORT_ORDER)
        reorder('Tendencies', TEND_IMPORT_ORDER)
        reorder('Durability', DUR_IMPORT_ORDER)
        # Save back in a deterministic order.  We prefer to display
        # categories in a consistent order matching the import tables.
        ordered = {}
        preferred = [
            'Body',
            'Vitals',
            'Attributes',
            'Durability',
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
        key = f"{first.lower()} {last.lower()}".strip()
        if self.name_index_map:
            return self.name_index_map.get(key, [])
        # Fallback: linear scan over players
        indices: list[int] = []
        for p in self.players:
            if p.first_name.lower() == first.lower() and p.last_name.lower() == last.lower():
                indices.append(p.index)
        return indices
    def import_table(self, category_name: str, filepath: str) -> int:
        """
        Import player data from a tab- or comma-delimited file for a single category.
        The file must have a header row where the first column is the player
        name and the subsequent columns correspond to fields of the given
        category.  The order of columns defines the order in which values
        should be applied.  Column headers are matched to field names using
        normalized strings and simple substring matching.  Values are
        converted to raw bitfield values as required.
        Args:
            category_name: Name of the category to import (e.g. "Attributes",
                "Tendencies", "Durability").
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
        header = rows[0]
        if not header or len(header) < 2:
            return 0
        # Build mapping list: for each column after the first, find the field
        # definition in the category.  For Attributes, we use fuzzy name
        # matching; for Tendencies and Durability we rely on column order
        # matching after the fields have been reordered according to the
        # import order lists.  This ensures that abbreviated headers like
        # "T/SCLOSE" map to their corresponding fields (e.g. Shot Close) even
        # without explicit synonyms.
        field_defs = self.categories[category_name]
        mappings: list[dict | None] = []
        # Build normalized field names list once for matching
        norm_fields: list[tuple[str, dict]] = []
        for f in field_defs:
            n = self._normalize_field_name(f.get('name', ''))
            norm_fields.append((n, f))
        # For each column header (skipping player name) attempt to match by name
        for i, col in enumerate(header[1:]):
            n_hdr = self._normalize_header_name(col)
            matched: dict | None = None
            # First attempt fuzzy match: exact or substring in either direction
            for norm_field, f in norm_fields:
                if n_hdr == norm_field or n_hdr in norm_field or norm_field in n_hdr:
                    matched = f
                    break
            if matched is None:
                # Fallback: map by position if within range
                if i < len(field_defs):
                    matched = field_defs[i]
            mappings.append(matched)
        # Process each row
        players_updated = 0
        for row in rows[1:]:
            if not row or len(row) < 2:
                continue
            name = row[0].strip()
            values = row[1:]
            idxs = self.find_player_indices_by_name(name)
            if not idxs:
                continue
            # Apply values to each matching player
            for idx in idxs:
                any_set = False
                for val, meta in zip(values, mappings):
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
                    if category_name in ('Attributes', 'Durability'):
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
        return players_updated
    def import_all(self, file_map: dict[str, str]) -> dict[str, int]:
        """
        Import multiple tables from a mapping of category names to file paths.
        Args:
            file_map: A mapping of category names ("Attributes", "Tendencies",
                "Durability") to file paths.  If a file path is an empty
                string or does not exist, that category will be skipped.
        Returns:
            A dictionary mapping category names to the number of players
            updated for each category.
        """
        results: dict[str, int] = {}
        for cat, path in file_map.items():
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
                ln = self.mem.read_wstring(table_base + OFF_LAST_NAME, NAME_MAX_CHARS).strip()
                fn = self.mem.read_wstring(table_base + OFF_FIRST_NAME, NAME_MAX_CHARS).strip()
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
                name = self.mem.read_wstring(team_base + TEAM_NAME_OFFSET, TEAM_NAME_LENGTH).strip()
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
                name = self.mem.read_wstring(rec_addr + TEAM_NAME_OFFSET, TEAM_NAME_LENGTH).strip()
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
                last_name = self.mem.read_wstring(ptr + OFF_LAST_NAME, NAME_MAX_CHARS).strip()
                first_name = self.mem.read_wstring(ptr + OFF_FIRST_NAME, NAME_MAX_CHARS).strip()
            except Exception:
                # Skip this player if any field cannot be read
                continue
            if not first_name and not last_name:
                continue
            team_name = self.team_list[team_idx][1] if (team_idx < len(self.team_list)) else "Unknown"
            players.append(Player(idx if idx >= 0 else len(players), first_name, last_name, team_name))
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
        for label, (offset, max_chars) in TEAM_FIELD_DEFS.items():
            try:
                val = self.mem.read_wstring(rec_addr + offset, max_chars).rstrip("\x00")
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
        for label, (offset, max_chars) in TEAM_FIELD_DEFS.items():
            if label not in values:
                continue
            val = values[label]
            try:
                self.mem.write_wstring_fixed(rec_addr + offset, val, max_chars)
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
        players: list[Player] = []
        for i in range(max_scan):
            # Compute address of the i‑th player record
            p_addr = table_base + i * PLAYER_STRIDE
            try:
                # Read essential fields; skip this record on failure
                last_name = self.mem.read_wstring(p_addr + OFF_LAST_NAME, NAME_MAX_CHARS).strip()
                first_name = self.mem.read_wstring(p_addr + OFF_FIRST_NAME, NAME_MAX_CHARS).strip()
            except Exception:
                # Skip invalid or unreadable records instead of aborting the scan
                continue
            # Attempt to resolve the team name; default to Unknown on failure
            team_name = "Unknown"
            try:
                team_ptr = self.mem.read_uint64(p_addr + OFF_TEAM_PTR)
                if team_ptr == 0:
                    team_name = "Free Agents"
                else:
                    tn = self.mem.read_wstring(team_ptr + OFF_TEAM_NAME, 32).strip()
                    team_name = tn or "Unknown"
            except Exception:
                pass
            # Skip completely blank name records
            if not first_name and not last_name:
                continue
            players.append(Player(i, first_name, last_name, team_name))
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
        """Populate team and player information.
        This method is the heart of the scanning logic.  It attempts to
        connect to the running game, resolve the player and team base
        pointers and extract team and roster information.  If the
        process cannot be opened or no valid pointers are found, the
        method falls back to scanning all player records sequentially.
        As a last resort it will load an offline roster from the CE
        table files (if present).  The results populate
        ``self.team_list`` and ``self.players`` and set flags
        ``fallback_players`` and ``external_loaded`` appropriately.
        """
        # Reset all state
        self.team_list = []
        self.players = []
        self.fallback_players = False
        self.external_loaded = False
        self._resolved_player_base = None
        self._resolved_team_base = None

        if self.mem.open_process():
            team_base = self._resolve_team_base_ptr()
            if team_base is not None:
                teams = self._scan_team_names()
                if teams:
                    players_all = self._scan_all_players(self.max_players)
                    if players_all:
                        unique_names = sorted({p.team for p in players_all})
                        def _team_sort_key(name: str) -> tuple[int, str]:
                            return (1 if name.strip().lower().startswith("team ") else 0, name)
                        ordered_names = sorted(unique_names, key=_team_sort_key)
                        self.team_list = [(i, name) for i, name in enumerate(ordered_names)]
                        self.players = players_all
                        self.fallback_players = True
                        self._build_name_index_map()
                        return
                    def _team_sort_key_pair(item: tuple[int, str]) -> tuple[int, str]:
                        idx, name = item
                        return (1 if name.strip().lower().startswith("team ") else 0, name)
                    ordered_teams = sorted(teams, key=_team_sort_key_pair)
                    self.team_list = ordered_teams
                    return
            players = self._scan_all_players(self.max_players)
            if players:
                unique_names = sorted({p.team for p in players})
                def _team_sort_key(name: str) -> tuple[int, str]:
                    return (1 if name.strip().lower().startswith("team ") else 0, name)
                ordered_names = sorted(unique_names, key=_team_sort_key)
                self.team_list = [(i, name) for i, name in enumerate(ordered_names)]
                self.players = players
                self.fallback_players = True
                self._build_name_index_map()
                return

        external_players = self._load_external_roster()
        if external_players:
            self.players = external_players
            unique_names = sorted({p.team for p in external_players})
            def _team_sort_key(name: str) -> tuple[int, str]:
                return (1 if name.strip().lower().startswith("team ") else 0, name)
            ordered_names = sorted(unique_names, key=_team_sort_key)
            self.team_list = [(i, name) for i, name in enumerate(ordered_names)]
            self.external_loaded = True
            self._build_name_index_map()
            return

        self.players = []
        self.team_list = []
        self.external_loaded = False
        self.fallback_players = False

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
          4. All‑Time teams (names containing "All Time" or "All‑Time")
          5. G‑League teams (names containing "G League", "G-League" or "GLeague")
        Within each category the original order is preserved.  In
        offline mode (when players are loaded from files and no
        ``team_list`` exists), the same grouping logic is applied
        against the distinct set of team names found in ``self.players``.
        """
        if self.team_list:
            names = [name for _, name in self.team_list]
            # Lowercase copies for testing membership
            lower_names = [n.lower() for n in names]
            free = [names[i] for i, ln in enumerate(lower_names) if 'free' in ln]
            draft = [names[i] for i, ln in enumerate(lower_names) if 'draft' in ln]
            all_time = [names[i] for i, ln in enumerate(lower_names) if 'all time' in ln or 'all-time' in ln]
            g_league = [names[i] for i, ln in enumerate(lower_names) if 'gleague' in ln or 'g league' in ln or 'g-league' in ln]
            assigned = set(free + draft + all_time + g_league)
            base = [n for n in names if n not in assigned]
            return free + draft + base + all_time + g_league
        # Offline fallback: derive categories from player team names
        names_set = {p.team for p in self.players}
        names = list(names_set)
        lower_names = [n.lower() for n in names]
        free = [names[i] for i, ln in enumerate(lower_names) if 'free' in ln]
        draft = [names[i] for i, ln in enumerate(lower_names) if 'draft' in ln]
        all_time = [names[i] for i, ln in enumerate(lower_names) if 'all time' in ln or 'all-time' in ln]
        g_league = [names[i] for i, ln in enumerate(lower_names) if 'gleague' in ln or 'g league' in ln or 'g-league' in ln]
        assigned = set(free + draft + all_time + g_league)
        base = [n for n in names if n not in assigned]
        return free + draft + base + all_time + g_league
    def get_players_by_team(self, team: str) -> list[Player]:
        """Return players for the specified team.
        If team data has been scanned from memory, use the team index
        mapping to look up players dynamically.  Otherwise, filter
        preloaded players (offline mode).
        """
        # Live memory mode: use team_list to find the index and scan players
        if self.team_list and not self.external_loaded:
            # If we are in fallback mode (scanned all players), filter from self.players
            if self.fallback_players:
                return [p for p in self.players if p.team == team]
            # Otherwise, use roster pointers to scan players for the team
            for idx, name in self.team_list:
                if name == team:
                    return self.scan_team_players(idx)
            return []
        # Offline or fallback mode: filter players by team name
        return [p for p in self.players if p.team == team]
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
        self.mem.write_wstring_fixed(p_addr + OFF_LAST_NAME, player.last_name, NAME_MAX_CHARS)
        self.mem.write_wstring_fixed(p_addr + OFF_FIRST_NAME, player.first_name, NAME_MAX_CHARS)
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
        self.sidebar = tk.Frame(self, width=200, bg="#2F3E46")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        # Buttons
        self.btn_home = tk.Button(
            self.sidebar,
            text="Home",
            command=self.show_home,
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
        )
        self.btn_home.pack(fill=tk.X, padx=10, pady=(20, 5))
        self.btn_players = tk.Button(
            self.sidebar,
            text="Players",
            command=self.show_players,
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
        )
        self.btn_players.pack(fill=tk.X, padx=10, pady=5)
        # Teams button
        self.btn_teams = tk.Button(
            self.sidebar,
            text="Teams",
            command=self.show_teams,
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
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
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
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
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
        )
        self.btn_coy.pack(fill=tk.X, padx=10, pady=5)
        # Load Excel button
        # This button imports player data from a user‑selected Excel workbook.
        # It prompts the user to choose the workbook first, then asks which
        # categories (Attributes, Tendencies, Durability) should be applied.  A
        # loading dialog is displayed while processing to discourage
        # interaction.  See ``_open_load_excel`` for details.
        self.btn_load_excel = tk.Button(
            self.sidebar,
            text="Load Excel",
            command=self._open_load_excel,
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
        )
        self.btn_load_excel.pack(fill=tk.X, padx=10, pady=5)
        # Team Shuffle button
        self.btn_shuffle = tk.Button(
            self.sidebar,
            text="Shuffle Teams",
            command=self._open_team_shuffle,
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
        )
        self.btn_shuffle.pack(fill=tk.X, padx=10, pady=5)
        # Batch Edit button
        self.btn_batch_edit = tk.Button(
            self.sidebar,
            text="Batch Edit",
            command=self._open_batch_edit,
            bg="#354F52",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
        )
        self.btn_batch_edit.pack(fill=tk.X, padx=10, pady=5)
    # ---------------------------------------------------------------------
    # Home screen
    # ---------------------------------------------------------------------
    def _build_home_screen(self):
        self.home_frame = tk.Frame(self, bg="#CAD2C5")
        # Title
        tk.Label(
            self.home_frame,
            text="2K26 Offline Player Editor",
            font=("Segoe UI", 20, "bold"),
            bg="#CAD2C5",
            fg="#2F3E46",
        ).pack(pady=(40, 20))
        # Status
        self.status_var = tk.StringVar()
        self.status_label = tk.Label(
            self.home_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 12),
            bg="#CAD2C5",
            fg="#2F3E46",
        )
        self.status_label.pack(pady=10)
        # Refresh button
        tk.Button(
            self.home_frame,
            text="Refresh",
            command=self._update_status,
            bg="#84A98C",
            fg="white",
            relief=tk.FLAT,
            activebackground="#52796F",
            activeforeground="white",
        ).pack(pady=5)
        # Version label
        tk.Label(
            self.home_frame,
            text=f"Version {APP_VERSION}",
            font=("Segoe UI", 9, "italic"),
            bg="#CAD2C5",
            fg="#52796F",
        ).pack(side=tk.BOTTOM, pady=10)
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
            fg="white",
            relief=tk.FLAT,
            activebackground="#415A77",
            activeforeground="white",
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
        self.player_search_var.trace_add("write", lambda *_: self._apply_player_filter())
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
        # Tendencies and Durability.  If they cancel or uncheck all
        # boxes, no import is performed.
        # ------------------------------------------------------------------
        categories_to_ask = ["Attributes", "Tendencies", "Durability"]
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
                    reader = _csv.reader(io.StringIO(csv_text))
                    header = next(reader, None)
                    for row in reader:
                        if not row:
                            continue
                        name = row[0].strip()
                        if not name:
                            continue
                        idxs = self.model.find_player_indices_by_name(name)
                        if not idxs:
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
            def collect_missing_names(path: str) -> None:
                import csv as _csv
                if not path or not os.path.isfile(path):
                    return
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        sample = f.readline()
                        delim = '\t' if '\t' in sample else ',' if ',' in sample else ';'
                        f.seek(0)
                        reader = _csv.reader(f, delimiter=delim)
                        next(reader, None)  # skip header
                        for row in reader:
                            if not row:
                                continue
                            name = row[0].strip()
                            if not name:
                                continue
                            idxs = self.model.find_player_indices_by_name(name)
                            if not idxs:
                                not_found.add(name)
                except Exception:
                    pass
            for p in file_map.values():
                collect_missing_names(p)
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
                # Skip header and collect non‑blank names
                for row in rows[1:]:
                    if not row or not row[0].strip():
                        continue
                    attr_names_set.add(row[0].strip())
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
            msg_lines.append("\nPlayers not found (no matches in roster):")
            for name in sorted(not_found):
                msg_lines.append(f"  {name}")
        else:
            msg_lines.append("\nAll players were found in the roster.")
        # Destroy the loading dialog before showing the summary
        try:
            loading_win.destroy()
        except Exception:
            pass
        messagebox.showinfo("2K COY Import", "\n".join(msg_lines))
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
        categories_to_ask = ["Attributes", "Tendencies", "Durability"]
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
        try:
            import pandas as _pd
        except Exception:
            messagebox.showerror('Excel Import', 'Pandas is required. Install with: pip install pandas openpyxl')
            loading_win.destroy()
            return
        # Helper to collect missing names from a DataFrame
        def collect_missing_names_df(df) -> None:
            for name in df.iloc[:, 0].astype(str).str.strip():
                if not name:
                    continue
                idxs = self.model.find_player_indices_by_name(name)
                if not idxs:
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
                collect_missing_names_df(df)
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
            msg_lines.append("\nPlayers not found:")
            for name in sorted(not_found):
                msg_lines.append(f"  {name}")
        messagebox.showinfo("Excel Import", "\n".join(msg_lines))
    # ---------------------------------------------------------------------
    # Teams screen
    # ---------------------------------------------------------------------
    def _build_teams_screen(self):
        """Construct the Teams editing screen."""
        self.teams_frame = tk.Frame(self, bg="#F5F5F5")
        # Top bar with team selection
        top = tk.Frame(self.teams_frame, bg="#F5F5F5")
        top.pack(side=tk.TOP, fill=tk.X, pady=10, padx=10)
        tk.Label(top, text="Team:", font=("Segoe UI", 12), bg="#F5F5F5", fg="#2F3E46").pack(side=tk.LEFT)
        self.team_edit_var = tk.StringVar()
        self.team_edit_dropdown = ttk.Combobox(top, textvariable=self.team_edit_var, state="readonly")
        self.team_edit_dropdown.bind("<<ComboboxSelected>>", self._on_team_edit_selected)
        self.team_edit_dropdown.pack(side=tk.LEFT, padx=5)
        # Scan status label for teams
        self.team_scan_status_var = tk.StringVar()
        self.team_scan_status_label = tk.Label(
            top,
            textvariable=self.team_scan_status_var,
            font=("Segoe UI", 10, "italic"),
            bg="#F5F5F5",
            fg="#52796F",
        )
        self.team_scan_status_label.pack(side=tk.LEFT, padx=10)
        # Detail pane for team fields
        detail = tk.Frame(self.teams_frame, bg="#FFFFFF", relief=tk.RIDGE, bd=1)
        detail.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        tk.Label(
            detail,
            text="Team Details",
            font=("Segoe UI", 14, "bold"),
            bg="#FFFFFF",
            fg="#2F3E46",
        ).pack(pady=(5, 10))
        # Form for each team field
        self.team_field_vars: Dict[str, tk.StringVar] = {}
        form = tk.Frame(detail, bg="#FFFFFF")
        form.pack(fill=tk.X, padx=10, pady=5)
        row = 0
        if TEAM_FIELD_DEFS:
            for label in TEAM_FIELD_DEFS.keys():
                tk.Label(form, text=f"{label}:", bg="#FFFFFF").grid(row=row, column=0, sticky=tk.W, pady=2)
                var = tk.StringVar()
                entry = tk.Entry(form, textvariable=var)
                entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=2)
                self.team_field_vars[label] = var
                row += 1
            form.columnconfigure(1, weight=1)
        else:
            tk.Label(
                form,
                text="No team field offsets found. Update 2K26_Offsets.json to enable editing.",
                bg="#FFFFFF",
                fg="#B0413E",
                wraplength=360,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=4)
        players_section = tk.Frame(detail, bg="#FFFFFF")
        players_section.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        tk.Label(
            players_section,
            text="Team Players",
            font=("Segoe UI", 12, "bold"),
            bg="#FFFFFF",
            fg="#2F3E46",
        ).pack(anchor=tk.W)
        list_container = tk.Frame(players_section, bg="#FFFFFF")
        list_container.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        scrollbar = tk.Scrollbar(list_container, orient="vertical")
        self.team_players_listbox = tk.Listbox(
            list_container,
            height=12,
            yscrollcommand=scrollbar.set,
            bg="#FFFFFF",
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
            bg="#84A98C",
            fg="white",
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
            self.team_dropdown['values'] = teams
            if teams:
                self.team_var.set(teams[0])
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
        try:
            idx = teams.index(team_name)
        except ValueError:
            self.btn_team_save.config(state=tk.DISABLED)
            self._update_team_players(None)
            return
        fields = self.model.get_team_fields(idx)
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
        self._update_team_players(idx)
        # Enable save if process open
        self.btn_team_save.config(state=tk.NORMAL if self.model.mem.hproc else tk.DISABLED)
    def _save_team(self):
        """Save the edited team fields back to memory."""
        team_name = self.team_edit_var.get()
        if not team_name:
            return
        teams = self.model.get_teams()
        try:
            idx = teams.index(team_name)
        except ValueError:
            return
        values = {label: var.get() for label, var in self.team_field_vars.items()}
        ok = self.model.set_team_fields(idx, values)
        if ok:
            messagebox.showinfo("Success", f"Updated {team_name} successfully.")
            # Refresh team list to reflect potential name change
            self.model.refresh_players()
            teams = self.model.get_teams()
            self._update_team_dropdown(teams)
            # Reselect the updated team name if changed
            if values.get("Team Name"):
                self.team_edit_var.set(values.get("Team Name"))
            self._update_team_players(idx)
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
            if self.model.external_loaded:
                self.status_var.set("Using offline roster from files")
            else:
                self.status_var.set("NBA2K26 not detected – using demo roster")
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
            self.var_first.set("")
            self.var_last.set("")
            self.var_player_team.set("")
            self.btn_save.config(state=tk.DISABLED)
            self.btn_edit.config(state=tk.DISABLED)
        else:
            self.var_first.set(p.first_name)
            self.var_last.set(p.last_name)
            self.var_player_team.set(p.team)
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
        if self.model.external_loaded or self.model.fallback_players:
            # Offline or fallback mode: use loaded players list
            dest_players = [p for p in self.model.players if p.index != src.index]
        else:
            # Live memory mode: scan players across all teams via roster pointers
            dest_players: list[Player] = []
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
        # dynamically based on the widget’s configuration (e.g. range)
        # when adjusting entire categories via buttons.
        self.spin_widgets: dict[tuple[str, str], tk.Spinbox] = {}
        # Track fields edited since last save
        self._unsaved_changes: set[tuple[str, str]] = set()
        # Suppress change-trace callbacks while populating initial values
        self._initializing = True
        # Notebook for category tabs
        notebook = ttk.Notebook(self)
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
        for name in ["Accessories", "Contract"]:
            if name not in categories:
                categories.append(name)
        for cat in categories:
            frame = tk.Frame(notebook, bg="#F5F5F5")
            notebook.add(frame, text=cat)
            self._build_category_tab(frame, cat)
        # Action buttons at bottom
        btn_frame = tk.Frame(self, bg="#F5F5F5")
        btn_frame.pack(fill=tk.X, pady=5)
        save_btn = tk.Button(
            btn_frame,
            text="Save",
            command=self._save_all,
            bg="#84A98C",
            fg="white",
            relief=tk.FLAT,
        )
        save_btn.pack(side=tk.LEFT, padx=10)
        close_btn = tk.Button(
            btn_frame,
            text="Close",
            command=self.destroy,
            bg="#B0413E",
            fg="white",
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
            btn_frame = tk.Frame(parent, bg="#F5F5F5")
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
                    bg="#52796F",
                    fg="white",
                    relief=tk.FLAT,
                    width=5,
                ).pack(side=tk.LEFT, padx=2)
        # Container for scrolled view if many fields
        canvas = tk.Canvas(parent, bg="#F5F5F5", highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#F5F5F5")
        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
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
                bg="#F5F5F5",
                fg="#6C757D",
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
            lbl = tk.Label(scroll_frame, text=name + ":", bg="#F5F5F5")
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
                # Attributes and Durability use the familiar 25–99 rating scale
                spin_from = 25
                spin_to = 99
            elif category_name == "Tendencies":
                # Tendencies are displayed on a 0–100 scale
                spin_from = 0
                spin_to = 100
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
                )
                spin.grid(row=row, column=1, sticky=tk.W, padx=(0, 10), pady=2)
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
                        if field_name.lower() == "weight":
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
                        elif category in ("Attributes", "Durability"):  # Map the raw bitfield value into the 25–99 rating scale
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
                    if field_name.lower() == "weight":
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
                # Fallback; not expected for randomizer categories
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
        # Obtain team names: use get_teams if available, fallback to model.team_list
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
        # Fetch team names: use get_teams or team_list fallback
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
        leftover players remain in Free Agents.  Unlike the old
        implementation, this function works in both live memory mode
        and offline mode and does not enforce a per‑team roster
        maximum prior to shuffling.
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
        # Determine whether we are in live memory mode.  Shuffling in
        # live memory writes directly to the game process; offline mode
        # simply updates the in‑memory roster representation.
        live_mode = not self.model.external_loaded and not self.model.fallback_players
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
                    total_assigned += 1
            # Rebuild the name index map after offline changes
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
# categories (Attributes, Tendencies, Durability) they wish to import.  This
# dialog presents a list of checkboxes and returns the selected categories
# when the user clicks OK.  If the dialog is cancelled or no categories are
# selected, ``selected`` is set to None.
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
    if not initialize_offsets(force=True):
        messagebox.showerror("Offsets missing", "Unable to load 2K26_Offsets.json. Place the file next to the editor.")
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
