from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")
BASELINE_RUN_ID = "editor_capture_026"
RAW_MINUTES_KEY = "Minutes"
RAW_VOLUME_STATS: tuple[str, ...] = (
    "Assists",
    "Blocks",
    "Defensive Rebounds",
    "Field Goals Attempted",
    "Field Goals Made",
    "Fouls",
    "Free Throws Attempted",
    "Free Throws Made",
    "Offensive Rebounds",
    "Points",
    "Steals",
    "Three Pointers Attempted",
    "Three Pointers Made",
    "Turnovers",
)
REQUIRED_TABLES: tuple[str, ...] = (
    "candidate_pool",
    "candidate_fields",
    "pool_export_rows",
    "pool_export_snapshots",
)


@dataclass(frozen=True)
class PoolAnalysisData:
    pool_path: Path
    pool_sha256: str
    package_keys: tuple[tuple[str, int], ...]
    run_ids: np.ndarray
    player_indices: np.ndarray
    positions: np.ndarray
    field_keys: tuple[str, ...]
    field_types: tuple[str, ...]
    field_values: np.ndarray
    sim_stat_names: tuple[str, ...]
    sim_values: np.ndarray
    raw_stat_names: tuple[str, ...]
    raw_values: np.ndarray
    minutes: np.ndarray
    baseline_mask: np.ndarray
    column_lineage: Mapping[str, str]

    @property
    def package_count(self) -> int:
        return len(self.package_keys)

    def field_indices(self, field_type: str | None = None) -> tuple[int, ...]:
        if field_type is None:
            return tuple(range(len(self.field_keys)))
        return tuple(i for i, value in enumerate(self.field_types) if value == field_type)


def default_pool_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "NBA Player Data"
        / "player_generation_pool"
        / "player_generation_pool.sqlite"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"missing player generation pool: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _float_or_nan(value: object) -> float:
    if value is None or value == "":
        return math.nan
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _required_tables(connection: sqlite3.Connection) -> None:
    available = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    missing = sorted(set(REQUIRED_TABLES) - available)
    if missing:
        raise RuntimeError(f"pool is missing required tables: {missing}")


def classify_candidate_pool_columns(columns: Sequence[str]) -> dict[str, str]:
    lineage: dict[str, str] = {}
    for column in columns:
        if column in {"run_id", "player_index"}:
            lineage[column] = "capture_local_package_key"
        elif column in {"player_label", "master_player"}:
            lineage[column] = "forbidden_2k_or_source_name"
        elif column == "master_player_id":
            lineage[column] = "forbidden_source_identity"
        elif column == "position":
            lineage[column] = "position_partition_key"
        elif column.startswith("master_"):
            lineage[column] = "source_feature_candidate_not_analysis_outcome"
        elif column.startswith("sim_"):
            lineage[column] = "captured_sim_outcome_for_analysis_only"
        else:
            lineage[column] = "legacy_merged_feature_forbidden_until_lineage_proven"
    return lineage


def _field_identity(value: object) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _authored_field_keys() -> dict[tuple[str, str, str], str]:
    from nba2k_editor.core import offsets as offsets_mod

    players = offsets_mod.get_editor_layout_for_super("Players")
    authored: dict[tuple[str, str, str], str] = {}
    for section, groups in players.items():
        if section not in {"Attributes", "Tendencies"} or not isinstance(groups, dict):
            continue
        for group, fields in groups.items():
            if not isinstance(fields, list):
                continue
            for field in fields:
                if not isinstance(field, dict):
                    continue
                normalized = str(field.get("normalized_name") or "").strip()
                display = str(field.get("display_name") or normalized).strip()
                if not normalized:
                    continue
                for field_name in (normalized, display):
                    key = (_field_identity(section), _field_identity(group), _field_identity(field_name))
                    existing = authored.get(key)
                    field_key = f"{section}/{normalized}"
                    if existing is not None and existing != field_key:
                        raise ValueError(f"ambiguous authored field identity: {key}")
                    authored[key] = field_key
    return authored


