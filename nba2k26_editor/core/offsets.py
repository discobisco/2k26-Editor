"""
Offset loading and schema normalization.

Handles:
* offset file discovery and parsing
* canonical field lookup helpers
* resolved constants for player/team tables
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from .config import MODULE_NAME as CONFIG_MODULE_NAME
from .conversions import to_int
from .offset_cache import CachedOffsetPayload, OffsetCache
from .offset_loader import OffsetRepository
from .offset_resolver import OffsetResolveError, OffsetResolver
from .perf import timed


class OffsetSchemaError(RuntimeError):
    """Raised when offsets are missing required definitions."""


BASE_POINTER_SIZE_KEY_MAP: dict[str, str | None] = {
    "Player": "playerSize",
    "Team": "teamSize",
    "Staff": "staffSize",
    "Stadium": "stadiumSize",
    "TeamHistory": "historySize",
    "NBAHistory": "historySize",
    "HallOfFame": "hallOfFameSize",
    "History": "historySize",
    "Jersey": "jerseySize",
    "career_stats": "careerStatsSize",
    "Cursor": None,
}
REQUIRED_LIVE_BASE_POINTER_KEYS: tuple[str, ...] = ("Player", "Team", "Staff", "Stadium")

STRICT_OFFSET_FIELD_KEYS: dict[str, tuple[str, str]] = {
    "player_first_name": ("Vitals", "FIRSTNAME"),
    "player_last_name": ("Vitals", "LASTNAME"),
    "player_current_team": ("Vitals", "CURRENTTEAM"),
    "team_name": ("Team Vitals", "TEAMNAME"),
    "team_city_name": ("Team Vitals", "CITYNAME"),
    "team_city_abbrev": ("Team Vitals", "CITYSHORTNAME"),
    "staff_first_name": ("Staff Vitals", "FIRSTNAME"),
    "staff_last_name": ("Staff Vitals", "LASTNAME"),
    "stadium_name": ("Stadium", "ARENANAME"),
}

# Hierarchy-aware required field specs:
# (source_super_type, source_category, source_group, normalized_name)
STRICT_OFFSET_HIERARCHY_FIELD_KEYS: dict[str, tuple[str, str, str, str]] = {
    "player_first_name": ("Player", "Vitals", "ID", "FIRSTNAME"),
    "player_last_name": ("Player", "Vitals", "ID", "LASTNAME"),
    "player_current_team": ("Player", "Vitals", "Team", "CURRENTTEAM"),
    "team_name": ("Team", "Info", "", "TEAMNAME"),
    "team_city_name": ("Team", "Info", "", "CITYNAME"),
    "team_city_abbrev": ("Team", "Info", "", "CITYSHORTNAME"),
    "staff_first_name": ("Staff", "Vitals", "vitals", "FIRSTNAME"),
    "staff_last_name": ("Staff", "Vitals", "vitals", "LASTNAME"),
    "stadium_name": ("Stadium", "Vitals", "Vitals", "ARENANAME"),
}

# Schema-driven required field sources keyed by split offsets file + normalized name.
REQUIRED_OFFSET_SCHEMA_FIELDS: dict[str, tuple[str, str]] = {
    "player_first_name": ("offsets_players.json", "FIRSTNAME"),
    "player_last_name": ("offsets_players.json", "LASTNAME"),
    "player_current_team": ("offsets_players.json", "CURRENTTEAM"),
    "team_name": ("offsets_teams.json", "TEAMNAME"),
    "team_city_name": ("offsets_teams.json", "CITYNAME"),
    "team_city_abbrev": ("offsets_teams.json", "CITYSHORTNAME"),
    "staff_first_name": ("offsets_staff.json", "FIRSTNAME"),
    "staff_last_name": ("offsets_staff.json", "LASTNAME"),
    "stadium_name": ("offsets_stadiums.json", "ARENANAME"),
}

MODULE_NAME = CONFIG_MODULE_NAME
OFFSET_FILENAME_PATTERNS: tuple[str, ...] = ()
SPLIT_OFFSETS_LEAGUE_FILE = "offsets_league.json"
SPLIT_OFFSETS_DOMAIN_FILES: tuple[str, ...] = (
    "offsets_players.json",
    "offsets_teams.json",
    "offsets_staff.json",
    "offsets_stadiums.json",
    "offsets_history.json",
    "offsets_shoes.json",
)
SPLIT_OFFSETS_OPTIONAL_FILES: tuple[str, ...] = ("dropdowns.json",)
OFFSETS_BUNDLE_FILE = "split offsets files (offsets_league.json + offsets_*.json)"
PLAYER_STATS_TABLE_CATEGORY_MAP: dict[str, str] = {
    "player stat id": "Stats - IDs",
    "stats": "Stats - IDs",
    "season": "Stats - Season",
    "season high stats": "Stats - Season",
    "career": "Stats - Career",
    "career high stats": "Stats - Career",
    "awards": "Stats - Awards",
}
PLAYER_STATS_IDS_CATEGORY = "Stats - IDs"
PLAYER_STATS_SEASON_CATEGORY = "Stats - Season"
_offset_file_path: Path | None = None
_offset_config: dict | None = None
_offset_config_primary: dict | None = None
_offset_file_path_primary: Path | None = None
_offset_config_offsets2: dict | None = None
_offset_file_path_offsets2: Path | None = None
_offset_index: dict[tuple[str, str], dict] = {}
_offset_normalized_index: dict[tuple[str, str], dict] = {}
_offset_hierarchy_index: dict[tuple[str, str, str, str], dict] = {}
_current_offset_target: str | None = None
CATEGORY_SUPER_TYPES: dict[str, str] = {}
CATEGORY_CANONICAL: dict[str, str] = {}
PLAYER_STATS_RELATIONS: dict[str, Any] = {}

_OFFSET_CACHE = OffsetCache()
_OFFSET_REPOSITORY = OffsetRepository(_OFFSET_CACHE)

PLAYER_TABLE_RVA = 0
PLAYER_STRIDE = 0
PLAYER_PTR_CHAINS: list[dict[str, object]] = []
DRAFT_PTR_CHAINS: list[dict[str, object]] = []
OFF_LAST_NAME = 0
OFF_FIRST_NAME = 0
OFF_TEAM_PTR = 0
OFF_TEAM_NAME = 0
OFF_TEAM_ID = 0
MAX_PLAYERS = 5500
MAX_DRAFT_PLAYERS = 150
DRAFT_CLASS_TEAM_ID = -2
MAX_TEAMS_SCAN = 400
NAME_MAX_CHARS = 20
FIRST_NAME_ENCODING = "utf16"
LAST_NAME_ENCODING = "utf16"
TEAM_NAME_ENCODING = "utf16"
TEAM_STRIDE = 0
TEAM_NAME_OFFSET = 0
TEAM_NAME_LENGTH = 0
TEAM_PLAYER_SLOT_COUNT = 30
TEAM_PTR_CHAINS: list[dict[str, object]] = []
TEAM_TABLE_RVA = 0
TEAM_FIELD_DEFS: dict[str, tuple[int, int, str]] = {}
TEAM_RECORD_SIZE = TEAM_STRIDE

TEAM_FIELD_SPECS: tuple[tuple[str, str], ...] = (
    ("Team Name", "TEAMNAME"),
    ("City Name", "CITYNAME"),
    ("City Abbrev", "CITYSHORTNAME"),
)
PLAYER_PANEL_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("Position", "Vitals", "Position"),
    ("Number", "Vitals", "Jersey Number"),
    ("Height", "Vitals", "Height"),
    ("Weight", "Vitals", "Weight"),
    ("Face ID", "Vitals", "Face ID"),
    ("Unique ID", "Vitals", "UNIQUESIGNATUREID"),
)
PLAYER_PANEL_OVR_FIELD: tuple[str, str] = ("Attributes", "CACHCED_OVR")

UNIFIED_FILES: tuple[str, ...] = ()
EXTRA_CATEGORY_FIELDS: dict[str, list[dict]] = {}

# Staff/Stadium metadata (populated when offsets define them)
STAFF_STRIDE = 0
STAFF_PTR_CHAINS: list[dict[str, object]] = []
STAFF_RECORD_SIZE = STAFF_STRIDE
STAFF_NAME_OFFSET = 0
STAFF_NAME_LENGTH = 0
STAFF_NAME_ENCODING = "utf16"
MAX_STAFF_SCAN = 400

STADIUM_STRIDE = 0
STADIUM_PTR_CHAINS: list[dict[str, object]] = []
STADIUM_RECORD_SIZE = STADIUM_STRIDE
STADIUM_NAME_OFFSET = 0
STADIUM_NAME_LENGTH = 0
STADIUM_NAME_ENCODING = "utf16"
MAX_STADIUM_SCAN = 200

ATTR_IMPORT_ORDER = [
    "Driving Layup",
    "Standing Dunk",
    "Driving Dunk",
    "Close Shot",
    "Mid Range",
    "Three Point",
    "Free Throw",
    "Post Hook",
    "Post Fade",
    "Post Control",
    "Draw Foul",
    "Shot IQ",
    "Ball Control",
    "Speed With Ball",
    "Hands",
    "Passing Accuracy",
    "Passing IQ",
    "Passing Vision",
    "Offensive Consistency",
    "Interior Defense",
    "Perimeter Defense",
    "Steal",
    "Block",
    "Offensive Rebound",
    "Defensive Rebound",
    "Help Defense IQ",
    "Passing Perception",
    "Defensive Consistency",
    "Speed",
    "Agility",
    "Strength",
    "Vertical",
    "Stamina",
    "Intangibles",
    "Hustle",
    "Misc Durability",
    "Potential",
]
DUR_IMPORT_ORDER = [
    "Back Durability",
    "Head Durability",
    "Left Ankle Durability",
    "Left Elbow Durability",
    "Left Foot Durability",
    "Left Hip Durability",
    "Left Knee Durability",
    "Left Shoulder Durability",
    "Neck Durability",
    "Right Ankle Durability",
    "Right Elbow Durability",
    "Right Foot Durability",
    "Right Hip Durability",
    "Right Knee Durability",
    "Right Shoulder Durability",
    "Misc Durability",
]
POTENTIAL_IMPORT_ORDER = [
    "Minimum Potential",
    "Potential",
    "Maximum Potential",
]

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

TEND_IMPORT_ORDER = [
    "Shot Three Right Center",
    "Shot Three Left Center",
    "Off Screen Shot Three",
    "Shot Three Right",
    "Spot Up Shot Three",
    "Alley Oop Pass",
    "Attack Strong On Drive",
    "Shot Under Basket",
    "Block Tendency",
    "Shot Mid Right Center",
    "Shot Close Middle",
    "Shot Close Right",
    "Shot Close Left",
    "Contested Jumper Three",
    "Contested Jumper Mid",
    "Contest Shot",
    "Crash",
    "Dish To Open Man",
    "Dribble Double Crossover",
    "Dribble Half Spin",
    "Drive",
    "Drive Pull Up Three",
    "Drive Pull Up Mid",
    "Drive Right",
    "Dribble Behind The Back",
    "Driving Dribble Hesitation",
    "Driving Dunk Tendency",
    "Driving In And Out",
    "Driving Layup Tendency",
    "Dribble Stepback",
    "Euro Step Layup",
    "Flashy Dunk",
    "Flashy Pass",
    "Floater",
    "Foul",
    "Post Shoot",
    "Hard Foul",
    "Post Hop Shot",
    "Hop Step Layup",
    "Iso Vs Average Defender",
    "Iso Vs Elite Defender",
    "Iso Vs Good Defender",
    "Iso Vs Poor Defender",
    "Shot Mid Left Center",
    "Off Screen Shot Mid",
    "Shot Mid Right",
    "Spot Up Shot Mid",
    "No Driving Dribble Move",
    "No Setup Dribble Move",
    "Off Screen Drive",
    "Steal Tendency",
    "Pass Interception",
    "Play Discipline",
    "Post Aggressive Backdown",
    "Post Back Down",
    "Post Drive",
    "Post Dropstep",
    "Post Fade Left",
    "Post Fade Right",
    "Post Hook Left",
    "Post Hook Right",
    "Post Hop Step",
    "Post Shimmy Shot",
    "Post Spin",
    "Post Stepback Shot",
    "Post Face Up",
    "Post Up And Under",
    "Putback Dunk",
    "Roll Vs Pop",
    "Setup With Hesitation",
    "Setup With Sizeup",
    "Shot Tendency",
    "Spin Jumper",
    "Spin Layup",
    "Spot Up Drive",
    "Standing Dunk Tendency",
    "Stepback Jumper Three",
    "Step Back Jumper Mid",
    "Step Through",
    "Take Charge",
    "Triple Threat Shoot",
    "Touches",
    "Transition Pull Up Three",
    "Transition Spot Up",
    "Triple Threat Idle",
    "Triple Threat Jab Step",
    "Triple Threat Pump Fake",
    "Use Glass",
]


FIELD_NAME_ALIASES: dict[str, str] = {
    "SHOT": "SHOOT",
    "SHOTTENDENCY": "SHOOT",
    "SHOTSHOT": "SHOOT",
    "SHOTATTRIBUTE": "SHOOT",
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
    "3PTSHOT": "THREEPOINT",
    "MIDRANGESHOT": "MIDRANGE",
    "FREETHROWS": "FREETHROW",
    "POSTMOVES": "POSTCONTROL",
    "PASSACCURACY": "PASSINGACCURACY",
    "PASSPERCEPTION": "PASSINGPERCEPTION",
    "MISCANELLOUSDURABILITY": "MISCDURABILITY",
    "SHOT3PTCENTER": "SHOT3PTRIGHTCENTER",
    "SHOT3PTLEFT": "SHOT3PTLEFTCENTER",
    "ALLEYOOPPASS": "ALLEYOOP",
    "BLOCKTENDENCY": "BLOCK",
    "DRIVINGCROSSOVER": "DRIBBLECROSSOVER",
    "DRIBBLEDOUBLECROSSOVER": "DRIBBLECROSSOVER",
    "DRIBBLEBEHINDTHEBACK": "DRIVINGBEHINDBACK",
    "DRIBBLESTEPBACK": "DRIVINGSTEPBACK",
    "POSTSHOOT": "POSTSHOT",
    "POSTHOPSHOTTENDENCY": "POSTHOPSHOT",
    "SPOTUPSHOTMID": "MIDSHOT",
    "SHOTMID": "MIDSHOT",
    "NOSETUPDRIBBLEMOVE": "NOSETUPDRIBBLE",
    "STEALTENDENCY": "STEAL",
    "POSTFACEUP": "POSTUP",
    "STEPTHROUGHSHOT": "STEPTHROUGH",
}


def _derive_offset_candidates(target_executable: str | None) -> tuple[str, ...]:
    """Return the split-offset file manifest."""
    del target_executable  # split files are not executable-specific
    return (SPLIT_OFFSETS_LEAGUE_FILE, *SPLIT_OFFSETS_DOMAIN_FILES)


def _split_version_tokens(raw_key: object) -> tuple[str, ...]:
    text = str(raw_key or "").strip()
    if not text:
        return ()
    tokens = [chunk.strip().upper() for chunk in text.split(",") if chunk and chunk.strip()]
    return tuple(dict.fromkeys(tokens))


def _version_key_matches(raw_key: object, target_label: str | None) -> bool:
    target = str(target_label or "").strip().upper()
    if not target:
        return False
    tokens = _split_version_tokens(raw_key)
    if tokens:
        return target in tokens
    return str(raw_key or "").strip().upper() == target


def _select_version_entry(per_version: dict[str, object], target_label: str) -> dict[str, object] | None:
    for raw_key, payload in per_version.items():
        if not isinstance(payload, dict):
            continue
        if _version_key_matches(raw_key, target_label):
            return payload
    return None


def _infer_length_bits(field_type: object, length_raw: object) -> int:
    length_val = to_int(length_raw)
    if length_val > 0:
        return length_val
    type_name = str(field_type or "").strip().lower()
    if type_name in {
        "byte",
        "ubyte",
        "sbyte",
    }:
        return 8
    if type_name in {"short", "ushort", "int16", "uint16", "word"}:
        return 16
    if type_name in {"integer", "int", "uint", "number", "slider", "long", "ulong", "int32", "uint32", "dword"}:
        return 32
    if type_name == "float":
        return 32
    if type_name in {"double", "int64", "uint64", "longlong", "ulonglong", "qword"}:
        return 64
    if "pointer" in type_name or type_name in {"ptr", "address"}:
        return 64
    if type_name in {"binary", "bool", "boolean", "bit", "bitfield"}:
        return 1
    return 0


def _normalize_offset_type(field_type: object) -> str:
    raw = str(field_type or "").strip().lower()
    if not raw:
        return ""
    if raw in {
        "integer",
        "int",
        "uint",
        "number",
        "slider",
        "byte",
        "ubyte",
        "char",
        "sbyte",
        "short",
        "ushort",
        "int16",
        "uint16",
        "word",
        "long",
        "ulong",
        "int32",
        "uint32",
        "dword",
        "int64",
        "uint64",
        "longlong",
        "ulonglong",
        "qword",
    }:
        return "integer"
    if raw in {"float", "single", "double"}:
        return "float"
    if "pointer" in raw or raw in {"ptr", "address"}:
        return "pointer"
    if raw in {"binary", "bool", "boolean", "bit", "bitfield", "combo"}:
        return "binary"
    if raw in {"wstring", "utf16", "utf-16", "wchar", "wide"}:
        return "wstring"
    if raw in {"string", "text", "ascii", "char", "cstring"}:
        return "string"
    return raw


_KNOWN_SUPER_TYPES: set[str] = {
    "Player",
    "Players",
    "Team",
    "Teams",
    "Staff",
    "Stadium",
    "Stadiums",
    "Jersey",
    "Jerseys",
    "Shoe",
    "Shoes",
    "NBA History List",
    "NBA History",
    "NBA Record List",
    "NBA Records",
    "Career Stats",
    "History",
    "Playbooks",
}


def _looks_like_super_type(label: object) -> bool:
    text = str(label or "").strip()
    if not text:
        return False
    return text in _KNOWN_SUPER_TYPES


def _normalized_super_type_label(raw_value: object) -> str:
    text = str(raw_value).strip() if raw_value is not None else ""
    if text.lower() in {"", "none", "null"}:
        return ""
    return text


def _derive_super_type_map_from_split_schema(split_schema: object) -> dict[str, str]:
    """Build category -> super_type map from offsets_league split_schema."""
    derived: dict[str, str] = {}
    if not isinstance(split_schema, dict):
        return derived
    for file_payload in split_schema.values():
        if not isinstance(file_payload, dict):
            continue
        for super_type_label, category_map in file_payload.items():
            super_type = _normalized_super_type_label(super_type_label)
            if not super_type or not isinstance(category_map, dict):
                continue
            for category_name in category_map.keys():
                category = str(category_name or "").strip()
                if not category:
                    continue
                derived.setdefault(category.lower(), super_type)
    return derived


def _select_active_version(
    versions_map: dict[str, object],
    target_executable: str | None,
    *,
    require_hint: bool = False,
) -> tuple[str, str, dict[str, object]] | None:
    version_hint = _derive_version_label(target_executable)
    if require_hint and not version_hint:
        return None
    selected_key: str | None = None
    selected_label = version_hint or ""
    if version_hint:
        for key in versions_map.keys():
            if _version_key_matches(key, version_hint):
                selected_key = str(key)
                break
        if selected_key is None:
            return None
    else:
        selected_key = str(next(iter(versions_map.keys()), ""))
        selected_label = selected_key
    selected_info = versions_map.get(selected_key) if selected_key else None
    if not isinstance(selected_info, dict) or not selected_key:
        return None
    return selected_label, selected_key, cast(dict[str, object], selected_info)


def _read_json_cached(path: Path) -> dict[str, Any] | None:
    parsed, _error = _read_json_with_error(path)
    return parsed


def _read_json_with_error(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    cached = _OFFSET_CACHE.get_json(path)
    if cached is not None:
        return cached, None
    try:
        with path.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
    except json.JSONDecodeError as exc:
        return None, (
            f"{path}: invalid JSON syntax at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        )
    except OSError as exc:
        return None, f"{path}: unable to read file: {exc}"
    except Exception as exc:
        return None, f"{path}: unable to parse JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, f"{path}: top-level JSON value must be an object."
    _OFFSET_CACHE.set_json(path, parsed)
    return parsed, None


def _build_dropdown_values_index(raw_dropdowns: object) -> dict[tuple[str, str, str], list[str]]:
    index: dict[tuple[str, str, str], list[str]] = {}
    if not isinstance(raw_dropdowns, dict):
        return index
    dropdown_entries = raw_dropdowns.get("dropdowns")
    if not isinstance(dropdown_entries, list):
        return index
    for entry in dropdown_entries:
        if not isinstance(entry, dict):
            continue
        canonical_category = str(entry.get("canonical_category") or "").strip()
        normalized_name = str(entry.get("normalized_name") or "").strip()
        versions = entry.get("versions")
        if not canonical_category or not normalized_name or not isinstance(versions, dict):
            continue
        category_key = canonical_category.lower()
        normalized_key = normalized_name.upper()
        for version_key, value in versions.items():
            if not isinstance(value, dict):
                continue
            values = value.get("values")
            if not isinstance(values, list):
                values = value.get("dropdown")
            if not isinstance(values, list):
                continue
            cleaned_values = [str(item) for item in values]
            if not cleaned_values:
                continue
            for token in _split_version_tokens(version_key):
                index[(category_key, normalized_key, token)] = cleaned_values
    return index


def _resolve_split_category(root_category: str, table_segments: tuple[str, ...]) -> str:
    """Return runtime category name for a split offsets leaf entry."""
    root = str(root_category or "").strip() or "Misc"
    if root.lower() != "stats":
        return root
    if not table_segments:
        return "Stats - Misc"
    table_key = str(table_segments[0] or "").strip().lower()
    mapped = PLAYER_STATS_TABLE_CATEGORY_MAP.get(table_key)
    if mapped:
        return mapped
    table_label = str(table_segments[0]).strip()
    return f"Stats - {table_label}" if table_label else "Stats - Misc"


def _iter_hierarchy_leaf_nodes(
    node: object,
    path_segments: tuple[str, ...],
):
    if isinstance(node, list):
        for item in node:
            yield from _iter_hierarchy_leaf_nodes(item, path_segments)
        return
    if not isinstance(node, dict):
        return

    versions_raw = node.get("versions")
    normalized_raw = (
        node.get("normalized_name")
        or node.get("canonical_name")
        or node.get("name")
        or node.get("display_name")
    )
    if isinstance(versions_raw, dict) and normalized_raw:
        yield cast(dict[str, object], node), path_segments
        return

    for key, child in node.items():
        if not isinstance(child, (dict, list)):
            continue
        child_path = path_segments + (str(key),)
        yield from _iter_hierarchy_leaf_nodes(child, child_path)


def _resolve_hierarchy_context(
    path_segments: tuple[str, ...],
    *,
    leaf_node: dict[str, object],
    version_payload: dict[str, object],
    super_type_map: dict[str, str],
) -> dict[str, object]:
    segments = tuple(str(seg).strip() for seg in path_segments if str(seg).strip())
    version_super = _normalized_super_type_label(
        version_payload.get("super_type")
        or version_payload.get("superType")
        or leaf_node.get("super_type")
        or leaf_node.get("superType")
    )
    source_category = "Misc"
    source_group = ""
    table_segments: tuple[str, ...] = ()
    source_super_type = version_super
    if segments and _looks_like_super_type(segments[0]):
        source_super_type = str(segments[0]).strip() or source_super_type
        source_category = str(segments[1] if len(segments) > 1 else "Misc")
        source_group = str(segments[2] if len(segments) > 2 else "")
        table_segments = tuple(segments[2:])
    else:
        source_category = str(segments[0] if segments else "Misc")
        source_group = str(segments[1] if len(segments) > 1 else "")
        table_segments = tuple(segments[1:])
        if not source_super_type:
            source_super_type = str(
                super_type_map.get(source_category.lower())
                or super_type_map.get(source_group.lower())
                or ""
            ).strip()
    emitted_category = _resolve_split_category(source_category, table_segments)
    source_table_path = "/".join(segments) if segments else source_category
    return {
        "source_super_type": source_super_type,
        "source_category": source_category,
        "source_group": source_group,
        "source_table_segments": table_segments,
        "source_table_path": source_table_path,
        "emitted_category": emitted_category,
    }


def _iter_hierarchy_sections(hierarchy: object):
    if not isinstance(hierarchy, dict):
        return
    for source_file, raw_domain in hierarchy.items():
        if not isinstance(raw_domain, dict):
            continue
        for domain_key, sections in raw_domain.items():
            if not isinstance(sections, list):
                continue
            for section in sections:
                if not isinstance(section, dict):
                    continue
                for category_name, payload in section.items():
                    yield str(source_file), str(domain_key), str(category_name).strip() or "Misc", payload


def _collect_selected_entries(
    data: dict[str, object],
    target_executable: str | None,
    *,
    require_hint: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object], str | None, str | None, dict[str, object] | None]:
    hierarchy = data.get("hierarchy")
    versions_map = data.get("versions")
    if not isinstance(hierarchy, dict) or not isinstance(versions_map, dict) or not versions_map:
        return [], {}, None, None, None
    version_ctx = _select_active_version(versions_map, target_executable, require_hint=require_hint)
    if version_ctx is None:
        return [], {}, None, None, None
    version_label, version_key, version_info = version_ctx
    super_type_map_raw = data.get("super_type_map")
    super_type_map: dict[str, str] = {}
    if isinstance(super_type_map_raw, dict):
        super_type_map = {str(key).lower(): str(value) for key, value in super_type_map_raw.items()}
    dropdown_values_raw = data.get("_dropdown_values_index")
    dropdown_values = (
        dropdown_values_raw
        if isinstance(dropdown_values_raw, dict)
        else {}
    )

    entries: list[dict[str, object]] = []
    skipped_entries: list[dict[str, object]] = []
    skips_by_reason: dict[str, int] = {}
    discovered_leaf_fields = 0

    def _record_skip(leaf_obj: dict[str, object], reason: str, **extra: object) -> None:
        skips_by_reason[reason] = skips_by_reason.get(reason, 0) + 1
        context = extra.pop("context", None)
        source_category = ""
        source_group = ""
        source_path = ""
        source_super_type = ""
        emitted_category = ""
        if isinstance(context, dict):
            source_category = str(context.get("source_category") or "")
            source_group = str(context.get("source_group") or "")
            source_path = str(context.get("source_table_path") or "")
            source_super_type = str(context.get("source_super_type") or "")
            emitted_category = str(context.get("emitted_category") or "")
        record: dict[str, object] = {
            "reason": reason,
            "category": emitted_category,
            "canonical_category": str(leaf_obj.get("canonical_category") or ""),
            "normalized_name": str(leaf_obj.get("normalized_name") or ""),
            "source_super_type": source_super_type,
            "source_category": source_category,
            "source_group": source_group,
            "source_root_category": source_category,
            "source_table_group": source_group,
            "source_table_path": source_path,
            "source_offsets_file": str(extra.pop("source_offsets_file", "")),
            "source_offsets_domain": str(extra.pop("source_offsets_domain", "")),
            "parse_report_entry_id": to_int(extra.pop("parse_report_entry_id", 0)),
        }
        for key_name, value in extra.items():
            record[str(key_name)] = value
        skipped_entries.append(record)

    entry_counter = 0
    for source_file, source_domain, category_name, payload in _iter_hierarchy_sections(hierarchy):
        for leaf_node, path_segments in _iter_hierarchy_leaf_nodes(payload, (category_name,)):
            discovered_leaf_fields += 1
            versions_raw = leaf_node.get("versions")
            normalized_raw = (
                leaf_node.get("normalized_name")
                or leaf_node.get("canonical_name")
                or leaf_node.get("name")
                or leaf_node.get("display_name")
            )
            if not isinstance(versions_raw, dict):
                _record_skip(
                    leaf_node,
                    "missing_versions",
                    source_offsets_file=source_file,
                    source_offsets_domain=source_domain,
                )
                continue
            version_payload = _select_version_entry(versions_raw, version_label)
            if not isinstance(version_payload, dict):
                _record_skip(
                    leaf_node,
                    "missing_target_version",
                    source_offsets_file=source_file,
                    source_offsets_domain=source_domain,
                    available_versions=[str(key) for key in versions_raw.keys()],
                )
                continue
            if not normalized_raw:
                _record_skip(
                    leaf_node,
                    "missing_normalized_name",
                    source_offsets_file=source_file,
                    source_offsets_domain=source_domain,
                )
                continue
            context = _resolve_hierarchy_context(
                path_segments,
                leaf_node=leaf_node,
                version_payload=cast(dict[str, object], version_payload),
                super_type_map=super_type_map,
            )
            normalized_name = str(normalized_raw).strip()
            canonical_category = str(
                leaf_node.get("canonical_category")
                or context.get("emitted_category")
                or "Misc"
            ).strip() or str(context.get("emitted_category") or "Misc")
            emitted_category = str(context.get("emitted_category") or "Misc").strip() or "Misc"
            display_name = str(
                leaf_node.get("display_name")
                or leaf_node.get("name")
                or normalized_name
            ).strip() or normalized_name

            normalized_payload: dict[str, object] = dict(version_payload)
            if not isinstance(normalized_payload.get("values"), list) and isinstance(dropdown_values, dict):
                dropdown_categories = (
                    canonical_category,
                    str(leaf_node.get("canonical_category") or ""),
                    emitted_category,
                    str(context.get("source_category") or ""),
                    str(context.get("source_group") or ""),
                )
                version_tokens = tuple(
                    dict.fromkeys(
                        [
                            *_split_version_tokens(version_key),
                            *_split_version_tokens(version_label),
                        ]
                    )
                )
                for token in version_tokens:
                    for dropdown_category in dropdown_categories:
                        if not dropdown_category:
                            continue
                        values = dropdown_values.get((dropdown_category.lower(), normalized_name.upper(), token))
                        if isinstance(values, list) and values:
                            normalized_payload["values"] = list(values)
                            break
                    if isinstance(normalized_payload.get("values"), list):
                        break

            address_raw = normalized_payload.get("address")
            if address_raw in (None, ""):
                address_raw = normalized_payload.get("offset")
            if address_raw in (None, ""):
                address_raw = normalized_payload.get("hex")
            if address_raw in (None, ""):
                _record_skip(
                    leaf_node,
                    "missing_address",
                    context=context,
                    source_offsets_file=source_file,
                    source_offsets_domain=source_domain,
                )
                continue
            address = to_int(address_raw)
            if address < 0:
                _record_skip(
                    leaf_node,
                    "invalid_address",
                    context=context,
                    source_offsets_file=source_file,
                    source_offsets_domain=source_domain,
                    address=address_raw,
                )
                continue
            field_type_raw = normalized_payload.get("type") or leaf_node.get("type")
            field_type_normalized = _normalize_offset_type(field_type_raw)
            explicit_length = to_int(normalized_payload.get("length"))
            length_bits = explicit_length
            if length_bits <= 0:
                if field_type_normalized in {"wstring", "string"}:
                    _record_skip(
                        leaf_node,
                        "missing_required_string_length",
                        context=context,
                        source_offsets_file=source_file,
                        source_offsets_domain=source_domain,
                    )
                    continue
                length_bits = _infer_length_bits(field_type_raw, normalized_payload.get("length"))
                if length_bits <= 0:
                    _record_skip(
                        leaf_node,
                        "missing_length",
                        context=context,
                        source_offsets_file=source_file,
                        source_offsets_domain=source_domain,
                    )
                    continue

            source_super_type = str(
                context.get("source_super_type")
                or leaf_node.get("super_type")
                or leaf_node.get("superType")
                or ""
            ).strip()
            if emitted_category.startswith("Stats - "):
                canonical_category = emitted_category

            entry_counter += 1
            entry: dict[str, object] = dict(normalized_payload)
            entry.update({
                "category": emitted_category,
                "name": display_name,
                "display_name": display_name,
                "canonical_category": canonical_category,
                "normalized_name": normalized_name,
                "super_type": source_super_type,
                "selected_version": version_label,
                "selected_version_key": version_key,
                "version_metadata": dict(normalized_payload),
                "source_super_type": source_super_type,
                "source_category": str(context.get("source_category") or ""),
                "source_group": str(context.get("source_group") or ""),
                "source_root_category": str(context.get("source_category") or ""),
                "source_table_group": str(context.get("source_group") or ""),
                "source_table_path": str(context.get("source_table_path") or ""),
                "source_offsets_domain": source_domain,
                "source_offsets_file": source_file,
                "parse_report_entry_id": int(entry_counter),
            })
            if "address" not in entry and "offset" not in entry and "hex" not in entry:
                # Preserve source payload shape while keeping entries addressable.
                entry["address"] = int(address)
            field_type_text = str(field_type_raw or "").strip()
            if field_type_text and "type" not in entry:
                entry["type"] = field_type_text
            if normalized_payload.get("requiresDereference") is True or normalized_payload.get("requires_deref") is True:
                entry["requiresDereference"] = True
            deref = normalized_payload.get("dereferenceAddress")
            if deref in (None, ""):
                deref = normalized_payload.get("deref_offset")
            if deref in (None, ""):
                deref = normalized_payload.get("dereference_address")
            if deref not in (None, ""):
                entry["dereferenceAddress"] = to_int(deref)
            values = normalized_payload.get("values")
            if isinstance(values, list):
                entry["values"] = list(values)
            if isinstance(leaf_node.get("variant_names"), list):
                entry["variant_names"] = list(leaf_node.get("variant_names") or [])
            if leaf_node.get("canonical_name"):
                entry["canonical_name"] = str(leaf_node.get("canonical_name"))
            entries.append(entry)

    skipped_fields = len(skipped_entries)
    emitted_fields = len(entries)
    accounted_fields = emitted_fields + skipped_fields
    report: dict[str, object] = {
        "target_version": version_label,
        "selected_version_key": version_key,
        "discovered_leaf_fields": discovered_leaf_fields,
        "emitted_fields": emitted_fields,
        "skipped_fields": skipped_fields,
        "accounted_fields": accounted_fields,
        "untracked_loss": max(0, discovered_leaf_fields - accounted_fields),
        "skips_by_reason": dict(sorted(skips_by_reason.items())),
        "skipped": skipped_entries,
    }
    return entries, report, version_label, version_key, version_info


def _iter_selected_entries(data: dict[str, object], target_executable: str | None):
    entries, _report, _version_label, _version_key, _version_info = _collect_selected_entries(data, target_executable)
    for entry in entries:
        yield entry


def _build_split_offsets_payload(
    offsets_dir: Path,
    *,
    parse_errors: list[str] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    league_path = offsets_dir / SPLIT_OFFSETS_LEAGUE_FILE
    if not league_path.is_file():
        return None
    missing_domains = [name for name in SPLIT_OFFSETS_DOMAIN_FILES if not (offsets_dir / name).is_file()]
    if missing_domains:
        return None

    league_raw, league_error = _read_json_with_error(league_path)
    if league_error and parse_errors is not None:
        parse_errors.append(league_error)
    if not isinstance(league_raw, dict):
        return None
    versions = league_raw.get("versions")
    if not isinstance(versions, dict) or not versions:
        return None
    dropdown_values: dict[tuple[str, str, str], list[str]] = {}
    dropdown_path = offsets_dir / SPLIT_OFFSETS_OPTIONAL_FILES[0]
    if dropdown_path.is_file():
        dropdown_values = _build_dropdown_values_index(_read_json_cached(dropdown_path))

    hierarchy_payload: dict[str, dict[str, object]] = {}
    discovered_leaf_fields = 0
    for file_name in SPLIT_OFFSETS_DOMAIN_FILES:
        file_path = offsets_dir / file_name
        raw_domain, domain_error = _read_json_with_error(file_path)
        if domain_error and parse_errors is not None:
            parse_errors.append(domain_error)
        if not isinstance(raw_domain, dict):
            return None
        hierarchy_payload[file_name] = raw_domain
        for _source_file, _source_domain, category_name, payload in _iter_hierarchy_sections({file_name: raw_domain}):
            for _leaf_node, _path_segments in _iter_hierarchy_leaf_nodes(payload, (category_name,)):
                discovered_leaf_fields += 1
    if not hierarchy_payload:
        return None

    merged_payload: dict[str, Any] = {
        "hierarchy": hierarchy_payload,
        "versions": dict(versions),
        "_dropdown_values_index": dropdown_values,
        "_split_manifest": {
            "required_files": [SPLIT_OFFSETS_LEAGUE_FILE, *SPLIT_OFFSETS_DOMAIN_FILES],
            "optional_files": list(SPLIT_OFFSETS_OPTIONAL_FILES),
            "discovered_leaf_fields": discovered_leaf_fields,
        },
    }
    super_type_map_raw = league_raw.get("super_type_map")
    split_schema_raw = league_raw.get("split_schema")
    if isinstance(split_schema_raw, dict):
        merged_payload["split_schema"] = dict(split_schema_raw)
    super_type_map: dict[str, str] = {}
    if isinstance(super_type_map_raw, dict):
        super_type_map.update(
            {
                str(key).lower(): str(value)
                for key, value in super_type_map_raw.items()
                if _normalized_super_type_label(value)
            }
        )
    for category_key, super_type_value in _derive_super_type_map_from_split_schema(split_schema_raw).items():
        super_type_map.setdefault(category_key, super_type_value)
    if super_type_map:
        merged_payload["super_type_map"] = super_type_map
    category_normalization = league_raw.get("category_normalization")
    if isinstance(category_normalization, dict):
        merged_payload["category_normalization"] = dict(category_normalization)
    league_category_pointer_map = league_raw.get("league_category_pointer_map")
    if isinstance(league_category_pointer_map, dict):
        merged_payload["league_category_pointer_map"] = dict(league_category_pointer_map)
    if isinstance(league_raw.get("game_info"), dict):
        merged_payload["game_info"] = dict(league_raw.get("game_info") or {})
    if isinstance(league_raw.get("base_pointers"), dict):
        merged_payload["base_pointers"] = dict(league_raw.get("base_pointers") or {})
    return league_path, merged_payload


def _build_player_stats_relations(offsets: list[dict[str, object]]) -> dict[str, object]:
    id_entries: list[dict[str, object]] = []
    season_entries: list[dict[str, object]] = []
    for entry in offsets:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("canonical_category") or entry.get("category") or "").strip()
        if category == PLAYER_STATS_IDS_CATEGORY:
            id_entries.append(entry)
        elif category == PLAYER_STATS_SEASON_CATEGORY:
            season_entries.append(entry)

    def _entry_sort_key(item: dict[str, object]) -> tuple[int, int, str]:
        return (
            to_int(item.get("address") or item.get("offset") or item.get("hex")),
            to_int(item.get("startBit") or item.get("start_bit")),
            str(item.get("normalized_name") or item.get("name") or ""),
        )

    def _id_sort_key(item: dict[str, object]) -> tuple[int, int, int, str]:
        normalized = str(item.get("normalized_name") or "").strip().upper()
        if normalized.startswith("STATSID"):
            suffix = normalized.replace("STATSID", "", 1)
            return (0, int(suffix or 0) if suffix.isdigit() else 0, 0, normalized)
        if normalized == "CURRENTYEARSTATID":
            return (1, 0, 0, normalized)
        addr, bit, name = _entry_sort_key(item)
        return (2, addr, bit, name)

    ordered_ids = [
        str(item.get("normalized_name") or item.get("name") or "").strip()
        for item in sorted(id_entries, key=_id_sort_key)
        if str(item.get("normalized_name") or item.get("name") or "").strip()
    ]
    ordered_season = [
        str(item.get("normalized_name") or item.get("name") or "").strip()
        for item in sorted(season_entries, key=_entry_sort_key)
        if str(item.get("normalized_name") or item.get("name") or "").strip()
    ]
    return {
        "source_category": PLAYER_STATS_IDS_CATEGORY,
        "target_category": PLAYER_STATS_SEASON_CATEGORY,
        "relation_type": "season_only",
        "id_fields": ordered_ids,
        "target_fields": ordered_season,
    }


def _extract_player_stats_relations(config_data: dict | None) -> dict[str, Any]:
    if not isinstance(config_data, dict):
        return {}
    relations = config_data.get("relations")
    if not isinstance(relations, dict):
        return {}
    relation = relations.get("player_stats")
    if not isinstance(relation, dict):
        return {}
    return dict(relation)


def _sync_player_stats_relations(config_data: dict | None) -> None:
    global PLAYER_STATS_RELATIONS
    PLAYER_STATS_RELATIONS = _extract_player_stats_relations(config_data)


def _convert_merged_offsets_schema(raw: object, target_exe: str | None) -> dict | None:
    """Validate and normalize hierarchy-first schema for the target executable."""
    if not isinstance(raw, dict):
        return None
    if not isinstance(raw.get("hierarchy"), dict):
        return None
    if not isinstance(raw.get("versions"), dict):
        return None

    selected_entries, parse_report, _version_label, version_key, version_info = _collect_selected_entries(
        cast(dict[str, object], raw),
        target_exe,
        require_hint=True,
    )
    if not selected_entries or not version_key or not isinstance(version_info, dict):
        return None

    player_stats_relations = _build_player_stats_relations(selected_entries)
    converted: dict[str, object] = {
        "hierarchy": dict(cast(dict[str, object], raw.get("hierarchy") or {})),
        "relations": {"player_stats": player_stats_relations},
        "_parse_report": parse_report,
        "versions": {version_key: dict(version_info)},
    }
    if isinstance(raw.get("_split_manifest"), dict):
        converted["_split_manifest"] = dict(cast(dict[str, object], raw.get("_split_manifest") or {}))
    if isinstance(raw.get("_dropdown_values_index"), dict):
        converted["_dropdown_values_index"] = dict(cast(dict[str, object], raw.get("_dropdown_values_index") or {}))
    if isinstance(raw.get("category_normalization"), dict):
        converted["category_normalization"] = raw["category_normalization"]
    if isinstance(raw.get("super_type_map"), dict):
        converted["super_type_map"] = raw["super_type_map"]
    elif isinstance(raw.get("split_schema"), dict):
        derived_super_type_map = _derive_super_type_map_from_split_schema(raw.get("split_schema"))
        if derived_super_type_map:
            converted["super_type_map"] = derived_super_type_map
    if isinstance(raw.get("league_category_pointer_map"), dict):
        converted["league_category_pointer_map"] = raw["league_category_pointer_map"]
    if isinstance(raw.get("split_schema"), dict):
        converted["split_schema"] = raw["split_schema"]

    base_ptrs = version_info.get("base_pointers") if isinstance(version_info.get("base_pointers"), dict) else None
    if base_ptrs:
        converted["base_pointers"] = dict(base_ptrs)
    game_info = version_info.get("game_info") if isinstance(version_info.get("game_info"), dict) else None
    if game_info:
        converted["game_info"] = dict(game_info)
    return converted


def _load_offset_config_file(target_executable: str | None = None) -> tuple[Path | None, dict | None]:
    """Locate and parse split offsets files for the given executable."""
    with timed("offsets.load_offset_config_file"):
        target_key = (target_executable or "").lower()
        if target_key:
            cached = _OFFSET_CACHE.get_target(target_key)
            if cached is not None:
                return cached.path, dict(cached.data)
        base_dir = Path(__file__).resolve().parent.parent
        search_dirs = [
            base_dir / "Offsets",
            base_dir / "offsets",
        ]
        resolver = OffsetResolver(convert_schema=_convert_merged_offsets_schema)
        parse_errors: list[str] = []
        for folder in search_dirs:
            split_payload = _build_split_offsets_payload(folder, parse_errors=parse_errors)
            if split_payload is None:
                continue
            path, raw_payload = split_payload
            resolved = resolver.resolve(raw_payload, target_executable)
            if not isinstance(resolved, dict):
                continue
            payload = dict(resolved)
            if target_key:
                _OFFSET_CACHE.set_target(CachedOffsetPayload(path=path, target_key=target_key, data=payload))
            return path, payload
        if parse_errors:
            unique_errors: list[str] = []
            seen_error_keys: set[str] = set()
            for message in parse_errors:
                key = message.casefold()
                if key in seen_error_keys:
                    continue
                seen_error_keys.add(key)
                unique_errors.append(message)
            details = " ; ".join(unique_errors)
            raise OffsetSchemaError(
                "Offsets files were found, but one or more required files could not be parsed. "
                f"{details}"
            )
        return None, None


def _build_offset_index(offsets: list[dict]) -> None:
    """Create strict exact-match lookup maps for offsets entries."""
    _offset_index.clear()
    _offset_normalized_index.clear()
    _offset_hierarchy_index.clear()
    for entry in offsets:
        if not isinstance(entry, dict):
            continue
        category_raw = str(entry.get("category", "")).strip()
        name_raw = str(entry.get("name", "")).strip()
        if not name_raw:
            continue
        _offset_index[(category_raw, name_raw)] = entry
        canonical = str(entry.get("canonical_category", "")).strip()
        normalized = str(entry.get("normalized_name", "")).strip()
        if canonical and normalized:
            _offset_normalized_index[(canonical, normalized)] = entry
        source_super_type = str(
            entry.get("source_super_type")
            or entry.get("super_type")
            or entry.get("superType")
            or ""
        ).strip()
        source_category = str(entry.get("source_category") or "").strip()
        source_group = str(entry.get("source_group") or "").strip()
        if source_super_type and source_category and normalized:
            _offset_hierarchy_index[(source_super_type, source_category, source_group, normalized)] = entry


def _find_offset_entry(name: str, category: str | None = None) -> dict | None:
    """Return the offset entry matching the provided exact name/category."""
    exact_name = name.strip()
    if category:
        return _offset_index.get((category.strip(), exact_name))
    for (cat, entry_name), entry in _offset_index.items():
        if entry_name == exact_name and (category is None or cat == category.strip()):
            return entry
    return None


def _find_offset_entry_by_normalized(canonical_category: str, normalized_name: str) -> dict | None:
    """Return an offsets entry by exact canonical_category + normalized_name."""
    return _offset_normalized_index.get((canonical_category, normalized_name))


def _find_offset_entry_by_hierarchy(
    source_super_type: str,
    source_category: str,
    source_group: str,
    normalized_name: str,
) -> dict | None:
    """Return an offsets entry by exact hierarchy + normalized name."""
    key = (
        str(source_super_type or "").strip(),
        str(source_category or "").strip(),
        str(source_group or "").strip(),
        str(normalized_name or "").strip(),
    )
    return _offset_hierarchy_index.get(key)


def _load_dropdowns_map() -> dict[str, dict[str, list[str]]]:
    """Load dropdown metadata once per process from Offsets/dropdowns.json when present."""
    with timed("offsets.load_dropdowns"):
        base_dir = Path(__file__).resolve().parent.parent
        search_dirs = [base_dir / "Offsets", base_dir / "offsets"]
        return _OFFSET_REPOSITORY.load_dropdowns(search_dirs=search_dirs)


def _derive_version_label(executable: str | None) -> str | None:
    """Return a version label like '2K26' based on the executable name."""
    if not executable:
        return None
    m = re.search(r"2k(\d{2})", executable.lower())
    if not m:
        return None
    return f"2K{m.group(1)}"


def _resolve_version_context(
    data: dict[str, Any] | None,
    target_executable: str | None,
) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
    """Return (version_label, base_pointers, game_info) for the active target."""
    version_label = _derive_version_label(target_executable)
    if not isinstance(data, dict):
        return version_label, {}, {}

    versions_raw = data.get("versions")
    versions_map = versions_raw if isinstance(versions_raw, dict) else {}
    version_info: dict[str, Any] = {}
    if version_label and versions_map:
        candidate = versions_map.get(version_label)
        if not isinstance(candidate, dict):
            candidate = versions_map.get(version_label.upper())
        if not isinstance(candidate, dict):
            candidate = versions_map.get(version_label.lower())
        if isinstance(candidate, dict):
            version_info = candidate

    version_base = version_info.get("base_pointers")
    base_pointers = version_base if isinstance(version_base, dict) else {}

    version_game = version_info.get("game_info")
    game_info = version_game if isinstance(version_game, dict) else {}
    stride_constants = version_info.get("stride_constants")
    if isinstance(stride_constants, dict):
        merged_game_info = dict(game_info)
        merged_game_info.update(stride_constants)
        game_info = merged_game_info

    return version_label, base_pointers, game_info


def _load_categories() -> dict[str, list[dict]]:
    """
    Load editor categories from the active offsets payload.
    Returns a dictionary mapping category names to lists of field
    definitions. If parsing fails or no offsets are available, an empty
    dictionary is returned.
    """
    dropdowns = _load_dropdowns_map()
    CATEGORY_SUPER_TYPES.clear()
    CATEGORY_CANONICAL.clear()
    category_normalization: dict[str, str] = {}
    try:
        if isinstance(_offset_config, dict):
            raw_norm = _offset_config.get("category_normalization")
            if isinstance(raw_norm, dict):
                category_normalization = {str(k).lower(): str(v) for k, v in raw_norm.items()}
    except Exception:
        category_normalization = {}

    super_type_map: dict[str, str] = {}
    try:
        if isinstance(_offset_config, dict):
            raw_map = _offset_config.get("super_type_map")
            if isinstance(raw_map, dict):
                super_type_map = {str(k).lower(): str(v) for k, v in raw_map.items()}
    except Exception:
        super_type_map = {}

    super_type_mismatches: set[str] = set()

    def _emit_super_type_warnings() -> None:
        if not super_type_mismatches:
            return
        warning_text = " ; ".join(sorted(super_type_mismatches))
        print(f"Offset warnings: super_type_map overrides: {warning_text}")

    def _register_category_metadata(cat_label: str, entry: dict | None = None) -> None:
        """Capture super type and canonical label for a category."""
        if not cat_label:
            return
        cat_key = str(cat_label)
        if cat_key not in CATEGORY_SUPER_TYPES:
            entry_super = None
            if isinstance(entry, dict):
                entry_super = entry.get("super_type") or entry.get("superType")
            entry_super = _normalized_super_type_label(entry_super)
            map_super = super_type_map.get(cat_key.lower())
            # Allow explicit mapping to override mis-labeled entries (e.g., team tabs tagged as Players).
            if map_super:
                if entry_super and str(entry_super).lower() != str(map_super).lower():
                    super_type_mismatches.add(f"{cat_key}: {entry_super} -> {map_super}")
                entry_super = map_super
            if entry_super is None:
                cat_lower = cat_key.lower()
                if cat_lower.startswith("team "):
                    entry_super = "Teams"
            if entry_super:
                CATEGORY_SUPER_TYPES[cat_key] = str(entry_super)
        if cat_key not in CATEGORY_CANONICAL:
            canonical = None
            if isinstance(entry, dict):
                canonical = entry.get("canonical_category")
            if canonical is None:
                canonical = category_normalization.get(cat_key.lower())
            CATEGORY_CANONICAL[cat_key] = str(canonical) if canonical else cat_key

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
            offset_val = to_int(field.get("address") or field.get("offset") or field.get("hex"))
        if offset_val is not None and offset_val >= 0:
            offset_int = int(offset_val)
            field["address"] = offset_int
            field.setdefault("offset", hex(offset_int))
            if provided_hex is None:
                provided_hex = f"0x{offset_int:X}"
        if provided_hex is not None:
            field["hex"] = provided_hex
        if "startBit" not in field or field.get("startBit") in (None, ""):
            start_val = start_bit_val
            if start_val is None:
                start_val = to_int(field.get("start_bit"))
            field["startBit"] = int(start_val or 0)
        if "start_bit" in field and "startBit" in field:
            field.pop("start_bit", None)
        if "length" not in field or to_int(field.get("length")) <= 0:
            length = length_val
            if length is None:
                length = to_int(field.get("length") or field.get("size"))
            if length is not None and length > 0:
                field["length"] = int(length)
        if source_entry is not None and source_entry.get("type") and not field.get("type"):
            field["type"] = source_entry.get("type")
        if source_entry is not None:
            for key_name in (
                "canonical_category",
                "normalized_name",
                "super_type",
                "type_normalized",
                "source_root_category",
                "source_table_group",
                "source_table_path",
                "source_offsets_domain",
                "source_offsets_file",
                "length_inferred",
                "start_bit_inferred",
                "parse_report_entry_id",
                "selected_version",
                "selected_version_key",
            ):
                if source_entry.get(key_name) and not field.get(key_name):
                    field[key_name] = source_entry.get(key_name)

    def _entry_to_field(entry: dict, display_name: str, target_category: str | None = None) -> dict | None:
        offset_val = to_int(entry.get("address") or entry.get("offset") or entry.get("hex"))
        length_val = to_int(entry.get("length"))
        if offset_val <= 0 or length_val <= 0:
            return None
        start_bit = to_int(entry.get("startBit"))
        field: dict[str, object] = {
            "name": display_name,
            "offset": hex(offset_val),
            "startBit": int(start_bit),
            "length": int(length_val),
        }
        if entry.get("requiresDereference"):
            field["requiresDereference"] = True
            field["dereferenceAddress"] = to_int(entry.get("dereferenceAddress"))
        raw_type = entry.get("type")
        normalized_type = entry.get("type_normalized")
        if raw_type not in (None, ""):
            field["type_raw"] = raw_type
        if normalized_type not in (None, ""):
            field["type_normalized"] = normalized_type
            field["type"] = normalized_type
        elif raw_type not in (None, ""):
            field["type"] = raw_type
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
                display_name = f"{prefix} - {display_name}" if display_name else prefix
        entry_type = str(entry.get("type", "")).strip().lower()
        if entry_type in {"blank", "folder", "section", "class"}:
            return None
        offset_val = to_int(entry.get("offset") or entry.get("address"))
        if offset_val < 0:
            return None
        info = entry.get("info") if isinstance(entry.get("info"), dict) else {}
        start_raw = entry.get("startBit") or entry.get("start_bit")
        if isinstance(info, dict):
            start_info = info.get("startbit") or info.get("startBit") or info.get("bit_start")
            if start_info is not None:
                start_raw = start_info
        explicit_start = start_raw is not None
        start_bit = to_int(start_raw)
        if start_bit < 0:
            start_bit = 0
        length_bits = to_int(entry.get("length"))
        if length_bits <= 0:
            size_val = to_int(entry.get("size"))
            if entry_type in {"combo", "bitfield", "bool", "boolean"}:
                length_bits = size_val
            else:
                length_bits = size_val * 8
        if length_bits <= 0 and isinstance(info, dict):
            length_bits = to_int(info.get("length") or info.get("bits"))
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
                deref = to_int(info.get("offset") or info.get("deviation"))
                if deref > 0:
                    field["requiresDereference"] = True
                    field["dereferenceAddress"] = deref
        _finalize_field_metadata(
            field,
            cat_label,
            offset_val=offset_val,
            start_bit_val=int(start_bit),
            length_val=int(length_bits),
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
        """Template merging is disabled."""
        return

    base_categories: dict[str, list[dict]] = {}
    bit_cursor: dict[tuple[str, int], int] = {}
    seen_fields_global: dict[str, set[str]] = {}
    if isinstance(_offset_config, dict):
        categories: dict[str, list[dict]] = {}
        combined_sections: list[dict] = []
        hierarchy_obj = _offset_config.get("hierarchy")

        if isinstance(hierarchy_obj, dict):
            target_exec = _current_offset_target or MODULE_NAME
            combined_sections.extend(
                entry
                for entry in _iter_selected_entries(cast(dict[str, object], _offset_config), target_exec)
                if isinstance(entry, dict)
            )

        def _extend(section: object) -> None:
            if isinstance(section, list):
                combined_sections.extend(item for item in section if isinstance(item, dict))

        if not combined_sections:
            _extend(_offset_config.get("offsets"))
            for key, value in _offset_config.items():
                if key in {
                    "offsets",
                    "hierarchy",
                    "versions",
                    "relations",
                    "_parse_report",
                    "_split_manifest",
                    "_dropdown_values_index",
                    "super_type_map",
                    "category_normalization",
                    "game_info",
                    "base_pointers",
                }:
                    continue
                _extend(value)
        seen_fields: set[tuple[str, str]] = set()
        for entry in combined_sections:
            cat_name = str(entry.get("category", "Misc")).strip() or "Misc"
            field_name = str(entry.get("name", "")).strip()
            if not field_name:
                continue
            _register_category_metadata(cat_name, entry)
            key = (cat_name.lower(), field_name.lower())
            if key in seen_fields:
                continue
            seen_fields.add(key)
            offset_val = to_int(entry.get("address") or entry.get("offset") or entry.get("hex"))
            if offset_val < 0:
                continue
            start_bit = to_int(entry.get("startBit") or entry.get("start_bit"))
            length_val = to_int(entry.get("length"))
            size_val = to_int(entry.get("size"))
            entry_type = str(entry.get("type", "")).lower()
            if length_val <= 0:
                if entry_type in ("bitfield", "bool", "boolean", "combo"):
                    length_val = size_val
                elif entry_type in ("number", "slider", "int", "uint", "pointer", "float"):
                    length_val = size_val * 8
            if length_val <= 0:
                length_val = _infer_length_bits(entry.get("type"), entry.get("length"))
            if length_val <= 0:
                continue
            field: dict[str, object] = {
                "name": field_name,
                "offset": hex(offset_val),
                "startBit": int(start_bit),
                "length": int(length_val),
            }
            raw_type = entry.get("type")
            normalized_type = entry.get("type_normalized")
            if raw_type not in (None, ""):
                field["type_raw"] = raw_type
            if normalized_type not in (None, ""):
                field["type_normalized"] = normalized_type
                field["type"] = normalized_type
            elif raw_type not in (None, ""):
                field["type"] = raw_type
            if entry.get("requiresDereference"):
                field["requiresDereference"] = True
                field["dereferenceAddress"] = to_int(entry.get("dereferenceAddress"))
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
                    offset_int = to_int(field.get("offset"))
                    start_val = to_int(field.get("startBit") or field.get("start_bit"))
                    length_val = to_int(field.get("length"))
                    key = (cat_name, offset_int)
                    bit_cursor[key] = max(bit_cursor.get(key, 0), start_val + max(length_val, 0))
    if base_categories:
        categories = {key: list(value) for key, value in base_categories.items()}
        if categories:
            _emit_super_type_warnings()
            return categories

    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent
    unified_candidates: list[Path] = []
    offsets_dir = project_root / "Offsets"
    offsets_dir_lower = project_root / "offsets"
    try:
        for fname in _derive_offset_candidates(MODULE_NAME):
            for folder in (project_root, offsets_dir, offsets_dir_lower):
                p = folder / fname
                if p.is_file():
                    unified_candidates.append(p)
                    break
    except Exception:
        pass
    if not unified_candidates:
        for fname in UNIFIED_FILES:
            for folder in (project_root, offsets_dir, offsets_dir_lower):
                p = folder / fname
                if p.is_file():
                    unified_candidates.append(p)
                    break
    for upath in unified_candidates:
        try:
            with open(upath, "r", encoding="utf-8") as f:
                udata = json.load(f)
            categories = {key: list(value) for key, value in base_categories.items()}
            for cat_name, fields in categories.items():
                seen = seen_fields_global.setdefault(cat_name, set())
                for field in fields:
                    if not isinstance(field, dict):
                        continue
                    seen.add(str(field.get("name", "")))
                    offset_int = to_int(field.get("offset"))
                    start_val = to_int(field.get("startBit") or field.get("start_bit"))
                    length_val = to_int(field.get("length"))
                    key = (cat_name, offset_int)
                    bit_cursor[key] = max(bit_cursor.get(key, 0), start_val + max(length_val, 0))
            if isinstance(udata, dict):
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
                            _register_category_metadata(key, entry)
                            _finalize_field_metadata(
                                entry,
                                key,
                                source_entry=entry,
                            )
                            normalized_fields.append(entry)
                            seen.add(str(entry.get("name", "")))
                            offset_int = to_int(entry.get("offset"))
                            start_val = to_int(entry.get("startBit") or entry.get("start_bit"))
                            length_val = to_int(entry.get("length"))
                            bit_cursor[(key, offset_int)] = max(
                                bit_cursor.get((key, offset_int), 0),
                                start_val + max(length_val, 0),
                            )
                        categories[key] = normalized_fields
                pinf = udata.get("Player_Info")
                if isinstance(pinf, dict):
                    new_cats: dict[str, list[dict]] = {}

                    def _append_field(cat_label: str, field_name: str, prefix: str | None, fdef: dict) -> None:
                        display_name = field_name if prefix in (None, "") else f"{prefix} - {field_name}"
                        off_raw = fdef.get("address") or fdef.get("offset_from_base") or fdef.get("offset")
                        offset_int = to_int(off_raw)
                        if offset_int < 0:
                            return
                        f_type = str(fdef.get("type", "")).lower()
                        start_raw = fdef.get("startBit") or fdef.get("start_bit") or fdef.get("bit_start")
                        explicit_start = start_raw is not None
                        start_bit_local = to_int(start_raw)
                        size_int = to_int(fdef.get("size"))
                        length_int = to_int(fdef.get("length"))
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
                            key_local = (cat_label, offset_int)
                            start_bit_local = bit_cursor.get(key_local, 0)
                            bit_cursor[key_local] = start_bit_local + length_int
                        entry_local: dict[str, object] = {
                            "name": display_name,
                            "offset": hex(offset_int),
                            "startBit": int(start_bit_local),
                            "length": int(length_int),
                        }
                        if f_type:
                            entry_local["type"] = f_type
                        if f_type == "combo":
                            try:
                                value_count = min(1 << length_int, 64)
                                entry_local["values"] = [str(i) for i in range(max(value_count, 0))]
                            except Exception:
                                pass
                        try:
                            dcat = dropdowns.get(cat_label) or dropdowns.get(cat_label.title()) or {}
                            if display_name in dcat and isinstance(dcat[display_name], list):
                                entry_local.setdefault("values", list(dcat[display_name]))
                            elif field_name.upper().startswith("PLAYTYPE") and isinstance(dcat.get("PLAYTYPE"), list):
                                entry_local.setdefault("values", list(dcat["PLAYTYPE"]))
                        except Exception:
                            pass
                        seen_set = seen_fields_global.setdefault(cat_label, set())
                        if display_name in seen_set:
                            return
                        seen_set.add(display_name)
                        bit_cursor[(cat_label, offset_int)] = max(
                            bit_cursor.get((cat_label, offset_int), 0),
                            start_bit_local + length_int,
                        )
                        _finalize_field_metadata(
                            entry_local,
                            cat_label,
                            offset_val=offset_int,
                            start_bit_val=start_bit_local,
                            length_val=length_int,
                            source_entry=fdef,
                        )
                        new_cats.setdefault(cat_label, []).append(entry_local)

                    def _walk_field_map(base_label: str, mapping: dict, prefix: str | None = None) -> None:
                        for fname, fdef in mapping.items():
                            if not isinstance(fdef, dict):
                                continue
                            has_direct_keys = any(
                                key_local in fdef
                                for key_local in (
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
                                cat_label_local = base_label
                                _append_field(cat_label_local, fname, prefix, fdef)
                            else:
                                next_prefix = fname if prefix is None else f"{prefix} - {fname}"
                                _walk_field_map(base_label, fdef, next_prefix)

                    for cat_key, field_map in pinf.items():
                        if not isinstance(field_map, dict):
                            continue
                        cat_name = cat_key[:-8] if cat_key.endswith("_offsets") else cat_key
                        cat_name = cat_name.title()
                        _register_category_metadata(cat_name, {"super_type": super_type_map.get(cat_name.lower())})
                        _walk_field_map(cat_name, field_map)
                    if new_cats:
                        for key_local, vals in new_cats.items():
                            if key_local in categories:
                                categories[key_local].extend(vals)
                            else:
                                categories[key_local] = vals
                if categories:
                    _emit_super_type_warnings()
                    return categories
        except Exception:
            pass
    if base_categories:
        categories = {key: list(value) for key, value in base_categories.items()}
        if categories:
            _emit_super_type_warnings()
            return categories
    return {}


def _normalize_chain_steps(chain_data: object) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    if chain_data is None:
        return steps
    if not isinstance(chain_data, list):
        raise OffsetSchemaError("Pointer chain must be a list.")
    allowed_keys = {"offset", "post_add", "dereference"}
    for index, hop in enumerate(chain_data):
        if not isinstance(hop, dict):
            raise OffsetSchemaError(f"Pointer chain step at index {index} must be an object.")
        unknown = [key for key in hop.keys() if key not in allowed_keys]
        if unknown:
            raise OffsetSchemaError(
                f"Pointer chain step at index {index} contains unsupported keys: {', '.join(sorted(unknown))}."
            )
        steps.append({
            "offset": to_int(hop.get("offset")),
            "post_add": to_int(hop.get("post_add")),
            "dereference": bool(hop.get("dereference")),
        })
    return steps


def _parse_pointer_chain_config(base_cfg: dict | None) -> list[dict[str, object]]:
    chains: list[dict[str, object]] = []
    if not isinstance(base_cfg, dict):
        return chains
    allowed_keys = {"address", "chain", "absolute", "direct_table", "final_offset"}
    unknown = [key for key in base_cfg.keys() if key not in allowed_keys]
    if unknown:
        raise OffsetSchemaError(f"Base pointer config contains unsupported keys: {', '.join(sorted(unknown))}.")
    addr_raw = base_cfg.get("address")
    if addr_raw is None:
        return chains
    base_addr = to_int(addr_raw)
    final_offset = to_int(base_cfg.get("final_offset"))
    is_absolute = bool(base_cfg.get("absolute"))
    chain_data = base_cfg.get("chain")
    if chain_data is None:
        raise OffsetSchemaError("Base pointer config must include a 'chain' list (use [] for direct table pointers).")
    if "direct_table" in base_cfg:
        direct_table = bool(base_cfg.get("direct_table"))
    else:
        # Empty chains represent direct table bases unless explicitly overridden.
        direct_table = isinstance(chain_data, list) and len(chain_data) == 0
    steps = _normalize_chain_steps(chain_data)
    chains.append({
        "rva": base_addr,
        "steps": steps,
        "final_offset": final_offset,
        "absolute": is_absolute,
        "direct_table": direct_table,
    })
    return chains


def _apply_offset_config(data: dict | None) -> None:
    """Update module-level constants using the loaded offset data."""
    global MODULE_NAME, PLAYER_TABLE_RVA, PLAYER_STRIDE
    global PLAYER_PTR_CHAINS, OFF_LAST_NAME, OFF_FIRST_NAME
    global OFF_TEAM_PTR, OFF_TEAM_ID, OFF_TEAM_NAME, NAME_MAX_CHARS
    global FIRST_NAME_ENCODING, LAST_NAME_ENCODING, TEAM_NAME_ENCODING
    global TEAM_STRIDE, TEAM_NAME_OFFSET, TEAM_NAME_LENGTH, TEAM_PLAYER_SLOT_COUNT
    global TEAM_PTR_CHAINS, TEAM_RECORD_SIZE, TEAM_FIELD_DEFS
    global STAFF_STRIDE, STAFF_RECORD_SIZE, STAFF_PTR_CHAINS, STAFF_NAME_OFFSET, STAFF_NAME_LENGTH, STAFF_NAME_ENCODING
    global STADIUM_STRIDE, STADIUM_RECORD_SIZE, STADIUM_PTR_CHAINS, STADIUM_NAME_OFFSET, STADIUM_NAME_LENGTH, STADIUM_NAME_ENCODING
    if not data:
        raise OffsetSchemaError(f"{OFFSETS_BUNDLE_FILE} is missing or empty.")
    _version_label, base_pointers, game_info = _resolve_version_context(
        cast(dict[str, Any], data),
        _current_offset_target or MODULE_NAME,
    )
    combined_offsets = [
        entry
        for entry in _iter_selected_entries(cast(dict[str, object], data), _current_offset_target or MODULE_NAME)
        if isinstance(entry, dict)
    ]
    if not combined_offsets:
        _offset_index.clear()
        _offset_normalized_index.clear()
        _offset_hierarchy_index.clear()
        raise OffsetSchemaError(f"No offsets defined in {OFFSETS_BUNDLE_FILE}.")
    _build_offset_index(combined_offsets)

    errors: list[str] = []
    warnings: list[str] = []

    module_candidate = game_info.get("executable")
    if module_candidate:
        MODULE_NAME = str(module_candidate)

    def _pointer_address(defn: dict | None) -> tuple[int, bool]:
        if not isinstance(defn, dict):
            return 0, False
        if "address" not in defn:
            return 0, False
        return to_int(defn.get("address")), True

    # Validate base pointers and mapped game_info size keys using exact keys only.
    for key_name in REQUIRED_LIVE_BASE_POINTER_KEYS:
        entry = base_pointers.get(key_name)
        if not isinstance(entry, dict):
            errors.append(f"Missing required base pointer '{key_name}'.")
            continue
        addr_val, has_addr = _pointer_address(entry)
        if not has_addr:
            errors.append(f"Base pointer '{key_name}' is missing required 'address' value.")
            continue
        if addr_val <= 0:
            errors.append(f"Base pointer '{key_name}' address must be > 0.")
    for pointer_key, size_key in BASE_POINTER_SIZE_KEY_MAP.items():
        if pointer_key not in base_pointers:
            continue
        entry = base_pointers.get(pointer_key)
        if not isinstance(entry, dict):
            errors.append(f"Base pointer '{pointer_key}' must be an object.")
            continue
        if size_key is None:
            continue
        size_val = to_int(game_info.get(size_key))
        if size_val <= 0:
            errors.append(f"Missing or invalid game_info '{size_key}' for base pointer '{pointer_key}'.")

    PLAYER_STRIDE = max(0, to_int(game_info.get("playerSize")) or 0)
    TEAM_STRIDE = max(0, to_int(game_info.get("teamSize")) or 0)
    STAFF_STRIDE = max(0, to_int(game_info.get("staffSize")) or 0)
    STADIUM_STRIDE = max(0, to_int(game_info.get("stadiumSize")) or 0)
    TEAM_RECORD_SIZE = TEAM_STRIDE
    STAFF_RECORD_SIZE = STAFF_STRIDE
    STADIUM_RECORD_SIZE = STADIUM_STRIDE

    PLAYER_PTR_CHAINS.clear()
    player_base = base_pointers.get("Player")
    player_addr, player_addr_defined = _pointer_address(player_base if isinstance(player_base, dict) else None)
    if player_addr_defined:
        PLAYER_TABLE_RVA = player_addr
        player_chains = _parse_pointer_chain_config(player_base)
        if player_chains:
            PLAYER_PTR_CHAINS.extend(player_chains)
        else:
            errors.append("Player base pointer chain produced no resolvable entries.")
    else:
        PLAYER_TABLE_RVA = 0

    TEAM_PTR_CHAINS.clear()
    team_base = base_pointers.get("Team")
    team_addr, team_addr_defined = _pointer_address(team_base if isinstance(team_base, dict) else None)
    global TEAM_TABLE_RVA
    TEAM_TABLE_RVA = team_addr if team_addr_defined else 0
    if team_addr_defined:
        team_chains = _parse_pointer_chain_config(team_base)
        if team_chains:
            TEAM_PTR_CHAINS.extend(team_chains)
        else:
            errors.append("Team base pointer chain produced no resolvable entries.")

    DRAFT_PTR_CHAINS.clear()
    draft_entry = base_pointers.get("DraftClass")
    if isinstance(draft_entry, dict):
        draft_chains = _parse_pointer_chain_config(draft_entry)
        if draft_chains:
            DRAFT_PTR_CHAINS.extend(draft_chains)

    def _entry_address(entry: dict[str, object]) -> int:
        return to_int(entry.get("address") or entry.get("offset") or entry.get("hex"))

    def _find_schema_field(source_file: str, normalized_name: str) -> dict[str, object] | None:
        source_key = str(source_file or "").strip().casefold()
        normalized_key = str(normalized_name or "").strip().upper()
        if not source_key or not normalized_key:
            return None
        candidates: list[dict[str, object]] = []
        for entry in combined_offsets:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("source_offsets_file") or "").strip().casefold() != source_key:
                continue
            if str(entry.get("normalized_name") or "").strip().upper() != normalized_key:
                continue
            candidates.append(cast(dict[str, object], entry))
        if not candidates:
            return None

        def _score(candidate: dict[str, object]) -> tuple[int, int, int, int, int]:
            category_text = str(candidate.get("canonical_category") or candidate.get("category") or "").strip().lower()
            non_stats = 0 if category_text.startswith("stats") else 1
            deref_raw = (
                candidate.get("dereferenceAddress")
                or candidate.get("deref_offset")
                or candidate.get("dereference_address")
            )
            has_deref = 1 if to_int(deref_raw) > 0 else 0
            addr = _entry_address(candidate)
            addr_valid = 1 if addr > 0 else 0
            length_val = to_int(candidate.get("length"))
            return (non_stats, has_deref, addr_valid, addr, length_val)

        return max(candidates, key=_score)

    def _require_field(key_name: str) -> dict | None:
        source_file, norm_name = REQUIRED_OFFSET_SCHEMA_FIELDS[key_name]
        entry = _find_schema_field(source_file, norm_name)
        if not isinstance(entry, dict):
            errors.append(
                "Missing required offset field "
                f"'{source_file}:{norm_name}'."
            )
            return None
        return entry

    first_entry = _require_field("player_first_name")
    OFF_FIRST_NAME = (
        to_int(first_entry.get("address") or first_entry.get("offset") or first_entry.get("hex"))
        if isinstance(first_entry, dict)
        else 0
    )
    if OFF_FIRST_NAME < 0:
        errors.append("Vitals/FIRSTNAME address must be >= 0.")
        OFF_FIRST_NAME = 0
    FIRST_NAME_ENCODING = "ascii" if str((first_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16"
    first_len = to_int((first_entry or {}).get("length"))
    if first_len <= 0:
        errors.append("Vitals/FIRSTNAME length must be > 0.")

    last_entry = _require_field("player_last_name")
    OFF_LAST_NAME = (
        to_int(last_entry.get("address") or last_entry.get("offset") or last_entry.get("hex"))
        if isinstance(last_entry, dict)
        else 0
    )
    if OFF_LAST_NAME < 0:
        errors.append("Vitals/LASTNAME address must be >= 0.")
        OFF_LAST_NAME = 0
    LAST_NAME_ENCODING = "ascii" if str((last_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16"
    last_len = to_int((last_entry or {}).get("length"))
    if last_len <= 0:
        errors.append("Vitals/LASTNAME length must be > 0.")
    if first_len > 0 or last_len > 0:
        NAME_MAX_CHARS = max(first_len or 0, last_len or 0)

    team_entry = _require_field("player_current_team")
    OFF_TEAM_PTR = to_int(
        (team_entry or {}).get("dereferenceAddress")
        or (team_entry or {}).get("deref_offset")
        or (team_entry or {}).get("dereference_address")
    )
    if OFF_TEAM_PTR <= 0:
        team_type = str((team_entry or {}).get("type_normalized") or (team_entry or {}).get("type") or "").strip().lower()
        if team_type in {"pointer", "address", "ptr", "uint64", "ulonglong", "qword"}:
            # CURRENTTEAM is frequently stored as a direct uint64 team-record pointer.
            OFF_TEAM_PTR = to_int((team_entry or {}).get("address") or (team_entry or {}).get("offset") or (team_entry or {}).get("hex"))
    if OFF_TEAM_PTR < 0:
        errors.append("Vitals/CURRENTTEAM dereference address must be >= 0.")
        OFF_TEAM_PTR = 0
    OFF_TEAM_ID = to_int((team_entry or {}).get("address") or (team_entry or {}).get("offset") or (team_entry or {}).get("hex")) or 0
    if OFF_TEAM_ID <= 0:
        errors.append("Vitals/CURRENTTEAM address must be > 0.")

    team_name_entry = _require_field("team_name")
    TEAM_NAME_OFFSET = to_int(
        (team_name_entry or {}).get("address")
        or (team_name_entry or {}).get("offset")
        or (team_name_entry or {}).get("hex")
    ) or 0
    if TEAM_NAME_OFFSET < 0:
        errors.append("Team Vitals/TEAMNAME address must be >= 0.")
        TEAM_NAME_OFFSET = 0
    team_name_type = str((team_name_entry or {}).get("type", "")).lower()
    TEAM_NAME_ENCODING = "ascii" if team_name_type in ("string", "text") else "utf16"
    TEAM_NAME_LENGTH = to_int((team_name_entry or {}).get("length")) or 0
    if TEAM_NAME_LENGTH <= 0:
        errors.append("Team Vitals/TEAMNAME length must be > 0.")
    OFF_TEAM_NAME = TEAM_NAME_OFFSET

    team_player_entries = [
        entry
        for entry in combined_offsets
        if str(entry.get("canonical_category", "")) == "Team Players"
    ]
    if team_player_entries:
        TEAM_PLAYER_SLOT_COUNT = len(team_player_entries)
    TEAM_FIELD_DEFS.clear()
    for label, normalized_name in TEAM_FIELD_SPECS:
        entry_obj = _find_schema_field("offsets_teams.json", normalized_name)
        if not isinstance(entry_obj, dict):
            continue
        offset = to_int(entry_obj.get("address") or entry_obj.get("offset") or entry_obj.get("hex"))
        length_val = to_int(entry_obj.get("length"))
        entry_type = str(entry_obj.get("type", "")).lower()
        if offset <= 0 or length_val <= 0:
            continue
        if entry_type not in ("wstring", "string", "text"):
            continue
        encoding = "ascii" if entry_type in ("string", "text") else "utf16"
        TEAM_FIELD_DEFS[label] = (offset, length_val, encoding)

    STAFF_PTR_CHAINS.clear()
    staff_base = base_pointers.get("Staff")
    staff_addr, staff_addr_defined = _pointer_address(staff_base if isinstance(staff_base, dict) else None)
    if staff_addr_defined:
        staff_chains = _parse_pointer_chain_config(staff_base)
        if staff_chains:
            STAFF_PTR_CHAINS.extend(staff_chains)
        else:
            errors.append("Staff base pointer chain produced no resolvable entries.")

    staff_first_entry = _require_field("staff_first_name")
    staff_last_entry = _require_field("staff_last_name")
    STAFF_NAME_OFFSET = to_int(
        (staff_first_entry or {}).get("address")
        or (staff_first_entry or {}).get("offset")
        or (staff_first_entry or {}).get("hex")
    ) or 0
    STAFF_NAME_ENCODING = "ascii" if str((staff_first_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16"
    STAFF_NAME_LENGTH = to_int((staff_first_entry or {}).get("length")) or 0
    if STAFF_NAME_LENGTH <= 0:
        errors.append("Staff Vitals/FIRSTNAME length must be > 0.")
    if isinstance(staff_last_entry, dict):
        last_staff_len = to_int(staff_last_entry.get("length"))
        if last_staff_len <= 0:
            errors.append("Staff Vitals/LASTNAME length must be > 0.")

    STADIUM_PTR_CHAINS.clear()
    stadium_base = base_pointers.get("Stadium")
    stadium_addr, stadium_addr_defined = _pointer_address(stadium_base if isinstance(stadium_base, dict) else None)
    if stadium_addr_defined:
        stadium_chains = _parse_pointer_chain_config(stadium_base)
        if stadium_chains:
            STADIUM_PTR_CHAINS.extend(stadium_chains)
        else:
            errors.append("Stadium base pointer chain produced no resolvable entries.")

    stadium_name_entry = _require_field("stadium_name")
    STADIUM_NAME_OFFSET = to_int(
        (stadium_name_entry or {}).get("address")
        or (stadium_name_entry or {}).get("offset")
        or (stadium_name_entry or {}).get("hex")
    ) or 0
    if STADIUM_NAME_OFFSET < 0:
        errors.append("Stadium/ARENANAME address must be >= 0.")
        STADIUM_NAME_OFFSET = 0
    STADIUM_NAME_ENCODING = "ascii" if str((stadium_name_entry or {}).get("type", "")).lower() in ("string", "text") else "utf16"
    STADIUM_NAME_LENGTH = to_int((stadium_name_entry or {}).get("length")) or 0
    if STADIUM_NAME_LENGTH <= 0:
        errors.append("Stadium/ARENANAME length must be > 0.")
    if errors:
        raise OffsetSchemaError(" ; ".join(errors))
    if warnings:
        warning_text = " ; ".join(dict.fromkeys(warnings))
        print(f"Offset warnings: {warning_text}")


def initialize_offsets(
    target_executable: str | None = None,
    force: bool = False,
    filename: str | None = None,
) -> None:
    """Ensure offset data for the requested executable is loaded."""
    global _offset_file_path, _offset_config, MODULE_NAME, _current_offset_target
    with timed("offsets.initialize_offsets"):
        target_exec = target_executable or MODULE_NAME
        target_key = target_exec.lower()
        if force:
            _OFFSET_CACHE.invalidate_target(target_key)
        if _offset_config is not None and not force and _current_offset_target == target_key and not filename:
            MODULE_NAME = target_exec
            _sync_player_stats_relations(_offset_config)
            return
        if filename:
            path = Path(filename)
            try:
                with path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
            except Exception as exc:
                raise OffsetSchemaError(f"Failed to load offsets file '{filename}': {exc}") from exc
            resolver = OffsetResolver(convert_schema=_convert_merged_offsets_schema)
            try:
                data = resolver.require_dict(raw, target_exec)
            except OffsetResolveError as exc:
                raise OffsetSchemaError(str(exc)) from exc
        else:
            path, data = _load_offset_config_file(target_exec)
        if not isinstance(data, dict):
            raise OffsetSchemaError(
                f"Unable to locate offset schema for {target_exec}. Expected {SPLIT_OFFSETS_LEAGUE_FILE} and "
                f"{', '.join(SPLIT_OFFSETS_DOMAIN_FILES)} in the Offsets folder."
            )
        _offset_file_path = path
        _offset_config = data
        MODULE_NAME = target_exec
        _apply_offset_config(data)
        _sync_player_stats_relations(data)
        MODULE_NAME = target_exec
        _current_offset_target = target_key


__all__ = [
    "OffsetSchemaError",
    "initialize_offsets",
    "BASE_POINTER_SIZE_KEY_MAP",
    "REQUIRED_LIVE_BASE_POINTER_KEYS",
    "STRICT_OFFSET_FIELD_KEYS",
    "STRICT_OFFSET_HIERARCHY_FIELD_KEYS",
    "CATEGORY_SUPER_TYPES",
    "PLAYER_STATS_RELATIONS",
    "PLAYER_TABLE_RVA",
    "PLAYER_STRIDE",
    "PLAYER_PTR_CHAINS",
    "DRAFT_PTR_CHAINS",
    "DRAFT_CLASS_TEAM_ID",
    "OFF_LAST_NAME",
    "OFF_FIRST_NAME",
    "OFF_TEAM_PTR",
    "OFF_TEAM_NAME",
    "OFF_TEAM_ID",
    "MAX_PLAYERS",
    "MAX_DRAFT_PLAYERS",
    "MAX_TEAMS_SCAN",
    "NAME_MAX_CHARS",
    "FIRST_NAME_ENCODING",
    "LAST_NAME_ENCODING",
    "TEAM_NAME_ENCODING",
    "TEAM_STRIDE",
    "TEAM_NAME_OFFSET",
    "TEAM_NAME_LENGTH",
    "TEAM_PLAYER_SLOT_COUNT",
    "TEAM_PTR_CHAINS",
    "TEAM_TABLE_RVA",
    "TEAM_FIELD_DEFS",
    "TEAM_RECORD_SIZE",
    "TEAM_FIELD_SPECS",
    "PLAYER_PANEL_FIELDS",
    "PLAYER_PANEL_OVR_FIELD",
    "UNIFIED_FILES",
    "EXTRA_CATEGORY_FIELDS",
    "STAFF_STRIDE",
    "STAFF_PTR_CHAINS",
    "STAFF_RECORD_SIZE",
    "STAFF_NAME_OFFSET",
    "STAFF_NAME_LENGTH",
    "STAFF_NAME_ENCODING",
    "MAX_STAFF_SCAN",
    "STADIUM_STRIDE",
    "STADIUM_PTR_CHAINS",
    "STADIUM_RECORD_SIZE",
    "STADIUM_NAME_OFFSET",
    "STADIUM_NAME_LENGTH",
    "STADIUM_NAME_ENCODING",
    "MAX_STADIUM_SCAN",
    "ATTR_IMPORT_ORDER",
    "DUR_IMPORT_ORDER",
    "POTENTIAL_IMPORT_ORDER",
    "TEND_IMPORT_ORDER",
    "FIELD_NAME_ALIASES",
    "NAME_SYNONYMS",
    "NAME_SUFFIXES",
    "_load_categories",
]
