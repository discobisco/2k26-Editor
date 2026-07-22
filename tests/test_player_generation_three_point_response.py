from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_generation_model_training import (  # type: ignore[import-not-found]
    build_three_point_shooting_artifact,
)
from player_generation_models import (  # type: ignore[import-not-found]
    THREE_POINT_LOCATION_TENDENCY_FIELDS,
    THREE_POINT_FEATURE_NAMES,
    THREE_POINT_FIELD_CONTRACTS,
    THREE_POINT_RUNTIME_FIELDS,
    load_three_point_shooting_artifact,
)
from player_generation_training_data import (  # type: ignore[import-not-found]
    ThreePointResponseExample,
    load_three_point_response_data,
)
from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_generator import _with_percentage_shot_locations  # type: ignore[import-not-found]
from player_rules import (  # type: ignore[import-not-found]
    PLAYER_RULE_SCHEME,
    PlayerRuleResult,
    RuleValue,
    derive_player_rule_values,
)
from stat_neighbor_framework import PositionSelection  # type: ignore[import-not-found]
import player_rules_offense  # type: ignore[import-not-found]


_LEGACY_THREE_POINT_HOT_ZONE_FIELDS = {
    "Tendencies/CENTER3",
    "Tendencies/LEFT3",
    "Tendencies/RIGHT3",
    "Tendencies/3CENTER",
    "Tendencies/3LEFT",
    "Tendencies/3LEFTCENTER",
    "Tendencies/3RIGHT",
    "Tendencies/3RIGHTCENTER",
}


def _field_values(player_index: int) -> tuple[int, ...]:
    attribute = 40 + player_index
    tendencies = tuple((player_index * (offset + 3) + offset * 11) % 101 for offset in range(13))
    return (attribute, *tendencies)


