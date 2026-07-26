from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
