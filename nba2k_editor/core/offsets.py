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
from importlib import resources
from typing import Any, cast

from .conversions import to_int

MODULE_NAME = "NBA2K26.exe"
HOOK_TARGET_LABELS: dict[str, str] = {
    "nba2k26.exe": "NBA 2K26",
    "nba2k25.exe": "NBA 2K25",
    "nba2k24.exe": "NBA 2K24",
    "nba2k23.exe": "NBA 2K23",
    "nba2k22.exe": "NBA 2K22",
}



class OffsetSchemaError(RuntimeError):
    """Raised when offsets are missing required definitions."""


BASE_POINTER_SIZE_KEY_MAP: dict[str, str | None] = {
    "Player": "playerSize",
    "DraftClass": "draftClassSize",
    "Team": "teamSize",
    "Staff": "staffSize",
    "Stadium": "stadiumSize",
    "TeamHistory": "historySize",
    "NBAHistory": "historySize",
    "Record": "recordSize",
    "HallOfFame": "hallOfFameSize",
    "History": "historySize",
    "Jersey": "jerseySize",
    "Shoes": "shoeSize",
    "career_stats": "careerStatsSize",
    "Cursor": None,
}

_OFFSETS_RESOURCE_ROOT = resources.files("nba2k_editor.core") / "Offsets"
_LEAGUE_OFFSETS_FILE = "offsets_league.json"
_DROPDOWNS_FILE = "dropdowns.json"
_SUPER_TYPE_OFFSETS_FILES: dict[str, str] = {
    "Players": "offsets_players.json",
    "Draft Class": "offsets_players.json",
    "Teams": "offsets_teams.json",
    "Staff": "offsets_staff.json",
    "Stadiums": "offsets_stadiums.json",
    "Jerseys": "offsets_jersey.json",
    "Shoes": "offsets_shoes.json",
    "NBA History": "offsets_history.json",
    "NBA Records": "offsets_history.json",
}

PLAYER_TABLE_RVA = 0
PLAYER_STRIDE = 0
PLAYER_PTR_CHAINS: list[dict[str, object]] = []
DRAFT_PTR_CHAINS: list[dict[str, object]] = []
OFF_LAST_NAME = 0
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
TEAM_PTR_CHAINS: list[dict[str, object]] = []
TEAM_TABLE_RVA = 0
TEAM_RECORD_SIZE = TEAM_STRIDE

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


def _select_active_version(
    versions_map: dict[str, object],
    target_executable: str | None,
    *,
    require_hint: bool = False,
) -> tuple[str, str, dict[str, object]] | None:
    del require_hint
    version_hint = _derive_version_label(target_executable)
    selected_label = cast(str, version_hint)
    selected_key = next(str(key) for key in versions_map.keys() if _version_key_matches(key, selected_label))
    return selected_label, selected_key, cast(dict[str, object], versions_map[selected_key])


def _resolved_length_bits(version_payload: dict[str, object]) -> int:
    explicit_length = to_int(version_payload.get("length"))
    if explicit_length > 0:
        return explicit_length
    bit_length = to_int(version_payload.get("bit_length"))
    if bit_length > 0:
        return bit_length
    byte_length = to_int(version_payload.get("byteLength"))
    if byte_length > 0:
        return byte_length * 8
    return 0


def get_editor_layout_for_super(super_type: str) -> dict[str, object]:
    """Return the owning offsets file's authored structure directly."""
    target_super = str(super_type or "").strip()
    source_file = _SUPER_TYPE_OFFSETS_FILES[target_super]
    layout_super = "Players" if target_super == "Draft Class" else target_super
    raw_domain = _load_offsets_resource(source_file)
    layout = cast(dict[str, object], raw_domain[layout_super])
    dropdowns = _load_offsets_resource(_DROPDOWNS_FILE).get(layout_super)
    if not isinstance(dropdowns, dict):
        return layout
    for section, dropdown_groups in dropdowns.items():
        layout_groups = layout.get(str(section))
        if not isinstance(layout_groups, dict) or not isinstance(dropdown_groups, dict):
            continue
        for group, dropdown_entries in dropdown_groups.items():
            layout_entries = layout_groups.get(str(group))
            if not isinstance(layout_entries, list) or not isinstance(dropdown_entries, list):
                continue
            layout_by_name = {
                str(entry.get("normalized_name")): entry
                for entry in layout_entries
                if isinstance(entry, dict) and entry.get("normalized_name")
            }
            for dropdown_entry in dropdown_entries:
                if not isinstance(dropdown_entry, dict):
                    continue
                layout_entry = layout_by_name.get(str(dropdown_entry.get("normalized_name")))
                if not isinstance(layout_entry, dict):
                    continue
                layout_versions = layout_entry.get("versions")
                dropdown_versions = dropdown_entry.get("versions")
                if not isinstance(layout_versions, dict) or not isinstance(dropdown_versions, dict):
                    continue
                for dropdown_version_key, dropdown_payload in dropdown_versions.items():
                    if not isinstance(dropdown_payload, dict):
                        continue
                    dropdown_tokens = set(_split_version_tokens(dropdown_version_key))
                    for layout_version_key, layout_payload in layout_versions.items():
                        if not isinstance(layout_payload, dict):
                            continue
                        layout_tokens = set(_split_version_tokens(layout_version_key))
                        if not dropdown_tokens or not layout_tokens or not dropdown_tokens.intersection(layout_tokens):
                            continue
                        for option_key in ("dropdown", "values"):
                            if option_key in dropdown_payload:
                                layout_payload[option_key] = dropdown_payload[option_key]
    return layout


