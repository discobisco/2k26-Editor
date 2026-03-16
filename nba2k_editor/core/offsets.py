"""
Offset loading and schema normalization.

Handles:
* offset file discovery and parsing
* canonical field lookup helpers
* resolved constants for player/team tables
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .conversions import to_int
from .offset_cache import OffsetCache
from .offset_loader import OffsetRepository
from .perf import timed
from . import offset_bundle as _offset_bundle_helpers
from . import offset_categories as _offset_categories_helpers
from . import offset_runtime_support as _offset_runtime_support_helpers
from . import offset_runtime_apply as _offset_runtime_apply_helpers
from . import offset_index_queries as _offset_index_query_helpers


class OffsetSchemaError(RuntimeError):
    """Raised when offsets are missing required definitions."""


@dataclass(frozen=True)
class OffsetCategoryBundle:
    categories: dict[str, list[dict]]
    super_types: dict[str, str]
    canonical: dict[str, str]


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
REQUIRED_LIVE_BASE_POINTER_KEYS: tuple[str, ...] = ("Player", "Team")

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

MODULE_NAME = "NBA2K26.exe"
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
    "player stat id": "Stats - Stat IDs",
    "stat ids": "Stats - Stat IDs",
    "season": "Stats - Season",
    "season high stats": "Stats - Season",
    "career": "Stats - Career",
    "career high stats": "Stats - Career",
    "awards": "Stats - Awards",
}
PLAYER_STATS_IDS_CATEGORY = "Stats - Stat IDs"
PLAYER_STATS_SEASON_CATEGORY = "Stats - Season"
_offset_file_path: Path | None = None
_offset_config: dict | None = None
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

# Stable compat bindings: these remain patchable module attributes on the facade.
_split_version_tokens = _offset_bundle_helpers._split_version_tokens
_version_key_matches = _offset_bundle_helpers._version_key_matches
_select_version_entry = _offset_bundle_helpers._select_version_entry


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


def _build_split_schema_file_category_map(
    split_schema: object,
) -> dict[str, dict[str, tuple[str, str]]]:
    """Build source_file -> category -> (canonical_category, top-level super_type)."""
    resolved: dict[str, dict[str, tuple[str, str]]] = {}
    if not isinstance(split_schema, dict):
        return resolved
    for source_file, file_payload in split_schema.items():
        if not isinstance(file_payload, dict):
            continue
        file_key = str(source_file or "").strip().casefold()
        if not file_key:
            continue
        file_map: dict[str, tuple[str, str]] = {}
        for super_type_label, category_map in file_payload.items():
            super_type = _normalized_super_type_label(super_type_label)
            if not super_type or not isinstance(category_map, dict):
                continue
            for category_name in category_map.keys():
                category = str(category_name or "").strip()
                if not category:
                    continue
                file_map.setdefault(category.lower(), (category, super_type))
        if file_map:
            resolved[file_key] = file_map
    return resolved


def _derive_super_type_map_from_split_schema(split_schema: object) -> dict[str, str]:
    derived: dict[str, str] = {}
    for file_map in _build_split_schema_file_category_map(split_schema).values():
        for category_key, (_canonical_category, super_type) in file_map.items():
            if category_key and super_type:
                derived.setdefault(category_key, super_type)
    return derived


def _select_active_version(
    versions_map: dict[str, object],
    target_executable: str | None,
    *,
    require_hint: bool = False,
) -> tuple[str, str, dict[str, object]] | None:
    return _offset_bundle_helpers._select_active_version(
        versions_map,
        target_executable,
        require_hint=require_hint,
        derive_version_label=_derive_version_label,
    )

def _read_json_cached(path: Path) -> dict[str, Any] | None:
    return _offset_bundle_helpers._read_json_cached(
        path,
        read_json_with_error=_read_json_with_error,
    )

def _read_json_with_error(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    return _offset_bundle_helpers._read_json_with_error(path, offset_cache=_OFFSET_CACHE)

_build_dropdown_values_index = _offset_bundle_helpers._build_dropdown_values_index

def _resolve_split_category(root_category: str, table_segments: tuple[str, ...]) -> str:
    """Return runtime category name for a split offsets leaf entry."""
    return _offset_bundle_helpers._resolve_split_category(
        root_category,
        table_segments,
        player_stats_table_category_map=PLAYER_STATS_TABLE_CATEGORY_MAP,
    )

_iter_hierarchy_leaf_nodes = _offset_bundle_helpers._iter_hierarchy_leaf_nodes

def _resolve_hierarchy_context(
    path_segments: tuple[str, ...],
    *,
    source_file: str,
    leaf_node: dict[str, object],
    version_payload: dict[str, object],
    split_schema_file_map: dict[str, dict[str, tuple[str, str]]],
) -> dict[str, object]:
    return _offset_bundle_helpers._resolve_hierarchy_context(
        path_segments,
        source_file=source_file,
        leaf_node=leaf_node,
        version_payload=version_payload,
        split_schema_file_map=split_schema_file_map,
        normalized_super_type_label=_normalized_super_type_label,
        looks_like_super_type=_looks_like_super_type,
        resolve_split_category=_resolve_split_category,
    )

_iter_hierarchy_sections = _offset_bundle_helpers._iter_hierarchy_sections

def _collect_selected_entries(
    data: dict[str, object],
    target_executable: str | None,
    *,
    require_hint: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object], str | None, str | None, dict[str, object] | None]:
    return _offset_bundle_helpers._collect_selected_entries(
        data,
        target_executable,
        require_hint=require_hint,
        select_active_version=_select_active_version,
        build_split_schema_file_category_map=_build_split_schema_file_category_map,
        resolve_hierarchy_context=_resolve_hierarchy_context,
        normalize_offset_type=_normalize_offset_type,
        infer_length_bits=_infer_length_bits,
    )

def _iter_selected_entries(data: dict[str, object], target_executable: str | None):
    yield from _offset_bundle_helpers._iter_selected_entries(
        data,
        target_executable,
        collect_selected_entries=_collect_selected_entries,
    )

def _build_split_offsets_payload(
    offsets_dir: Path,
    *,
    parse_errors: list[str] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    return _offset_bundle_helpers._build_split_offsets_payload(
        offsets_dir,
        parse_errors=parse_errors,
        split_offsets_league_file=SPLIT_OFFSETS_LEAGUE_FILE,
        split_offsets_domain_files=SPLIT_OFFSETS_DOMAIN_FILES,
        split_offsets_optional_files=SPLIT_OFFSETS_OPTIONAL_FILES,
        read_json_with_error=_read_json_with_error,
        read_json_cached=_read_json_cached,
        derive_super_type_map_from_split_schema=_derive_super_type_map_from_split_schema,
    )

def _build_player_stats_relations(offsets: list[dict[str, object]]) -> dict[str, object]:
    return _offset_bundle_helpers._build_player_stats_relations(
        offsets,
        player_stats_ids_category=PLAYER_STATS_IDS_CATEGORY,
        player_stats_season_category=PLAYER_STATS_SEASON_CATEGORY,
    )

_extract_player_stats_relations = _offset_bundle_helpers._extract_player_stats_relations

def _sync_player_stats_relations(config_data: dict | None) -> None:
    global PLAYER_STATS_RELATIONS
    PLAYER_STATS_RELATIONS = _extract_player_stats_relations(config_data)


def _resolve_split_offsets_config(raw: object, target_exe: str | None) -> dict | None:
    """Resolve the active version from a split-offsets bundle."""
    return _offset_bundle_helpers._resolve_split_offsets_config(
        raw,
        target_exe,
        collect_selected_entries=_collect_selected_entries,
        build_player_stats_relations=_build_player_stats_relations,
        derive_super_type_map_from_split_schema=_derive_super_type_map_from_split_schema,
    )

def _load_offset_bundle_from_dir(
    offsets_dir: Path,
    target_executable: str | None,
    *,
    parse_errors: list[str] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    return _offset_bundle_helpers._load_offset_bundle_from_dir(
        offsets_dir,
        target_executable,
        parse_errors=parse_errors,
        build_split_offsets_payload=_build_split_offsets_payload,
        resolve_split_offsets_config=_resolve_split_offsets_config,
    )

def _load_offset_config_file(target_executable: str | None = None) -> tuple[Path | None, dict | None]:
    """Locate and parse split offsets files for the given executable."""
    base_dir = Path(__file__).resolve().parent.parent
    search_dirs = [base_dir / "Offsets", base_dir / "offsets"]
    return _offset_bundle_helpers._load_offset_config_file(
        target_executable,
        timed_ctx=timed,
        offset_cache=_OFFSET_CACHE,
        offset_schema_error=OffsetSchemaError,
        load_offset_bundle_from_dir=_load_offset_bundle_from_dir,
        search_dirs=search_dirs,
    )

def _build_offset_index(offsets: list[dict]) -> None:
    """Create strict exact-match lookup maps for offsets entries."""
    _offset_index_query_helpers.build_offset_index(
        offsets,
        offset_index=_offset_index,
        offset_normalized_index=_offset_normalized_index,
        offset_hierarchy_index=_offset_hierarchy_index,
    )


def _find_offset_entry(name: str, category: str | None = None) -> dict | None:
    """Return the offset entry matching the provided exact name/category."""
    return _offset_index_query_helpers.find_offset_entry(
        name,
        category,
        offset_index=_offset_index,
    )


def has_active_config() -> bool:
    """Return whether an offsets config is currently loaded."""
    return isinstance(_offset_config, dict)


def get_current_target() -> str | None:
    """Return the active offsets target key, if any."""
    return _current_offset_target


def get_offset_file_path() -> Path | None:
    """Return the loaded offsets file path, if one backed the active config."""
    return _offset_file_path


def get_offset_category_metadata() -> tuple[dict[str, str], dict[str, str]]:
    """Return copies of category super-type and canonical-name maps."""
    return dict(CATEGORY_SUPER_TYPES), dict(CATEGORY_CANONICAL)


def load_category_bundle() -> OffsetCategoryBundle:
    """Return categories plus their metadata as one bundle.

    Compatibility globals are still refreshed as a side effect for older callers,
    but new callers should consume the returned bundle instead.
    """
    categories, super_types, canonical = _offset_categories_helpers._load_categories_bundle(
        _offset_config,
        _current_offset_target,
        MODULE_NAME,
        load_dropdowns_map=_load_dropdowns_map,
        iter_selected_entries=_iter_selected_entries,
        normalized_super_type_label=_normalized_super_type_label,
        infer_length_bits=_infer_length_bits,
    )
    CATEGORY_SUPER_TYPES.clear()
    CATEGORY_CANONICAL.clear()
    CATEGORY_SUPER_TYPES.update(super_types)
    CATEGORY_CANONICAL.update(canonical)
    return OffsetCategoryBundle(
        categories=categories,
        super_types=super_types,
        canonical=canonical,
    )


def get_version_context(
    target_executable: str | None = None,
) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
    """Return active version label, base pointers, and game info for the requested target."""
    target = target_executable or _current_offset_target or MODULE_NAME
    version_label, base_pointers, game_info = _resolve_version_context(_offset_config, target)
    return version_label, dict(base_pointers), dict(game_info)


def parse_pointer_chain_config(base_cfg: dict | None) -> list[dict[str, object]]:
    """Public wrapper for pointer-chain parsing against the active offsets schema."""
    return list(_parse_pointer_chain_config(base_cfg))


def get_league_category_pointer_map() -> dict[str, tuple[str, int]]:
    """Return explicit league category -> (pointer key, default limit) mappings."""
    if not isinstance(_offset_config, dict):
        return {}
    raw_map = _offset_config.get("league_category_pointer_map")
    resolved: dict[str, tuple[str, int]] = {}
    if not isinstance(raw_map, dict):
        return {}
    for category_name, mapping in raw_map.items():
        category_key = str(category_name or "").strip()
        if not category_key:
            continue
        pointer_key = ""
        default_limit = 0
        if isinstance(mapping, str):
            pointer_key = str(mapping).strip()
        elif isinstance(mapping, dict):
            pointer_key = str(
                mapping.get("pointer")
                or mapping.get("pointer_key")
                or mapping.get("base_pointer")
                or ""
            ).strip()
            default_limit = max(
                0,
                to_int(
                    mapping.get("max_records")
                    or mapping.get("limit")
                    or mapping.get("default_limit")
                    or 0
                ),
            )
        if pointer_key:
            resolved[category_key] = (pointer_key, default_limit)
    return resolved


def get_league_pointer_meta(
    pointer_key: str,
    target_executable: str | None = None,
) -> tuple[list[dict[str, object]], int]:
    """Return parsed pointer chains plus stride for a league/runtime base pointer key."""
    if not pointer_key:
        return [], 0
    _version_label, base_pointers, game_info = get_version_context(target_executable)
    pointer_def = base_pointers.get(pointer_key) if isinstance(base_pointers, dict) else None
    chains: list[dict[str, object]] = []
    if isinstance(pointer_def, dict):
        try:
            parsed = parse_pointer_chain_config(pointer_def)
            if isinstance(parsed, list):
                chains = parsed
        except Exception:
            chains = []
    size_key = BASE_POINTER_SIZE_KEY_MAP.get(pointer_key)
    stride = max(0, to_int(game_info.get(size_key)) or 0) if size_key else 0
    return chains, stride


def find_offset_entry(name: str, category: str | None = None) -> dict | None:
    """Public exact-name/category lookup for active offsets entries."""
    return _find_offset_entry(name, category)


def _find_offset_entry_by_normalized(canonical_category: str, normalized_name: str) -> dict | None:
    """Return an offsets entry by exact canonical_category + normalized_name."""
    return _offset_index_query_helpers.find_offset_entry_by_normalized(
        canonical_category,
        normalized_name,
        offset_normalized_index=_offset_normalized_index,
    )


def _find_offset_entry_by_hierarchy(
    source_super_type: str,
    source_category: str,
    source_group: str,
    normalized_name: str,
) -> dict | None:
    """Return an offsets entry by exact hierarchy + normalized name."""
    return _offset_index_query_helpers.find_offset_entry_by_hierarchy(
        source_super_type,
        source_category,
        source_group,
        normalized_name,
        offset_hierarchy_index=_offset_hierarchy_index,
    )


def _load_dropdowns_map() -> dict[str, dict[str, list[str]]]:
    return _offset_categories_helpers._load_dropdowns_map(
        timed=timed,
        load_dropdowns=_OFFSET_REPOSITORY.load_dropdowns,
        module_file=__file__,
    )


_derive_version_label = _offset_runtime_support_helpers._derive_version_label


def _resolve_version_context(
    data: dict[str, Any] | None,
    target_executable: str | None,
) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
    """Return (version_label, base_pointers, game_info) for the active target."""
    return _offset_runtime_support_helpers._resolve_version_context(
        data,
        target_executable,
        derive_version_label=_derive_version_label,
    )


def _normalize_chain_steps(chain_data: object) -> list[dict[str, object]]:
    return _offset_runtime_support_helpers._normalize_chain_steps(
        chain_data,
        to_int=to_int,
        offset_schema_error=OffsetSchemaError,
    )


def _parse_pointer_chain_config(base_cfg: dict | None) -> list[dict[str, object]]:
    return _offset_runtime_support_helpers._parse_pointer_chain_config(
        base_cfg,
        normalize_chain_steps=_normalize_chain_steps,
        to_int=to_int,
        offset_schema_error=OffsetSchemaError,
    )


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
    global DRAFT_PTR_CHAINS, TEAM_TABLE_RVA
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

    runtime_result = _offset_runtime_apply_helpers.OffsetRuntimeInstaller(
        combined_offsets=[cast(dict[str, object], entry) for entry in combined_offsets],
        base_pointers=base_pointers,
        game_info=game_info,
        required_live_base_pointer_keys=REQUIRED_LIVE_BASE_POINTER_KEYS,
        base_pointer_size_key_map=BASE_POINTER_SIZE_KEY_MAP,
        required_offset_schema_fields=REQUIRED_OFFSET_SCHEMA_FIELDS,
        team_field_specs=TEAM_FIELD_SPECS,
        to_int=to_int,
        parse_pointer_chain_config=_parse_pointer_chain_config,
    ).build()

    if runtime_result.module_name:
        MODULE_NAME = runtime_result.module_name

    for attr_name, attr_value in runtime_result.scalar_updates.items():
        globals()[attr_name] = attr_value

    PLAYER_PTR_CHAINS[:] = runtime_result.chain_updates.get("PLAYER_PTR_CHAINS", [])
    TEAM_PTR_CHAINS[:] = runtime_result.chain_updates.get("TEAM_PTR_CHAINS", [])
    DRAFT_PTR_CHAINS[:] = runtime_result.chain_updates.get("DRAFT_PTR_CHAINS", [])
    STAFF_PTR_CHAINS[:] = runtime_result.chain_updates.get("STAFF_PTR_CHAINS", [])
    STADIUM_PTR_CHAINS[:] = runtime_result.chain_updates.get("STADIUM_PTR_CHAINS", [])

    TEAM_FIELD_DEFS.clear()
    TEAM_FIELD_DEFS.update(runtime_result.mapping_updates.get("TEAM_FIELD_DEFS", {}))

    if runtime_result.errors:
        raise OffsetSchemaError(" ; ".join(runtime_result.errors))
    if runtime_result.warnings:
        warning_text = " ; ".join(dict.fromkeys(runtime_result.warnings))
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
            if not path.exists():
                raise OffsetSchemaError(f"Failed to load offsets file '{filename}': file does not exist.")
            bundle_dir = path if path.is_dir() else path.parent
            resolved_payload = _load_offset_bundle_from_dir(bundle_dir, target_exec)
            if resolved_payload is None:
                raise OffsetSchemaError(
                    f"Selected path '{filename}' is not part of a valid split offsets bundle. "
                    "Choose a JSON file from a folder containing offsets_league.json and all required offsets_*.json files."
                )
            path, data = resolved_payload
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
        _current_offset_target = target_key
        _apply_offset_config(data)
        _sync_player_stats_relations(data)
        MODULE_NAME = target_exec
        _current_offset_target = target_key
__all__ = [
    "OffsetSchemaError",
    "OffsetCategoryBundle",
    "initialize_offsets",
    "has_active_config",
    "get_current_target",
    "get_offset_category_metadata",
    "load_category_bundle",
    "get_version_context",
    "parse_pointer_chain_config",
    "get_league_category_pointer_map",
    "get_league_pointer_meta",
    "find_offset_entry",
    "BASE_POINTER_SIZE_KEY_MAP",
    "REQUIRED_LIVE_BASE_POINTER_KEYS",
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
    "NAME_SYNONYMS",
    "NAME_SUFFIXES",
]
