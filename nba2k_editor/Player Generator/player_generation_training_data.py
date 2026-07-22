from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from player_generation_models import (
    THREE_POINT_CAPTURE_FIELDS,
    THREE_POINT_FIELD_CONTRACTS,
    THREE_POINT_RUNTIME_FIELDS,
    TWO_POINT_CAPTURE_FIELDS,
    TWO_POINT_FIELD_CONTRACTS,
    TWO_POINT_RUNTIME_FIELDS,
)

FREE_THROW_CAPTURE_FIELD = "Offense / Free Throws"
_SENTINEL_STAT_VALUE = 65535.0


@dataclass(frozen=True)
class FreeThrowResponseExample:
    """One immutable 2K package used by the free-throw execution model.

    ``run_id`` and ``player_index`` are grouping/provenance only. The model input
    is the exact captured Free Throw attribute; the outputs are raw made and
    attempted free throws. Names and Tendencies are intentionally absent.
    """

    run_id: str
    player_index: int
    free_throw_rating: int
    free_throws_made: float
    free_throws_attempted: float

    @property
    def observed_make_probability(self) -> float:
        return self.free_throws_made / self.free_throws_attempted


@dataclass(frozen=True)
class FreeThrowResponseData:
    pool_path: Path
    pool_fingerprint: str
    pool_file_hashes: tuple[tuple[str, str], ...]
    pool_files_unchanged: bool
    examples: tuple[FreeThrowResponseExample, ...]
    candidate_packages: int
    excluded_missing_stats: int
    excluded_zero_attempts: int
    excluded_invalid_totals: int
    excluded_invalid_rating: int


@dataclass(frozen=True)
class ThreePointResponseExample:
    """One complete 3PT input package and its aggregate shooting response."""

    run_id: str
    player_index: int
    field_values: tuple[int, ...]
    three_pointers_made: float
    three_pointers_attempted: float
    field_goals_attempted: float

    def field_mapping(self) -> dict[str, int]:
        return dict(zip(THREE_POINT_RUNTIME_FIELDS, self.field_values, strict=True))

    @property
    def observed_make_probability(self) -> float | None:
        if self.three_pointers_attempted <= 0.0:
            return None
        return self.three_pointers_made / self.three_pointers_attempted

    @property
    def observed_attempt_share(self) -> float:
        return self.three_pointers_attempted / self.field_goals_attempted


@dataclass(frozen=True)
class ThreePointResponseData:
    pool_path: Path
    pool_fingerprint: str
    pool_file_hashes: tuple[tuple[str, str], ...]
    pool_files_unchanged: bool
    examples: tuple[ThreePointResponseExample, ...]
    candidate_packages: int
    excluded_missing_input_fields: int
    excluded_invalid_input_values: int
    excluded_missing_stats: int
    excluded_zero_field_goal_attempts: int
    excluded_invalid_totals: int


@dataclass(frozen=True)
class TwoPointResponseExample:
    """One complete 2PT field package and its aggregate 2PT response."""

    run_id: str
    player_index: int
    field_values: tuple[int, ...]
    two_points_made: float
    two_points_attempted: float
    minutes: float
    height_inches: float
    weight_pounds: float
    position: str

    def field_mapping(self) -> dict[str, int]:
        return dict(zip(TWO_POINT_RUNTIME_FIELDS, self.field_values, strict=True))

    def player_context(self) -> dict[str, Any]:
        return {
            "height_inches": self.height_inches,
            "weight_pounds": self.weight_pounds,
            "position": self.position,
        }

    @property
    def observed_make_probability(self) -> float | None:
        if self.two_points_attempted <= 0.0:
            return None
        return self.two_points_made / self.two_points_attempted

    @property
    def observed_attempts_per_36(self) -> float:
        return 36.0 * self.two_points_attempted / self.minutes


