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
    "e_fg_percent",
    "fta_per36",
    "ft_pct",
    "ast_per36",
    "orb_per36",
    "drb_per36",
    "stl_per36",
    "blk_per36",
    "tov_per36",
    "pf_per36",
    "games",
    "mp_per_game",
    "pts_per100",
    "fga_per100",
    "x3pa_per100",
    "fta_per100",
    "ast_per100",
    "orb_per100",
    "drb_per100",
    "trb_per100",
    "stl_per100",
    "blk_per100",
    "tov_per100",
    "pf_per100",
    "player_o_rtg",
    "player_d_rtg",
    "per",
    "ts_percent",
    "x3p_ar",
    "f_tr",
    "orb_percent",
    "drb_percent",
    "trb_percent",
    "ast_percent",
    "stl_percent",
    "blk_percent",
    "tov_percent",
    "usg_percent",
    "ows",
    "dws",
    "ws",
    "ws_48",
    "obpm",
    "dbpm",
    "bpm",
    "vorp",
    "avg_dist_fga",
    "percent_fga_from_x2p_range",
    "percent_fga_from_x0_3_range",
    "percent_fga_from_x3_10_range",
    "percent_fga_from_x10_16_range",
    "percent_fga_from_x16_3p_range",
    "percent_fga_from_x3p_range",
    "fg_percent_from_x2p_range",
    "fg_percent_from_x0_3_range",
    "fg_percent_from_x3_10_range",
    "fg_percent_from_x10_16_range",
    "fg_percent_from_x16_3p_range",
    "fg_percent_from_x3p_range",
    "percent_assisted_x2p_fg",
    "percent_assisted_x3p_fg",
    "percent_dunks_of_fga",
    "num_of_dunks",
    "percent_corner_3s_of_3pa",
    "corner_3_point_percent",
    "team_o_rtg",
    "team_d_rtg",
    "team_n_rtg",
    "team_pace",
    "team_srs",
    "team_ts_percent",
    "team_x3p_ar",
    "team_e_fg_percent",
    "team_tov_percent",
    "team_orb_percent",
    "team_drb_percent",
    "team_opp_e_fg_percent",
    "all_star",
    "all_nba",
    "all_defense",
    "award_share",
    "mvp_share",
    "dpoy_share",
    "all_team_vote_share",
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
    merged_sqlite = base / "POSITION_STAT_NEIGHBOR_MODEL.sqlite"
    if merged_sqlite.is_file():
        return merged_sqlite
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
    section, _sep, raw_name = field_key.partition("/")
    key = _identity(raw_name or field_key)
    section_key = _identity(section)
    is_tendency = section_key == "TENDENCIES"

    # Availability / body / durability. These should not fall through to star-impact stats.
    three_zone_keys = {"CENTER3", "LEFT3", "RIGHT3", "3CENTER", "3LEFT", "3LEFTCENTER", "3RIGHT", "3RIGHTCENTER"}
    mid_zone_keys = {"MIDRANGECENTER", "MIDRANGELEFT", "MIDRANGELEFTCENTER", "MIDRANGERIGHT", "MIDRANGERIGHTCENTER"}
    close_zone_keys = {"CLOSELEFT", "CLOSEMIDDLE", "CLOSERIGHT", "UNDERBASKET"}
    if key in three_zone_keys:
        return ("fg_percent_from_x3p_range", "corner_3_point_percent", "percent_corner_3s_of_3pa", "x3p_pct")
    if key in mid_zone_keys:
        return ("fg_percent_from_x10_16_range", "fg_percent_from_x16_3p_range", "avg_dist_fga")
    if key in close_zone_keys:
        return ("fg_percent_from_x0_3_range", "fg_percent_from_x3_10_range", "percent_fga_from_x0_3_range")
    if "DURABILITY" in key:
        return ("games", "mp_per_game")
    if key == "STAMINA":
        return ("mp_per_game", "games")
    if key == "STRENGTH":
        return ("weight_pounds", "height_inches", "orb_percent", "drb_percent", "f_tr")
    if key == "VERTICAL":
        return ("blk_percent", "percent_dunks_of_fga", "num_of_dunks", "height_inches")
    if key in {"SPEED", "ACCELERATION", "AGILITY"}:
        return ("height_inches", "weight_pounds", "stl_percent", "ast_percent")
    if key in {"SPEEDWITHBALL", "BALLCONTROL"} or "HANDLE" in key or "DRIBBLE" in key or "SIZEUP" in key:
        return ("ast_percent", "tov_percent", "usg_percent", "percent_assisted_x2p_fg")

    # Defense-specific names must precede PASS/SHOT/FREE string checks.
    if key == "PASSPERCEPTION" or "INTERCEPTION" in key:
        return ("stl_percent", "stl_per100", "dbpm", "dws")
    if key in {"CONTESTSHOT", "TAKECHARGE"}:
        return ("dbpm", "dws", "pf_per100", "team_d_rtg")
    if key in {"FOUL", "HARDFOUL"}:
        return ("pf_per100", "player_d_rtg")
    if "PERIMETERDEFENSE" in key or "LATERAL" in key:
        return ("stl_percent", "dbpm", "dws", "pf_per100")
    if "INTERIORDEFENSE" in key or "HELPDEFENSE" in key:
        return ("blk_percent", "drb_percent", "dbpm", "dws", "height_inches", "weight_pounds", "all_defense", "dpoy_share")
    if "DEFENSECONSISTENCY" in key or key == "PICKANDROLLDEFENSEIQ":
        return ("dbpm", "dws", "stl_percent", "blk_percent", "drb_percent", "all_defense", "dpoy_share")

    # Shot-location skill vs behavior. Attributes use efficiency; tendencies use frequency/location.
    if "3PT" in key or "3POINT" in key or "THREE" in key:
        return (
            "x3pa_per100",
            "percent_fga_from_x3p_range",
            "x3p_ar",
            "percent_corner_3s_of_3pa",
            "avg_dist_fga",
        ) if is_tendency else (
            "x3p_pct",
            "fg_percent_from_x3p_range",
            "corner_3_point_percent",
        )
    if "MIDRANGE" in key or key.startswith("MID") or "MID" in key or "FADE" in key:
        return (
            "percent_fga_from_x10_16_range",
            "percent_fga_from_x16_3p_range",
            "avg_dist_fga",
        ) if is_tendency else (
            "fg_percent_from_x10_16_range",
            "fg_percent_from_x16_3p_range",
            "fg_pct",
        )
    if "CLOSE" in key or "BASKETUNDER" in key or "UNDERBASKET" in key:
        return (
            "percent_fga_from_x0_3_range",
            "percent_fga_from_x3_10_range",
            "fta_per100",
            "f_tr",
        ) if is_tendency else (
            "fg_percent_from_x0_3_range",
            "fg_percent_from_x2p_range",
            "ts_percent",
            "height_inches",
            "weight_pounds",
        )
    if "LAYUP" in key or "FLOATER" in key or "EUROSTEP" in key or "HOPSTEP" in key or "STEPTHROUGH" in key or "USEGLASS" in key:
        return (
            "percent_fga_from_x0_3_range",
            "percent_fga_from_x3_10_range",
            "f_tr",
            "percent_assisted_x2p_fg",
        ) if is_tendency else (
            "fg_percent_from_x0_3_range",
            "fg_percent_from_x3_10_range",
            "ts_percent",
        )
    if "DUNK" in key or "ALLEYOOP" in key:
        return ("percent_dunks_of_fga", "num_of_dunks", "percent_fga_from_x0_3_range", "height_inches", "weight_pounds")

    # Post fields are close/mid/self-created proxies, not general points.
    if "POSTHOOK" in key or "HOOK" in key:
        return ("fg_percent_from_x3_10_range", "fg_percent_from_x0_3_range", "height_inches", "weight_pounds")
    if "POSTFADE" in key:
        return ("fg_percent_from_x10_16_range", "fg_percent_from_x16_3p_range", "percent_assisted_x2p_fg", "height_inches")
    if "POST" in key:
        return (
            "percent_fga_from_x0_3_range",
            "percent_fga_from_x3_10_range",
            "height_inches",
            "weight_pounds",
            "f_tr",
        ) if is_tendency else (
            "fg_percent_from_x0_3_range",
            "fg_percent_from_x3_10_range",
            "height_inches",
            "weight_pounds",
            "f_tr",
        )

    # Playmaking: skill/risk for attributes; frequency/role for tendencies.
    if "TOUCH" in key:
        return ("usg_percent", "ast_per100", "fga_per100", "tov_per100")
    if "PASS" in key or "ASSIST" in key or "VISION" in key or "DISH" in key:
        return ("ast_per100", "usg_percent", "tov_per100") if is_tendency else ("ast_percent", "tov_percent")

    # Rebounding: split offensive/defensive when the field names do.
    if "OFFENSIVEREBOUND" in key:
        return ("orb_percent", "orb_per100", "height_inches", "weight_pounds")
    if "DEFENSEREBOUND" in key or "DEFENSIVEREBOUND" in key:
        return ("drb_percent", "drb_per100", "height_inches", "weight_pounds")
    if "REBOUND" in key or "BOXOUT" in key:
        return ("orb_percent", "drb_percent", "trb_percent", "orb_per100", "drb_per100", "height_inches", "weight_pounds")
    if "PUTBACK" in key:
        return ("orb_percent", "orb_per100", "percent_fga_from_x0_3_range", "height_inches", "weight_pounds")

    if "STEAL" in key:
        return ("stl_per100", "pf_per100") if is_tendency else ("stl_percent", "stl_per100", "dbpm", "dws")
    if "BLOCK" in key:
        return ("blk_per100", "pf_per100", "height_inches") if is_tendency else ("blk_percent", "blk_per100", "dbpm", "dws", "height_inches", "weight_pounds")

    # Drive/freelance/setup tendencies are behavior, not shooting skill.
    if key == "CRASH":
        return ("orb_percent", "drb_percent", "orb_per100", "drb_per100", "height_inches", "weight_pounds")
    if any(token in key for token in ("DRIVE", "DRIVING", "ISO", "SETUP", "TRIPLETHREAT", "JABSTEP", "PUMPFAKE", "ATTACKSTRONG", "SPOTUPDRIVE", "OFFSCREENDRIVE")):
        return ("f_tr", "percent_fga_from_x0_3_range", "percent_fga_from_x3_10_range", "usg_percent", "tov_percent", "percent_assisted_x2p_fg")
    if "SPOTUP" in key or "OFFSCREEN" in key or "TRANSITION" in key:
        return ("percent_assisted_x3p_fg", "percent_fga_from_x3p_range", "percent_corner_3s_of_3pa", "x3pa_per100", "x3p_ar")
    if key == "ROLLVSPOP":
        return ("percent_dunks_of_fga", "percent_fga_from_x3p_range", "x3p_ar", "height_inches", "weight_pounds")
    if key == "PLAYDISCIPLINE":
        return ("tov_percent", "pf_per100", "team_tov_percent")

    if "FREE" in key:
        return ("ft_pct",)
    if "DRAWFOUL" in key or "DRAW" in key:
        return ("fta_per100", "f_tr")
    if "SHOT" in key or "JUMPER" in key or key == "IQSHOT":
        return (
            "percent_fga_from_x2p_range",
            "avg_dist_fga",
            "fga_per100",
        ) if is_tendency else (
            "fg_pct",
            "e_fg_percent",
            "ts_percent",
        )

    if key in {"HANDS", "HUSTLE"}:
        return ("orb_percent", "stl_percent", "blk_percent", "games", "mp_per_game")
    if "OFFENSIVECONSISTENCY" in key or key == "IQSHOT":
        return ("ts_percent", "ows", "obpm", "tov_percent", "usg_percent")
    if "CONSIST" in key or "POTENTIAL" in key or "INTANG" in key or key.endswith("IQ"):
        return ("per", "bpm", "vorp", "ws", "ws_48", "award_share", "all_nba", "all_star")
    return ("per", "bpm", "vorp", "ws", "ts_percent", "usg_percent")