def _load_offsets_resource(file_name: str) -> dict[str, object]:
    raw = json.loads((_OFFSETS_RESOURCE_ROOT / file_name).read_text(encoding="utf-8"))
    return dict(cast(dict[str, object], raw))


def _load_league_offset_config(target_executable: str | None = None) -> dict[str, object]:
    """Load the authored league offsets resource only."""
    target_exec = str(target_executable or MODULE_NAME or "").strip()
    league_raw = _load_offsets_resource(_LEAGUE_OFFSETS_FILE)
    versions = cast(dict[str, object], league_raw["versions"])
    _version_label, version_key, version_info = cast(
        tuple[str, str, dict[str, object]],
        _select_active_version(versions, target_exec, require_hint=True),
    )
    converted: dict[str, object] = {
        "versions": {version_key: version_info},
        "super_type_map": cast(dict[str, object], league_raw["super_type_map"]),
        "base_pointers": cast(dict[str, object], version_info["base_pointers"]),
        "game_info": {
            **cast(dict[str, object], version_info["game_info"]),
            **cast(dict[str, object], version_info["stride_constants"]),
        },
    }
    if "league_category_pointer_map" in league_raw:
        converted["league_category_pointer_map"] = cast(dict[str, object], league_raw["league_category_pointer_map"])
    return converted


def get_active_offset_config(target_executable: str | None = None) -> dict[str, object]:
    target_exec = str(target_executable or MODULE_NAME or "").strip()
    data = _load_league_offset_config(target_exec)
    return cast(dict[str, object], data)


def _derive_version_label(executable: str | None) -> str:
    exe = str(executable or MODULE_NAME).strip().lower()
    mapped = HOOK_TARGET_LABELS.get(exe)
    if mapped:
        return "2K" + re.search(r"(\d{2})$", mapped).group(1)
    return "2K" + re.search(r"nba2k(\d{2})\.exe$", exe).group(1)


def _resolve_version_context(
    data: dict[str, Any] | None,
    target_executable: str | None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    versions = cast(dict[str, object], cast(dict[str, Any], data)["versions"])
    version_label, selected_key, _selected = cast(
        tuple[str, str, dict[str, object]],
        _select_active_version(versions, target_executable, require_hint=True),
    )
    return (
        version_label or selected_key,
        cast(dict[str, Any], cast(dict[str, Any], data)["base_pointers"]),
        cast(dict[str, Any], cast(dict[str, Any], data)["game_info"]),
    )



def _normalize_chain_steps(chain_data: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "offset": to_int(step["offset"]),
            "dereference": bool(step["dereference"]),
        }
        for step in chain_data
    ]


def _parse_pointer_chain_config(base_cfg: dict[str, object]) -> list[dict[str, object]]:
    if isinstance(base_cfg, list):
        return [chain for entry in base_cfg for chain in _parse_pointer_chain_config(cast(dict[str, object], entry))]
    chain = _normalize_chain_steps(cast(list[dict[str, object]], base_cfg["chain"] if "chain" in base_cfg else base_cfg["steps"]))
    direct_table = bool(base_cfg["direct_table"]) if "direct_table" in base_cfg else False
    final_offset = 0 if direct_table else to_int(base_cfg["finalOffset"]) if "finalOffset" in base_cfg else 0
    return [{
        "address": to_int(base_cfg["address"]),
        "absolute": bool(base_cfg["absolute"]) if "absolute" in base_cfg else False,
        "finalOffset": final_offset,
        "direct_table": direct_table,
        "steps": chain,
    }]


