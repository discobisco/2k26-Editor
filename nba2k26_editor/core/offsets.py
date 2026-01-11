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
from typing import Any, cast, TypedDict

from .config import DEFAULT_OFFSET_FILES, MODULE_NAME as CONFIG_MODULE_NAME
from .conversions import to_int


class OffsetSchemaError(RuntimeError):
    """Raised when offsets are missing required definitions."""


# Field name synonyms for offsets across schema variants
OFFSET_FIELD_SYNONYMS: dict[str, list[str]] = {
    "first name": [
        "player_first_name",
        "first_name",
        "firstname",
        "offset player first name",
        "offset first name",
    ],
    "last name": [
        "player_last_name",
        "last_name",
        "lastname",
        "surname",
        "offset player last name",
        "offset last name",
    ],
    "face id": [
        "player_faceid",
        "faceid",
        "offset player face id",
        "offset face id",
    ],
    "current team": [
        "player team",
        "team",
        "team_id",
        "current team address",
        "offset player team",
    ],
    "team name": [
        "offset team name",
        "city name",
    ],
    "team short name": [
        "team_short_name",
        "offset team short name",
        "team abbrev",
        "team abbreviation",
        "city abbrev",
    ],
    "team year": [
        "team year",
        "historic year",
        "offset team year",
    ],
    "team type": [
        "team type",
        "offset team type",
    ],
}

CATEGORY_ALIASES: dict[str, str] = {
    "vitals_offsets": "vitals",
    "attributes_offsets": "attributes",
    "tendencies_offsets": "tendencies",
    "hotzone_offsets": "hotzones",
    "signature_offsets": "signatures",
    "contract_offsets": "contracts",
    "stats_offsets": "stats",
    "edit_offsets": "edit",
    "look_offsets": "appearance",
    "shoes/gear_offsets": "gear",
    "team vitals": "teams",
    "team_vitals": "teams",
}


def _build_field_canonical_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canon, syns in OFFSET_FIELD_SYNONYMS.items():
        canon_l = canon.lower()
        lookup[canon_l] = canon_l
        for alias in syns:
            lookup[str(alias).lower()] = canon_l
    return lookup


_FIELD_CANONICAL_LOOKUP: dict[str, str] = _build_field_canonical_lookup()
_CANONICAL_DISPLAY_NAMES: dict[str, str] = {
    key.lower(): key.title() for key in OFFSET_FIELD_SYNONYMS
}
BASE_CANONICAL_FIELD_INFO: dict[str, dict[str, str]] = {
    "first name": {"category": "Vitals", "display": "First Name", "type": "wstring"},
    "last name": {"category": "Vitals", "display": "Last Name", "type": "wstring"},
    "face id": {"category": "Vitals", "display": "Face ID", "type": "number"},
    "current team": {"category": "Vitals", "display": "Current Team", "type": "number"},
    "team name": {"category": "Teams", "display": "Team Name", "type": "wstring"},
    "team short name": {"category": "Teams", "display": "Team Short Name", "type": "wstring"},
    "team year": {"category": "Teams", "display": "Team Year", "type": "number"},
    "team type": {"category": "Teams", "display": "Team Type", "type": "number"},
}

MODULE_NAME = CONFIG_MODULE_NAME
OFFSET_FILENAME_PATTERNS: tuple[str, ...] = ()
OFFSETS_BUNDLE_FILE = DEFAULT_OFFSET_FILES[0] if DEFAULT_OFFSET_FILES else "offsets.json"
_offset_file_path: Path | None = None
_offset_config: dict | None = None
_offset_index: dict[tuple[str, str], dict] = {}
_current_offset_target: str | None = None
_base_pointer_overrides: dict[str, int] | None = None
CATEGORY_SUPER_TYPES: dict[str, str] = {}
CATEGORY_CANONICAL: dict[str, str] = {}
CATEGORY_SUPER_TYPES: dict[str, str] = {}

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
    ("Team Name", "Team Name"),
    ("City Name", "City Name"),
    ("City Abbrev", "City Abbrev"),
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

UNIFIED_FILES = (OFFSETS_BUNDLE_FILE,)
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
    """Return an ordered list of offset filenames to probe for the target executable."""
    base: list[str] = list(DEFAULT_OFFSET_FILES)
    # Try common per-version filenames first (helps when users drop standalone files).
    version_hint = None
    if target_executable:
        m = re.search(r"2k(\d{2})", target_executable.lower())
        if m:
            version_hint = m.group(1)
    if version_hint:
        base.insert(0, f"2k{version_hint}_offsets.json")
        base.insert(0, f"2K{version_hint}_Offsets.json")
    # Hard-coded 2K26 standalone names for convenience.
    base.insert(0, "2k26_offsets-2.json")
    base.insert(0, "2k26_offsets.json")
    return tuple(dict.fromkeys(base))  # de-dup while preserving order


