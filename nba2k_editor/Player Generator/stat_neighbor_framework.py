from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")
FEATURES: tuple[str, ...] = (
    "pts_per36",
    "fga_per36",
    "fg_pct",
    "x3pa_per36",
    "x3p_pct",
    "fta_per36",
    "ft_pct",
    "ast_per36",
    "orb_per36",
    "drb_per36",
    "stl_per36",
    "blk_per36",
    "tov_per36",
    "pf_per36",
)
BODY_FEATURES: tuple[str, ...] = ("height_inches", "weight_pounds")
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
    candidates_by_position: dict[str, tuple[dict[str, Any], ...]]
    scales_by_position: dict[str, dict[str, tuple[float, float]]]

    def suggestions_for(self, *, player_id: str, team: str, position: str) -> dict[str, NeighborFieldSuggestion]:
        team_key = (_clean_key(player_id), _clean_key(team), position.strip().upper())
        exact = self.suggestions_by_player_team_position.get(team_key)
        if exact:
            return dict(exact)
        player_key = (_clean_key(player_id), position.strip().upper())
        return dict(self.suggestions_by_player_position.get(player_key, {}))

    def suggestions_for_evidence(self, *, evidence: Any, position: str) -> dict[str, NeighborFieldSuggestion]:
        return self.suggestions_for_features(
            target_features=target_features_from_evidence(evidence),
            position=position,
        )

    def suggestions_for_features(self, *, target_features: dict[str, float | None], position: str) -> dict[str, NeighborFieldSuggestion]:
        pos = str(position or "").strip().upper()
        candidates = self.candidates_by_position.get(pos, ())
        if not candidates:
            return {}
        relpath = str(self.path.relative_to(_repo_root()))
        values: dict[str, NeighborFieldSuggestion] = {}
        all_fields = sorted(set().union(*(set(candidate["fields"]) for candidate in candidates)))
        fields_by_features: dict[tuple[str, ...], list[str]] = {}
        for field_key in all_fields:
            fields_by_features.setdefault(_features_for_field(field_key), []).append(field_key)
        for section_features, field_keys in fields_by_features.items():
            neighbors = _nearest_neighbors(
                target_features,
                candidates,
                self.scales_by_position.get(pos, {}),
                features=section_features,
                k=5,
            )
            for field_key in field_keys:
                top = [row["candidate"] for row in neighbors if field_key in row["candidate"]["fields"]]
                if not top:
                    continue
                field_values = [float(candidate["fields"][field_key]) for candidate in top]
                values[field_key] = NeighborFieldSuggestion(
                    field_key=field_key,
                    value=int(round(median(field_values))),
                    source_rule="position_stat_neighbor_section_top5_median",
                    evidence_keys=(
                        relpath,
                        f"position={pos}",
                        f"section_features={','.join(section_features)}",
                        f"neighbor_count={len(field_values)}",
                        f"top_neighbor={top[0].get('player_label')}",
                    ),
                )
        return values


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
    suggestion_relpath = str(model_dir.relative_to(_repo_root()))
    for row in _suggestion_rows(model_dir):
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
    candidates_by_position = _load_candidate_pool(model_dir, field_map)
    scales_by_position = _scale_by_position(candidates_by_position)
    return StatNeighborModel(
        path=model_dir,
        suggestions_by_player_position=suggestions_by_player,
        suggestions_by_player_team_position=suggestions_by_team,
        candidates_by_position=candidates_by_position,
        scales_by_position=scales_by_position,
    )


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
    base = _repo_root() / "nba2k_editor" / "Player Generator" / "NBA Player Data" / "player_generation_pool"
    candidates = []
    for path in base.iterdir() if base.exists() else ():
        if path.is_file() and path.name.startswith(_MODEL_PREFIX) and path.suffix == ".sqlite":
            suffix = path.stem[len(_MODEL_PREFIX) :]
            if suffix.isdigit():
                candidates.append((int(suffix), path))
            continue
        if path.is_dir() and path.name.startswith(_MODEL_PREFIX):
            suffix = path.name[len(_MODEL_PREFIX) :]
            if suffix.isdigit() and (path / _SUGGESTIONS_FILE).is_file():
                candidates.append((int(suffix), path))
    if not candidates:
        raise FileNotFoundError(f"no {_MODEL_PREFIX}### SQLite model or CSV artifact under {base}")
    return max(candidates, key=lambda item: item[0])[1]


