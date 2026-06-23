from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")
_MODEL_PREFIX = "POSITION_STAT_NEIGHBOR_MODEL_"
_SUGGESTIONS_FILE = "suggested_field_values.csv"
@dataclass(frozen=True)
class NeighborFieldSuggestion:
    field_key: str
    value: int | str
    source_rule: str
    evidence_keys: tuple[str, ...]



@dataclass(frozen=True)
class PositionSelection:
    primary: str
    secondary: str | None
    all_positions: tuple[str, ...]


@dataclass(frozen=True)
class StatNeighborModel:
    path: Path
    suggestions_by_player_position: dict[tuple[str, str], dict[str, NeighborFieldSuggestion]]
    suggestions_by_player_team_position: dict[tuple[str, str, str], dict[str, NeighborFieldSuggestion]]

    def suggestions_for(self, *, player_id: str, team: str, position: str) -> dict[str, NeighborFieldSuggestion]:
        team_key = (_clean_key(player_id), _clean_key(team), position.strip().upper())
        exact = self.suggestions_by_player_team_position.get(team_key)
        if exact:
            return dict(exact)
        player_key = (_clean_key(player_id), position.strip().upper())
        return dict(self.suggestions_by_player_position.get(player_key, {}))


def select_positions_from_evidence(play_by_play: dict[str, Any], fallback_pos: object = None) -> PositionSelection:
    percent_rows: list[tuple[str, float]] = []
    for pos, col in (
        ("PG", "pg_percent"),
        ("SG", "sg_percent"),
        ("SF", "sf_percent"),
        ("PF", "pf_percent"),
        ("C", "c_percent"),
    ):
        value = _float(play_by_play.get(col))
        if value is not None and value > 0:
            percent_rows.append((pos, value))
    if percent_rows:
        ordered = tuple(pos for pos, _ in sorted(percent_rows, key=lambda item: (-item[1], POSITIONS.index(item[0]))))
        return PositionSelection(primary=ordered[0], secondary=ordered[1] if len(ordered) > 1 else None, all_positions=ordered)

    parsed = _parse_listed_positions(fallback_pos)
    primary = parsed[0] if parsed else ""
    secondary = parsed[1] if len(parsed) > 1 else None
    return PositionSelection(primary=primary, secondary=secondary, all_positions=parsed)


@lru_cache(maxsize=1)
def load_latest_stat_neighbor_model() -> StatNeighborModel:
    model_dir = _latest_model_dir()
    field_map = _field_key_map()
    suggestions_by_team: dict[tuple[str, str, str], dict[str, NeighborFieldSuggestion]] = {}
    suggestions_by_player: dict[tuple[str, str], dict[str, NeighborFieldSuggestion]] = {}
    suggestion_path = model_dir / _SUGGESTIONS_FILE
    suggestion_relpath = str(suggestion_path.relative_to(_repo_root()))
    with suggestion_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            field_key = field_map.get((str(row.get("Type") or ""), str(row.get("Input Field") or "")))
            if not field_key:
                continue
            value = _int_round(row.get("suggested_top5_median"))
            if value is None:
                continue
            key = (_clean_key(row.get("target_player_id")), _clean_key(row.get("target_team")), str(row.get("position") or "").strip().upper())
            if not all(key):
                continue
            suggestion = NeighborFieldSuggestion(
                field_key=field_key,
                value=value,
                source_rule="position_stat_neighbor_top5_median",
                evidence_keys=(
                    suggestion_relpath,
                    f"position={key[2]}",
                    f"neighbor_count={row.get('neighbor_count')}",
                    f"top_neighbor={row.get('top_neighbor')}",
                ),
            )
            suggestions_by_team.setdefault(key, {})[field_key] = suggestion
            suggestions_by_player.setdefault((key[0], key[2]), {})[field_key] = suggestion
    return StatNeighborModel(path=model_dir, suggestions_by_player_position=suggestions_by_player, suggestions_by_player_team_position=suggestions_by_team)


@lru_cache(maxsize=1)
def hot_zone_neutral_values() -> dict[str, NeighborFieldSuggestion]:
    values: dict[str, NeighborFieldSuggestion] = {}
    for section, group, normalized, _display in _offset_entries():
        if section == "Tendencies" and _identity(group) == "HOTZONES":
            field_key = f"{section}/{normalized}"
            values[field_key] = NeighborFieldSuggestion(
                field_key=field_key,
                value="Neutral",
                source_rule="hot_zone_neutral_default",
                evidence_keys=("hot_zones_default_neutral",),
            )
    return values


