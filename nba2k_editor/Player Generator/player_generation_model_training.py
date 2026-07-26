from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from player_generation_models import (
    DEFAULT_FREE_THROW_ARTIFACT_PATH,
    FREE_THROW_ARTIFACT_SCHEMA_VERSION,
    FREE_THROW_FIELD_KEY,
    FREE_THROW_RATING_DOMAIN,
    FREE_THROW_RESPONSE_OUTPUT,
    FreeThrowExecutionArtifact,
)
from player_generation_training_data import FreeThrowResponseExample, load_free_throw_response_data

DEFAULT_POOL_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_pool"
    / "player_generation_pool.sqlite"
)


@dataclass
class _IsotonicBlock:
    ratings: list[int]
    made: float
    attempted: float

    @property
    def probability(self) -> float:
        return self.made / self.attempted


def fit_free_throw_curve(
    examples: Iterable[FreeThrowResponseExample],
    *,
    require_full_rating_domain: bool = True,
) -> tuple[tuple[int, float], ...]:
    totals: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for example in examples:
        totals[example.free_throw_rating][0] += example.free_throws_made
        totals[example.free_throw_rating][1] += example.free_throws_attempted
    ratings = tuple(sorted(totals))
    if require_full_rating_domain and ratings != FREE_THROW_RATING_DOMAIN:
        missing = tuple(rating for rating in FREE_THROW_RATING_DOMAIN if rating not in totals)
        raise ValueError(f"Free Throw training data does not cover exact ratings: {missing}")
    if not ratings:
        raise ValueError("Free Throw training data has no attempted free throws")

    blocks: list[_IsotonicBlock] = []
    for rating in ratings:
        made, attempted = totals[rating]
        if attempted <= 0.0:
            raise ValueError(f"Free Throw rating {rating} has no attempts")
        blocks.append(_IsotonicBlock(ratings=[rating], made=made, attempted=attempted))
        while len(blocks) >= 2:
            left = blocks[-2]
            right = blocks[-1]
            if left.probability <= right.probability:
                break
            blocks[-2:] = [
                _IsotonicBlock(
                    ratings=[*left.ratings, *right.ratings],
                    made=left.made + right.made,
                    attempted=left.attempted + right.attempted,
                )
            ]

    fitted: list[tuple[int, float]] = []
    for block in blocks:
        fitted.extend((rating, block.probability) for rating in block.ratings)
    return tuple(fitted)


def _scored_probability(probability: float) -> float:
    return min(max(probability, 1e-12), 1.0 - 1e-12)


def evaluate_free_throw_curve_grouped_by_package(
    examples: Sequence[FreeThrowResponseExample],
    *,
    fold_count: int = 5,
) -> dict[str, float | int]:
    if fold_count < 2:
        raise ValueError("Free Throw evaluation requires at least 2 folds")
    packages_by_rating: dict[int, list[FreeThrowResponseExample]] = defaultdict(list)
    for example in examples:
        packages_by_rating[example.free_throw_rating].append(example)
    package_fold: dict[tuple[str, int], int] = {}
    for rating, rating_examples in sorted(packages_by_rating.items()):
        for index, example in enumerate(sorted(rating_examples, key=lambda row: (row.run_id, row.player_index))):
            package_key = (example.run_id, example.player_index)
            if package_key in package_fold:
                raise ValueError(f"Duplicate Free Throw evaluation package: {package_key!r}")
            package_fold[package_key] = (index + rating) % fold_count
    if fold_count > len(package_fold):
        raise ValueError("Free Throw evaluation cannot have more folds than packages")

    held_out_packages = 0
    held_out_attempts = 0.0
    unsupported_packages = 0
    unsupported_attempts = 0.0
    weighted_absolute_error = 0.0
    negative_log_likelihood = 0.0
    baseline_negative_log_likelihood = 0.0
    fold_package_counts: list[int] = []
    for fold in range(fold_count):
        training = tuple(example for example in examples if package_fold[(example.run_id, example.player_index)] != fold)
        holdout = tuple(example for example in examples if package_fold[(example.run_id, example.player_index)] == fold)
        fold_package_counts.append(len(holdout))
        curve = dict(fit_free_throw_curve(training, require_full_rating_domain=False))
        training_made = sum(example.free_throws_made for example in training)
        training_attempted = sum(example.free_throws_attempted for example in training)
        if training_attempted <= 0.0:
            raise ValueError(f"Free Throw fold {fold} has no training attempts")
        baseline_probability = _scored_probability(training_made / training_attempted)
        for example in holdout:
            probability = curve.get(example.free_throw_rating)
            if probability is None:
                unsupported_packages += 1
                unsupported_attempts += example.free_throws_attempted
                continue
            scored = _scored_probability(probability)
            observed = example.observed_make_probability
            attempts = example.free_throws_attempted
            misses = attempts - example.free_throws_made
            held_out_packages += 1
            held_out_attempts += attempts
            weighted_absolute_error += abs(observed - probability) * attempts
            negative_log_likelihood -= example.free_throws_made * math.log(scored) + misses * math.log(1.0 - scored)
            baseline_negative_log_likelihood -= (
                example.free_throws_made * math.log(baseline_probability)
                + misses * math.log(1.0 - baseline_probability)
            )
    if held_out_attempts <= 0.0:
        raise ValueError("Free Throw package evaluation has no supported held-out attempts")
    model_log_loss = negative_log_likelihood / held_out_attempts
    baseline_log_loss = baseline_negative_log_likelihood / held_out_attempts
    return {
        "fold_count": fold_count,
        "package_count": len(package_fold),
        "run_count": len({example.run_id for example in examples}),
        "fold_package_count_min": min(fold_package_counts),
        "fold_package_count_max": max(fold_package_counts),
        "held_out_packages": held_out_packages,
        "held_out_attempts": held_out_attempts,
        "unsupported_packages": unsupported_packages,
        "unsupported_attempts": unsupported_attempts,
        "attempt_weighted_mae": weighted_absolute_error / held_out_attempts,
        "binomial_log_loss": model_log_loss,
        "global_rate_baseline_log_loss": baseline_log_loss,
        "log_loss_improvement_over_global_rate": baseline_log_loss - model_log_loss,
    }


