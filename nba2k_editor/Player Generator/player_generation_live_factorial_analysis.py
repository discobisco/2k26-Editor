from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

RUN_ID_DEFAULT = "editor_capture_027"
FACTOR_NAMES = (
    "Touches",
    "Shot",
    "3PT_Tendency",
    "3PT_Attribute",
)
FACTOR_FIELDS = {
    "Touches": ("Tendencies/TOUCHES", "tendencies", "Freelance / Touches", 100.0),
    "Shot": ("Tendencies/SHOT", "tendencies", "Tendencies / Shoot", 100.0),
    "3PT_Tendency": (
        "Tendencies/3POINTSHOT",
        "tendencies",
        "Jump Shooting / Shot 3pt",
        100.0,
    ),
    "3PT_Attribute": ("Attributes/3POINT", "attributes", "Offense / 3pt Shot", 99.0),
}
IDENTITY_KEYS = {
    "player_index",
    "player_label",
    "team_index",
    "team_label",
    "team_slot",
    "roster_slot",
}
PLAYER_ROW_TYPES = ("stats", "attributes", "tendencies")
STAT_KEYS = (
    "Minutes",
    "Field Goals Attempted",
    "Field Goals Made",
    "Three Pointers Attempted",
    "Three Pointers Made",
    "Points",
    "Assists",
    "Turnovers",
)


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_pool_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "NBA Player Data"
        / "player_generation_pool"
        / "player_generation_pool.sqlite"
    )


