from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_generation_model_training import (  # type: ignore[import-not-found]
    build_two_point_shooting_artifact,
)
from player_generation_models import (  # type: ignore[import-not-found]
    CLOSE_SHOT_LOCATION_TENDENCY_FIELDS,
    MID_SHOT_LOCATION_TENDENCY_FIELDS,
    THREE_POINT_LOCATION_TENDENCY_FIELDS,
    TWO_POINT_ACTION_ATTRIBUTE_MAP,
    TWO_POINT_ATTRIBUTE_FIELDS,
    TWO_POINT_CONTEXT_FIELDS,
    TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS,
    TWO_POINT_FEATURE_NAMES,
    TWO_POINT_FIELD_CONTRACTS,
    TWO_POINT_RUNTIME_FIELDS,
    TWO_POINT_TENDENCY_FIELDS,
    TWO_POINT_SOURCE_TENDENCY_GROUPS,
    condition_two_point_package_from_source,
    load_two_point_shooting_artifact,
    normalize_shot_location_tendency_percentages,
    two_point_context_vector,
    two_point_feature_vector,
)
from player_generation_training_data import (  # type: ignore[import-not-found]
    TwoPointResponseExample,
    load_two_point_response_data,
)
from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_generator import (  # type: ignore[import-not-found]
    generate_player_proposal,
    two_point_targets_from_evidence,
)
from player_attribute_rank_adjuster import _adjustable_attribute_candidates  # type: ignore[import-not-found]
from player_rules import PLAYER_RULE_SCHEME, derive_player_rule_values  # type: ignore[import-not-found]
from stat_neighbor_framework import PositionSelection  # type: ignore[import-not-found]
import player_rules_mental  # type: ignore[import-not-found]
import player_rules_offense  # type: ignore[import-not-found]
import player_rules_rebounding  # type: ignore[import-not-found]


_LEGACY_TWO_POINT_FIELDS = {
    "Attributes/POSTFADEAWAY",
    "Tendencies/CONTESTEDJUMPERMID",
    "Tendencies/DRIVEPULLUPMID",
    "Tendencies/PUTBACKDUNK",
    "Tendencies/STEPBACKJUMPERMID",
    "Tendencies/CLOSELEFT",
    "Tendencies/CLOSEMIDDLE",
    "Tendencies/CLOSERIGHT",
    "Tendencies/UNDERBASKET",
    "Tendencies/MIDRANGECENTER",
    "Tendencies/MIDRANGELEFT",
    "Tendencies/MIDRANGELEFTCENTER",
    "Tendencies/MIDRANGERIGHT",
    "Tendencies/MIDRANGERIGHTCENTER",
}


def _field_values(player_index: int) -> tuple[int, ...]:
    attributes = tuple(25 + ((player_index * (offset + 5) + offset * 7) % 75) for offset in range(8))
    tendencies = tuple((player_index * (offset + 3) + offset * 11) % 101 for offset in range(39))
    return (*attributes, *tendencies)


def _player_context(player_index: int = 10) -> dict[str, object]:
    return {
        "height_inches": 72 + player_index % 12,
        "weight_pounds": 180 + player_index * 3,
        "position": ("PG", "SG", "SF", "PF", "C")[player_index % 5],
    }