def _latest_model_dir() -> Path:
    base = _repo_root() / "outputs" / "current_active_stat_extractor_runs"
    candidates = []
    for path in base.iterdir() if base.exists() else ():
        if not path.is_dir() or not path.name.startswith(_MODEL_PREFIX):
            continue
        suffix = path.name[len(_MODEL_PREFIX) :]
        if suffix.isdigit() and (path / _SUGGESTIONS_FILE).is_file():
            candidates.append((int(suffix), path))
    if not candidates:
        raise FileNotFoundError(f"no {_MODEL_PREFIX}### artifact with {_SUGGESTIONS_FILE} under {base}")
    return max(candidates, key=lambda item: item[0])[1]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _field_key_map() -> dict[tuple[str, str], str]:
    entries = _offset_entries()
    out: dict[tuple[str, str], str] = {}
    suggestion_path = _latest_model_dir() / _SUGGESTIONS_FILE
    with suggestion_path.open(newline="", encoding="utf-8-sig") as handle:
        pairs = sorted({(str(row.get("Type") or ""), str(row.get("Input Field") or "")) for row in csv.DictReader(handle)})
    for field_type, input_field in pairs:
        section = "Attributes" if field_type == "Attribute" else "Tendencies" if field_type == "Tendency" else ""
        if not section or "/" not in input_field:
            continue
        group_text, field_text = (part.strip() for part in input_field.split("/", 1))
        match = _find_offset_entry(entries, section, group_text, field_text)
        if match:
            _section, _group, normalized, _display = match
            out[(field_type, input_field)] = f"{section}/{normalized}"
    return out


def _find_offset_entry(entries: tuple[tuple[str, str, str, str], ...], section: str, group_text: str, field_text: str) -> tuple[str, str, str, str] | None:
    wanted_group = _identity(group_text)
    wanted_field = _identity(field_text)
    wanted_field_singular = wanted_field.rstrip("S")
    for entry in entries:
        sec, group, normalized, display = entry
        if sec != section or _identity(group) != wanted_group:
            continue
        identities = {_identity(normalized), _identity(display)}
        if wanted_field in identities or wanted_field_singular in {value.rstrip("S") for value in identities}:
            return entry
    return _manual_field_alias(section, wanted_group, wanted_field, entries)


def _manual_field_alias(section: str, group: str, field: str, entries: tuple[tuple[str, str, str, str], ...]) -> tuple[str, str, str, str] | None:
    aliases = {
        ("Tendencies", "JUMPSHOOTING", "CONTESTEDJUMPERMID"): "CONTESTEDJUMPERMIDRANGE",
        ("Tendencies", "LAYUPSANDDUNKS", "PUTBACKDUNK"): "PUTBACK",
    }
    normalized = aliases.get((section, group, field))
    if not normalized:
        return None
    for entry in entries:
        if entry[0] == section and _identity(entry[1]) == group and entry[2] == normalized:
            return entry
    return None


@lru_cache(maxsize=1)
def _offset_entries() -> tuple[tuple[str, str, str, str], ...]:
    path = _repo_root() / "nba2k_editor" / "core" / "Offsets" / "offsets_players.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    players = payload.get("Players")
    if not isinstance(players, dict):
        raise KeyError("offsets_players.json is missing Players")
    entries: list[tuple[str, str, str, str]] = []
    for section, groups in players.items():
        if not isinstance(groups, dict):
            continue
        for group, rows in groups.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized = str(row.get("normalized_name") or row.get("display_name") or "").strip()
                if not normalized:
                    continue
                display = str(row.get("display_name") or normalized).strip()
                entries.append((str(section), str(group), normalized, display))
    return tuple(entries)


def _parse_listed_positions(value: object) -> tuple[str, ...]:
    text = str(value or "").upper()
    found = [pos for pos in POSITIONS if re.search(rf"\b{pos}\b", text)]
    if found:
        return tuple(dict.fromkeys(found))
    if text == "G":
        return ("PG", "SG")
    if text == "F":
        return ("SF", "PF")
    if text == "G-F":
        return ("PG", "SG", "SF")
    if text == "F-C":
        return ("SF", "PF", "C")
    return ()


def _identity(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _clean_key(value: object) -> str:
    return str(value or "").strip().upper()


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_round(value: object) -> int | None:
    number = _float(value)
    if number is None:
        return None
    return int(round(number))


__all__ = [
    "NeighborFieldSuggestion",
    "PositionSelection",
    "StatNeighborModel",
    "hot_zone_neutral_values",
    "load_latest_stat_neighbor_model",
    "select_positions_from_evidence",
]