def default_manifest_path() -> Path:
    return (
        _default_repo_root()
        / ".hermes"
        / "audits"
        / "player_generation_live_experiment_2026-07-17"
        / "experiment_manifest.json"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _numeric(value: object, *, blank: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return blank
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _snapshot_rows(
    connection: sqlite3.Connection,
    run_id: str,
    row_type: str,
) -> list[dict[str, Any]]:
    return [
        json.loads(str(row_json))
        for (row_json,) in connection.execute(
            """
            SELECT row_json
            FROM pool_export_rows
            WHERE snapshot_id = ? AND row_type = ?
            ORDER BY rowid
            """,
            (run_id, row_type),
        )
    ]


def _last_player_rows(rows: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        result[int(row["player_index"])] = row
    return result


@dataclass(frozen=True)
class FactorialRunData:
    pool_path: Path
    pool_sha256: str
    run_id: str
    player_indices: np.ndarray
    team_indices: np.ndarray
    roster_slots: np.ndarray
    positions: np.ndarray
    play_types: tuple[tuple[str, str, str, str], ...]
    cells: np.ndarray
    factors: np.ndarray
    stats: dict[str, np.ndarray]
    ending_three_point_attribute: np.ndarray
    starting_three_point_attribute: np.ndarray
    ending_noncontrolled_attribute_mean: np.ndarray
    validation: dict[str, Any]


def load_factorial_run(
    pool_path: Path | None = None,
    manifest_path: Path | None = None,
    *,
    run_id: str = RUN_ID_DEFAULT,
) -> FactorialRunData:
    pool = (pool_path or default_pool_path()).resolve()
    manifest_file = (manifest_path or default_manifest_path()).resolve()
    pool_hash = _sha256(pool)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_records = sorted(
        manifest["records"],
        key=lambda row: (int(row["team_index"]), int(row["team_slot"])),
    )
    if len(manifest_records) != 450:
        raise ValueError(f"expected 450 manifest records, found {len(manifest_records)}")

    with _open_read_only(pool) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        metadata = connection.execute(
            """
            SELECT snapshot_id, season, created_at, source,
                   stats_rows, attribute_rows, tendency_rows, team_stat_rows
            FROM pool_export_snapshots
            WHERE snapshot_id = ?
            """,
            (run_id,),
        ).fetchone()
        if metadata is None:
            raise ValueError(f"missing snapshot {run_id}")
        rows_by_type = {
            row_type: _snapshot_rows(connection, run_id, row_type)
            for row_type in (*PLAYER_ROW_TYPES, "team_stats")
        }
        player_rows = {
            row_type: _last_player_rows(rows_by_type[row_type])
            for row_type in PLAYER_ROW_TYPES
        }
        candidate_rows = int(
            connection.execute(
                "SELECT COUNT(*) FROM candidate_pool WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
        )
        candidate_field_rows = int(
            connection.execute(
                "SELECT COUNT(*) FROM candidate_fields WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
        )
        candidate_runs = int(
            connection.execute("SELECT COUNT(DISTINCT run_id) FROM candidate_pool").fetchone()[0]
        )

    row_counts = {row_type: len(rows) for row_type, rows in rows_by_type.items()}
    expected_counts = {"stats": 450, "attributes": 450, "tendencies": 450, "team_stats": 30}
    if row_counts != expected_counts:
        raise ValueError(f"unexpected snapshot row counts: {row_counts}")

    player_indices: list[int] = []
    team_indices: list[int] = []
    roster_slots: list[int] = []
    positions: list[str] = []
    play_types: list[tuple[str, str, str, str]] = []
    cells: list[int] = []
    factor_rows: list[list[float]] = []
    stat_values = {key: [] for key in STAT_KEYS}
    ending_three_point: list[float] = []
    starting_three_point: list[float] = []
    ending_other_attribute_mean: list[float] = []

    placement_mismatches: list[dict[str, Any]] = []
    playtype_mismatches: list[dict[str, Any]] = []
    controlled_mismatches: list[dict[str, Any]] = []
    invalid_stat_rows: list[int] = []
    noncontrolled_attribute_distribution: dict[str, int] = {}

    for record in manifest_records:
        player_index = int(record["player_index"])
        stat_row = player_rows["stats"].get(player_index)
        attribute_row = player_rows["attributes"].get(player_index)
        tendency_row = player_rows["tendencies"].get(player_index)
        if stat_row is None or attribute_row is None or tendency_row is None:
            raise ValueError(f"missing player package for index {player_index}")

        expected_team = int(record["team_index"])
        expected_slot = int(record["team_slot"])
        package_rows = (stat_row, attribute_row, tendency_row)
        if any(
            int(row["team_index"]) != expected_team
            or int(row["roster_slot"]) != expected_slot
            for row in package_rows
        ):
            placement_mismatches.append(
                {
                    "player_index": player_index,
                    "expected_team_index": expected_team,
                    "expected_roster_slot": expected_slot,
                }
            )

        captured_play_types = tuple(
            str(stat_row.get(f"play_type_{number}", "")) for number in range(1, 5)
        )
        expected_play_types = tuple(str(value) for value in record["playtypes_unchanged"])
        if captured_play_types != expected_play_types:
            playtype_mismatches.append(
                {
                    "player_index": player_index,
                    "expected": expected_play_types,
                    "captured": captured_play_types,
                }
            )

        assigned = record["assigned"]
        factor_values: list[float] = []
        for factor_name in FACTOR_NAMES:
            manifest_key, row_type, captured_key, high_value = FACTOR_FIELDS[factor_name]
            assigned_value = float(assigned[manifest_key])
            captured_value = _numeric(player_rows[row_type][player_index].get(captured_key))
            factor_values.append(1.0 if assigned_value == high_value else -1.0)
            if captured_value != assigned_value:
                controlled_mismatches.append(
                    {
                        "player_index": player_index,
                        "team_index": expected_team,
                        "roster_slot": expected_slot,
                        "field_key": manifest_key,
                        "assigned_start": assigned_value,
                        "captured_end": captured_value,
                    }
                )

        numeric_stats = {key: _numeric(stat_row.get(key), blank=0.0) for key in STAT_KEYS}
        if (
            numeric_stats["Three Pointers Made"] > numeric_stats["Three Pointers Attempted"]
            or numeric_stats["Three Pointers Attempted"] > numeric_stats["Field Goals Attempted"]
            or numeric_stats["Field Goals Made"] > numeric_stats["Field Goals Attempted"]
        ):
            invalid_stat_rows.append(player_index)

        other_attribute_values: list[float] = []
        for key, value in attribute_row.items():
            if key in IDENTITY_KEYS or key == "Offense / 3pt Shot":
                continue
            numeric_value = _numeric(value, blank=math.nan)
            if math.isfinite(numeric_value):
                other_attribute_values.append(numeric_value)
                value_key = str(int(numeric_value)) if numeric_value.is_integer() else str(numeric_value)
                noncontrolled_attribute_distribution[value_key] = (
                    noncontrolled_attribute_distribution.get(value_key, 0) + 1
                )

        player_indices.append(player_index)
        team_indices.append(expected_team)
        roster_slots.append(expected_slot)
        positions.append(str(record["position"]))
        play_types.append(captured_play_types)
        cells.append(int(record["cell"]))
        factor_rows.append(factor_values)
        for key in STAT_KEYS:
            stat_values[key].append(numeric_stats[key])
        ending_three_point.append(_numeric(attribute_row["Offense / 3pt Shot"]))
        starting_three_point.append(float(assigned["Attributes/3POINT"]))
        ending_other_attribute_mean.append(float(np.mean(other_attribute_values)))

    if placement_mismatches or playtype_mismatches or invalid_stat_rows:
        raise ValueError(
            "factorial snapshot failed hard alignment checks: "
            f"placement={len(placement_mismatches)}, "
            f"playtypes={len(playtype_mismatches)}, stats={len(invalid_stat_rows)}"
        )

    factor_array = np.asarray(factor_rows, dtype=np.float64)
    validation = {
        "run_id": run_id,
        "pool_sha256": pool_hash,
        "pool_integrity": integrity,
        "snapshot_metadata": {
            "snapshot_id": str(metadata[0]),
            "season": int(metadata[1]),
            "created_at": str(metadata[2]),
            "source": str(metadata[3]),
            "stats_rows": int(metadata[4]),
            "attribute_rows": int(metadata[5]),
            "tendency_rows": int(metadata[6]),
            "team_stat_rows": int(metadata[7]),
        },
        "raw_row_counts": row_counts,
        "candidate_rows": candidate_rows,
        "candidate_field_rows": candidate_field_rows,
        "candidate_run_count": candidate_runs,
        "manifest_record_count": len(manifest_records),
        "placement_mismatch_count": len(placement_mismatches),
        "playtype_mismatch_count": len(playtype_mismatches),
        "invalid_stat_row_count": len(invalid_stat_rows),
        "controlled_end_value_mismatch_count": len(controlled_mismatches),
        "controlled_end_value_mismatches": controlled_mismatches,
        "controlled_start_balance": {
            factor_name: {
                "low": int((factor_array[:, index] == -1.0).sum()),
                "high": int((factor_array[:, index] == 1.0).sum()),
            }
            for index, factor_name in enumerate(FACTOR_NAMES)
        },
        "cell_counts": {
            str(cell): int(sum(int(record["cell"]) == cell for record in manifest_records))
            for cell in range(16)
        },
        "players_with_positive_minutes": int(
            sum(value > 0.0 for value in stat_values["Minutes"])
        ),
        "players_with_nonempty_or_zero_minutes": int(
            sum(value >= 0.0 for value in stat_values["Minutes"])
        ),
        "noncontrolled_ending_attribute_distribution": dict(
            sorted(noncontrolled_attribute_distribution.items(), key=lambda item: float(item[0]))
        ),
        "treatment_source": "pre-simulation immutable experiment manifest",
        "ending_rating_policy": (
            "captured ending ratings are progression outcomes, not treatment assignments"
        ),
        "names_used": False,
    }

    return FactorialRunData(
        pool_path=pool,
        pool_sha256=pool_hash,
        run_id=run_id,
        player_indices=np.asarray(player_indices, dtype=np.int64),
        team_indices=np.asarray(team_indices, dtype=np.int64),
        roster_slots=np.asarray(roster_slots, dtype=np.int64),
        positions=np.asarray(positions, dtype=object),
        play_types=tuple(play_types),
        cells=np.asarray(cells, dtype=np.int64),
        factors=factor_array,
        stats={key: np.asarray(values, dtype=np.float64) for key, values in stat_values.items()},
        ending_three_point_attribute=np.asarray(ending_three_point, dtype=np.float64),
        starting_three_point_attribute=np.asarray(starting_three_point, dtype=np.float64),
        ending_noncontrolled_attribute_mean=np.asarray(
            ending_other_attribute_mean, dtype=np.float64
        ),
        validation=validation,
    )


def _clean_full_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "player_label"}


def _clean_package_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in IDENTITY_KEYS}


def snapshot_name_free_hashes(
    connection: sqlite3.Connection,
    run_id: str,
) -> dict[str, str]:
    rows_by_type = {
        row_type: _snapshot_rows(connection, run_id, row_type)
        for row_type in (*PLAYER_ROW_TYPES, "team_stats")
    }
    full_rows = sorted(
        (
            (row_type, _clean_full_row(row))
            for row_type, rows in rows_by_type.items()
            for row in rows
        ),
        key=lambda item: (item[0], _canonical(item[1])),
    )

    package_rows = {
        row_type: _last_player_rows(rows_by_type[row_type])
        for row_type in PLAYER_ROW_TYPES
    }
    common_indices = sorted(set.intersection(*(set(rows) for rows in package_rows.values())))
    player_packages = sorted(
        _canonical(
            {
                row_type: _clean_package_row(package_rows[row_type][player_index])
                for row_type in PLAYER_ROW_TYPES
            }
        )
        for player_index in common_indices
    )
    field_packages = sorted(
        _canonical(
            {
                row_type: _clean_package_row(package_rows[row_type][player_index])
                for row_type in ("attributes", "tendencies")
            }
        )
        for player_index in common_indices
    )
    return {
        "full_content_without_player_labels": _hash_canonical(full_rows),
        "order_independent_player_packages_without_names_or_storage_identity": _hash_canonical(
            player_packages
        ),
        "order_independent_attribute_tendency_packages_without_names_or_storage_identity": _hash_canonical(
            field_packages
        ),
    }


def analyze_snapshot_distinctness(
    pool_path: Path | None = None,
    *,
    latest_run_id: str = RUN_ID_DEFAULT,
) -> dict[str, Any]:
    pool = (pool_path or default_pool_path()).resolve()
    with _open_read_only(pool) as connection:
        run_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT snapshot_id FROM pool_export_snapshots ORDER BY rowid"
            )
        ]
        hashes = {
            run_id: snapshot_name_free_hashes(connection, run_id) for run_id in run_ids
        }
    methods = tuple(next(iter(hashes.values())).keys())
    uniqueness = {
        method: len({values[method] for values in hashes.values()}) for method in methods
    }
    latest_matches = {
        method: [
            run_id
            for run_id, values in hashes.items()
            if run_id != latest_run_id and values[method] == hashes[latest_run_id][method]
        ]
        for method in methods
    }
    return {
        "pool_sha256": _sha256(pool),
        "snapshot_count": len(run_ids),
        "run_ids": run_ids,
        "unique_hash_counts": uniqueness,
        "latest_run_id": latest_run_id,
        "latest_matches": latest_matches,
        "latest_unique_under_all_methods": all(not matches for matches in latest_matches.values()),
        "hashes": hashes,
        "names_used": False,
    }


def _safe_rate(numerator: np.ndarray, denominator: np.ndarray, scale: float = 1.0) -> np.ndarray:
    result = np.full(numerator.shape, np.nan, dtype=np.float64)
    mask = np.isfinite(numerator) & np.isfinite(denominator) & (denominator > 0.0)
    result[mask] = scale * numerator[mask] / denominator[mask]
    return result


def _dummy_columns(values: np.ndarray, prefix: str) -> tuple[list[str], list[np.ndarray]]:
    categories = sorted({str(value) for value in values})
    return (
        [f"{prefix}={category}" for category in categories[1:]],
        [(values.astype(str) == category).astype(np.float64) for category in categories[1:]],
    )


def _factor_terms(factors: np.ndarray) -> tuple[list[str], list[np.ndarray]]:
    names: list[str] = []
    columns: list[np.ndarray] = []
    for size in range(1, len(FACTOR_NAMES) + 1):
        for indices in itertools.combinations(range(len(FACTOR_NAMES)), size):
            names.append("*".join(FACTOR_NAMES[index] for index in indices))
            columns.append(np.prod(factors[:, indices], axis=1))
    return names, columns


def build_design_matrix(
    data: FactorialRunData,
    *,
    include_play_type_controls: bool = True,
    include_three_point_play_type_moderation: bool = False,
) -> tuple[np.ndarray, list[str]]:
    factor_names, factor_columns = _factor_terms(data.factors)
    names = ["Intercept", *factor_names]
    columns: list[np.ndarray] = [np.ones(data.player_indices.size), *factor_columns]
    # Keep the authored factorial and moderation terms before nuisance controls so
    # rank pruning can only discard redundant controls, never experimental terms.
    if include_three_point_play_type_moderation:
        has_three = np.asarray(
            [any(value == "3 PT" for value in row) for row in data.play_types],
            dtype=np.float64,
        )
        names.append("Has3PTPlayType")
        columns.append(has_three)
        for index, factor_name in enumerate(FACTOR_NAMES):
            names.append(f"Has3PTPlayType*{factor_name}")
            columns.append(has_three * data.factors[:, index])
    for values, prefix in (
        (data.positions, "Position"),
        (data.team_indices, "Team"),
        (data.roster_slots, "RosterSlot"),
    ):
        dummy_names, dummy_values = _dummy_columns(np.asarray(values), prefix)
        names.extend(dummy_names)
        columns.extend(dummy_values)
    if include_play_type_controls:
        for slot in range(4):
            values = np.asarray([row[slot] for row in data.play_types], dtype=object)
            dummy_names, dummy_values = _dummy_columns(values, f"PlayType{slot + 1}")
            names.extend(dummy_names)
            columns.extend(dummy_values)
    return np.column_stack(columns).astype(np.float64), names


def _independent_column_indices(values: np.ndarray) -> list[int]:
    selected: list[int] = []
    basis: list[np.ndarray] = []
    for index in range(values.shape[1]):
        column = values[:, index].astype(np.float64, copy=True)
        original_norm = float(np.linalg.norm(column))
        if original_norm == 0.0:
            continue
        # Re-orthogonalize once to keep the deterministic rank decision stable.
        for _ in range(2):
            for vector in basis:
                column -= vector * float(np.dot(vector, column))
        residual_norm = float(np.linalg.norm(column))
        if residual_norm <= 1e-10 * max(1.0, original_norm):
            continue
        selected.append(index)
        basis.append(column / residual_norm)
    return selected


def _fit_clustered_wls(
    design: np.ndarray,
    outcome: np.ndarray,
    weights: np.ndarray,
    clusters: np.ndarray,
) -> dict[str, Any]:
    mask = (
        np.all(np.isfinite(design), axis=1)
        & np.isfinite(outcome)
        & np.isfinite(weights)
        & (weights > 0.0)
    )
    x_full = design[mask]
    y = outcome[mask]
    w = weights[mask]
    cluster = clusters[mask]
    if x_full.shape[0] == 0:
        raise ValueError("no complete weighted rows")
    w = w / float(np.mean(w))
    sqrt_w = np.sqrt(w)
    xw_full = x_full * sqrt_w[:, None]
    selected = _independent_column_indices(xw_full)
    x = x_full[:, selected]
    xw = xw_full[:, selected]
    yw = y * sqrt_w
    beta_selected = np.linalg.lstsq(xw, yw, rcond=None)[0]
    rank = len(selected)
    bread = np.linalg.inv(xw.T @ xw)
    transformed_residual = sqrt_w * (y - x @ beta_selected)
    meat = np.zeros((x.shape[1], x.shape[1]), dtype=np.float64)
    unique_clusters = np.unique(cluster)
    for cluster_value in unique_clusters:
        cluster_mask = cluster == cluster_value
        score = xw[cluster_mask].T @ transformed_residual[cluster_mask]
        meat += np.outer(score, score)
    covariance = bread @ meat @ bread
    cluster_count = int(unique_clusters.size)
    if cluster_count > 1 and x.shape[0] > rank:
        covariance *= (cluster_count / (cluster_count - 1.0)) * (
            (x.shape[0] - 1.0) / (x.shape[0] - rank)
        )
    standard_errors_selected = np.sqrt(np.maximum(0.0, np.diag(covariance)))
    beta = np.full(design.shape[1], np.nan, dtype=np.float64)
    standard_errors = np.full(design.shape[1], np.nan, dtype=np.float64)
    beta[selected] = beta_selected
    standard_errors[selected] = standard_errors_selected
    return {
        "mask": mask,
        "beta": beta,
        "standard_errors": standard_errors,
        "n": int(x.shape[0]),
        "rank": rank,
        "columns": int(design.shape[1]),
        "active_columns": selected,
        "dropped_redundant_column_count": int(design.shape[1] - len(selected)),
        "cluster_count": cluster_count,
    }


def _normal_p(coefficient: float, standard_error: float) -> float | None:
    if not math.isfinite(standard_error) or standard_error <= 0.0:
        return None
    return math.erfc(abs(coefficient / standard_error) / math.sqrt(2.0))


def _outcomes(data: FactorialRunData) -> dict[str, tuple[np.ndarray, np.ndarray, str]]:
    minutes = data.stats["Minutes"]
    fga = data.stats["Field Goals Attempted"]
    fgm = data.stats["Field Goals Made"]
    three_a = data.stats["Three Pointers Attempted"]
    three_m = data.stats["Three Pointers Made"]
    two_a = fga - three_a
    two_m = fgm - three_m
    ones = np.ones(minutes.shape, dtype=np.float64)
    return {
        "minutes": (minutes, ones, "unweighted_player_season"),
        "fga_per36": (_safe_rate(fga, minutes, 36.0), minutes, "minutes_weighted_rate"),
        "three_pa_per36": (
            _safe_rate(three_a, minutes, 36.0),
            minutes,
            "minutes_weighted_rate",
        ),
        "points_per36": (
            _safe_rate(data.stats["Points"], minutes, 36.0),
            minutes,
            "minutes_weighted_rate",
        ),
        "assists_per36": (
            _safe_rate(data.stats["Assists"], minutes, 36.0),
            minutes,
            "minutes_weighted_rate",
        ),
        "turnovers_per36": (
            _safe_rate(data.stats["Turnovers"], minutes, 36.0),
            minutes,
            "minutes_weighted_rate",
        ),
        "three_attempt_share": (
            _safe_rate(three_a, fga),
            fga,
            "field_goal_attempt_weighted_rate",
        ),
        "three_point_pct": (
            _safe_rate(three_m, three_a),
            three_a,
            "three_point_attempt_weighted_rate",
        ),
        "two_point_pct": (
            _safe_rate(two_m, two_a),
            two_a,
            "two_point_attempt_weighted_rate",
        ),
        "ending_3pt_attribute_change": (
            data.ending_three_point_attribute - data.starting_three_point_attribute,
            ones,
            "unweighted_progression_outcome",
        ),
        "ending_noncontrolled_attribute_mean_change": (
            data.ending_noncontrolled_attribute_mean - 99.0,
            ones,
            "unweighted_progression_outcome",
        ),
    }


def analyze_factorial_effects(data: FactorialRunData) -> list[dict[str, Any]]:
    design, names = build_design_matrix(data, include_play_type_controls=True)
    factor_term_names, _ = _factor_terms(data.factors)
    rows: list[dict[str, Any]] = []
    for outcome_name, (outcome, weights, weighting) in _outcomes(data).items():
        fit = _fit_clustered_wls(design, outcome, weights, data.team_indices)
        for term_name in factor_term_names:
            index = names.index(term_name)
            coefficient = float(fit["beta"][index])
            standard_error = float(fit["standard_errors"][index])
            effect = 2.0 * coefficient
            effect_se = 2.0 * standard_error
            rows.append(
                {
                    "outcome": outcome_name,
                    "term": term_name,
                    "term_order": term_name.count("*") + 1,
                    "coded_factorial_effect": effect,
                    "standard_error": effect_se,
                    "ci95_low": effect - 1.96 * effect_se,
                    "ci95_high": effect + 1.96 * effect_se,
                    "p_value_normal_cluster_robust": _normal_p(effect, effect_se),
                    "n": fit["n"],
                    "design_rank": fit["rank"],
                    "design_columns": fit["columns"],
                    "team_clusters": fit["cluster_count"],
                    "weighting": weighting,
                    "controls": "position+team+roster_slot+PlayTypes1-4",
                    "assignment": "deterministic_balanced_factorial",
                }
            )
    return rows


def analyze_play_type_moderation(data: FactorialRunData) -> list[dict[str, Any]]:
    design, names = build_design_matrix(
        data,
        include_play_type_controls=True,
        include_three_point_play_type_moderation=True,
    )
    outcomes = _outcomes(data)
    rows: list[dict[str, Any]] = []
    for outcome_name in ("three_pa_per36", "three_attempt_share", "three_point_pct"):
        outcome, weights, weighting = outcomes[outcome_name]
        fit = _fit_clustered_wls(design, outcome, weights, data.team_indices)
        for factor_name in FACTOR_NAMES:
            term = f"Has3PTPlayType*{factor_name}"
            index = names.index(term)
            coefficient = float(fit["beta"][index])
            standard_error = float(fit["standard_errors"][index])
            moderation = 2.0 * coefficient
            moderation_se = 2.0 * standard_error
            rows.append(
                {
                    "outcome": outcome_name,
                    "term": term,
                    "difference_in_factor_effect_has_3pt_playtype_minus_not": moderation,
                    "standard_error": moderation_se,
                    "ci95_low": moderation - 1.96 * moderation_se,
                    "ci95_high": moderation + 1.96 * moderation_se,
                    "p_value_normal_cluster_robust": _normal_p(moderation, moderation_se),
                    "n": fit["n"],
                    "players_with_3pt_playtype": int(
                        sum(any(value == "3 PT" for value in row) for row in data.play_types)
                    ),
                    "weighting": weighting,
                    "status": "exploratory_nonrandomized_playtype_context",
                }
            )
    return rows


def cell_summaries(data: FactorialRunData) -> list[dict[str, Any]]:
    stats = data.stats
    rows: list[dict[str, Any]] = []
    for cell in range(16):
        mask = data.cells == cell
        minutes = float(np.sum(stats["Minutes"][mask]))
        fga = float(np.sum(stats["Field Goals Attempted"][mask]))
        fgm = float(np.sum(stats["Field Goals Made"][mask]))
        three_a = float(np.sum(stats["Three Pointers Attempted"][mask]))
        three_m = float(np.sum(stats["Three Pointers Made"][mask]))
        rows.append(
            {
                "cell": cell,
                **{
                    factor_name: "high" if cell & (1 << index) else "low"
                    for index, factor_name in enumerate(FACTOR_NAMES)
                },
                "players": int(mask.sum()),
                "players_with_minutes": int((stats["Minutes"][mask] > 0.0).sum()),
                "minutes": minutes,
                "fga": fga,
                "three_pa": three_a,
                "three_pm": three_m,
                "fga_per36": 36.0 * fga / minutes if minutes > 0.0 else None,
                "three_pa_per36": 36.0 * three_a / minutes if minutes > 0.0 else None,
                "three_attempt_share": three_a / fga if fga > 0.0 else None,
                "three_point_pct": three_m / three_a if three_a > 0.0 else None,
                "two_point_pct": (fgm - three_m) / (fga - three_a)
                if fga > three_a
                else None,
            }
        )
    return rows


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_analysis(
    data: FactorialRunData,
    output_dir: Path,
    *,
    distinctness: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    effects = analyze_factorial_effects(data)
    moderation = analyze_play_type_moderation(data)
    cells = cell_summaries(data)
    focus_terms = {
        ("fga_per36", "Touches"),
        ("fga_per36", "Shot"),
        ("fga_per36", "Touches*Shot"),
        ("three_pa_per36", "Touches"),
        ("three_pa_per36", "Shot"),
        ("three_pa_per36", "3PT_Tendency"),
        ("three_pa_per36", "Shot*3PT_Tendency"),
        ("three_attempt_share", "3PT_Tendency"),
        ("three_point_pct", "3PT_Attribute"),
        ("three_attempt_share", "3PT_Attribute"),
        ("three_point_pct", "3PT_Tendency"),
    }
    focused = [row for row in effects if (row["outcome"], row["term"]) in focus_terms]
    summary = {
        "run_id": data.run_id,
        "pool_sha256": data.pool_sha256,
        "design": {
            "type": "deterministic balanced 2x2x2x2 factorial",
            "factors": list(FACTOR_NAMES),
            "factor_levels": {
                "Touches": [0, 100],
                "Shot": [0, 100],
                "3PT_Tendency": [0, 100],
                "3PT_Attribute": [25, 99],
            },
            "treatment_source": "pre-simulation experiment manifest",
            "ending_ratings_are_treatments": False,
        },
        "validation": data.validation,
        "distinctness": {
            "snapshot_count": distinctness["snapshot_count"],
            "unique_hash_counts": distinctness["unique_hash_counts"],
            "latest_matches": distinctness["latest_matches"],
            "latest_unique_under_all_methods": distinctness[
                "latest_unique_under_all_methods"
            ],
        },
        "focused_effects": focused,
        "playtype_moderation": moderation,
        "interpretation_limits": [
            "assignment was deterministic and balanced, not random",
            "season aggregates do not expose event-level touches, branch eligibility, openness, selected actions, pass targets, or defender matchups",
            "Play Types are captured, but called-play events and coach playbook selections are not",
            "ending Attributes include post-season progression/regression and are not treatment inputs",
            "cluster-robust uncertainty is model-based and secondary to effect magnitude and semantic fit",
            "player names are excluded from alignment, controls, diagnostics, and analysis",
        ],
    }
    (output_dir / "validation.json").write_text(
        json.dumps(data.validation, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "distinctness.json").write_text(
        json.dumps(distinctness, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_csv(output_dir / "factorial_effects.csv", effects)
    _write_csv(output_dir / "focused_effects.csv", focused)
    _write_csv(output_dir / "playtype_moderation.csv", moderation)
    _write_csv(output_dir / "cell_summary.csv", cells)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze the controlled NBA2K26 live factorial run")
    parser.add_argument("--pool", type=Path, default=default_pool_path())
    parser.add_argument("--manifest", type=Path, default=default_manifest_path())
    parser.add_argument("--run-id", default=RUN_ID_DEFAULT)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            _default_repo_root()
            / ".hermes"
            / "audits"
            / "player_generation_live_factorial_analysis_2026-07-18"
        ),
    )
    args = parser.parse_args()
    before = _sha256(args.pool)
    data = load_factorial_run(args.pool, args.manifest, run_id=args.run_id)
    distinctness = analyze_snapshot_distinctness(args.pool, latest_run_id=args.run_id)
    summary = write_analysis(data, args.output, distinctness=distinctness)
    after = _sha256(args.pool)
    if before != after:
        raise RuntimeError("Pool changed during read-only analysis")
    print(
        json.dumps(
            {
                "run_id": summary["run_id"],
                "pool_sha256": before,
                "pool_unchanged": True,
                "output": str(args.output.resolve()),
                "focused_effect_count": len(summary["focused_effects"]),
                "latest_unique_under_all_methods": summary["distinctness"][
                    "latest_unique_under_all_methods"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