def _apply_offset_config(data: dict | None, target_executable: str | None = None) -> None:
    """Update module-level constants using the loaded offset data."""
    global MODULE_NAME, PLAYER_TABLE_RVA, PLAYER_STRIDE
    global PLAYER_PTR_CHAINS, OFF_LAST_NAME
    global OFF_TEAM_ID, NAME_MAX_CHARS
    global FIRST_NAME_ENCODING, LAST_NAME_ENCODING, TEAM_NAME_ENCODING
    global TEAM_STRIDE
    global TEAM_PTR_CHAINS, TEAM_RECORD_SIZE
    global STAFF_STRIDE, STAFF_RECORD_SIZE, STAFF_PTR_CHAINS, STAFF_NAME_OFFSET, STAFF_NAME_LENGTH, STAFF_NAME_ENCODING
    global STADIUM_STRIDE, STADIUM_RECORD_SIZE, STADIUM_PTR_CHAINS, STADIUM_NAME_OFFSET, STADIUM_NAME_LENGTH, STADIUM_NAME_ENCODING
    _version_label, base_pointers, game_info = _resolve_version_context(
        cast(dict[str, Any], data),
        target_executable or MODULE_NAME,
    )

    MODULE_NAME = str(game_info["executable"])

    PLAYER_STRIDE = max(0, to_int(game_info["playerSize"]))
    TEAM_STRIDE = max(0, to_int(game_info["teamSize"]))
    STAFF_STRIDE = max(0, to_int(game_info["staffSize"]))
    STADIUM_STRIDE = max(0, to_int(game_info["stadiumSize"]))
    TEAM_RECORD_SIZE = TEAM_STRIDE
    STAFF_RECORD_SIZE = STAFF_STRIDE
    STADIUM_RECORD_SIZE = STADIUM_STRIDE

    PLAYER_PTR_CHAINS.clear()
    player_chains = _parse_pointer_chain_config(cast(dict[str, object], base_pointers["Player"]))
    PLAYER_PTR_CHAINS.extend(player_chains)
    PLAYER_TABLE_RVA = to_int(player_chains[0].get("address"))

    TEAM_PTR_CHAINS.clear()
    team_chains = _parse_pointer_chain_config(cast(dict[str, object], base_pointers["Team"]))
    global TEAM_TABLE_RVA
    TEAM_TABLE_RVA = to_int(team_chains[0].get("address"))
    TEAM_PTR_CHAINS.extend(team_chains)

    DRAFT_PTR_CHAINS.clear()
    draft_entry = base_pointers.get("DraftClass")
    if draft_entry is not None:
        DRAFT_PTR_CHAINS.extend(_parse_pointer_chain_config(cast(dict[str, object], draft_entry)))
    OFF_LAST_NAME = 0
    OFF_TEAM_ID = 0
    NAME_MAX_CHARS = 0
    FIRST_NAME_ENCODING = "utf16"
    LAST_NAME_ENCODING = "utf16"
    TEAM_NAME_ENCODING = "utf16"

    STAFF_PTR_CHAINS.clear()
    STAFF_PTR_CHAINS.extend(_parse_pointer_chain_config(cast(dict[str, object], base_pointers["Staff"])))
    STAFF_NAME_OFFSET = 0
    STAFF_NAME_LENGTH = 0
    STAFF_NAME_ENCODING = "utf16"

    STADIUM_PTR_CHAINS.clear()
    STADIUM_PTR_CHAINS.extend(_parse_pointer_chain_config(cast(dict[str, object], base_pointers["Stadium"])))
    STADIUM_NAME_OFFSET = 0
    STADIUM_NAME_LENGTH = 0
    STADIUM_NAME_ENCODING = "utf16"


def has_active_config() -> bool:
    return bool(PLAYER_STRIDE > 0 or TEAM_STRIDE > 0 or PLAYER_PTR_CHAINS or TEAM_PTR_CHAINS)


def get_current_target() -> str:
    return str(MODULE_NAME)


def initialize_offsets(
    target_executable: str | None = None,
    force: bool = False,
) -> None:
    """Ensure embedded offset data for the requested executable is loaded."""
    global MODULE_NAME
    target_exec = target_executable or MODULE_NAME
    if not force and has_active_config() and str(MODULE_NAME or "").lower() == str(target_exec).lower():
        MODULE_NAME = target_exec
        return
    data = get_active_offset_config(target_exec)
    MODULE_NAME = target_exec
    _apply_offset_config(data, target_exec)
    MODULE_NAME = target_exec


__all__ = [
    "OffsetSchemaError",
    "get_active_offset_config",
    "get_current_target",
    "get_editor_layout_for_super",
    "has_active_config",
    "initialize_offsets",
    "BASE_POINTER_SIZE_KEY_MAP",
    "PLAYER_TABLE_RVA",
    "PLAYER_STRIDE",
    "PLAYER_PTR_CHAINS",
    "DRAFT_PTR_CHAINS",
    "DRAFT_CLASS_TEAM_ID",
    "OFF_LAST_NAME",
    "OFF_TEAM_ID",
    "MAX_PLAYERS",
    "MAX_DRAFT_PLAYERS",
    "MAX_TEAMS_SCAN",
    "NAME_MAX_CHARS",
    "FIRST_NAME_ENCODING",
    "LAST_NAME_ENCODING",
    "TEAM_NAME_ENCODING",
    "TEAM_STRIDE",
    "TEAM_PTR_CHAINS",
    "TEAM_TABLE_RVA",
    "TEAM_RECORD_SIZE",
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
]