def _suggestion_rows(model_path: Path) -> list[dict[str, Any]]:
    if model_path.is_file() and model_path.suffix == ".sqlite":
        with sqlite3.connect(model_path) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute('SELECT * FROM suggested_field_values')]
    suggestion_path = model_path / _SUGGESTIONS_FILE
    with suggestion_path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _candidate_source_path(model_path: Path) -> Path | None:
    if not (model_path.is_file() and model_path.suffix == ".sqlite"):
        return None
    if _sqlite_has_table(model_path, "candidate_fields"):
        return model_path
    pool_path = model_path.parent / "player_generation_pool.sqlite"
    if pool_path.is_file() and _sqlite_has_table(pool_path, "candidate_fields"):
        return pool_path
    return model_path if _sqlite_has_table(model_path, "candidate_pool") else None


def _sqlite_has_table(path: Path, table: str) -> bool:
    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            return row is not None
    except sqlite3.Error:
        return False


def _candidate_field_rows(model_path: Path) -> list[dict[str, Any]]:
    source_path = _candidate_source_path(model_path)
    if source_path is None or not _sqlite_has_table(source_path, "candidate_fields"):
        return []
    with sqlite3.connect(source_path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute('SELECT * FROM candidate_fields')]


def _load_candidate_pool(model_path: Path, field_map: dict[tuple[str, str], str]) -> dict[str, tuple[dict[str, Any], ...]]:
    source_path = _candidate_source_path(model_path)
    if source_path is None or not _sqlite_has_table(source_path, "candidate_pool"):
        return {}
    fields_by_candidate: dict[tuple[str, str, str], dict[str, float]] = {}
    for row in _candidate_field_rows(model_path):
        field_key = field_map.get((str(row.get("field_type") or row.get("Type") or ""), str(row.get("input_field") or row.get("Input Field") or "")))
        value = _float(row.get("value"))
        if not field_key or value is None:
            continue
        key = (str(row.get("run_id") or ""), str(row.get("player_index") or ""), str(row.get("position") or "").strip().upper())
        fields_by_candidate.setdefault(key, {})[field_key] = value
    by_position: dict[str, list[dict[str, Any]]] = {}
    with sqlite3.connect(source_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute('SELECT * FROM candidate_pool')]
    for row in rows:
        pos = str(row.get("position") or "").strip().upper()
        key = (str(row.get("run_id") or ""), str(row.get("player_index") or ""), pos)
        fields = fields_by_candidate.get(key, {})
        if not pos or not fields:
            continue
        candidate = {
            "run_id": key[0],
            "player_index": key[1],
            "player_label": str(row.get("player_label") or ""),
            "master_player_id": str(row.get("master_player_id") or ""),
            "position": pos,
            "features": {feature: _float(row.get(feature)) for feature in (*FEATURES, *BODY_FEATURES)},
            "fields": fields,
        }
        by_position.setdefault(pos, []).append(candidate)
    return {pos: tuple(candidates) for pos, candidates in by_position.items()}


def _scale_by_position(candidates_by_position: dict[str, tuple[dict[str, Any], ...]]) -> dict[str, dict[str, tuple[float, float]]]:
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for pos in POSITIONS:
        rows = candidates_by_position.get(pos, ())
        pos_scales: dict[str, tuple[float, float]] = {}
        for feature in (*FEATURES, *BODY_FEATURES):
            vals = sorted(
                float(candidate["features"][feature])
                for candidate in rows
                if candidate["features"].get(feature) is not None and math.isfinite(float(candidate["features"][feature]))
            )
            if not vals:
                pos_scales[feature] = (0.0, 1.0)
                continue
            mean = sum(vals) / len(vals)
            variance = sum((value - mean) ** 2 for value in vals) / max(1, len(vals) - 1)
            pos_scales[feature] = (float(median(vals)), math.sqrt(variance) or 1.0)
        out[pos] = pos_scales
    return out


