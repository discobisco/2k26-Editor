from __future__ import annotations

import math
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

GENERATOR_DIR = Path(__file__).resolve().parent
REPO_ROOT = GENERATOR_DIR.parents[1]
for import_path in (REPO_ROOT, GENERATOR_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

PLAYER_MASTER_FEATURES: tuple[str, ...] = (
    "master_pts_per36",
    "master_fga_per36",
    "master_fg_pct",
    "master_x3pa_per36",
    "master_fta_per36",
    "master_ft_pct",
    "master_ast_per36",
    "master_orb_per36",
    "master_drb_per36",
    "master_stl_per36",
    "master_blk_per36",
    "master_tov_per36",
    "master_pf_per36",
    "master_games",
    "master_per",
    "master_ts_percent",
    "master_usg_percent",
)
PLAYER_RUNTIME_FEATURES: tuple[str, ...] = tuple(
    column.removeprefix("master_") for column in PLAYER_MASTER_FEATURES
)
PLAYER_FEATURE_RUNTIME_SOURCES: dict[str, str] = {
    "master_pts_per36": "PlayerEvidence.per_36.pts_per_36_min",
    "master_fga_per36": "PlayerEvidence.per_36.fga_per_36_min",
    "master_fg_pct": "PlayerEvidence.per_game.fg_percent",
    "master_x3pa_per36": "PlayerEvidence.per_36.x3pa_per_36_min",
    "master_fta_per36": "PlayerEvidence.per_36.fta_per_36_min",
    "master_ft_pct": "PlayerEvidence.per_game.ft_percent",
    "master_ast_per36": "PlayerEvidence.per_36.ast_per_36_min",
    "master_orb_per36": "PlayerEvidence.per_36.orb_per_36_min",
    "master_drb_per36": "PlayerEvidence.per_36.drb_per_36_min",
    "master_stl_per36": "PlayerEvidence.per_36.stl_per_36_min",
    "master_blk_per36": "PlayerEvidence.per_36.blk_per_36_min",
    "master_tov_per36": "PlayerEvidence.per_36.tov_per_36_min",
    "master_pf_per36": "PlayerEvidence.per_36.pf_per_36_min",
    "master_games": "PlayerEvidence.per_game.g",
    "master_per": "PlayerEvidence.advanced.per",
    "master_ts_percent": "PlayerEvidence.advanced.ts_percent",
    "master_usg_percent": "PlayerEvidence.advanced.usg_percent",
}

@dataclass(frozen=True)
class SourceMatch:
    package_key: tuple[str, int]
    position: str
    player_id: str
    season: int
    team: str


@dataclass(frozen=True)
class RuntimeFeatureAlignment:
    pool_path: Path
    source_path: Path
    source_matches: dict[tuple[str, int], SourceMatch]
    evidence_by_package: dict[tuple[str, int], Any]
    comparison_rows_by_season: dict[int, tuple[dict[str, Any], ...]]
    raw_vectors: dict[tuple[str, int], np.ndarray]
    runtime_vectors: dict[tuple[str, int], np.ndarray]
    aligned_vectors: dict[tuple[str, int], np.ndarray]
    multi_team_package_keys: frozenset[tuple[str, int]]
    raw_mismatch_package_keys: frozenset[tuple[str, int]]
    aligned_mismatch_package_keys: frozenset[tuple[str, int]]
    context_key_mismatch_count: int
    context_unresolved_count: int

    @property
    def summary(self) -> dict[str, Any]:
        complete_aligned_keys = {
            key for key, vector in self.aligned_vectors.items() if bool(np.isfinite(vector).all())
        }
        complete_runtime_exact_keys = {
            key
            for key in complete_aligned_keys
            if key in self.runtime_vectors and _vectors_match(self.aligned_vectors[key], self.runtime_vectors[key])
        }
        return {
            "exact_source_match_count": len(self.source_matches),
            "unresolved_source_package_count": self.package_count - len(self.source_matches),
            "runtime_vector_count": len(self.runtime_vectors),
            "multi_team_runtime_override_count": len(self.multi_team_package_keys),
            "raw_runtime_mismatch_package_count": len(self.raw_mismatch_package_keys),
            "aligned_runtime_mismatch_package_count": len(self.aligned_mismatch_package_keys),
            "complete_aligned_feature_package_count": len(complete_aligned_keys),
            "complete_aligned_runtime_exact_package_count": len(complete_runtime_exact_keys),
            "complete_aligned_runtime_mismatch_package_count": len(
                (complete_aligned_keys & set(self.runtime_vectors)) - complete_runtime_exact_keys
            ),
            "complete_aligned_source_unresolved_package_count": len(
                complete_aligned_keys - set(self.runtime_vectors)
            ),
            "context_key_mismatch_count": self.context_key_mismatch_count,
            "context_unresolved_count": self.context_unresolved_count,
            "rule": "aggregate 2TM/3TM/etc player rows own player totals/rates; actual teams own game-weighted team/opponent context",
        }

    @property
    def package_count(self) -> int:
        return len(self.raw_vectors)


def default_source_path() -> Path:
    return GENERATOR_DIR / "NBA Player Data" / "NBA_DATA_Master.sqlite"


def _read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"missing SQLite source: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _number(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _float_or_nan(value: object) -> float:
    number = _number(value)
    return number if number is not None else math.nan


def runtime_player_feature_vector(evidence: Any) -> np.ndarray:
    """Build the ordered Option C player vector from the runtime evidence owner."""
    from stat_neighbor_framework import target_features_from_evidence

    features = target_features_from_evidence(evidence)
    return np.asarray(
        [_float_or_nan(features.get(feature)) for feature in PLAYER_RUNTIME_FEATURES],
        dtype=np.float64,
    )


def _vectors_match(left: np.ndarray, right: np.ndarray) -> bool:
    same_missing = np.isnan(left) & np.isnan(right)
    same_value = np.isfinite(left) & np.isfinite(right) & np.isclose(left, right, rtol=0.0, atol=1e-9)
    return bool(np.all(same_missing | same_value))


def _pool_vectors(pool_path: Path) -> dict[tuple[str, int], np.ndarray]:
    columns = ",".join(f'"{column}"' for column in PLAYER_MASTER_FEATURES)
    with _read_only_connection(pool_path) as connection:
        return {
            (str(row["run_id"]), int(row["player_index"])): np.asarray(
                [_float_or_nan(row[column]) for column in PLAYER_MASTER_FEATURES],
                dtype=np.float64,
            )
            for row in connection.execute(
                f"SELECT run_id,player_index,{columns} FROM candidate_pool ORDER BY run_id,player_index"
            )
        }


def exact_source_matches(pool_path: Path, source_path: Path) -> dict[tuple[str, int], SourceMatch]:
    # Reconstruct source candidates with the Pool writer's exact feature owner.
    # Direct SQL-column comparisons miss its per-game -> per-36 fallback and its
    # authored position parser, especially for sparse historical seasons.
    from player_generation_pool import (
        _player_team_key,
        _sheet_rows,
        _sql_feature_values,
        parse_positions,
    )

    with _read_only_connection(source_path) as source:
        season_rows = _sheet_rows(source, "Player Season Info")
        per_game = {_player_team_key(row): row for row in _sheet_rows(source, "Player Per Game")}
        per_36 = {_player_team_key(row): row for row in _sheet_rows(source, "Player Per 36 min")}
        advanced = {_player_team_key(row): row for row in _sheet_rows(source, "Advanced")}

    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_row in season_rows:
        season = int(source_row.get("season") or 0)
        player_id = str(source_row.get("player_id") or "").strip()
        team = str(source_row.get("team") or "").strip().upper()
        if not season or not player_id or not team or (len(team) == 3 and team[0].isdigit() and team[1:] == "TM"):
            continue
        source_key = _player_team_key(source_row)
        features = _sql_feature_values(
            identity={},
            per_game=per_game.get(source_key, {}),
            per_36=per_36.get(source_key, {}),
            per_100={},
            advanced=advanced.get(source_key, {}),
            shooting={},
            team_summary={},
            awards={},
        )
        by_id[player_id.lower()].append(
            {
                "season": season,
                "player_id": player_id,
                "team": team,
                "positions": parse_positions(source_row.get("pos")),
                "features": features,
            }
        )

    matches: dict[tuple[str, int], SourceMatch] = {}
    pool_columns = ",".join(PLAYER_MASTER_FEATURES)
    with _read_only_connection(pool_path) as pool:
        query = f"SELECT run_id,player_index,position,master_player_id,{pool_columns} FROM candidate_pool"
        for row in pool.execute(query):
            candidates: list[dict[str, Any]] = []
            pool_position = str(row["position"] or "").strip().upper()
            for source_row in by_id.get(str(row["master_player_id"]).strip().lower(), ()):
                compared = 0
                valid = True
                for pool_column, runtime_feature in zip(PLAYER_MASTER_FEATURES, PLAYER_RUNTIME_FEATURES):
                    left = _number(row[pool_column])
                    right = _number(source_row["features"].get(runtime_feature))
                    if left is None or right is None:
                        continue
                    compared += 1
                    if abs(left - right) > 1e-6:
                        valid = False
                        break
                if (
                    valid
                    and compared >= 2
                    and (not source_row["positions"] or pool_position in source_row["positions"])
                ):
                    candidates.append(source_row)
            if len(candidates) != 1:
                continue
            source_row = candidates[0]
            key = (str(row["run_id"]), int(row["player_index"]))
            matches[key] = SourceMatch(
                package_key=key,
                position=pool_position,
                player_id=str(source_row["player_id"]).strip(),
                season=int(source_row["season"]),
                team=str(source_row["team"] or "").strip().upper(),
            )
    return matches


def _build_runtime_feature_alignment(pool_path: Path, source_path: Path) -> RuntimeFeatureAlignment:
    from contracts import GeneratorInputContract, OutputTarget
    from player_generator import season_context_index

    raw_vectors = _pool_vectors(pool_path)
    matches = exact_source_matches(pool_path, source_path)
    contexts: dict[int, Any] = {}
    evidence_by_package: dict[tuple[str, int], Any] = {}
    runtime_vectors: dict[tuple[str, int], np.ndarray] = {}
    aligned_vectors = {key: value.copy() for key, value in raw_vectors.items()}
    multi_team_keys: set[tuple[str, int]] = set()
    raw_mismatch_keys: set[tuple[str, int]] = set()
    aligned_mismatch_keys: set[tuple[str, int]] = set()
    context_key_mismatch_count = 0
    context_unresolved_count = 0

    for key, match in matches.items():
        context = contexts.get(match.season)
        if context is None:
            contract = GeneratorInputContract(match.season, source_path.parent, OutputTarget.PREVIEW)
            context = season_context_index(contract)
            contexts[match.season] = context
        try:
            evidence = context.evidence_for(player_id=match.player_id, team=match.team)
        except KeyError:
            context_keys = [
                context_key
                for context_key in context.evidence_by_key
                if str(context_key[0]).lower() == match.player_id.lower()
            ]
            if len(context_keys) != 1:
                context_unresolved_count += 1
                continue
            context_key_mismatch_count += 1
            evidence = context.evidence_by_key[context_keys[0]]

        runtime_vector = runtime_player_feature_vector(evidence)
        evidence_by_package[key] = evidence
        runtime_vectors[key] = runtime_vector
        if not _vectors_match(raw_vectors[key], runtime_vector):
            raw_mismatch_keys.add(key)

        is_multi_team = bool(evidence.season_info.get("multi_team_stat_shares"))
        if is_multi_team:
            multi_team_keys.add(key)
            # Existing master rule: aggregate multi-team player rows own player
            # totals/rates. This is a read-only derivative override; Pool SQL is immutable.
            aligned_vectors[key] = runtime_vector.copy()
        if not _vectors_match(aligned_vectors[key], runtime_vector):
            aligned_mismatch_keys.add(key)

    return RuntimeFeatureAlignment(
        pool_path=pool_path,
        source_path=source_path,
        source_matches=matches,
        evidence_by_package=evidence_by_package,
        comparison_rows_by_season={season: context.comparison_rows for season, context in contexts.items()},
        raw_vectors=raw_vectors,
        runtime_vectors=runtime_vectors,
        aligned_vectors=aligned_vectors,
        multi_team_package_keys=frozenset(multi_team_keys),
        raw_mismatch_package_keys=frozenset(raw_mismatch_keys),
        aligned_mismatch_package_keys=frozenset(aligned_mismatch_keys),
        context_key_mismatch_count=context_key_mismatch_count,
        context_unresolved_count=context_unresolved_count,
    )


@lru_cache(maxsize=4)
def _cached_runtime_feature_alignment(
    pool_path: str,
    source_path: str,
    pool_signature: str,
    source_size: int,
    source_mtime_ns: int,
) -> RuntimeFeatureAlignment:
    del pool_signature, source_size, source_mtime_ns
    return _build_runtime_feature_alignment(Path(pool_path), Path(source_path))


def load_runtime_feature_alignment(
    pool_path: Path | str,
    source_path: Path | str | None = None,
) -> RuntimeFeatureAlignment:
    from player_generation_training_data import sha256_file

    pool = Path(pool_path).resolve()
    source = Path(source_path).resolve() if source_path is not None else default_source_path().resolve()
    source_stat = source.stat()
    return _cached_runtime_feature_alignment(
        str(pool),
        str(source),
        sha256_file(pool),
        source_stat.st_size,
        source_stat.st_mtime_ns,
    )