def _create_two_point_pool(path: Path, package_count: int = 24) -> None:
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
        CREATE TABLE candidate_pool (
            run_id TEXT NOT NULL,
            player_index INTEGER NOT NULL,
            height_inches REAL NOT NULL,
            weight_pounds REAL NOT NULL,
            position TEXT NOT NULL
        );
        """
    )
    candidate_rows = []
    context_rows = []
    stat_rows = [
        (
            "same_run",
            "stats",
            json.dumps(
                {
                    "player_index": 0,
                    "Field Goals Made": "65535",
                    "Field Goals Attempted": "65535",
                    "Three Pointers Made": "65535",
                    "Three Pointers Attempted": "65535",
                    "Minutes": "65535",
                }
            ),
        )
    ]
    for player_index in range(package_count):
        position = ("PG", "SG", "SF", "PF", "C")[player_index % 5]
        context_rows.append(("same_run", player_index, 72 + player_index % 12, 180 + player_index * 3, position))
        values = _field_values(player_index)
        for value, (_runtime, field_type, captured_field, _minimum, _maximum) in zip(
            values, TWO_POINT_FIELD_CONTRACTS, strict=True
        ):
            candidate_rows.append(("same_run", player_index, "PG", field_type, captured_field, value))

        two_attempted = 0 if player_index == 0 else 20 + player_index % 10
        three_attempted = 6 + player_index % 7
        make_probability = 0.32 + sum(values[:8]) / (8 * 300.0)
        two_made = round(two_attempted * make_probability)
        three_made = round(three_attempted * 0.35)
        minutes = 0 if player_index == package_count - 1 else 80 + 2 * player_index
        payload = {
            "player_index": player_index,
            "player_label": f"ignored-{player_index}",
            "Field Goals Made": str(two_made + three_made),
            "Field Goals Attempted": str(two_attempted + three_attempted),
            "Three Pointers Made": str(three_made),
            "Three Pointers Attempted": str(three_attempted),
            "Minutes": str(minutes),
        }
        stat_rows.append(("same_run", "stats", json.dumps(payload)))
    connection.executemany("INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)", candidate_rows)
    connection.executemany("INSERT INTO candidate_pool VALUES (?, ?, ?, ?, ?)", context_rows)
    connection.executemany("INSERT INTO pool_export_rows VALUES (?, ?, ?)", stat_rows)
    connection.commit()
    connection.close()


def test_two_point_contract_is_exact_complete_family() -> None:
    assert len(TWO_POINT_RUNTIME_FIELDS) == 47
    assert len(TWO_POINT_ATTRIBUTE_FIELDS) == 8
    assert len(TWO_POINT_TENDENCY_FIELDS) == 39
    assert "Attributes/POSTCONTROL" in TWO_POINT_ATTRIBUTE_FIELDS
    assert "Tendencies/STEPTHROUGH" in TWO_POINT_TENDENCY_FIELDS
    assert "Tendencies/POSTDROPSTEP" in TWO_POINT_TENDENCY_FIELDS
    assert "Tendencies/FROMPOSTSHOT" in TWO_POINT_TENDENCY_FIELDS
    assert all(contract[3:] == (25, 99) for contract in TWO_POINT_FIELD_CONTRACTS[:8])
    assert all(contract[3:] == (0, 100) for contract in TWO_POINT_FIELD_CONTRACTS[8:])
    assert tuple(tendency for tendency, _attributes in TWO_POINT_ACTION_ATTRIBUTE_MAP) == TWO_POINT_TENDENCY_FIELDS
    grouped_tendencies = tuple(
        field for _group, fields in TWO_POINT_SOURCE_TENDENCY_GROUPS for field in fields
    )
    assert len(grouped_tendencies) == len(set(grouped_tendencies)) == len(TWO_POINT_TENDENCY_FIELDS)
    assert set(grouped_tendencies) == set(TWO_POINT_TENDENCY_FIELDS)
    assert len(TWO_POINT_FEATURE_NAMES) == (
        1
        + len(TWO_POINT_TENDENCY_FIELDS)
        + sum(len(attributes) for _tendency, attributes in TWO_POINT_ACTION_ATTRIBUTE_MAP)
        + len(TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS) * len(TWO_POINT_CONTEXT_FIELDS)
    )
    assert not any(attribute in TWO_POINT_FEATURE_NAMES for attribute in TWO_POINT_ATTRIBUTE_FIELDS)


def test_directional_shot_location_groups_are_integer_percentages_out_of_100() -> None:
    assert len(CLOSE_SHOT_LOCATION_TENDENCY_FIELDS) == 3
    assert len(MID_SHOT_LOCATION_TENDENCY_FIELDS) == 5
    assert len(THREE_POINT_LOCATION_TENDENCY_FIELDS) == 5
    raw = {
        **dict(zip(CLOSE_SHOT_LOCATION_TENDENCY_FIELDS, (1, 1, 1), strict=True)),
        **dict(zip(MID_SHOT_LOCATION_TENDENCY_FIELDS, (1, 1, 1, 1, 1), strict=True)),
        **dict(zip(THREE_POINT_LOCATION_TENDENCY_FIELDS, (10, 20, 30, 40, 50), strict=True)),
        "unrelated": 73,
    }

    normalized = normalize_shot_location_tendency_percentages(raw)

    assert [normalized[field] for field in CLOSE_SHOT_LOCATION_TENDENCY_FIELDS] == [34, 33, 33]
    assert [normalized[field] for field in MID_SHOT_LOCATION_TENDENCY_FIELDS] == [20, 20, 20, 20, 20]
    assert [normalized[field] for field in THREE_POINT_LOCATION_TENDENCY_FIELDS] == [7, 13, 20, 27, 33]
    assert all(sum(normalized[field] for field in fields) == 100 for fields in (
        CLOSE_SHOT_LOCATION_TENDENCY_FIELDS,
        MID_SHOT_LOCATION_TENDENCY_FIELDS,
        THREE_POINT_LOCATION_TENDENCY_FIELDS,
    ))
    assert normalized["unrelated"] == 73

    inactive = {field: 0 for field in CLOSE_SHOT_LOCATION_TENDENCY_FIELDS}
    assert normalize_shot_location_tendency_percentages(
        inactive, (CLOSE_SHOT_LOCATION_TENDENCY_FIELDS,)
    ) == inactive


def test_two_point_features_encode_action_probability_times_conditional_effectiveness() -> None:
    values = {
        field: minimum
        for field, _field_type, _captured, minimum, _maximum in TWO_POINT_FIELD_CONTRACTS
    }
    guard = two_point_context_vector({"height_inches": 74, "weight_pounds": 190, "position": "PG"})
    center = two_point_context_vector({"height_inches": 84, "weight_pounds": 275, "position": "C"})
    assert guard is not None and center is not None

    baseline = two_point_feature_vector(tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), guard)
    values["Attributes/CLOSESHOT"] = 99
    attribute_without_action = two_point_feature_vector(
        tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), guard
    )
    assert attribute_without_action == baseline

    values["Tendencies/CLOSESHOT"] = 100
    high_close = two_point_feature_vector(tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), guard)
    values["Attributes/CLOSESHOT"] = 25
    low_close = two_point_feature_vector(tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), guard)
    assert high_close != low_close

    values["Tendencies/CLOSESHOT"] = 0
    guard_without_contextual_action = two_point_feature_vector(
        tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), guard
    )
    center_without_contextual_action = two_point_feature_vector(
        tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), center
    )
    assert guard_without_contextual_action == center_without_contextual_action
    values["Tendencies/STANDINGDUNK"] = 100
    assert two_point_feature_vector(
        tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), guard
    ) != two_point_feature_vector(tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS), center)


def test_two_point_loader_derives_fg_minus_three_and_keeps_zero_attempt_rate_evidence(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    _create_two_point_pool(pool_path)
    before = pool_path.read_bytes()

    loaded = load_two_point_response_data(pool_path)

    assert pool_path.read_bytes() == before
    assert loaded.pool_files_unchanged is True
    assert loaded.candidate_packages == 24
    assert loaded.excluded_nonpositive_minutes == 1
    assert len(loaded.examples) == 23
    assert loaded.examples[0].two_points_made == 0
    assert loaded.examples[0].two_points_attempted == 0
    assert loaded.examples[0].observed_make_probability is None
    assert loaded.examples[0].observed_attempts_per_36 == 0
    assert loaded.examples[1].field_mapping() == dict(
        zip(TWO_POINT_RUNTIME_FIELDS, _field_values(1), strict=True)
    )
    assert loaded.examples[1].player_context() == {
        "height_inches": 73.0,
        "weight_pounds": 183.0,
        "position": "SG",
    }
    assert "player_label" not in TwoPointResponseExample.__dataclass_fields__


def test_two_point_training_publishes_dual_head_self_contained_artifact(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    artifact_path = tmp_path / "two_point.json"
    _create_two_point_pool(pool_path)
    before = pool_path.read_bytes()

    artifact = build_two_point_shooting_artifact(pool_path, artifact_path)
    assert pool_path.read_bytes() == before
    pool_path.unlink()

    loaded = load_two_point_shooting_artifact(artifact_path)
    prediction = loaded.predict(
        dict(zip(TWO_POINT_RUNTIME_FIELDS, _field_values(10), strict=True)),
        _player_context(10),
    )
    unresolved = loaded.predict({TWO_POINT_RUNTIME_FIELDS[0]: 80}, _player_context(10))
    invalid_values = dict(zip(TWO_POINT_RUNTIME_FIELDS, _field_values(10), strict=True))
    invalid_values["Attributes/POSTCONTROL"] = 24
    invalid = loaded.predict(invalid_values, _player_context(10))

    assert artifact.field_keys == TWO_POINT_RUNTIME_FIELDS
    assert artifact.feature_names == TWO_POINT_FEATURE_NAMES
    assert artifact.training_summary["attribute_field_count"] == 8
    assert artifact.training_summary["tendency_field_count"] == 39
    assert artifact.training_summary["attempt_rate_packages"] == 23
    assert artifact.training_summary["make_probability_packages"] == 22
    assert artifact.evaluation_summary["package_count"] == 23
    assert artifact.evaluation_summary["make_probability"]["held_out_packages"] == 22
    assert artifact.evaluation_summary["attempts_per_36"]["held_out_packages"] == 23
    assert len(artifact.inverse_field_means) == 47
    assert len(artifact.inverse_response_coefficients) == 47
    assert all(any(abs(value) > 1e-12 for value in row) for row in artifact.inverse_response_coefficients)
    assert prediction.resolved is True
    assert prediction.make_probability is not None and 0.0 < prediction.make_probability < 1.0
    assert prediction.attempts_per_36 is not None and prediction.attempts_per_36 > 0.0
    assert unresolved.resolved is False
    assert set(unresolved.missing_fields) == set(TWO_POINT_RUNTIME_FIELDS[1:])
    assert invalid.resolved is False
    assert invalid.invalid_fields == ("Attributes/POSTCONTROL",)
    payload = loaded.to_dict()
    assert len(payload["field_contract"]) == 47
    assert payload["output_contract"]["two_points_made"] == "Field Goals Made - Three Pointers Made"
    assert payload["output_contract"]["attempts_per_36"] == "36 * two_points_attempted / Minutes"

    exact_package = dict(zip(TWO_POINT_RUNTIME_FIELDS, _field_values(10), strict=True))
    exact_response = loaded.predict(exact_package, _player_context(10))
    solved = loaded.solve_package(
        exact_response.make_probability,
        exact_response.attempts_per_36,
        player_context=_player_context(10),
    )
    repeated = loaded.solve_package(
        exact_response.make_probability,
        exact_response.attempts_per_36,
        player_context=_player_context(10),
    )
    assert solved.resolved is True
    assert solved.field_values is not None
    assert set(solved.field_values) == set(TWO_POINT_RUNTIME_FIELDS)
    assert solved.field_values["Tendencies/BASKETUNDERSHOT"] == 100
    assert sum(solved.field_values[field] for field in CLOSE_SHOT_LOCATION_TENDENCY_FIELDS) == 100
    assert sum(solved.field_values[field] for field in MID_SHOT_LOCATION_TENDENCY_FIELDS) == 100
    assert repeated.field_values == solved.field_values
    assert loaded.predict(solved.field_values, _player_context(10)).resolved is True
    assert loaded.solve_package(None, exact_response.attempts_per_36, player_context=_player_context(10)).resolved is False
    assert loaded.solve_package(1.1, exact_response.attempts_per_36, player_context=_player_context(10)).resolved is False
    assert "inverse_error_scales" not in payload
    assert "inverse_packages" not in payload
    assert payload["inverse_contract"]["method"].startswith("Master action mixture")


def _evidence(per_game: dict[str, object], *, season: int = 2025) -> PlayerEvidence:
    return PlayerEvidence(
        player_id="fixture",
        season=season,
        team="T",
        identity={"ht_in_in": 78, "wt": 220},
        season_info={"pos": "PF"},
        per_game=per_game,
        totals={},
        per_36={},
        per_100={},
        advanced={},
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


def test_two_point_master_targets_and_correlated_proposal_integration(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    artifact_path = tmp_path / "two_point.json"
    _create_two_point_pool(pool_path)
    artifact = build_two_point_shooting_artifact(pool_path, artifact_path)

    direct = _evidence(
        {
            "lg": "NBA",
            "x2p_percent": 0.55,
            "x2pa_per_game": 12.0,
            "mp_per_game": 36.0,
        }
    )
    targets = two_point_targets_from_evidence(direct)
    assert targets is not None
    assert targets.make_probability == 0.55
    assert targets.attempts_per_36 == 12.0
    assert targets.evidence_keys == (
        "PlayerEvidence.per_game.x2p_percent",
        "PlayerEvidence.per_game.x2pa_per_game",
        "PlayerEvidence.per_game.mp_per_game",
    )

    proposal = generate_player_proposal(direct, two_point_artifact=artifact)
    authored = [candidate for candidate in proposal.field_candidates if candidate.field_key in TWO_POINT_RUNTIME_FIELDS]
    assert len(authored) == 47
    assert {candidate.field_key for candidate in authored} == set(TWO_POINT_RUNTIME_FIELDS)
    assert {candidate.source_rule for candidate in authored} == {"model_two_point_correlated_inverse"}
    assert next(candidate.display_value for candidate in authored if candidate.field_key == "Tendencies/BASKETUNDERSHOT") == 100
    assert sum(candidate.field_key == "Tendencies/STEPTHROUGH" for candidate in authored) == 1
    adjustable_keys = {candidate.field_key for candidate in _adjustable_attribute_candidates(proposal)}
    assert adjustable_keys.isdisjoint(TWO_POINT_ATTRIBUTE_FIELDS)
    boundary = artifact.solve_package(0.0, 1.0, player_context=_player_context(10))
    assert boundary.resolved is True
    assert boundary.boundary_limited_targets == ("make_probability",)

    pre_three = _evidence(
        {
            "lg": "NBA",
            "fg_percent": 0.48,
            "fga_per_game": 10.0,
            "mp_per_game": 30.0,
            "x2p_percent": None,
            "x2pa_per_game": None,
            "x3pa_per_game": None,
        },
        season=1979,
    )
    historical_targets = two_point_targets_from_evidence(pre_three)
    assert historical_targets is not None
    assert historical_targets.make_probability == 0.48
    assert historical_targets.attempts_per_36 == 12.0
    assert "two_point_attempts_equal_field_goal_attempts_no_three_point_rule" in historical_targets.evidence_keys

    unresolved_modern = _evidence(
        {
            "lg": "NBA",
            "fg_percent": 0.48,
            "fga_per_game": 10.0,
            "mp_per_game": 30.0,
            "x2p_percent": None,
            "x2pa_per_game": None,
        }
    )
    assert two_point_targets_from_evidence(unresolved_modern) is None
    unresolved_proposal = generate_player_proposal(unresolved_modern, two_point_artifact=artifact)
    assert not ({candidate.field_key for candidate in unresolved_proposal.field_candidates} & set(TWO_POINT_RUNTIME_FIELDS))

    zero_attempts = _evidence(
        {"lg": "NBA", "x2p_percent": None, "x2pa_per_game": 0.0, "mp_per_game": 10.0}
    )
    assert two_point_targets_from_evidence(zero_attempts) is None


def test_two_point_source_profile_separates_supported_shot_groups(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    artifact_path = tmp_path / "two_point.json"
    _create_two_point_pool(pool_path)
    artifact = build_two_point_shooting_artifact(pool_path, artifact_path)
    base = artifact.solve_package(0.62, 19.6842105263, player_context=_player_context(10))
    conditioned = artifact.solve_package(
        0.62,
        19.6842105263,
        source_shooting={
            "percent_fga_from_x0_3_range": 0.511,
            "percent_fga_from_x3_10_range": 0.195,
            "percent_fga_from_x10_16_range": 0.096,
            "percent_fga_from_x16_3p_range": 0.150,
            "fg_percent_from_x0_3_range": 0.773,
            "fg_percent_from_x3_10_range": 0.428,
            "fg_percent_from_x10_16_range": 0.480,
            "fg_percent_from_x16_3p_range": 0.439,
            "fg_percent_from_x2p_range": 0.620,
            "percent_dunks_of_fga": 0.205,
        },
        player_context=_player_context(10),
    )
    assert base.resolved and base.field_values is not None
    assert conditioned.resolved and conditioned.field_values is not None
    assert sum(conditioned.field_values[field] for field in CLOSE_SHOT_LOCATION_TENDENCY_FIELDS) == 100
    assert sum(conditioned.field_values[field] for field in MID_SHOT_LOCATION_TENDENCY_FIELDS) == 100
    group_masses = {
        name: sum(conditioned.field_values[field] for field in fields)
        for name, fields in TWO_POINT_SOURCE_TENDENCY_GROUPS
    }
    assert group_masses["rim_non_dunk"] == max(group_masses.values())
    assert group_masses["close"] == min(group_masses.values())
    assert len(set(group_masses.values())) == 4
    composition_only = {
        "percent_fga_from_x0_3_range": 0.511,
        "percent_fga_from_x3_10_range": 0.195,
        "percent_fga_from_x10_16_range": 0.096,
        "percent_fga_from_x16_3p_range": 0.150,
        "percent_dunks_of_fga": 0.205,
    }
    guard_values, _guard_fields = condition_two_point_package_from_source(
        base.field_values,
        composition_only,
        context_values=two_point_context_vector({"height_inches": 74, "weight_pounds": 190, "position": "PG"}),
        attempts_per_36_coefficients=artifact.attempts_per_36_coefficients,
    )
    center_values, _center_fields = condition_two_point_package_from_source(
        base.field_values,
        composition_only,
        context_values=two_point_context_vector({"height_inches": 84, "weight_pounds": 275, "position": "C"}),
        attempts_per_36_coefficients=artifact.attempts_per_36_coefficients,
    )
    assert any(
        guard_values[field] != center_values[field]
        for field in TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS
    )
    assert all(
        sum(guard_values[field] for field in fields)
        == sum(center_values[field] for field in fields)
        for _name, fields in TWO_POINT_SOURCE_TENDENCY_GROUPS
    )
    assert set(conditioned.source_conditioning_fields) == {
        "percent_fga_from_x0_3_range",
        "percent_fga_from_x3_10_range",
        "percent_fga_from_x10_16_range",
        "percent_fga_from_x16_3p_range",
        "fg_percent_from_x0_3_range",
        "fg_percent_from_x3_10_range",
        "fg_percent_from_x10_16_range",
        "fg_percent_from_x16_3p_range",
        "fg_percent_from_x2p_range",
        "percent_dunks_of_fga",
    }


def test_old_rule_neighbor_and_hot_zone_paths_do_not_author_two_point_fields() -> None:
    stripped_fields = set(TWO_POINT_RUNTIME_FIELDS) | _LEGACY_TWO_POINT_FIELDS
    evidence = PlayerEvidence(
        player_id="fixture",
        season=2025,
        team="T",
        identity={"ht_in_in": 78, "wt": 220},
        season_info={"pos": "PF"},
        per_game={"x2p_percent": 0.55, "x2pa_per_game": 12.0, "fga_per_game": 18.0},
        totals={},
        per_36={},
        per_100={},
        advanced={},
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
        positions=PositionSelection("PF", None, ("PF",), (("PF", 1.0),)),
        active_field_keys=stripped_fields,
    )

    assert stripped_fields.isdisjoint(PLAYER_RULE_SCHEME)
    assert stripped_fields.isdisjoint(result.values)
    assert not hasattr(player_rules_offense, "derive_attribute_closeshot")
    assert not hasattr(player_rules_offense, "derive_tendency_postdropstep")
    assert not hasattr(player_rules_rebounding, "derive_tendency_putback")
    assert not hasattr(player_rules_mental, "derive_attribute_postfadeaway")