def _nearest_neighbors(
    target_features: dict[str, float | None],
    candidates: tuple[dict[str, Any], ...],
    scales: dict[str, tuple[float, float]],
    *,
    features: tuple[str, ...] = FEATURES,
    k: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        dist, common = _distance(target_features, candidate["features"], scales, features=features)
        if dist is None:
            continue
        rows.append({"candidate": candidate, "distance": dist, "common_features": common})
    rows.sort(key=lambda row: row["distance"])
    return rows[:k]


def _distance(
    a: dict[str, float | None],
    b: dict[str, float | None],
    scales: dict[str, tuple[float, float]],
    *,
    features: tuple[str, ...] = FEATURES,
) -> tuple[float | None, int]:
    parts: list[float] = []
    for feature in features:
        av = a.get(feature)
        bv = b.get(feature)
        if av is None or bv is None:
            continue
        scale = scales.get(feature, (0.0, 1.0))[1] or 1.0
        parts.append(((float(av) - float(bv)) / scale) ** 2)
    if not parts:
        return None, 0
    return math.sqrt(sum(parts) / len(parts)), len(parts)


def _features_for_field(field_key: str) -> tuple[str, ...]:
    key = _identity(field_key)
    if "3PT" in key or "3POINT" in key or "THREE" in key:
        return ("x3pa_per36", "x3p_pct", "fga_per36", "pts_per36")
    if "FREE" in key or "FOUL" in key or "DRAW" in key:
        return ("fta_per36", "ft_pct", "pts_per36")
    if "PASS" in key or "ASSIST" in key or "VISION" in key or "TOUCH" in key:
        return ("ast_per36", "tov_per36")
    if "REBOUND" in key or "BOXOUT" in key or "PUTBACK" in key:
        return ("orb_per36", "drb_per36", "height_inches", "weight_pounds")
    if "STEAL" in key or "INTERCEPT" in key:
        return ("stl_per36", "pf_per36")
    if "BLOCK" in key or "INTERIORDEFENSE" in key or "HELPDEFENSE" in key:
        return ("blk_per36", "pf_per36", "drb_per36", "height_inches", "weight_pounds")
    if "DUNK" in key or "LAYUP" in key or "CLOSE" in key or "POST" in key:
        return ("pts_per36", "fga_per36", "fg_pct", "fta_per36", "height_inches", "weight_pounds")
    if "SHOT" in key or "JUMPER" in key or "MIDRANGE" in key or "FADE" in key:
        return ("pts_per36", "fga_per36", "fg_pct")
    if "BALL" in key or "HANDLE" in key:
        return ("ast_per36", "tov_per36", "pts_per36")
    if "DEFENSE" in key or "LATERAL" in key:
        return ("stl_per36", "blk_per36", "pf_per36")
    return FEATURES


def target_features_from_evidence(evidence: Any) -> dict[str, float | None]:
    per_game = getattr(evidence, "per_game", {}) or {}
    per_36 = getattr(evidence, "per_36", {}) or {}

    def per36(per36_col: str, per_game_col: str) -> float | None:
        direct = _float(per_36.get(per36_col))
        if direct is not None:
            return direct
        per_game_value = _float(per_game.get(per_game_col))
        minutes = _float(per_game.get("mp_per_game"))
        if per_game_value is None:
            return None
        if minutes in (None, 0):
            return per_game_value
        return per_game_value * 36.0 / minutes

    features = {
        "pts_per36": per36("pts_per_36_min", "pts_per_game"),
        "fga_per36": per36("fga_per_36_min", "fga_per_game"),
        "fg_pct": _float(per_game.get("fg_percent")),
        "x3pa_per36": per36("x3pa_per_36_min", "x3pa_per_game"),
        "x3p_pct": _float(per_game.get("x3p_percent")),
        "fta_per36": per36("fta_per_36_min", "fta_per_game"),
        "ft_pct": _float(per_game.get("ft_percent")),
        "ast_per36": per36("ast_per_36_min", "ast_per_game"),
        "orb_per36": per36("orb_per_36_min", "orb_per_game"),
        "drb_per36": per36("drb_per_36_min", "drb_per_game"),
        "stl_per36": per36("stl_per_36_min", "stl_per_game"),
        "blk_per36": per36("blk_per_36_min", "blk_per_game"),
        "tov_per36": per36("tov_per_36_min", "tov_per_game"),
        "pf_per36": per36("pf_per_36_min", "pf_per_game"),
        "height_inches": _float(getattr(evidence, "identity", {}).get("ht_in_in")),
        "weight_pounds": _float(getattr(evidence, "identity", {}).get("wt")),
    }
    return {key: (0.0 if value is None else value) for key, value in features.items()}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _field_key_map() -> dict[tuple[str, str], str]:
    entries = _offset_entries()
    out: dict[tuple[str, str], str] = {}
    model_path = _latest_model_dir()
    pairs = sorted(
        {(str(row.get("Type") or ""), str(row.get("Input Field") or "")) for row in _suggestion_rows(model_path)}
        | {(str(row.get("field_type") or ""), str(row.get("input_field") or "")) for row in _candidate_field_rows(model_path)}
    )
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
    compact = re.sub(r"[^A-Z]+", "", text)
    position_map = {
        "G": ("PG", "SG"),
        "GF": ("SG", "SF"),
        "FG": ("SF", "SG"),
        "F": ("SF", "PF"),
        "FC": ("PF", "C"),
        "CF": ("C", "PF"),
    }
    mapped = position_map.get(compact)
    if mapped:
        return mapped
    found = [pos for pos in POSITIONS if re.search(rf"\b{pos}\b", text)]
    if found:
        return tuple(dict.fromkeys(found))
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
    "target_features_from_evidence",
]
