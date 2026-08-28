from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_generation_model_training import (  # type: ignore[import-not-found]
    evaluate_free_throw_curve_grouped_by_package,
    fit_free_throw_curve,
)
from player_generation_models import (  # type: ignore[import-not-found]
    FREE_THROW_FIELD_KEY,
    FreeThrowExecutionArtifact,
    load_free_throw_execution_artifact,
)
from player_generation_training_data import (  # type: ignore[import-not-found]
    FreeThrowResponseExample,
    _pool_file_hashes,
    load_free_throw_response_data,
)
from player_generator import authored_player_field_index, generate_player_proposal  # type: ignore[import-not-found]
import player_rules_offense  # type: ignore[import-not-found]
from player_evidence import PlayerEvidence  # type: ignore[import-not-found]
from player_rules import PLAYER_RULE_SCHEME, derive_neighbor_rule_values  # type: ignore[import-not-found]
from stat_neighbor_framework import NeighborFieldSuggestion, PositionSelection  # type: ignore[import-not-found]


def _create_pool(path: Path) -> None:
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
    connection.executemany(
        "INSERT INTO candidate_fields VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("run_1", 7, "PG", "Attribute", "Offense / Free Throws", 80),
            ("run_1", 7, "PG", "Tendency", "Tendencies / Shoot", 95),
            ("run_1", 8, "C", "Attribute", "Offense / Free Throws", 60),
            ("run_1", 9, "SG", "Attribute", "Offense / Free Throws", 70),
        ],
    )
    stats_rows = [
        ("run_1", "stats", {"player_index": 7, "player_label": "meaningless old", "Free Throws Made": "1", "Free Throws Attempted": "2"}),
        ("run_1", "stats", {"player_index": 7, "player_label": "meaningless new", "Free Throws Made": "9", "Free Throws Attempted": "10"}),
        ("run_1", "stats", {"player_index": 8, "player_label": "ignored", "Free Throws Made": "0", "Free Throws Attempted": "0"}),
        ("run_1", "stats", {"player_index": 9, "player_label": "ignored", "Free Throws Made": "65535", "Free Throws Attempted": "65535"}),
    ]
    connection.executemany(
        "INSERT INTO pool_export_rows VALUES (?, ?, ?)",
        [(snapshot, row_type, json.dumps(payload)) for snapshot, row_type, payload in stats_rows],
    )
    connection.commit()
    connection.close()