def _select_merged_offset_entry(raw: object, target_executable: str | None) -> dict | None:
    """
    Pick the best offsets entry from a merged offsets payload.
    Supports:
      1) a single offsets object with an `offsets` list
      2) a mapping of version keys -> offsets objects
    """
    if isinstance(raw, dict) and isinstance(raw.get("offsets"), list):
        return raw
    version_hint = None
    if target_executable:
        match = re.search(r"2k(\d{2})", target_executable.lower())
        if match:
            version_hint = match.group(1)
    if isinstance(raw, dict):
        best: dict | None = None
        best_score = -1
        for key, value in raw.items():
            if not isinstance(value, dict) or not isinstance(value.get("offsets"), list):
                continue
            score = 0
            key_lower = str(key).lower()
            game_info = value.get("game_info") if isinstance(value.get("game_info"), dict) else {}
            exec_name = str(game_info.get("executable", "")).lower() if isinstance(game_info, dict) else ""
            # Only accept entries that explicitly match the loaded game's executable (or 2kXX hint).
            if target_executable and exec_name and exec_name != target_executable.lower():
                continue
            if version_hint and not (version_hint in key_lower or version_hint in exec_name):
                continue
            if version_hint and version_hint in key_lower:
                score += 3
            if target_executable and exec_name == target_executable.lower():
                score += 4
            elif version_hint and version_hint in exec_name:
                score += 2
            version_field = str(game_info.get("version", "")).lower() if isinstance(game_info, dict) else ""
            if version_hint and version_hint in version_field:
                score += 1
            if score > best_score:
                best_score = score
                best = value
        if best:
            return best
        for value in raw.values():
            if isinstance(value, dict) and isinstance(value.get("offsets"), list):
                return value
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and isinstance(entry.get("offsets"), list):
                return entry
    return None


def _convert_merged_offsets_schema(raw: object, target_exe: str | None) -> dict | None:
    """Handle merged_offsets schema where each entry carries per-version data."""
    if not isinstance(raw, dict):
        return None
    offsets = raw.get("offsets")
    versions_map = raw.get("versions")
    if not isinstance(offsets, list) or not isinstance(versions_map, dict):
        return None

    version_hint = None
    if target_exe:
        match = re.search(r"2k(\d{2})", target_exe.lower())
        if match:
            version_hint = f"2k{match.group(1)}"
    version_key: str | None = None
    if version_hint:
        for key in versions_map.keys():
            key_l = str(key).lower()
            if version_hint in key_l:
                version_key = key
                break
    if version_key is None:
        return None
    version_info = versions_map.get(version_key)
    if not isinstance(version_info, dict):
        return None
    unified_offsets: list[dict[str, object]] = []
    for entry in offsets:
        if not isinstance(entry, dict):
            continue
        per_version = entry.get("versions")
        if not isinstance(per_version, dict):
            continue
        v_entry = per_version.get(version_key)
        if not isinstance(v_entry, dict):
            continue
        address_raw = v_entry.get("address")
        if address_raw in (None, ""):
            address_raw = v_entry.get("hex")
        address = to_int(address_raw)
        ftype = v_entry.get("type")
        length = to_int(v_entry.get("length"))
        if length < 0:
            length = 0
        is_pointer = isinstance(ftype, str) and ("pointer" in ftype.lower() or "ptr" in ftype.lower())
        if address < 0 or (length == 0 and not is_pointer):
            continue
        start_bit = to_int(v_entry.get("startBit") or v_entry.get("start_bit"))
        category = (
            v_entry.get("category")
            or entry.get("canonical_category")
            or entry.get("super_type")
            or entry.get("superType")
            or ""
        )
        name = (
            v_entry.get("name")
            or entry.get("display_name")
            or entry.get("normalized_name")
            or entry.get("canonical_name")
            or f"Field 0x{address:X}"
        )
        new_entry: dict[str, object] = {
            "category": str(category),
            "name": str(name),
            # Preserve both keys since downstream consumers check for `address` or `offset`
            "address": address,
            "offset": address,
            "hex": f"0x{address:X}",
            "length": length,
            "startBit": start_bit,
        }
        if isinstance(ftype, str):
            new_entry["type"] = ftype
        if v_entry.get("requiresDereference") is True or v_entry.get("requires_deref") is True:
            new_entry["requiresDereference"] = True
        deref = v_entry.get("dereferenceAddress") or v_entry.get("deref_offset")
        if deref is not None:
            new_entry["dereferenceAddress"] = deref
        values = v_entry.get("values")
        if isinstance(values, list):
            new_entry["values"] = values
        unified_offsets.append(new_entry)
    if not unified_offsets:
        return None
    converted: dict[str, object] = {"offsets": unified_offsets}
    # Preserve helpers that inform category grouping/canonicalization.
    if isinstance(raw.get("category_normalization"), dict):
        converted["category_normalization"] = raw["category_normalization"]
    if isinstance(raw.get("super_type_map"), dict):
        converted["super_type_map"] = raw["super_type_map"]
    converted["versions"] = {version_key: version_info}
    base_ptrs = version_info.get("base_pointers") if isinstance(version_info.get("base_pointers"), dict) else None
    if base_ptrs:
        converted["base_pointers"] = base_ptrs
    game_info = version_info.get("game_info") if isinstance(version_info.get("game_info"), dict) else None
    if game_info:
        converted["game_info"] = game_info
    return converted