def _exact_field_map(
    pairs: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    authored = _authored_field_keys()
    mapped: dict[tuple[str, str], str] = {}
    for field_type, input_field in sorted(set(pairs)):
        section = (
            "Attributes"
            if field_type == "Attribute"
            else "Tendencies"
            if field_type == "Tendency"
            else ""
        )
        if not section or "/" not in input_field:
            raise ValueError(f"unsupported candidate field: {(field_type, input_field)!r}")
        group_text, field_text = (part.strip() for part in input_field.split("/", 1))
        key = authored.get((_field_identity(section), _field_identity(group_text), _field_identity(field_text)))
        if key is None:
            raise KeyError(f"candidate field is not in authored offsets: {(field_type, input_field)!r}")
        if key in mapped.values():
            raise ValueError(f"multiple candidate fields resolve to {key}")
        mapped[(field_type, input_field)] = key
    return mapped


def _load_raw_stats_by_package(
    connection: sqlite3.Connection,
) -> dict[tuple[str, int], dict[str, object]]:
    # Deliberately reproduce player_generation_pool._stored_snapshot_rows:
    # ORDER BY rowid and last row wins for a repeated capture-local player_index.
    rows: dict[tuple[str, int], dict[str, object]] = {}
    query = """
        SELECT snapshot_id, row_json
        FROM pool_export_rows
        WHERE row_type = 'stats'
        ORDER BY rowid
    """
    for row in connection.execute(query):
        payload = json.loads(str(row["row_json"]))
        key = (str(row["snapshot_id"]), int(payload["player_index"]))
        rows[key] = payload
    return rows


def load_pool_analysis_data(pool_path: Path | str | None = None) -> PoolAnalysisData:
    path = Path(pool_path) if pool_path is not None else default_pool_path()
    before_hash = sha256_file(path)

    with _read_only_connection(path) as connection:
        _required_tables(connection)
        table_info = list(connection.execute("PRAGMA table_info(candidate_pool)"))
        candidate_columns = tuple(str(row[1]) for row in table_info)
        lineage = classify_candidate_pool_columns(candidate_columns)
        sim_stat_names = tuple(column for column in candidate_columns if column.startswith("sim_"))
        if not sim_stat_names:
            raise RuntimeError("candidate_pool has no sim_* analysis outcomes")

        select_columns = ("run_id", "player_index", "position", *sim_stat_names)
        quoted = ", ".join(f'"{column}"' for column in select_columns)
        candidate_rows = list(
            connection.execute(
                f"SELECT {quoted} FROM candidate_pool ORDER BY run_id, player_index"
            )
        )
        package_keys = tuple(
            (str(row["run_id"]), int(row["player_index"])) for row in candidate_rows
        )
        if len(package_keys) != len(set(package_keys)):
            raise RuntimeError("candidate_pool contains duplicate (run_id, player_index) packages")
        package_index = {key: i for i, key in enumerate(package_keys)}

        run_ids = np.asarray([key[0] for key in package_keys], dtype=object)
        player_indices = np.asarray([key[1] for key in package_keys], dtype=np.int64)
        positions = np.asarray([str(row["position"]).strip().upper() for row in candidate_rows], dtype=object)
        invalid_positions = sorted(set(positions.tolist()) - set(POSITIONS))
        if invalid_positions:
            raise ValueError(f"candidate_pool has unsupported positions: {invalid_positions}")

        sim_values = np.full((len(candidate_rows), len(sim_stat_names)), np.nan, dtype=np.float64)
        for row_index, row in enumerate(candidate_rows):
            for stat_index, stat_name in enumerate(sim_stat_names):
                sim_values[row_index, stat_index] = _float_or_nan(row[stat_name])

        field_rows = list(
            connection.execute(
                """
                SELECT run_id, player_index, position, field_type, input_field, value
                FROM candidate_fields
                ORDER BY run_id, player_index, field_type, input_field
                """
            )
        )
        pairs = {
            (str(row["field_type"]), str(row["input_field"])) for row in field_rows
        }
        field_map = _exact_field_map(pairs)
        ordered_fields = sorted(
            (
                field_key,
                field_type,
                input_field,
            )
            for (field_type, input_field), field_key in field_map.items()
        )
        field_keys = tuple(item[0] for item in ordered_fields)
        field_types = tuple(item[1] for item in ordered_fields)
        field_index = {key: i for i, key in enumerate(field_keys)}
        pair_to_index = {
            (field_type, input_field): field_index[field_key]
            for field_key, field_type, input_field in ordered_fields
        }
        field_values = np.full((len(candidate_rows), len(field_keys)), np.nan, dtype=np.float64)
        seen_field_cells: set[tuple[int, int]] = set()
        for row in field_rows:
            key = (str(row["run_id"]), int(row["player_index"]))
            row_index = package_index.get(key)
            if row_index is None:
                raise KeyError(f"candidate_fields package is missing from candidate_pool: {key}")
            position = str(row["position"]).strip().upper()
            if position != positions[row_index]:
                raise ValueError(f"position mismatch for package {key}: {position} != {positions[row_index]}")
            pair = (str(row["field_type"]), str(row["input_field"]))
            column_index = pair_to_index[pair]
            cell = (row_index, column_index)
            if cell in seen_field_cells:
                raise RuntimeError(f"duplicate candidate field cell: {key}, {pair}")
            seen_field_cells.add(cell)
            field_values[row_index, column_index] = _float_or_nan(row["value"])

        raw_by_package = _load_raw_stats_by_package(connection)

    raw_stat_names = RAW_VOLUME_STATS
    raw_values = np.full((len(package_keys), len(raw_stat_names)), np.nan, dtype=np.float64)
    minutes = np.full(len(package_keys), np.nan, dtype=np.float64)
    for row_index, key in enumerate(package_keys):
        payload = raw_by_package.get(key)
        if payload is None:
            continue
        minutes[row_index] = _float_or_nan(payload.get(RAW_MINUTES_KEY))
        for stat_index, stat_name in enumerate(raw_stat_names):
            raw_values[row_index, stat_index] = _float_or_nan(payload.get(stat_name))

    after_hash = sha256_file(path)
    if after_hash != before_hash:
        raise RuntimeError("pool changed while read-only analysis data was loading")

    if len(field_keys) != 159:
        raise RuntimeError(f"expected 159 exact fields, found {len(field_keys)}")
    attribute_count = sum(value == "Attribute" for value in field_types)
    tendency_count = sum(value == "Tendency" for value in field_types)
    if (attribute_count, tendency_count) != (52, 107):
        raise RuntimeError(
            f"expected 52 Attributes and 107 Tendencies, found {attribute_count} and {tendency_count}"
        )

    return PoolAnalysisData(
        pool_path=path.resolve(),
        pool_sha256=before_hash,
        package_keys=package_keys,
        run_ids=run_ids,
        player_indices=player_indices,
        positions=positions,
        field_keys=field_keys,
        field_types=field_types,
        field_values=field_values,
        sim_stat_names=sim_stat_names,
        sim_values=sim_values,
        raw_stat_names=raw_stat_names,
        raw_values=raw_values,
        minutes=minutes,
        baseline_mask=run_ids == BASELINE_RUN_ID,
        column_lineage=lineage,
    )


__all__ = [
    "BASELINE_RUN_ID",
    "POSITIONS",
    "PoolAnalysisData",
    "RAW_MINUTES_KEY",
    "RAW_VOLUME_STATS",
    "classify_candidate_pool_columns",
    "default_pool_path",
    "load_pool_analysis_data",
    "sha256_file",
]