def test_pool_fingerprint_ignores_ephemeral_empty_wal_sidecar(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    pool_path.write_bytes(b"immutable pool fixture")
    without_sidecar = _pool_file_hashes(pool_path)
    Path(f"{pool_path}-wal").write_bytes(b"")

    assert _pool_file_hashes(pool_path) == without_sidecar


def test_free_throw_loader_is_read_only_last_row_wins_and_ignores_names_and_tendencies(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.sqlite"
    _create_pool(pool_path)
    before = pool_path.read_bytes()

    loaded = load_free_throw_response_data(pool_path)

    assert pool_path.read_bytes() == before
    assert loaded.pool_files_unchanged is True
    assert loaded.excluded_zero_attempts == 1
    assert loaded.excluded_invalid_totals == 1
    assert loaded.excluded_missing_stats == 0
    assert loaded.examples == (
        FreeThrowResponseExample(
            run_id="run_1",
            player_index=7,
            free_throw_rating=80,
            free_throws_made=9,
            free_throws_attempted=10,
        ),
    )
    assert "player_label" not in FreeThrowResponseExample.__dataclass_fields__
    assert "tendency" not in FreeThrowResponseExample.__dataclass_fields__


def test_free_throw_curve_uses_attempt_weighted_monotone_pooling() -> None:
    examples = (
        FreeThrowResponseExample("run_1", 1, 25, 4, 10),
        FreeThrowResponseExample("run_1", 2, 26, 3, 10),
        FreeThrowResponseExample("run_2", 3, 27, 6, 10),
    )

    curve = fit_free_throw_curve(examples, require_full_rating_domain=False)

    assert curve == ((25, 0.35), (26, 0.35), (27, 0.6))


def test_free_throw_evaluation_holds_out_distinct_player_packages_not_whole_runs() -> None:
    examples = tuple(
        FreeThrowResponseExample(
            run_id="same_run",
            player_index=index,
            free_throw_rating=31,
            free_throws_made=20 + index,
            free_throws_attempted=100,
        )
        for index in range(10)
    )

    evaluation = evaluate_free_throw_curve_grouped_by_package(examples, fold_count=5)

    assert evaluation["run_count"] == 1
    assert evaluation["package_count"] == 10
    assert evaluation["held_out_packages"] == 10
    assert evaluation["unsupported_packages"] == 0
    assert evaluation["fold_package_count_min"] == 2
    assert evaluation["fold_package_count_max"] == 2


def test_free_throw_artifact_loads_without_pool_and_predicts_only_the_attribute_response(tmp_path: Path) -> None:
    curve = tuple((rating, rating / 100.0) for rating in range(25, 100))
    artifact = FreeThrowExecutionArtifact(
        schema_version=1,
        field_key=FREE_THROW_FIELD_KEY,
        response_output="free_throw_make_probability",
        curve=curve,
        pool_fingerprint="fixture",
        training_summary={"examples": 75},
        evaluation_summary={"held_out_attempts": 1000},
    )
    artifact_path = tmp_path / "free_throw.json"
    artifact.write(artifact_path)

    loaded = load_free_throw_execution_artifact(artifact_path)

    assert loaded.field_key == "Attributes/FREETHROW"
    assert loaded.predict_make_probability(87) == 0.87
    assert loaded.predict_make_probability(99) == 0.99
    assert loaded.to_dict()["technical_readiness"] == "self-contained runtime inverse author for Attributes/FREETHROW"
    assert loaded.to_dict()["master_stat_inputs"] == [
        "PlayerEvidence.per_game.ft_percent",
        "PlayerEvidence.per_game.fta_per_game",
    ]
    assert loaded.to_dict()["runtime_inverse_author"] is True
    assert loaded.predict_make_probability(100) is None


def test_free_throw_artifact_ignores_malformed_curve_members() -> None:
    curve = tuple((rating, rating / 100.0) for rating in range(25, 100))
    artifact = FreeThrowExecutionArtifact(
        schema_version=1,
        field_key=FREE_THROW_FIELD_KEY,
        response_output="free_throw_make_probability",
        curve=curve,
        pool_fingerprint="fixture",
        training_summary={},
        evaluation_summary={},
    )
    payload = artifact.to_dict()
    payload["curve"].append("not a curve point")

    loaded = FreeThrowExecutionArtifact.from_dict(payload)
    assert loaded.curve == curve


def _player_evidence_with_ft_percent(
    ft_percent: float | None,
    *,
    fta_per_game: float | None = None,
) -> PlayerEvidence:
    per_game = {}
    if ft_percent is not None:
        per_game["ft_percent"] = ft_percent
    if fta_per_game is not None:
        per_game["fta_per_game"] = fta_per_game
    return PlayerEvidence(
        player_id="fixture",
        season=2025,
        team="T",
        identity={},
        season_info={"pos": "PG"},
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


def test_old_rule_and_neighbor_paths_do_not_author_free_throw() -> None:
    evidence = _player_evidence_with_ft_percent(0.73)

    class CandidateModel:
        def suggestions_for_evidence(self, **_kwargs: object) -> dict[str, NeighborFieldSuggestion]:
            return {
                FREE_THROW_FIELD_KEY: NeighborFieldSuggestion(
                    field_key=FREE_THROW_FIELD_KEY,
                    value=73,
                    source_rule="candidate_neighbor",
                    evidence_keys=("candidate",),
                )
            }

    assert FREE_THROW_FIELD_KEY not in PLAYER_RULE_SCHEME
    assert not hasattr(player_rules_offense, "derive_attribute_freethrow")
    assert FREE_THROW_FIELD_KEY not in derive_neighbor_rule_values(
        evidence,
        PositionSelection("PG", None, ("PG",), (("PG", 1.0),)),
        model=CandidateModel(),
    )


def test_free_throw_inverse_solves_only_from_the_forward_curve() -> None:
    artifact = FreeThrowExecutionArtifact(
        schema_version=1,
        field_key=FREE_THROW_FIELD_KEY,
        response_output="free_throw_make_probability",
        curve=((25, 0.20), (26, 0.25), (27, 0.25), (28, 0.40), (99, 0.98)),
        pool_fingerprint="fixture",
        training_summary={},
        evaluation_summary={},
    )

    plateau = artifact.solve_rating(0.25)
    assert plateau.resolved is True
    assert plateau.rating == 26
    assert plateau.tied_ratings == (26, 27)
    assert plateau.absolute_error == 0.0
    boundary = artifact.solve_rating(1.0)
    assert boundary.rating == 99
    assert boundary.boundary_limited is True
    assert artifact.solve_rating(None).reason == "missing_or_non_numeric_target"
    assert artifact.solve_rating(1.1).reason == "target_outside_probability_domain"


def test_player_proposal_authors_free_throw_only_through_the_new_model_path() -> None:
    artifact = FreeThrowExecutionArtifact(
        schema_version=1,
        field_key=FREE_THROW_FIELD_KEY,
        response_output="free_throw_make_probability",
        curve=tuple((rating, rating / 100.0) for rating in range(25, 100)),
        pool_fingerprint="fixture",
        training_summary={},
        evaluation_summary={},
    )
    evidence = _player_evidence_with_ft_percent(0.73)

    proposal = generate_player_proposal(
        evidence,
        field_index=authored_player_field_index(),
        free_throw_artifact=artifact,
    )
    candidate = proposal.by_field_key()[FREE_THROW_FIELD_KEY]

    assert candidate.display_value == 73
    assert candidate.source_rule == "model_free_throw_inverse"
    assert "PlayerEvidence.per_game.ft_percent" in candidate.evidence_keys


def test_player_proposal_omits_free_throw_without_master_target() -> None:
    artifact = FreeThrowExecutionArtifact(
        schema_version=1,
        field_key=FREE_THROW_FIELD_KEY,
        response_output="free_throw_make_probability",
        curve=tuple((rating, rating / 100.0) for rating in range(25, 100)),
        pool_fingerprint="fixture",
        training_summary={},
        evaluation_summary={},
    )

    proposal = generate_player_proposal(
        _player_evidence_with_ft_percent(None),
        field_index=authored_player_field_index(),
        free_throw_artifact=artifact,
    )

    assert FREE_THROW_FIELD_KEY not in proposal.by_field_key()


def test_zero_free_throw_attempts_mean_zero_target_not_missing_target() -> None:
    artifact = FreeThrowExecutionArtifact(
        schema_version=1,
        field_key=FREE_THROW_FIELD_KEY,
        response_output="free_throw_make_probability",
        curve=tuple((rating, rating / 100.0) for rating in range(25, 100)),
        pool_fingerprint="fixture",
        training_summary={},
        evaluation_summary={},
    )

    proposal = generate_player_proposal(
        _player_evidence_with_ft_percent(None, fta_per_game=0.0),
        field_index=authored_player_field_index(),
        free_throw_artifact=artifact,
    )
    candidate = proposal.by_field_key()[FREE_THROW_FIELD_KEY]

    assert candidate.display_value == 25
    assert "zero_attempt_free_throw_target=0" in candidate.evidence_keys
    assert "target_make_probability=0" in candidate.evidence_keys


def test_free_throw_artifact_does_not_interpolate_an_unresolved_exact_rating() -> None:
    curve = tuple((rating, rating / 100.0) for rating in range(25, 100) if rating != 31)
    artifact = FreeThrowExecutionArtifact(
        schema_version=1,
        field_key=FREE_THROW_FIELD_KEY,
        response_output="free_throw_make_probability",
        curve=curve,
        pool_fingerprint="fixture",
        training_summary={"unresolved_ratings": [31]},
        evaluation_summary={},
    )

    assert artifact.predict_make_probability(31) is None