def _load_offset_config_file(target_executable: str | None = None) -> tuple[Path | None, dict | None]:
    """Locate and parse the offsets bundle for the given executable."""
    base_dir = Path(__file__).resolve().parent.parent
    # Single source: packaged Offsets folder (avoid cross-version/conflicting files).
    search_dirs = [
        base_dir / "Offsets",
        base_dir / "offsets",
    ]
    candidates = _derive_offset_candidates(target_executable)
    for folder in search_dirs:
        for fname in candidates:
            path = folder / fname
            if not path.is_file():
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception as exc:
                print(f"Failed to load offsets from {path}: {exc}")
                continue
            converted = _convert_merged_offsets_schema(raw, target_executable)
            if converted:
                return path, converted
            selected = _select_merged_offset_entry(raw, target_executable)
            if selected and selected is not raw:
                converted_selected = _convert_merged_offsets_schema(selected, target_executable)
                return path, converted_selected or selected
            if isinstance(raw, dict):
                return path, raw
    return None, None


def _build_offset_index(offsets: list[dict]) -> None:
    """Create a lookup of offset entries by (category, name) with aliases."""
    _offset_index.clear()
    for entry in offsets:
        if not isinstance(entry, dict):
            continue
        category_raw = str(entry.get("category", "")).strip()
        name_raw = str(entry.get("name", "")).strip()
        if not name_raw:
            continue
        category = category_raw.lower()
        name = name_raw.lower()
        _offset_index[(category, name)] = entry
        alias_cat = CATEGORY_ALIASES.get(category) or (category[:-8] if category.endswith("_offsets") else None)
        if alias_cat:
            _offset_index[(alias_cat, name)] = entry
        for canon, syns in OFFSET_FIELD_SYNONYMS.items():
            all_names = [canon] + syns
            if name in (s.lower() for s in all_names):
                for alt in all_names:
                    alt_l = alt.lower()
                    _offset_index[(category, alt_l)] = entry
                    if alias_cat:
                        _offset_index[(alias_cat, alt_l)] = entry


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


def _load_dropdowns_map() -> dict[str, dict[str, list[str]]]:
    """Return an empty dropdown map. Dropdowns.json support has been disabled."""
    return {}


def _derive_version_label(executable: str | None) -> str | None:
    """Return a version label like '2K26' based on the executable name."""
    if not executable:
        return None
    m = re.search(r"2k(\d{2})", executable.lower())
    if not m:
        return None
    return f"2K{m.group(1)}"


def _load_categories_from_mega(version_label: str | None) -> dict[str, list[dict]]:
    """Mega offsets are disabled; rely solely on offsets.json."""
    return {}