def target_features_from_evidence(evidence: Any) -> dict[str, float | None]:
    identity = getattr(evidence, "identity", {}) or {}
    per_game = getattr(evidence, "per_game", {}) or {}
    per_36 = getattr(evidence, "per_36", {}) or {}
    per_100 = getattr(evidence, "per_100", {}) or {}
    advanced = getattr(evidence, "advanced", {}) or {}
    shooting = getattr(evidence, "shooting", {}) or {}
    team_summary = getattr(evidence, "team_summary", {}) or {}
    source_context = getattr(evidence, "source_context", {}) or {}

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

    features: dict[str, float | None] = {
        "pts_per36": per36("pts_per_36_min", "pts_per_game"),
        "fga_per36": per36("fga_per_36_min", "fga_per_game"),
        "fg_pct": _float(per_game.get("fg_percent")),
        "x3pa_per36": per36("x3pa_per_36_min", "x3pa_per_game"),
        "x3p_pct": _float(per_game.get("x3p_percent")),
        "e_fg_percent": _float(per_100.get("e_fg_percent")) or _float(per_game.get("e_fg_percent")),
        "fta_per36": per36("fta_per_36_min", "fta_per_game"),
        "ft_pct": _float(per_game.get("ft_percent")),
        "ast_per36": per36("ast_per_36_min", "ast_per_game"),
        "orb_per36": per36("orb_per_36_min", "orb_per_game"),
        "drb_per36": per36("drb_per_36_min", "drb_per_game"),
        "stl_per36": per36("stl_per_36_min", "stl_per_game"),
        "blk_per36": per36("blk_per_36_min", "blk_per_game"),
        "tov_per36": per36("tov_per_36_min", "tov_per_game"),
        "pf_per36": per36("pf_per_36_min", "pf_per_game"),
        "games": _float(per_game.get("g")),
        "mp_per_game": _float(per_game.get("mp_per_game")),
        "pts_per100": _float(per_100.get("pts_per_100_poss")),
        "fga_per100": _float(per_100.get("fga_per_100_poss")),
        "x3pa_per100": _float(per_100.get("x3pa_per_100_poss")),
        "fta_per100": _float(per_100.get("fta_per_100_poss")),
        "ast_per100": _float(per_100.get("ast_per_100_poss")),
        "orb_per100": _float(per_100.get("orb_per_100_poss")),
        "drb_per100": _float(per_100.get("drb_per_100_poss")),
        "trb_per100": _float(per_100.get("trb_per_100_poss")),
        "stl_per100": _float(per_100.get("stl_per_100_poss")),
        "blk_per100": _float(per_100.get("blk_per_100_poss")),
        "tov_per100": _float(per_100.get("tov_per_100_poss")),
        "pf_per100": _float(per_100.get("pf_per_100_poss")),
        "player_o_rtg": _float(per_100.get("o_rtg")),
        "player_d_rtg": _float(per_100.get("d_rtg")),
        "height_inches": _float(identity.get("ht_in_in")),
        "weight_pounds": _float(identity.get("wt")),
    }
    for column in (
        "per", "ts_percent", "x3p_ar", "f_tr", "orb_percent", "drb_percent", "trb_percent", "ast_percent", "stl_percent", "blk_percent", "tov_percent", "usg_percent", "ows", "dws", "ws", "ws_48", "obpm", "dbpm", "bpm", "vorp",
    ):
        features[column] = _float(advanced.get(column))
    for column in (
        "avg_dist_fga", "percent_fga_from_x2p_range", "percent_fga_from_x0_3_range", "percent_fga_from_x3_10_range", "percent_fga_from_x10_16_range", "percent_fga_from_x16_3p_range", "percent_fga_from_x3p_range", "fg_percent_from_x2p_range", "fg_percent_from_x0_3_range", "fg_percent_from_x3_10_range", "fg_percent_from_x10_16_range", "fg_percent_from_x16_3p_range", "fg_percent_from_x3p_range", "percent_assisted_x2p_fg", "percent_assisted_x3p_fg", "percent_dunks_of_fga", "num_of_dunks", "percent_corner_3s_of_3pa", "corner_3_point_percent",
    ):
        features[column] = _float(shooting.get(column))
    for source, target in (
        ("o_rtg", "team_o_rtg"), ("d_rtg", "team_d_rtg"), ("n_rtg", "team_n_rtg"), ("pace", "team_pace"), ("srs", "team_srs"), ("ts_percent", "team_ts_percent"), ("x3p_ar", "team_x3p_ar"), ("e_fg_percent", "team_e_fg_percent"), ("tov_percent", "team_tov_percent"), ("orb_percent", "team_orb_percent"), ("drb_percent", "team_drb_percent"), ("opp_e_fg_percent", "team_opp_e_fg_percent"),
    ):
        features[target] = _float(team_summary.get(source))
    features["all_star"] = 1.0 if source_context.get("all_star_selections.season") is not None else None
    all_team_type = str(source_context.get("all_teams.type") or "").upper()
    all_team_number = _float(source_context.get("all_teams.number_tm"))
    features["all_nba"] = max(1.0, 4.0 - all_team_number) if all_team_number is not None and "NBA" in all_team_type else None
    features["all_defense"] = max(1.0, 3.0 - all_team_number) if all_team_number is not None and "DEF" in all_team_type else None
    features["award_share"] = _float(source_context.get("player_award_shares.share"))
    award_name = str(source_context.get("player_award_shares.award") or "").upper()
    features["mvp_share"] = features["award_share"] if "MVP" in award_name and "FINAL" not in award_name else None
    features["dpoy_share"] = features["award_share"] if "DPOY" in award_name or "DEFENSIVE" in award_name else None
    features["all_team_vote_share"] = _float(source_context.get("all_team_voting.share"))
    return features


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