def _create_three_point_pool(path: Path, package_count: int = 30) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE candidate_fields (
            run_id TEXT NOT NULL,
            player_index INTEGER NOT NULL,
            position TEXT,
            field_type TEXT NOT NULL,
            input_field TEXT NOT NULL,
            value REAL NOT NULL
        );
        CREATE TABLE pool_export_rows (
            snapshot_id TEXT NOT NULL,
            row_type TEXT NOT NULL,
            row_json TEXT NOT NULL
        );
        """
    )
    candidate_rows = []
    stat_rows = []
    for player_index in range(package_count):
        values = _field_values(player_index)
        for value, (_runtime, field_type, captured_field, _minimum, _maximum) in zip(
            values, THREE_POINT_FIELD_CONTRACTS, strict=True
        ):
            candidate_rows.append(("same_run", player_index, "PG", field_type, captured_field, value))
        three_attempted = 0 if player_index == 0 else 10 + player_index
        make_probability = 0.24 + values[0] / 300.0
        three_made = round(three_attempted * make_probability)
        field_attempted = 80 + player_index
        field_made = min(field_attempted, three_made + 20)
        payload = {
            "player_index": player_index,
            "player_label": f"ignored-{player_index}",
            "Three Pointers Made": str(three_made),
            "Three Pointers Attempted": str(three_attempted),
            "Field Goals Made": str(field_made),
            "Field Goals Attempted": str(field_attempted),
        }
        stat_rows.append(("same_run", "stats", json.dumps(payload)))
    connection.executemany("INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)", candidate_rows)
    connection.executemany("INSERT INTO pool_export_rows VALUES (?, ?, ?)", stat_rows)
    connection.commit()
    connection.close()


def test_three_point_loader_keeps_all_correlated_fields_and_zero_attempt_volume_evidence(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    _create_three_point_pool(pool_path)
    before = pool_path.read_bytes()

    loaded = load_three_point_response_data(pool_path)

    assert pool_path.read_bytes() == before
    assert loaded.pool_files_unchanged is True
    assert loaded.candidate_packages == 30
    assert len(loaded.examples) == 30
    assert loaded.examples[0].three_pointers_attempted == 0
    assert loaded.examples[0].observed_make_probability is None
    assert loaded.examples[0].observed_attempt_share == 0
    assert loaded.examples[1].field_mapping() == dict(
        zip(THREE_POINT_RUNTIME_FIELDS, _field_values(1), strict=True)
    )
    assert len(loaded.examples[1].field_values) == 14
    assert "Tendencies/STEPTHROUGH" in THREE_POINT_RUNTIME_FIELDS
    assert "player_label" not in ThreePointResponseExample.__dataclass_fields__


def test_proposal_assembly_normalizes_complete_three_point_location_group() -> None:
    raw_values = (10, 20, 30, 40, 50)
    rules = PlayerRuleResult(values={
        field: RuleValue(value=value, source_rule="fixture_3pt", evidence_keys=("fixture",))
        for field, value in zip(THREE_POINT_LOCATION_TENDENCY_FIELDS, raw_values, strict=True)
    })

    normalized = _with_percentage_shot_locations(rules)

    assert [normalized.values[field].value for field in THREE_POINT_LOCATION_TENDENCY_FIELDS] == [7, 13, 20, 27, 33]
    assert sum(int(normalized.values[field].value) for field in THREE_POINT_LOCATION_TENDENCY_FIELDS) == 100
    assert {normalized.values[field].source_rule for field in THREE_POINT_LOCATION_TENDENCY_FIELDS} == {"fixture_3pt"}
    assert all(
        "directional_location_percentage_total=100" in normalized.values[field].evidence_keys
        for field in THREE_POINT_LOCATION_TENDENCY_FIELDS
    )


def test_three_point_training_publishes_joint_package_evaluation_and_runtime_artifact(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    artifact_path = tmp_path / "three_point.json"
    _create_three_point_pool(pool_path)
    before = pool_path.read_bytes()

    artifact = build_three_point_shooting_artifact(pool_path, artifact_path)
    loaded = load_three_point_shooting_artifact(artifact_path)
    prediction = loaded.predict(dict(zip(THREE_POINT_RUNTIME_FIELDS, _field_values(10), strict=True)))
    unresolved = loaded.predict({THREE_POINT_RUNTIME_FIELDS[0]: 80})

    assert pool_path.read_bytes() == before
    assert artifact.field_keys == THREE_POINT_RUNTIME_FIELDS
    assert artifact.feature_names == THREE_POINT_FEATURE_NAMES
    assert artifact.training_summary["attribute_field_count"] == 1
    assert artifact.training_summary["tendency_field_count"] == 13
    assert artifact.training_summary["attempt_share_packages"] == 30
    assert artifact.training_summary["make_probability_packages"] == 29
    assert artifact.evaluation_summary["package_count"] == 30
    assert artifact.evaluation_summary["make_probability"]["held_out_packages"] == 29
    assert artifact.evaluation_summary["attempt_share"]["held_out_packages"] == 30
    assert prediction.resolved is True
    assert prediction.make_probability is not None and 0.0 < prediction.make_probability < 1.0
    assert prediction.attempt_share is not None and 0.0 < prediction.attempt_share < 1.0
    assert unresolved.resolved is False
    assert unresolved.make_probability is None
    assert set(unresolved.missing_fields) == set(THREE_POINT_RUNTIME_FIELDS[1:])
    payload = loaded.to_dict()
    assert len(payload["field_contract"]) == 14
    assert payload["field_contract"][0]["minimum"] == 25
    assert all(row["minimum"] == 0 for row in payload["field_contract"][1:])


def test_old_rule_neighbor_fixed_and_hot_zone_paths_do_not_author_three_point_fields() -> None:
    stripped_fields = set(THREE_POINT_RUNTIME_FIELDS) | _LEGACY_THREE_POINT_HOT_ZONE_FIELDS
    evidence = PlayerEvidence(
        player_id="fixture",
        season=2025,
        team="T",
        identity={},
        season_info={"pos": "PG"},
        per_game={"x3p_percent": 0.4, "x3pa_per_game": 8.0},
        totals={},
        per_36={},
        per_100={},
        advanced={"x3p_ar": 0.5},
        shooting={},
        play_by_play={},
        team_roster=(),
        team_stats_per_game={},
        team_stats_per_100={},
        team_summary={},
        opponent_stats_per_game={},
        opponent_stats_per_100={},
        source_context={},
        missing_sources=(),
    )

    result = derive_player_rule_values(
        evidence,
        positions=PositionSelection("PG", None, ("PG",), (("PG", 1.0),)),
        active_field_keys=stripped_fields,
    )

    assert stripped_fields.isdisjoint(PLAYER_RULE_SCHEME)
    assert stripped_fields.isdisjoint(result.values)
    assert not hasattr(player_rules_offense, "derive_attribute_field_3point")
    assert not hasattr(player_rules_offense, "derive_tendency_stepthrough")