def _load_categories() -> dict[str, list[dict]]:
    """
    Load editor categories from a unified offsets file.
    Returns a dictionary mapping category names to lists of field
    definitions. If parsing fails or no unified file is found, an empty
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

    def _entry_to_field(entry: dict, display_name: str, target_category: str | None = None) -> dict | None:
        offset_val = to_int(entry.get("address"))
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
        """Template merging disabled; offsets are sourced solely from offsets.json."""
        return

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
        try:
            initialize_offsets()
        except OffsetSchemaError as exc:
            # Allow startup without offsets; categories remain empty until loaded later.
            try:
                print(f"Offset warnings: {exc}")
            except Exception:
                pass
    base_categories = {}
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
            _register_category_metadata(cat_name, entry)
            key = (cat_name.lower(), field_name.lower())
            if key in seen_fields:
                continue
            seen_fields.add(key)
            offset_val = to_int(entry.get("address"))
            if offset_val < 0:
                continue
            start_bit = to_int(entry.get("startBit"))
            length_val = to_int(entry.get("length"))
            size_val = to_int(entry.get("size"))
            entry_type = str(entry.get("type", "")).lower()
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
                    _ensure_potential_category(categories)
                    _emit_super_type_warnings()
                    return categories
        except Exception:
            pass
    if base_categories:
        categories = {key: list(value) for key, value in base_categories.items()}
        if categories:
            _ensure_potential_category(categories)
            _emit_super_type_warnings()
            return categories
    return {}


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


def _collect_base_entries(base_data: object) -> list[dict]:
    """Convert legacy Base map entries into indexed offsets where possible."""
    entries: list[dict] = []
    if not isinstance(base_data, dict):
        return entries
    for raw_key, raw_value in base_data.items():
        if isinstance(raw_value, (dict, list)):
            continue
        key = str(raw_key).strip().lower()
        canonical = _FIELD_CANONICAL_LOOKUP.get(key)
        if canonical is None:
            continue
        info = BASE_CANONICAL_FIELD_INFO.get(canonical)
        if info is None:
            continue
        address = to_int(raw_value)
        entry: dict[str, object] = {
            "category": info["category"],
            "name": info.get("display") or _CANONICAL_DISPLAY_NAMES.get(canonical, canonical.title()),
            "address": address,
            "type": info.get("type", "number"),
        }
        entries.append(entry)
    return entries


def _normalize_chain_steps(chain_data: object) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    if not isinstance(chain_data, list):
        return steps
    for hop in chain_data:
        if isinstance(hop, dict):
            offset = to_int(
                hop.get("offset")
                or hop.get("add")
                or hop.get("delta")
                or hop.get("value")
                or hop.get("rva")
            )
            post_add = to_int(
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
                "offset": to_int(hop),
                "post_add": 0,
                "dereference": True,
            })
    return steps


def _parse_pointer_chain_config(base_cfg: dict | None) -> list[dict[str, object]]:
    chains: list[dict[str, object]] = []
    if not isinstance(base_cfg, dict):
        return chains
    addr_raw = base_cfg.get("address")
    if addr_raw is None:
        addr_raw = base_cfg.get("rva")
    if addr_raw is None:
        addr_raw = base_cfg.get("base")
    if addr_raw is None:
        return chains
    base_addr = to_int(addr_raw)
    final_offset = to_int(base_cfg.get("finalOffset") or base_cfg.get("final_offset"))
    absolute_flag = base_cfg.get("absolute")
    if absolute_flag is None:
        absolute_flag = base_cfg.get("isAbsolute")
    is_absolute = bool(absolute_flag)
    direct_table = bool(
        base_cfg.get("direct_table")
        or base_cfg.get("direct")
        or base_cfg.get("directTable")
        or base_cfg.get("treat_as_base")
    )
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
                    "direct_table": candidate.get("direct_table") or candidate.get("direct"),
                }))
        if chains:
            return chains
    steps = _normalize_chain_steps(chain_data)
    chains.append({
        "rva": base_addr,
        "steps": steps,
        "final_offset": final_offset,
        "absolute": is_absolute,
        "direct_table": direct_table,
    })
    return chains


def _extend_pointer_candidates(target: list[dict[str, object]], candidates: object) -> None:
    """Append pointer chain candidates defined using legacy tuple/dict notation."""
    if not isinstance(candidates, (list, tuple)):
        return
    for candidate in candidates:
        candidate_cfg: dict[str, object] | None = None
        if isinstance(candidate, dict):
            candidate_cfg = dict(candidate)
        elif isinstance(candidate, (list, tuple)):
            if not candidate:
                continue
            rva = to_int(candidate[0])
            if rva == 0:
                continue
            final_offset = to_int(candidate[1]) if len(candidate) > 1 else 0
            extra_deref = bool(candidate[2]) if len(candidate) > 2 else False
            direct_table = bool(candidate[3]) if len(candidate) > 3 else False
            candidate_cfg = {
                "address": rva,
                "absolute": False,
                "finalOffset": final_offset,
            }
            steps: list[dict[str, object]] = []
            if extra_deref:
                steps.append({"offset": 0, "dereference": True})
            if steps:
                candidate_cfg["steps"] = steps
            if direct_table:
                candidate_cfg["direct_table"] = True
        else:
            continue
        if not isinstance(candidate_cfg, dict):
            continue
        chains = _parse_pointer_chain_config(candidate_cfg)
        if chains:
            target.extend(chains)


def _normalize_base_pointer_overrides(overrides: dict[str, int] | None) -> dict[str, int]:
    if not overrides:
        return {}
    normalized: dict[str, int] = {}
    for raw_key, raw_value in overrides.items():
        addr = to_int(raw_value)
        if addr is None or addr <= 0:
            continue
        label = str(raw_key or "").strip()
        if not label:
            continue
        low = label.lower()
        if "player" in low:
            label = "Player"
        elif "team" in low:
            label = "Team"
        elif "stadium" in low:
            label = "Stadium"
        elif "arena" in low:
            label = "Arena"
        normalized[label] = addr
    return normalized


def _apply_base_pointer_overrides(data: dict, overrides: dict[str, int]) -> None:
    """Merge dynamic base overrides into an offsets payload."""
    if not overrides or not isinstance(data, dict):
        return

    def _merge(target: object) -> dict[str, object]:
        base_map = target if isinstance(target, dict) else {}
        merged = dict(base_map)
        for key, addr in overrides.items():
            merged[key] = {"address": addr, "absolute": True, "direct_table": True, "finalOffset": 0}
        return merged

    data["base_pointers"] = _merge(data.get("base_pointers"))
    versions = data.get("versions")
    if isinstance(versions, dict):
        for vinfo in versions.values():
            if not isinstance(vinfo, dict):
                continue
            vinfo["base_pointers"] = _merge(vinfo.get("base_pointers"))


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
    # Version-aware fallback helpers (in case the selected payload lost game_info/base_pointers)
    versions_map_raw = data.get("versions") if isinstance(data.get("versions"), dict) else {}
    versions_map = cast(dict[str, VersionInfo], versions_map_raw)
    version_label = _derive_version_label(_current_offset_target or MODULE_NAME)
    def _version_info(label: str | None) -> VersionInfo:
        if not versions_map or not label:
            return VersionInfo()
        vinfo = versions_map.get(label)
        if isinstance(vinfo, dict):
            return vinfo
        vinfo = versions_map.get(label.upper()) if isinstance(label, str) else None
        if isinstance(vinfo, dict):
            return vinfo
        vinfo = versions_map.get(label.lower()) if isinstance(label, str) else None
        if isinstance(vinfo, dict):
            return vinfo
        return VersionInfo()

    base_pointers_source = data.get("base_pointers") or data.get("BasePointers")
    legacy_base = data.get("Base") or data.get("base")
    if legacy_base is None and isinstance(base_pointers_source, dict):
        legacy_base = base_pointers_source
    if legacy_base is None:
        legacy_base = {}
    combined_offsets: list[dict] = []
    offsets = data.get("offsets")
    if isinstance(offsets, list):
        combined_offsets.extend(offsets)
    player_info_entries = _collect_player_info_entries(data.get("Player_Info"))
    if player_info_entries:
        combined_offsets.extend(player_info_entries)
    base_entries = _collect_base_entries(legacy_base)
    if base_entries:
        combined_offsets.extend(base_entries)
    team_offsets = data.get("Teams") or data.get("team_offsets")
    if isinstance(team_offsets, list):
        combined_offsets.extend(team_offsets)
    if not combined_offsets:
        _offset_index.clear()
        raise OffsetSchemaError(f"No offsets defined in {OFFSETS_BUNDLE_FILE}.")
    _build_offset_index(combined_offsets)
    errors: list[str] = []
    warnings: list[str] = []
    game_info = data.get("game_info") or {}
    process_info = data.get("process_info") or {}
    process_base_addr = to_int(
        process_info.get("base_address")
        or process_info.get("BaseAddress")
        or process_info.get("module_base")
    )

    def _legacy_lookup(section: object, *candidates: str) -> object:
        if not isinstance(section, dict):
            return None
        for key in candidates:
            if key in section:
                return section[key]
        lowered = {str(k).lower(): v for k, v in section.items()}
        for key in candidates:
            value = lowered.get(key.lower())
            if value is not None:
                return value
        return None

    module_candidate = game_info.get("executable") or process_info.get("name")
    if module_candidate:
        MODULE_NAME = str(module_candidate)
    vinfo: VersionInfo = VersionInfo()
    vgi: dict[str, Any] = {}
    player_stride_val = to_int(
        game_info.get("playerSize")
        or process_info.get("playerSize")
        or _legacy_lookup(legacy_base, "Player Offset Length")
    )
    if player_stride_val <= 0:
        vinfo = _version_info(version_label)
        vgi = cast(dict[str, Any], vinfo.get("game_info") or {})
        player_stride_val = to_int(vgi.get("playerSize") or vgi.get("player_size"))
    if player_stride_val <= 0:
        warnings.append("Player stride missing; defaulting to 0.")
    else:
        PLAYER_STRIDE = player_stride_val
    team_stride_val = to_int(
        game_info.get("teamSize")
        or process_info.get("teamSize")
        or _legacy_lookup(legacy_base, "Team Offset Length")
    )
    if team_stride_val <= 0:
        vinfo = _version_info(version_label)
        vgi = cast(dict[str, Any], vinfo.get("game_info") or {})
        team_stride_val = to_int(vgi.get("teamSize") or vgi.get("team_size"))
    if team_stride_val <= 0:
        warnings.append("Team stride missing; defaulting to 0.")
    else:
        TEAM_STRIDE = team_stride_val
        TEAM_RECORD_SIZE = TEAM_STRIDE
    base_pointers: dict[str, Any] = base_pointers_source if isinstance(base_pointers_source, dict) else {}
    if not base_pointers and versions_map:
        vinfo = _version_info(version_label)
        v_bp = cast(dict[str, Any], vinfo.get("base_pointers") or {})
        if v_bp:
            base_pointers = v_bp
    if not isinstance(base_pointers, dict):
        base_pointers = {}
    if not base_pointers:
        legacy_player_addr_raw = _legacy_lookup(legacy_base, "Player Base Address")
        legacy_player_chain = _legacy_lookup(legacy_base, "Player Offset Chain")
        if legacy_player_addr_raw is not None:
            addr_int = to_int(legacy_player_addr_raw)
            direct_player = not legacy_player_chain
            absolute_flag = True
            if addr_int and process_base_addr:
                if 0 <= addr_int < process_base_addr:
                    absolute_flag = False
            entry: dict[str, object] = {
                "address": addr_int,
                "absolute": absolute_flag,
                "chain": legacy_player_chain if isinstance(legacy_player_chain, list) else [],
            }
            if direct_player:
                entry["direct_table"] = True
            base_pointers["Player"] = entry
        legacy_team_addr_raw = _legacy_lookup(legacy_base, "Team Base Address")
        legacy_team_chain = _legacy_lookup(legacy_base, "Team Offset Chain")
        if legacy_team_addr_raw is not None:
            addr_int = to_int(legacy_team_addr_raw)
            direct_team = not legacy_team_chain
            absolute_flag = True
            if addr_int and process_base_addr:
                if 0 <= addr_int < process_base_addr:
                    absolute_flag = False
            entry: dict[str, object] = {
                "address": addr_int,
                "absolute": absolute_flag,
                "chain": legacy_team_chain if isinstance(legacy_team_chain, list) else [],
            }
            if direct_team:
                entry["direct_table"] = True
            base_pointers["Team"] = entry
    global TEAM_TABLE_RVA
    TEAM_TABLE_RVA = to_int(_legacy_lookup(legacy_base, "Team Base Address"))

    def _pointer_address(defn: dict | None) -> tuple[int, bool]:
        if not isinstance(defn, dict):
            return 0, False
        for key in ("address", "rva", "base"):
            if key in defn:
                return to_int(defn.get(key)), True
        return 0, False

    PLAYER_PTR_CHAINS.clear()
    player_base = base_pointers.get("Player")
    player_addr, player_addr_defined = _pointer_address(player_base)
    if not player_addr_defined:
        warnings.append("Player base pointer definition missing; live player scanning disabled.")
        PLAYER_TABLE_RVA = 0
    else:
        PLAYER_TABLE_RVA = player_addr
        chains = _parse_pointer_chain_config(player_base)
        if chains:
            PLAYER_PTR_CHAINS.extend(chains)
        else:
            warnings.append("Player base pointer chain produced no resolvable entries; live player scanning disabled.")
    TEAM_PTR_CHAINS.clear()
    team_base = base_pointers.get("Team")
    team_addr, team_addr_defined = _pointer_address(team_base)
    if not team_addr_defined:
        warnings.append("Team base pointer definition missing; team scanning disabled.")
    else:
        chains = _parse_pointer_chain_config(team_base)
        if chains:
            TEAM_PTR_CHAINS.extend(chains)
        else:
            warnings.append("Team base pointer chain produced no resolvable entries; team scanning disabled.")
    DRAFT_PTR_CHAINS.clear()
    draft_entry = (
        base_pointers.get("DraftClass")
        or base_pointers.get("draftclass")
        or base_pointers.get("Draft")
    )
    if draft_entry:
        draft_chains = _parse_pointer_chain_config(draft_entry)
        if draft_chains:
            DRAFT_PTR_CHAINS.extend(draft_chains)
    pointer_candidates = data.get("pointer_candidates") or data.get("PointerCandidates")
    if isinstance(pointer_candidates, dict):
        extra_player_candidates = (
            pointer_candidates.get("Player")
            or pointer_candidates.get("player")
            or pointer_candidates.get("Players")
        )
        if extra_player_candidates:
            _extend_pointer_candidates(PLAYER_PTR_CHAINS, extra_player_candidates)
        extra_team_candidates = (
            pointer_candidates.get("Team")
            or pointer_candidates.get("team")
            or pointer_candidates.get("Teams")
        )
        if extra_team_candidates:
            _extend_pointer_candidates(TEAM_PTR_CHAINS, extra_team_candidates)
        extra_draft_candidates = (
            pointer_candidates.get("DraftClass")
            or pointer_candidates.get("draft")
            or pointer_candidates.get("draftclass")
        )
        if extra_draft_candidates:
            _extend_pointer_candidates(DRAFT_PTR_CHAINS, extra_draft_candidates)
        extra_staff_candidates = pointer_candidates.get("Staff") or pointer_candidates.get("staff")
        if extra_staff_candidates:
            _extend_pointer_candidates(STAFF_PTR_CHAINS, extra_staff_candidates)
        extra_stadium_candidates = (
            pointer_candidates.get("Stadium")
            or pointer_candidates.get("stadium")
            or pointer_candidates.get("Stadiums")
        )
        if extra_stadium_candidates:
            _extend_pointer_candidates(STADIUM_PTR_CHAINS, extra_stadium_candidates)
    name_char_limit: int | None = None

    def _derive_char_capacity(offset_val: int, enc: str, length_val: int) -> int | None:
        if length_val > 0:
            return length_val
        if PLAYER_STRIDE > 0 and offset_val >= 0:
            try:
                remaining = max(0, PLAYER_STRIDE - offset_val)
                return remaining
            except Exception:
                return None
        return None

    first_entry = _find_offset_entry("First Name", "Vitals")
    if not first_entry:
        OFF_FIRST_NAME = to_int(_legacy_lookup(legacy_base, "Offset Player First Name", "Offset First Name", "First Name Offset")) or 0
        FIRST_NAME_ENCODING = "utf16"
        if OFF_FIRST_NAME > 0:
            cap = _derive_char_capacity(OFF_FIRST_NAME, FIRST_NAME_ENCODING, 0)
            if cap is not None:
                name_char_limit = cap if name_char_limit is None else max(name_char_limit, cap)
            warnings.append("Vitals.First Name not found; using Base offset.")
        else:
            warnings.append("Vitals.First Name not found; name editing limited.")
    else:
        OFF_FIRST_NAME = to_int(first_entry.get("address"))
        if OFF_FIRST_NAME < 0:
            warnings.append("First Name address must be zero or positive; disabling first-name edits.")
            OFF_FIRST_NAME = 0
        first_type = str(first_entry.get("type", "")).lower()
        FIRST_NAME_ENCODING = "ascii" if first_type in ("string", "text") else "utf16"
        length_val = to_int(first_entry.get("length"))
        cap = _derive_char_capacity(OFF_FIRST_NAME, FIRST_NAME_ENCODING, length_val)
        if cap is not None:
            name_char_limit = cap if name_char_limit is None else max(name_char_limit, cap)
    last_entry = _find_offset_entry("Last Name", "Vitals")
    if not last_entry:
        OFF_LAST_NAME = to_int(_legacy_lookup(legacy_base, "Offset Player Last Name", "Offset Last Name", "Last Name Offset")) or 0
        LAST_NAME_ENCODING = "utf16"
        if OFF_LAST_NAME >= 0:
            cap = _derive_char_capacity(OFF_LAST_NAME, LAST_NAME_ENCODING, 0)
            if cap is not None:
                name_char_limit = cap if name_char_limit is None else max(name_char_limit, cap)
            warnings.append("Vitals.Last Name not found; using Base offset.")
        else:
            warnings.append("Vitals.Last Name not found; name editing limited.")
    else:
        OFF_LAST_NAME = to_int(last_entry.get("address"))
        if OFF_LAST_NAME < 0:
            warnings.append("Last Name address must be zero or positive; disabling last-name edits.")
            OFF_LAST_NAME = 0
        last_type = str(last_entry.get("type", "")).lower()
        LAST_NAME_ENCODING = "ascii" if last_type in ("string", "text") else "utf16"
        length_val = to_int(last_entry.get("length"))
        cap = _derive_char_capacity(OFF_LAST_NAME, LAST_NAME_ENCODING, length_val)
        if cap is not None:
            name_char_limit = cap if name_char_limit is None else max(name_char_limit, cap)
    if name_char_limit is not None:
        NAME_MAX_CHARS = name_char_limit
    team_entry = _find_offset_entry("Current Team", "Vitals")
    if not team_entry:
        OFF_TEAM_PTR = 0
        OFF_TEAM_ID = to_int(_legacy_lookup(legacy_base, "Offset Player Team", "Player Team Offset")) or 0
        if OFF_TEAM_ID <= 0:
            warnings.append("Player_Info.Vitals.Current Team entry missing; team link disabled.")
    else:
        OFF_TEAM_PTR = to_int(
            team_entry.get("dereferenceAddress")
            or team_entry.get("deref_offset")
            or team_entry.get("dereference_address")
        )
        if OFF_TEAM_PTR < 0:
            warnings.append("Current Team deref address must be >= 0; disabling team link.")
            OFF_TEAM_PTR = 0
        OFF_TEAM_ID = to_int(team_entry.get("address")) or to_int(_legacy_lookup(legacy_base, "Offset Player Team", "Player Team Offset")) or 0
    team_name_entry = _find_offset_entry("Team Name", "Teams")
    if not team_name_entry:
        TEAM_NAME_OFFSET = to_int(_legacy_lookup(legacy_base, "Offset Team Name", "Team Name Offset")) or 0
        TEAM_NAME_ENCODING = "utf16"
        if TEAM_NAME_OFFSET > 0 and TEAM_STRIDE > 0:
            TEAM_NAME_LENGTH = max(0, TEAM_STRIDE - TEAM_NAME_OFFSET)
            OFF_TEAM_NAME = TEAM_NAME_OFFSET
            warnings.append("Teams.Team Name missing; using Base offset and derived length.")
        else:
            warnings.append("Teams.Team Name entry missing; team names disabled.")
            TEAM_NAME_LENGTH = 0
            OFF_TEAM_NAME = 0
    else:
        TEAM_NAME_OFFSET = to_int(team_name_entry.get("address"))
        if TEAM_NAME_OFFSET < 0:
            warnings.append("Team Name address must be >= 0; team names disabled.")
            TEAM_NAME_OFFSET = 0
        team_type = str(team_name_entry.get("type", "")).lower()
        TEAM_NAME_ENCODING = "ascii" if team_type in ("string", "text") else "utf16"
        TEAM_NAME_LENGTH = to_int(team_name_entry.get("length"))
        if TEAM_NAME_LENGTH <= 0:
            if TEAM_STRIDE > 0 and TEAM_NAME_OFFSET >= 0:
                remaining = max(0, TEAM_STRIDE - TEAM_NAME_OFFSET)
                TEAM_NAME_LENGTH = remaining
            if TEAM_NAME_LENGTH <= 0:
                warnings.append("Team Name length unavailable; team names disabled.")
        OFF_TEAM_NAME = TEAM_NAME_OFFSET
    team_player_entries = [
        entry for (cat, _), entry in _offset_index.items() if cat == "team players"
    ]
    if team_player_entries:
        TEAM_PLAYER_SLOT_COUNT = len(team_player_entries)
    TEAM_FIELD_DEFS.clear()
    for label, entry_name in TEAM_FIELD_SPECS:
        entry_obj = _find_offset_entry(entry_name, "Teams")
        if not isinstance(entry_obj, dict):
            continue
        offset = to_int(entry_obj.get("address"))
        length_val = to_int(entry_obj.get("length"))
        entry_type = str(entry_obj.get("type", "")).lower()
        if offset <= 0 or length_val <= 0:
            continue
        if entry_type not in ("wstring", "string", "text"):
            continue
        encoding = "ascii" if entry_type in ("string", "text") else "utf16"
        TEAM_FIELD_DEFS[label] = (offset, length_val, encoding)
    if TEAM_STRIDE > 0:
        TEAM_RECORD_SIZE = TEAM_STRIDE
    # Staff stride/name metadata
    staff_stride_val = to_int(
        game_info.get("staffSize")
        or process_info.get("staffSize")
        or _legacy_lookup(legacy_base, "Staff Offset Length")
    )
    if staff_stride_val <= 0:
        vinfo = _version_info(version_label)
        vgi = cast(dict[str, Any], vinfo.get("game_info") or {})
        staff_stride_val = to_int(vgi.get("staffSize") or vgi.get("staff_size"))
    STAFF_STRIDE = max(0, staff_stride_val or 0)
    STAFF_RECORD_SIZE = STAFF_STRIDE
    STAFF_PTR_CHAINS.clear()
    staff_base = base_pointers.get("Staff")
    staff_addr, staff_addr_defined = _pointer_address(staff_base)
    if staff_addr_defined:
        chains = _parse_pointer_chain_config(staff_base)
        if chains:
            STAFF_PTR_CHAINS.extend(chains)
    staff_first_entry = _find_offset_entry("Staff Vitals - FIRSTNAME", "Staff")
    staff_last_entry = _find_offset_entry("Staff Vitals - LASTNAME", "Staff")
    staff_name_entry = staff_first_entry or staff_last_entry
    if staff_name_entry:
        STAFF_NAME_OFFSET = to_int(staff_name_entry.get("address")) or 0
        entry_type = str(staff_name_entry.get("type", "")).lower()
        STAFF_NAME_ENCODING = "ascii" if entry_type in ("string", "text") else "utf16"
        STAFF_NAME_LENGTH = to_int(staff_name_entry.get("length")) or 0
        if STAFF_NAME_LENGTH <= 0 and STAFF_STRIDE > 0 and STAFF_NAME_OFFSET > 0:
            remaining = max(0, STAFF_STRIDE - STAFF_NAME_OFFSET)
            STAFF_NAME_LENGTH = remaining
    # Stadium stride/name metadata
    stadium_stride_val = to_int(
        game_info.get("stadiumSize")
        or process_info.get("stadiumSize")
        or _legacy_lookup(legacy_base, "Stadium Offset Length")
    )
    if stadium_stride_val <= 0:
        vinfo = _version_info(version_label)
        vgi = cast(dict[str, Any], vinfo.get("game_info") or {})
        stadium_stride_val = to_int(vgi.get("stadiumSize") or vgi.get("stadium_size"))
    STADIUM_STRIDE = max(0, stadium_stride_val or 0)
    STADIUM_RECORD_SIZE = STADIUM_STRIDE
    STADIUM_PTR_CHAINS.clear()
    stadium_base = base_pointers.get("Stadium")
    stadium_addr, stadium_addr_defined = _pointer_address(stadium_base)
    if stadium_addr_defined:
        chains = _parse_pointer_chain_config(stadium_base)
        if chains:
            STADIUM_PTR_CHAINS.extend(chains)
    stadium_name_entry = _find_offset_entry("Stadium Vitals - NAME", "Stadium")
    if stadium_name_entry:
        STADIUM_NAME_OFFSET = to_int(stadium_name_entry.get("address")) or 0
        entry_type = str(stadium_name_entry.get("type", "")).lower()
        STADIUM_NAME_ENCODING = "ascii" if entry_type in ("string", "text") else "utf16"
        STADIUM_NAME_LENGTH = to_int(stadium_name_entry.get("length")) or 0
        if STADIUM_NAME_LENGTH <= 0 and STADIUM_STRIDE > 0 and STADIUM_NAME_OFFSET > 0:
            remaining = max(0, STADIUM_STRIDE - STADIUM_NAME_OFFSET)
            STADIUM_NAME_LENGTH = remaining
    if errors:
        raise OffsetSchemaError(" ; ".join(errors))
    if warnings:
        warning_text = " ; ".join(dict.fromkeys(warnings))
        print(f"Offset warnings: {warning_text}")


def initialize_offsets(
    target_executable: str | None = None,
    force: bool = False,
    base_pointer_overrides: dict[str, int] | None = None,
) -> None:
    """Ensure offset data for the requested executable is loaded."""
    global _offset_file_path, _offset_config, MODULE_NAME, _current_offset_target, _base_pointer_overrides
    target_exec = target_executable or MODULE_NAME
    target_key = target_exec.lower()
    overrides_norm = _normalize_base_pointer_overrides(base_pointer_overrides)
    if overrides_norm:
        _base_pointer_overrides = overrides_norm
    elif _base_pointer_overrides:
        overrides_norm = dict(_base_pointer_overrides)
    if _offset_config is not None and not force and _current_offset_target == target_key:
        MODULE_NAME = target_exec
        if overrides_norm:
            _apply_base_pointer_overrides(_offset_config, overrides_norm)
            _apply_offset_config(_offset_config)
        return
    path, data = _load_offset_config_file(target_exec)
    if data is None:
        raise OffsetSchemaError(
            f"Unable to locate offset schema for {target_exec}. Expected {OFFSETS_BUNDLE_FILE} in the Offsets folder."
        )
    if overrides_norm:
        _apply_base_pointer_overrides(data, overrides_norm)
    _offset_file_path = path
    _offset_config = data
    MODULE_NAME = target_exec
    _apply_offset_config(data)
    MODULE_NAME = target_exec
    _current_offset_target = target_key


__all__ = [
    "OffsetSchemaError",
    "initialize_offsets",
    "OFFSET_FIELD_SYNONYMS",
    "CATEGORY_ALIASES",
    "CATEGORY_SUPER_TYPES",
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
class VersionInfo(TypedDict, total=False):
    """Offsets bundle metadata for a specific game version."""
    game_info: dict[str, Any]
    base_pointers: dict[str, Any]
