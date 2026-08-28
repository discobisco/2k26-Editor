from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_generation_model_training import build_three_point_exact_field_artifact  # type: ignore[import-not-found]  # noqa: E402
from player_generation_models import (  # type: ignore[import-not-found]  # noqa: E402
    THREE_POINT_EXACT_FIELD_CONTRACTS,
    THREE_POINT_RUNTIME_FIELDS,
    ThreePointExactFieldArtifact,
    load_three_point_exact_field_artifact,
)
from player_generation_training_data import load_three_point_exact_field_data  # type: ignore[import-not-found]  # noqa: E402
from player_generator import three_point_features_from_evidence  # type: ignore[import-not-found]  # noqa: E402
from player_rules import PLAYER_RULE_SCHEME  # type: ignore[import-not-found]  # noqa: E402


def _create_pool(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE candidate_pool (
            run_id TEXT NOT NULL,
            player_index INTEGER NOT NULL,
            games REAL,
            mp_per_game REAL,
            pts_per36 REAL,
            fga_per36 REAL,
            x3pa_per36 REAL,
            x3p_pct REAL,
            fta_per36 REAL,
            ast_per36 REAL,
            tov_per36 REAL
        );
        CREATE TABLE candidate_fields (
            run_id TEXT NOT NULL,
            player_index INTEGER NOT NULL,
            position TEXT,
            field_type TEXT NOT NULL,
            input_field TEXT NOT NULL,
            value REAL NOT NULL
        );
        """
    )
    pool_rows = []
    field_rows = []
    for run_index in range(3):
        run_id = f"run_{run_index}"
        for player_index in range(24):
            x3pa = (player_index % 12) * 0.8 + run_index * 0.15
            x3p = 0.22 + 0.018 * (player_index % 10) + 0.004 * run_index if x3pa > 0 else None
            fga = 7.0 + (player_index % 10) * 1.5
            pts = 10.0 + (player_index % 12) * 2.2
            fta = 1.0 + (player_index % 5) * 0.7
            ast = 0.8 + (player_index % 7) * 0.9
            tov = 0.5 + (player_index % 4) * 0.45
            pool_rows.append((run_id, player_index, 50 + player_index % 20, 20 + player_index % 15, pts, fga, x3pa, x3p, fta, ast, tov))
            for contract_index, contract in enumerate(THREE_POINT_EXACT_FIELD_CONTRACTS):
                if contract.field_key == "Attributes/3POINT":
                    value = 25 if x3p is None else round(25 + 130 * x3p + 1.5 * x3pa)
                else:
                    value = round(1.5 * x3pa + 0.15 * pts + 0.25 * ast + contract_index)
                value = max(contract.minimum, min(contract.maximum, value))
                field_rows.append((run_id, player_index, "PG", contract.field_type, contract.capture_field, value))
    connection.executemany("INSERT INTO candidate_pool VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", pool_rows)
    connection.executemany("INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)", field_rows)
    connection.commit()
    connection.close()


def _evidence() -> SimpleNamespace:
    return SimpleNamespace(
        per_game={
            "g": 82,
            "mp_per_game": 34.0,
            "pts_per_game": 28.0,
            "fga_per_game": 20.0,
            "x3pa_per_game": 10.0,
            "x3p_percent": 0.40,
            "fta_per_game": 5.0,
            "ast_per_game": 6.0,
            "tov_per_game": 3.0,
        }
    )


def test_three_point_loader_and_training_are_stats_to_independent_exact_fields(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    artifact_path = tmp_path / "three_point.json"
    _create_pool(pool_path)
    before = pool_path.read_bytes()

    loaded = load_three_point_exact_field_data(pool_path)
    artifact = build_three_point_exact_field_artifact(pool_path, artifact_path)
    reloaded = load_three_point_exact_field_artifact(artifact_path)

    assert pool_path.read_bytes() == before
    assert loaded.pool_files_unchanged is True
    assert set(loaded.examples_by_field) == set(THREE_POINT_RUNTIME_FIELDS)
    assert len(reloaded.models) == 14
    assert tuple(model.field_key for model in reloaded.models) == THREE_POINT_RUNTIME_FIELDS
    assert len({model.capture_field for model in reloaded.models}) == 14
    assert all(model.input_stats for model in reloaded.models)
    assert all("name" not in stat and "id" not in stat for model in reloaded.models for stat in model.input_stats)
    assert all(model.evaluation["held_out_packages"] > 0 for model in reloaded.models)
    assert all(model.evaluation["run_count"] == 3 for model in reloaded.models)
    assert artifact.pool_fingerprint == loaded.pool_fingerprint


def test_three_point_artifact_models_predict_independently(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    artifact_path = tmp_path / "three_point.json"
    _create_pool(pool_path)
    artifact = build_three_point_exact_field_artifact(pool_path, artifact_path)
    features = three_point_features_from_evidence(_evidence())

    baseline = artifact.predict_fields(features)
    first = artifact.models[0]
    changed_first = replace(first, intercept=first.intercept + 10.0)
    changed = ThreePointExactFieldArtifact(
        schema_version=artifact.schema_version,
        models=(changed_first, *artifact.models[1:]),
        pool_fingerprint=artifact.pool_fingerprint,
        training_summary=artifact.training_summary,
    ).predict_fields(features)

    assert set(baseline) == set(THREE_POINT_RUNTIME_FIELDS)
    assert changed[first.field_key] != baseline[first.field_key]
    assert {key: value for key, value in changed.items() if key != first.field_key} == {
        key: value for key, value in baseline.items() if key != first.field_key
    }


def test_legacy_rules_do_not_author_exact_three_point_fields() -> None:
    assert set(THREE_POINT_RUNTIME_FIELDS).isdisjoint(PLAYER_RULE_SCHEME)