@dataclass(frozen=True)
class TwoPointResponseData:
    pool_path: Path
    pool_fingerprint: str
    pool_file_hashes: tuple[tuple[str, str], ...]
    pool_files_unchanged: bool
    examples: tuple[TwoPointResponseExample, ...]
    candidate_packages: int
    excluded_missing_input_fields: int
    excluded_invalid_input_values: int
    excluded_missing_stats: int
    excluded_missing_stat_values: int
    excluded_missing_context: int
    excluded_invalid_context: int
    excluded_nonpositive_minutes: int
    excluded_invalid_totals: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pool_file_hashes(pool_path: Path) -> tuple[tuple[str, str], ...]:
    files = [pool_path]
    wal_path = Path(f"{pool_path}-wal")
    if wal_path.exists() and wal_path.stat().st_size > 0:
        files.append(wal_path)
    return tuple((path.name, _sha256(path)) for path in files)


def _pool_fingerprint(file_hashes: tuple[tuple[str, str], ...]) -> str:
    payload = json.dumps(file_hashes, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _read_numeric(payload: dict[str, Any], key: str) -> float | None:
    raw = payload.get(key)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _read_rating(raw: Any) -> int | None:
    return _read_bounded_integer(raw, 25, 99)


def _read_bounded_integer(raw: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(raw, bool):
        return None
    try:
        numeric = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer():
        return None
    value = int(numeric)
    return value if minimum <= value <= maximum else None


def load_free_throw_response_data(pool_path: str | Path) -> FreeThrowResponseData:
    """Load the Free Throw attribute response slice from the Pool, read-only.

    Raw stat rows use the capture writer's canonical last-row-wins rule for each
    ``(snapshot_id, player_index)``. Packages with no free-throw attempts carry
    no execution information and are reported, not used as observations.
    """

    path = Path(pool_path).resolve()
    before_hashes = _pool_file_hashes(path)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError(f"Pool integrity check failed: {integrity!r}")

        candidate_rows = connection.execute(
            """
            SELECT run_id, player_index, value
            FROM candidate_fields
            WHERE field_type = 'Attribute' AND input_field = ?
            ORDER BY run_id, player_index
            """,
            (FREE_THROW_CAPTURE_FIELD,),
        ).fetchall()

        canonical_stats: dict[tuple[str, int], dict[str, Any]] = {}
        for snapshot_id, row_json in connection.execute(
            """
            SELECT snapshot_id, row_json
            FROM pool_export_rows
            WHERE row_type = 'stats'
            ORDER BY rowid
            """
        ):
            payload = json.loads(row_json)
            player_index = payload.get("player_index")
            if isinstance(player_index, bool):
                continue
            try:
                index = int(player_index)
            except (TypeError, ValueError):
                continue
            canonical_stats[(str(snapshot_id), index)] = payload
    finally:
        connection.close()

    examples: list[FreeThrowResponseExample] = []
    missing_stats = 0
    zero_attempts = 0
    invalid_totals = 0
    invalid_rating = 0
    seen_packages: set[tuple[str, int]] = set()
    for run_id_raw, player_index_raw, rating_raw in candidate_rows:
        run_id = str(run_id_raw)
        player_index = int(player_index_raw)
        package_key = (run_id, player_index)
        if package_key in seen_packages:
            raise ValueError(f"Duplicate Free Throw candidate package: {package_key!r}")
        seen_packages.add(package_key)

        rating = _read_rating(rating_raw)
        if rating is None:
            invalid_rating += 1
            continue
        stats = canonical_stats.get(package_key)
        if stats is None:
            missing_stats += 1
            continue
        made = _read_numeric(stats, "Free Throws Made")
        attempted = _read_numeric(stats, "Free Throws Attempted")
        if (
            made is None
            or attempted is None
            or made < 0.0
            or attempted < 0.0
            or made > attempted
            or made >= _SENTINEL_STAT_VALUE
            or attempted >= _SENTINEL_STAT_VALUE
        ):
            invalid_totals += 1
            continue
        if attempted == 0.0:
            zero_attempts += 1
            continue
        examples.append(
            FreeThrowResponseExample(
                run_id=run_id,
                player_index=player_index,
                free_throw_rating=rating,
                free_throws_made=made,
                free_throws_attempted=attempted,
            )
        )

    after_hashes = _pool_file_hashes(path)
    if after_hashes != before_hashes:
        raise RuntimeError("Pool files changed during the read-only Free Throw load")
    return FreeThrowResponseData(
        pool_path=path,
        pool_fingerprint=_pool_fingerprint(before_hashes),
        pool_file_hashes=before_hashes,
        pool_files_unchanged=True,
        examples=tuple(examples),
        candidate_packages=len(candidate_rows),
        excluded_missing_stats=missing_stats,
        excluded_zero_attempts=zero_attempts,
        excluded_invalid_totals=invalid_totals,
        excluded_invalid_rating=invalid_rating,
    )


def load_three_point_response_data(pool_path: str | Path) -> ThreePointResponseData:
    """Load the complete 3PT Attribute/Tendency group and aggregate responses."""

    path = Path(pool_path).resolve()
    before_hashes = _pool_file_hashes(path)
    contract_by_capture = {
        capture_field: (runtime_field, field_type, minimum, maximum, index)
        for index, (runtime_field, field_type, capture_field, minimum, maximum) in enumerate(
            THREE_POINT_FIELD_CONTRACTS
        )
    }
    placeholders = ",".join("?" for _field in THREE_POINT_CAPTURE_FIELDS)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError(f"Pool integrity check failed: {integrity!r}")
        candidate_rows = connection.execute(
            f"""
            SELECT run_id, player_index, field_type, input_field, value
            FROM candidate_fields
            WHERE input_field IN ({placeholders})
            ORDER BY run_id, player_index, input_field
            """,
            THREE_POINT_CAPTURE_FIELDS,
        ).fetchall()
        canonical_stats: dict[tuple[str, int], dict[str, Any]] = {}
        for snapshot_id, row_json in connection.execute(
            """
            SELECT snapshot_id, row_json
            FROM pool_export_rows
            WHERE row_type = 'stats'
            ORDER BY rowid
            """
        ):
            payload = json.loads(row_json)
            player_index = payload.get("player_index")
            if isinstance(player_index, bool):
                continue
            try:
                index = int(player_index)
            except (TypeError, ValueError):
                continue
            canonical_stats[(str(snapshot_id), index)] = payload
    finally:
        connection.close()

    package_values: dict[tuple[str, int], dict[str, Any]] = {}
    invalid_packages: set[tuple[str, int]] = set()
    for run_id_raw, player_index_raw, field_type_raw, capture_field_raw, value in candidate_rows:
        package_key = (str(run_id_raw), int(player_index_raw))
        capture_field = str(capture_field_raw)
        contract = contract_by_capture.get(capture_field)
        if contract is None or str(field_type_raw) != contract[1]:
            invalid_packages.add(package_key)
            continue
        values = package_values.setdefault(package_key, {})
        if capture_field in values:
            invalid_packages.add(package_key)
            continue
        values[capture_field] = value

    examples: list[ThreePointResponseExample] = []
    missing_input_fields = 0
    invalid_input_values = 0
    missing_stats = 0
    zero_field_goal_attempts = 0
    invalid_totals = 0
    for package_key in sorted(package_values):
        values = package_values[package_key]
        if package_key in invalid_packages:
            invalid_input_values += 1
            continue
        if any(capture_field not in values for capture_field in THREE_POINT_CAPTURE_FIELDS):
            missing_input_fields += 1
            continue
        parsed_values: list[int] = []
        for _runtime_field, _field_type, capture_field, minimum, maximum in THREE_POINT_FIELD_CONTRACTS:
            parsed = _read_bounded_integer(values[capture_field], minimum, maximum)
            if parsed is None:
                break
            parsed_values.append(parsed)
        if len(parsed_values) != len(THREE_POINT_FIELD_CONTRACTS):
            invalid_input_values += 1
            continue
        stats = canonical_stats.get(package_key)
        if stats is None:
            missing_stats += 1
            continue
        three_made = _read_numeric(stats, "Three Pointers Made")
        three_attempted = _read_numeric(stats, "Three Pointers Attempted")
        field_made = _read_numeric(stats, "Field Goals Made")
        field_attempted = _read_numeric(stats, "Field Goals Attempted")
        if (
            three_made is None
            or three_attempted is None
            or field_made is None
            or field_attempted is None
            or any(
                value < 0.0 or value >= _SENTINEL_STAT_VALUE
                for value in (three_made, three_attempted, field_made, field_attempted)
            )
            or three_made > three_attempted
            or three_attempted > field_attempted
            or three_made > field_made
            or field_made > field_attempted
        ):
            invalid_totals += 1
            continue
        if field_attempted == 0.0:
            zero_field_goal_attempts += 1
            continue
        examples.append(
            ThreePointResponseExample(
                run_id=package_key[0],
                player_index=package_key[1],
                field_values=tuple(parsed_values),
                three_pointers_made=three_made,
                three_pointers_attempted=three_attempted,
                field_goals_attempted=field_attempted,
            )
        )

    after_hashes = _pool_file_hashes(path)
    if after_hashes != before_hashes:
        raise RuntimeError("Pool files changed during the read-only 3PT load")
    return ThreePointResponseData(
        pool_path=path,
        pool_fingerprint=_pool_fingerprint(before_hashes),
        pool_file_hashes=before_hashes,
        pool_files_unchanged=True,
        examples=tuple(examples),
        candidate_packages=len(package_values),
        excluded_missing_input_fields=missing_input_fields,
        excluded_invalid_input_values=invalid_input_values,
        excluded_missing_stats=missing_stats,
        excluded_zero_field_goal_attempts=zero_field_goal_attempts,
        excluded_invalid_totals=invalid_totals,
    )


def load_two_point_response_data(pool_path: str | Path) -> TwoPointResponseData:
    """Load the complete 2PT field group and derive aggregate 2PT responses."""

    path = Path(pool_path).resolve()
    before_hashes = _pool_file_hashes(path)
    contract_by_capture = {
        capture_field: (runtime_field, field_type, minimum, maximum)
        for runtime_field, field_type, capture_field, minimum, maximum in TWO_POINT_FIELD_CONTRACTS
    }
    placeholders = ",".join("?" for _field in TWO_POINT_CAPTURE_FIELDS)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError(f"Pool integrity check failed: {integrity!r}")
        candidate_rows = connection.execute(
            f"""
            SELECT run_id, player_index, field_type, input_field, value
            FROM candidate_fields
            WHERE input_field IN ({placeholders})
            ORDER BY run_id, player_index, input_field
            """,
            TWO_POINT_CAPTURE_FIELDS,
        ).fetchall()
        candidate_context = {
            (str(run_id), int(player_index)): (height_inches, weight_pounds, position)
            for run_id, player_index, height_inches, weight_pounds, position in connection.execute(
                """
                SELECT run_id, player_index, height_inches, weight_pounds, position
                FROM candidate_pool
                ORDER BY run_id, player_index
                """
            )
        }
        canonical_stats: dict[tuple[str, int], dict[str, Any]] = {}
        for snapshot_id, row_json in connection.execute(
            """
            SELECT snapshot_id, row_json
            FROM pool_export_rows
            WHERE row_type = 'stats'
            ORDER BY rowid
            """
        ):
            payload = json.loads(row_json)
            player_index = payload.get("player_index")
            if isinstance(player_index, bool):
                continue
            try:
                index = int(player_index)
            except (TypeError, ValueError):
                continue
            canonical_stats[(str(snapshot_id), index)] = payload
    finally:
        connection.close()

    package_values: dict[tuple[str, int], dict[str, Any]] = {}
    invalid_packages: set[tuple[str, int]] = set()
    for run_id_raw, player_index_raw, field_type_raw, capture_field_raw, value in candidate_rows:
        package_key = (str(run_id_raw), int(player_index_raw))
        capture_field = str(capture_field_raw)
        contract = contract_by_capture.get(capture_field)
        if contract is None or str(field_type_raw) != contract[1]:
            invalid_packages.add(package_key)
            continue
        values = package_values.setdefault(package_key, {})
        if capture_field in values:
            invalid_packages.add(package_key)
            continue
        values[capture_field] = value

    examples: list[TwoPointResponseExample] = []
    missing_input_fields = 0
    invalid_input_values = 0
    missing_stats = 0
    missing_stat_values = 0
    missing_context = 0
    invalid_context = 0
    nonpositive_minutes = 0
    invalid_totals = 0
    for package_key in sorted(package_values):
        values = package_values[package_key]
        if package_key in invalid_packages:
            invalid_input_values += 1
            continue
        if any(capture_field not in values for capture_field in TWO_POINT_CAPTURE_FIELDS):
            missing_input_fields += 1
            continue
        parsed_values: list[int] = []
        for _runtime_field, _field_type, capture_field, minimum, maximum in TWO_POINT_FIELD_CONTRACTS:
            parsed = _read_bounded_integer(values[capture_field], minimum, maximum)
            if parsed is None:
                break
            parsed_values.append(parsed)
        if len(parsed_values) != len(TWO_POINT_FIELD_CONTRACTS):
            invalid_input_values += 1
            continue
        stats = canonical_stats.get(package_key)
        if stats is None:
            missing_stats += 1
            continue
        context = candidate_context.get(package_key)
        if context is None:
            missing_context += 1
            continue
        height_raw, weight_raw, position_raw = context
        try:
            height_inches = float(height_raw)
            weight_pounds = float(weight_raw)
        except (TypeError, ValueError):
            invalid_context += 1
            continue
        position = str(position_raw or "").strip().upper()
        if (
            not math.isfinite(height_inches)
            or not math.isfinite(weight_pounds)
            or position not in {"PG", "SG", "SF", "PF", "C"}
        ):
            invalid_context += 1
            continue
        field_made = _read_numeric(stats, "Field Goals Made")
        field_attempted = _read_numeric(stats, "Field Goals Attempted")
        three_made = _read_numeric(stats, "Three Pointers Made")
        three_attempted = _read_numeric(stats, "Three Pointers Attempted")
        minutes = _read_numeric(stats, "Minutes")
        if (
            field_made is None
            or field_attempted is None
            or three_made is None
            or three_attempted is None
            or minutes is None
        ):
            missing_stat_values += 1
            continue
        if minutes <= 0.0:
            nonpositive_minutes += 1
            continue
        if (
            any(
                value < 0.0 or value >= _SENTINEL_STAT_VALUE
                for value in (field_made, field_attempted, three_made, three_attempted, minutes)
            )
            or field_made > field_attempted
            or three_made > three_attempted
            or three_made > field_made
            or three_attempted > field_attempted
        ):
            invalid_totals += 1
            continue
        two_made = field_made - three_made
        two_attempted = field_attempted - three_attempted
        if two_made < 0.0 or two_attempted < 0.0 or two_made > two_attempted:
            invalid_totals += 1
            continue
        examples.append(
            TwoPointResponseExample(
                run_id=package_key[0],
                player_index=package_key[1],
                field_values=tuple(parsed_values),
                two_points_made=two_made,
                two_points_attempted=two_attempted,
                minutes=minutes,
                height_inches=height_inches,
                weight_pounds=weight_pounds,
                position=position,
            )
        )

    after_hashes = _pool_file_hashes(path)
    if after_hashes != before_hashes:
        raise RuntimeError("Pool files changed during the read-only 2PT load")
    return TwoPointResponseData(
        pool_path=path,
        pool_fingerprint=_pool_fingerprint(before_hashes),
        pool_file_hashes=before_hashes,
        pool_files_unchanged=True,
        examples=tuple(examples),
        candidate_packages=len(package_values),
        excluded_missing_input_fields=missing_input_fields,
        excluded_invalid_input_values=invalid_input_values,
        excluded_missing_stats=missing_stats,
        excluded_missing_stat_values=missing_stat_values,
        excluded_missing_context=missing_context,
        excluded_invalid_context=invalid_context,
        excluded_nonpositive_minutes=nonpositive_minutes,
        excluded_invalid_totals=invalid_totals,
    )