def build_free_throw_execution_artifact(
    pool_path: str | Path = DEFAULT_POOL_PATH,
    artifact_path: str | Path = DEFAULT_FREE_THROW_ARTIFACT_PATH,
) -> FreeThrowExecutionArtifact:
    loaded = load_free_throw_response_data(pool_path)
    evaluation = evaluate_free_throw_curve_grouped_by_package(loaded.examples)
    curve = fit_free_throw_curve(loaded.examples, require_full_rating_domain=False)
    supported_ratings = {rating for rating, _probability in curve}
    unresolved_ratings = [rating for rating in FREE_THROW_RATING_DOMAIN if rating not in supported_ratings]
    total_made = sum(example.free_throws_made for example in loaded.examples)
    total_attempted = sum(example.free_throws_attempted for example in loaded.examples)
    artifact = FreeThrowExecutionArtifact(
        schema_version=FREE_THROW_ARTIFACT_SCHEMA_VERSION,
        field_key=FREE_THROW_FIELD_KEY,
        response_output=FREE_THROW_RESPONSE_OUTPUT,
        curve=curve,
        pool_fingerprint=loaded.pool_fingerprint,
        training_summary={
            "candidate_packages": loaded.candidate_packages,
            "training_packages": len(loaded.examples),
            "training_runs": len({example.run_id for example in loaded.examples}),
            "free_throws_made": total_made,
            "free_throws_attempted": total_attempted,
            "rating_min": curve[0][0],
            "rating_max": curve[-1][0],
            "rating_count": len(curve),
            "supported_ratings": sorted(supported_ratings),
            "unresolved_ratings": unresolved_ratings,
            "excluded_missing_stats": loaded.excluded_missing_stats,
            "excluded_zero_attempts": loaded.excluded_zero_attempts,
            "excluded_invalid_totals": loaded.excluded_invalid_totals,
            "excluded_invalid_rating": loaded.excluded_invalid_rating,
            "pool_file_hashes": dict(loaded.pool_file_hashes),
            "pool_files_unchanged": loaded.pool_files_unchanged,
            "identity_features": False,
            "tendency_inputs": False,
        },
        evaluation_summary=evaluation,
    )
    artifact.write(artifact_path)
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the offline Free Throw response artifact")
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL_PATH)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_FREE_THROW_ARTIFACT_PATH)
    arguments = parser.parse_args(argv)
    artifact = build_free_throw_execution_artifact(arguments.pool, arguments.artifact)
    payload = {
        "artifact": str(arguments.artifact.resolve()),
        "field_key": artifact.field_key,
        "pool_fingerprint": artifact.pool_fingerprint,
        "training_summary": dict(artifact.training_summary),
        "evaluation_summary": dict(artifact.evaluation_summary),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
