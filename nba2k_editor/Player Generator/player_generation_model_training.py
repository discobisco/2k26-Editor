from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence, TypeVar

import numpy as np  # type: ignore[import-not-found]

from player_generation_models import (
    DEFAULT_FREE_THROW_ARTIFACT_PATH,
    DEFAULT_THREE_POINT_ARTIFACT_PATH,
    DEFAULT_TWO_POINT_ARTIFACT_PATH,
    FREE_THROW_ARTIFACT_SCHEMA_VERSION,
    FREE_THROW_FIELD_KEY,
    FREE_THROW_RATING_DOMAIN,
    FREE_THROW_RESPONSE_OUTPUT,
    THREE_POINT_ARTIFACT_SCHEMA_VERSION,
    THREE_POINT_FEATURE_NAMES,
    THREE_POINT_RUNTIME_FIELDS,
    TWO_POINT_ARTIFACT_SCHEMA_VERSION,
    TWO_POINT_ATTRIBUTE_FIELDS,
    TWO_POINT_FEATURE_NAMES,
    TWO_POINT_FIELD_CONTRACTS,
    TWO_POINT_RUNTIME_FIELDS,
    TWO_POINT_SOURCE_PROFILE_FIELDS,
    TWO_POINT_TENDENCY_FIELDS,
    FreeThrowExecutionArtifact,
    ThreePointShootingArtifact,
    TwoPointShootingArtifact,
    three_point_feature_vector,
    two_point_context_vector,
    two_point_feature_vector,
)
from player_generation_training_data import (
    FreeThrowResponseExample,
    ThreePointResponseExample,
    TwoPointResponseExample,
    load_free_throw_response_data,
    load_three_point_response_data,
    load_two_point_response_data,
)

DEFAULT_POOL_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_pool"
    / "player_generation_pool.sqlite"
)
_ResponseExampleT = TypeVar("_ResponseExampleT")


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
    """Fit attempt-weighted isotonic make probabilities by exact 2K rating."""

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
    """Evaluate deterministic folds while keeping each player package intact."""

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
        training = tuple(
            example
            for example in examples
            if package_fold[(example.run_id, example.player_index)] != fold
        )
        holdout = tuple(
            example
            for example in examples
            if package_fold[(example.run_id, example.player_index)] == fold
        )
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
    """Train, evaluate, and publish only the Free Throw execution slice."""

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


@dataclass(frozen=True)
class _BinomialFit:
    coefficients: tuple[float, ...]
    iterations: int
    converged: bool


def _fit_binomial_logistic_head(
    examples: Sequence[ThreePointResponseExample],
    successes: Callable[[ThreePointResponseExample], float],
    trials: Callable[[ThreePointResponseExample], float],
    *,
    ridge_penalty: float,
    max_iterations: int = 60,
) -> _BinomialFit:
    training = tuple(example for example in examples if trials(example) > 0.0)
    if not training:
        raise ValueError("3PT response head has no packages with positive trial exposure")
    design = np.asarray(
        [three_point_feature_vector(example.field_values) for example in training],
        dtype=float,
    )
    made = np.asarray([successes(example) for example in training], dtype=float)
    attempted = np.asarray([trials(example) for example in training], dtype=float)
    global_probability = float(np.clip(made.sum() / attempted.sum(), 1e-6, 1.0 - 1e-6))
    coefficients = np.zeros(design.shape[1], dtype=float)
    coefficients[0] = math.log(global_probability / (1.0 - global_probability))
    penalty = np.full(design.shape[1], ridge_penalty, dtype=float)
    penalty[0] = 0.0

    def objective(candidate: np.ndarray) -> float:
        scores = np.clip(design @ candidate, -35.0, 35.0)
        probabilities = np.clip(1.0 / (1.0 + np.exp(-scores)), 1e-12, 1.0 - 1e-12)
        misses = attempted - made
        likelihood = -float(np.sum(made * np.log(probabilities) + misses * np.log1p(-probabilities)))
        return likelihood + 0.5 * float(np.sum(penalty * candidate * candidate))

    converged = False
    iterations = 0
    current_objective = objective(coefficients)
    for iterations in range(1, max_iterations + 1):
        scores = np.clip(design @ coefficients, -35.0, 35.0)
        probabilities = 1.0 / (1.0 + np.exp(-scores))
        weights = attempted * probabilities * (1.0 - probabilities)
        gradient = design.T @ (made - attempted * probabilities) - penalty * coefficients
        information = design.T @ (design * weights[:, None]) + np.diag(penalty)
        step = np.linalg.solve(information, gradient)
        step_scale = 1.0
        accepted = False
        while step_scale >= 1.0 / 1024.0:
            candidate = coefficients + step_scale * step
            candidate_objective = objective(candidate)
            if candidate_objective <= current_objective:
                coefficients = candidate
                current_objective = candidate_objective
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            break
        if float(np.max(np.abs(step_scale * step))) < 1e-8:
            converged = True
            break
    return _BinomialFit(
        coefficients=tuple(float(value) for value in coefficients),
        iterations=iterations,
        converged=converged,
    )


def _predict_binomial(coefficients: tuple[float, ...], example: ThreePointResponseExample) -> float:
    score = sum(
        feature * coefficient
        for feature, coefficient in zip(
            three_point_feature_vector(example.field_values), coefficients, strict=True
        )
    )
    return _scored_probability(1.0 / (1.0 + math.exp(-max(min(score, 35.0), -35.0))))


def _binomial_evaluation_summary(
    holdouts: Sequence[tuple[_ResponseExampleT, float]],
    successes: Callable[[_ResponseExampleT], float],
    trials: Callable[[_ResponseExampleT], float],
    baseline_probability: float,
) -> dict[str, float | int]:
    package_count = 0
    exposure = 0.0
    weighted_absolute_error = 0.0
    model_negative_log_likelihood = 0.0
    baseline_negative_log_likelihood = 0.0
    baseline = _scored_probability(baseline_probability)
    for example, prediction in holdouts:
        attempted = trials(example)
        if attempted <= 0.0:
            continue
        made = successes(example)
        observed = made / attempted
        misses = attempted - made
        scored = _scored_probability(prediction)
        package_count += 1
        exposure += attempted
        weighted_absolute_error += abs(observed - scored) * attempted
        model_negative_log_likelihood -= made * math.log(scored) + misses * math.log(1.0 - scored)
        baseline_negative_log_likelihood -= made * math.log(baseline) + misses * math.log(1.0 - baseline)
    return {
        "held_out_packages": package_count,
        "held_out_exposure": exposure,
        "exposure_weighted_mae": weighted_absolute_error / exposure,
        "binomial_log_loss": model_negative_log_likelihood / exposure,
        "global_rate_baseline_log_loss": baseline_negative_log_likelihood / exposure,
        "log_loss_improvement_over_global_rate": (
            baseline_negative_log_likelihood - model_negative_log_likelihood
        )
        / exposure,
    }


def evaluate_three_point_model_grouped_by_package(
    examples: Sequence[ThreePointResponseExample],
    *,
    ridge_penalty: float = 1.0,
    fold_count: int = 5,
) -> dict[str, object]:
    """Evaluate both 3PT response heads while keeping each player package intact."""

    if fold_count < 2 or fold_count > len(examples):
        raise ValueError("3PT evaluation requires 2..number-of-packages folds")
    packages_by_rating: dict[int, list[ThreePointResponseExample]] = defaultdict(list)
    for example in examples:
        packages_by_rating[example.field_values[0]].append(example)
    package_fold: dict[tuple[str, int], int] = {}
    for rating, rating_examples in sorted(packages_by_rating.items()):
        for index, example in enumerate(sorted(rating_examples, key=lambda row: (row.run_id, row.player_index))):
            package_fold[(example.run_id, example.player_index)] = (index + rating) % fold_count

    make_holdouts: list[tuple[ThreePointResponseExample, float]] = []
    share_holdouts: list[tuple[ThreePointResponseExample, float]] = []
    make_baseline_made = 0.0
    make_baseline_attempted = 0.0
    share_baseline_attempted = 0.0
    share_baseline_field_attempted = 0.0
    fold_package_counts: list[int] = []
    for fold in range(fold_count):
        training = tuple(
            example
            for example in examples
            if package_fold[(example.run_id, example.player_index)] != fold
        )
        holdout = tuple(
            example
            for example in examples
            if package_fold[(example.run_id, example.player_index)] == fold
        )
        fold_package_counts.append(len(holdout))
        make_fit = _fit_binomial_logistic_head(
            training,
            lambda example: example.three_pointers_made,
            lambda example: example.three_pointers_attempted,
            ridge_penalty=ridge_penalty,
        )
        share_fit = _fit_binomial_logistic_head(
            training,
            lambda example: example.three_pointers_attempted,
            lambda example: example.field_goals_attempted,
            ridge_penalty=ridge_penalty,
        )
        make_training = tuple(example for example in training if example.three_pointers_attempted > 0.0)
        make_baseline_made += sum(example.three_pointers_made for example in make_training)
        make_baseline_attempted += sum(example.three_pointers_attempted for example in make_training)
        share_baseline_attempted += sum(example.three_pointers_attempted for example in training)
        share_baseline_field_attempted += sum(example.field_goals_attempted for example in training)
        make_holdouts.extend(
            (example, _predict_binomial(make_fit.coefficients, example))
            for example in holdout
            if example.three_pointers_attempted > 0.0
        )
        share_holdouts.extend(
            (example, _predict_binomial(share_fit.coefficients, example))
            for example in holdout
        )
    return {
        "fold_count": fold_count,
        "package_count": len(examples),
        "run_count": len({example.run_id for example in examples}),
        "fold_package_count_min": min(fold_package_counts),
        "fold_package_count_max": max(fold_package_counts),
        "make_probability": _binomial_evaluation_summary(
            make_holdouts,
            lambda example: example.three_pointers_made,
            lambda example: example.three_pointers_attempted,
            make_baseline_made / make_baseline_attempted,
        ),
        "attempt_share": _binomial_evaluation_summary(
            share_holdouts,
            lambda example: example.three_pointers_attempted,
            lambda example: example.field_goals_attempted,
            share_baseline_attempted / share_baseline_field_attempted,
        ),
    }


def build_three_point_shooting_artifact(
    pool_path: str | Path = DEFAULT_POOL_PATH,
    artifact_path: str | Path = DEFAULT_THREE_POINT_ARTIFACT_PATH,
    *,
    ridge_penalty: float = 1.0,
) -> ThreePointShootingArtifact:
    """Train, evaluate, and publish the complete correlated 3PT field group."""

    loaded = load_three_point_response_data(pool_path)
    make_examples = tuple(example for example in loaded.examples if example.three_pointers_attempted > 0.0)
    make_fit = _fit_binomial_logistic_head(
        make_examples,
        lambda example: example.three_pointers_made,
        lambda example: example.three_pointers_attempted,
        ridge_penalty=ridge_penalty,
    )
    share_fit = _fit_binomial_logistic_head(
        loaded.examples,
        lambda example: example.three_pointers_attempted,
        lambda example: example.field_goals_attempted,
        ridge_penalty=ridge_penalty,
    )
    evaluation = evaluate_three_point_model_grouped_by_package(
        loaded.examples,
        ridge_penalty=ridge_penalty,
    )
    artifact = ThreePointShootingArtifact(
        schema_version=THREE_POINT_ARTIFACT_SCHEMA_VERSION,
        field_keys=THREE_POINT_RUNTIME_FIELDS,
        feature_names=THREE_POINT_FEATURE_NAMES,
        make_probability_coefficients=make_fit.coefficients,
        attempt_share_coefficients=share_fit.coefficients,
        ridge_penalty=ridge_penalty,
        pool_fingerprint=loaded.pool_fingerprint,
        training_summary={
            "candidate_packages": loaded.candidate_packages,
            "attempt_share_packages": len(loaded.examples),
            "make_probability_packages": len(make_examples),
            "training_runs": len({example.run_id for example in loaded.examples}),
            "three_pointers_made": sum(example.three_pointers_made for example in loaded.examples),
            "three_pointers_attempted": sum(example.three_pointers_attempted for example in loaded.examples),
            "field_goals_attempted": sum(example.field_goals_attempted for example in loaded.examples),
            "input_field_count": len(THREE_POINT_RUNTIME_FIELDS),
            "attribute_field_count": 1,
            "tendency_field_count": len(THREE_POINT_RUNTIME_FIELDS) - 1,
            "make_head_iterations": make_fit.iterations,
            "make_head_converged": make_fit.converged,
            "attempt_share_head_iterations": share_fit.iterations,
            "attempt_share_head_converged": share_fit.converged,
            "excluded_missing_input_fields": loaded.excluded_missing_input_fields,
            "excluded_invalid_input_values": loaded.excluded_invalid_input_values,
            "excluded_missing_stats": loaded.excluded_missing_stats,
            "excluded_zero_field_goal_attempts": loaded.excluded_zero_field_goal_attempts,
            "excluded_invalid_totals": loaded.excluded_invalid_totals,
            "pool_file_hashes": dict(loaded.pool_file_hashes),
            "pool_files_unchanged": loaded.pool_files_unchanged,
            "identity_features": False,
            "master_stat_inputs": False,
        },
        evaluation_summary=evaluation,
    )
    artifact.write(artifact_path)
    return artifact


def _two_point_features(example: TwoPointResponseExample) -> tuple[float, ...]:
    context = two_point_context_vector(example.player_context())
    if context is None:
        raise ValueError("complete 2PT training example has invalid player context")
    return two_point_feature_vector(example.field_values, context)


def _fit_two_point_binomial_head(
    examples: Sequence[TwoPointResponseExample],
    *,
    ridge_penalty: float,
    max_iterations: int = 60,
) -> _BinomialFit:
    training = tuple(example for example in examples if example.two_points_attempted > 0.0)
    if not training:
        raise ValueError("2PT efficiency head has no attempted shots")
    design = np.asarray([_two_point_features(example) for example in training], dtype=float)
    made = np.asarray([example.two_points_made for example in training], dtype=float)
    attempted = np.asarray([example.two_points_attempted for example in training], dtype=float)
    global_probability = float(np.clip(made.sum() / attempted.sum(), 1e-6, 1.0 - 1e-6))
    coefficients = np.zeros(design.shape[1], dtype=float)
    coefficients[0] = math.log(global_probability / (1.0 - global_probability))
    penalty = np.full(design.shape[1], ridge_penalty, dtype=float)
    penalty[0] = 0.0

    def objective(candidate: np.ndarray) -> float:
        scores = np.clip(design @ candidate, -35.0, 35.0)
        probabilities = np.clip(1.0 / (1.0 + np.exp(-scores)), 1e-12, 1.0 - 1e-12)
        misses = attempted - made
        likelihood = -float(np.sum(made * np.log(probabilities) + misses * np.log1p(-probabilities)))
        return likelihood + 0.5 * float(np.sum(penalty * candidate * candidate))

    converged = False
    iterations = 0
    current_objective = objective(coefficients)
    for iterations in range(1, max_iterations + 1):
        scores = np.clip(design @ coefficients, -35.0, 35.0)
        probabilities = 1.0 / (1.0 + np.exp(-scores))
        weights = attempted * probabilities * (1.0 - probabilities)
        gradient = design.T @ (made - attempted * probabilities) - penalty * coefficients
        information = design.T @ (design * weights[:, None]) + np.diag(penalty)
        step = np.linalg.solve(information, gradient)
        step_scale = 1.0
        accepted = False
        while step_scale >= 1.0 / 1024.0:
            candidate = coefficients + step_scale * step
            candidate_objective = objective(candidate)
            if candidate_objective <= current_objective:
                coefficients = candidate
                current_objective = candidate_objective
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            break
        if float(np.max(np.abs(step_scale * step))) < 1e-8:
            converged = True
            break
    return _BinomialFit(tuple(float(value) for value in coefficients), iterations, converged)


def _fit_two_point_poisson_rate_head(
    examples: Sequence[TwoPointResponseExample],
    *,
    ridge_penalty: float,
    max_iterations: int = 60,
) -> _BinomialFit:
    training = tuple(example for example in examples if example.minutes > 0.0)
    if not training:
        raise ValueError("2PT attempt-rate head has no positive-minute observations")
    design = np.asarray([_two_point_features(example) for example in training], dtype=float)
    counts = np.asarray([example.two_points_attempted for example in training], dtype=float)
    exposures = np.asarray([example.minutes / 36.0 for example in training], dtype=float)
    global_rate = float(np.clip(counts.sum() / exposures.sum(), 1e-9, None))
    coefficients = np.zeros(design.shape[1], dtype=float)
    coefficients[0] = math.log(global_rate)
    penalty = np.full(design.shape[1], ridge_penalty, dtype=float)
    penalty[0] = 0.0

    def objective(candidate: np.ndarray) -> float:
        scores = np.clip(design @ candidate, -35.0, 35.0)
        expected = exposures * np.exp(scores)
        likelihood = float(np.sum(expected - counts * scores))
        return likelihood + 0.5 * float(np.sum(penalty * candidate * candidate))

    converged = False
    iterations = 0
    current_objective = objective(coefficients)
    for iterations in range(1, max_iterations + 1):
        scores = np.clip(design @ coefficients, -35.0, 35.0)
        expected = exposures * np.exp(scores)
        gradient = design.T @ (counts - expected) - penalty * coefficients
        information = design.T @ (design * expected[:, None]) + np.diag(penalty)
        step = np.linalg.solve(information, gradient)
        step_scale = 1.0
        accepted = False
        while step_scale >= 1.0 / 1024.0:
            candidate = coefficients + step_scale * step
            candidate_objective = objective(candidate)
            if candidate_objective <= current_objective:
                coefficients = candidate
                current_objective = candidate_objective
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            break
        if float(np.max(np.abs(step_scale * step))) < 1e-8:
            converged = True
            break
    return _BinomialFit(tuple(float(value) for value in coefficients), iterations, converged)


def _predict_two_point_binomial(coefficients: tuple[float, ...], example: TwoPointResponseExample) -> float:
    score = sum(
        feature * coefficient
        for feature, coefficient in zip(_two_point_features(example), coefficients, strict=True)
    )
    return _scored_probability(1.0 / (1.0 + math.exp(-max(min(score, 35.0), -35.0))))


def _predict_two_point_rate(coefficients: tuple[float, ...], example: TwoPointResponseExample) -> float:
    score = sum(
        feature * coefficient
        for feature, coefficient in zip(_two_point_features(example), coefficients, strict=True)
    )
    return math.exp(max(min(score, 35.0), -35.0))


def _poisson_rate_evaluation_summary(
    holdouts: Sequence[tuple[TwoPointResponseExample, float, float]],
) -> dict[str, float | int]:
    exposure = 0.0
    minutes = 0.0
    attempts = 0.0
    weighted_absolute_error = 0.0
    model_negative_log_likelihood = 0.0
    baseline_negative_log_likelihood = 0.0
    for example, prediction, baseline_rate in holdouts:
        observation_exposure = example.minutes / 36.0
        observed_rate = example.two_points_attempted / observation_exposure
        model_rate = max(prediction, 1e-12)
        baseline = max(baseline_rate, 1e-12)
        model_expected = observation_exposure * model_rate
        baseline_expected = observation_exposure * baseline
        exposure += observation_exposure
        minutes += example.minutes
        attempts += example.two_points_attempted
        weighted_absolute_error += abs(observed_rate - model_rate) * observation_exposure
        model_negative_log_likelihood += model_expected
        baseline_negative_log_likelihood += baseline_expected
        if example.two_points_attempted > 0.0:
            model_negative_log_likelihood -= example.two_points_attempted * math.log(model_expected)
            baseline_negative_log_likelihood -= example.two_points_attempted * math.log(baseline_expected)
    return {
        "held_out_packages": len(holdouts),
        "held_out_minutes": minutes,
        "held_out_attempts": attempts,
        "exposure_weighted_mae_per_36": weighted_absolute_error / exposure,
        "poisson_nll_without_factorial_constant_per_36_exposure": model_negative_log_likelihood / exposure,
        "global_rate_baseline_nll_without_factorial_constant_per_36_exposure": (
            baseline_negative_log_likelihood / exposure
        ),
        "nll_improvement_over_global_rate": (
            baseline_negative_log_likelihood - model_negative_log_likelihood
        ) / exposure,
    }


def evaluate_two_point_model_grouped_by_package(
    examples: Sequence[TwoPointResponseExample],
    *,
    ridge_penalty: float = 1.0,
    fold_count: int = 5,
) -> dict[str, object]:
    """Evaluate 2PT efficiency and per-36 volume with package-level holdouts."""

    if fold_count < 2 or fold_count > len(examples):
        raise ValueError("2PT evaluation requires 2..number-of-packages folds")
    packages_by_rating: dict[int, list[TwoPointResponseExample]] = defaultdict(list)
    for example in examples:
        packages_by_rating[example.field_values[0]].append(example)
    package_fold: dict[tuple[str, int], int] = {}
    for rating, rating_examples in sorted(packages_by_rating.items()):
        for index, example in enumerate(sorted(rating_examples, key=lambda row: (row.run_id, row.player_index))):
            package_fold[(example.run_id, example.player_index)] = (index + rating) % fold_count

    make_holdouts: list[tuple[TwoPointResponseExample, float]] = []
    rate_holdouts: list[tuple[TwoPointResponseExample, float, float]] = []
    make_baseline_made = 0.0
    make_baseline_attempted = 0.0
    fold_package_counts: list[int] = []
    for fold in range(fold_count):
        training = tuple(
            example for example in examples if package_fold[(example.run_id, example.player_index)] != fold
        )
        holdout = tuple(
            example for example in examples if package_fold[(example.run_id, example.player_index)] == fold
        )
        fold_package_counts.append(len(holdout))
        make_fit = _fit_two_point_binomial_head(training, ridge_penalty=ridge_penalty)
        rate_fit = _fit_two_point_poisson_rate_head(training, ridge_penalty=ridge_penalty)
        make_training = tuple(example for example in training if example.two_points_attempted > 0.0)
        make_baseline_made += sum(example.two_points_made for example in make_training)
        make_baseline_attempted += sum(example.two_points_attempted for example in make_training)
        training_exposure = sum(example.minutes / 36.0 for example in training)
        baseline_rate = sum(example.two_points_attempted for example in training) / training_exposure
        make_holdouts.extend(
            (example, _predict_two_point_binomial(make_fit.coefficients, example))
            for example in holdout
            if example.two_points_attempted > 0.0
        )
        rate_holdouts.extend(
            (example, _predict_two_point_rate(rate_fit.coefficients, example), baseline_rate)
            for example in holdout
        )
    return {
        "fold_count": fold_count,
        "package_count": len(examples),
        "run_count": len({example.run_id for example in examples}),
        "fold_package_count_min": min(fold_package_counts),
        "fold_package_count_max": max(fold_package_counts),
        "make_probability": _binomial_evaluation_summary(
            make_holdouts,
            lambda example: example.two_points_made,
            lambda example: example.two_points_attempted,
            make_baseline_made / make_baseline_attempted,
        ),
        "attempts_per_36": _poisson_rate_evaluation_summary(rate_holdouts),
    }


def _fit_two_point_conditional_inverse(
    examples: Sequence[TwoPointResponseExample],
    make_coefficients: tuple[float, ...],
    rate_coefficients: tuple[float, ...],
) -> tuple[
    tuple[float, ...],
    tuple[float, float],
    tuple[tuple[float, float], ...],
    tuple[tuple[float, float], tuple[float, float]],
]:
    """Fit E[normalized controls | fitted logit efficiency, fitted log rate]."""

    if len(examples) < 3:
        raise ValueError("2PT conditional inverse requires at least three complete packages")
    normalized_fields = np.asarray(
        [
            [
                (value - contract[3]) / (contract[4] - contract[3])
                for value, contract in zip(example.field_values, TWO_POINT_FIELD_CONTRACTS, strict=True)
            ]
            for example in examples
        ],
        dtype=float,
    )
    features = np.asarray([_two_point_features(example) for example in examples], dtype=float)
    response_scores = np.column_stack((
        features @ np.asarray(make_coefficients, dtype=float),
        features @ np.asarray(rate_coefficients, dtype=float),
    ))
    field_means = normalized_fields.mean(axis=0)
    response_means = response_scores.mean(axis=0)
    centered_fields = normalized_fields - field_means
    centered_responses = response_scores - response_means
    response_covariance = centered_responses.T @ centered_responses / (len(examples) - 1)
    if np.linalg.matrix_rank(response_covariance) != 2:
        raise ValueError("2PT fitted response scores do not span both inverse dimensions")
    cross_covariance = centered_fields.T @ centered_responses / (len(examples) - 1)
    conditional_coefficients = cross_covariance @ np.linalg.inv(response_covariance)
    response_bounds = (
        (float(response_scores[:, 0].min()), float(response_scores[:, 0].max())),
        (float(response_scores[:, 1].min()), float(response_scores[:, 1].max())),
    )
    return (
        tuple(float(value) for value in field_means),
        (float(response_means[0]), float(response_means[1])),
        tuple((float(row[0]), float(row[1])) for row in conditional_coefficients),
        response_bounds,
    )


def build_two_point_shooting_artifact(
    pool_path: str | Path = DEFAULT_POOL_PATH,
    artifact_path: str | Path = DEFAULT_TWO_POINT_ARTIFACT_PATH,
    *,
    ridge_penalty: float = 1.0,
) -> TwoPointShootingArtifact:
    """Train, evaluate, and publish the complete correlated 2PT field group."""

    loaded = load_two_point_response_data(pool_path)
    make_examples = tuple(example for example in loaded.examples if example.two_points_attempted > 0.0)
    make_fit = _fit_two_point_binomial_head(make_examples, ridge_penalty=ridge_penalty)
    rate_fit = _fit_two_point_poisson_rate_head(loaded.examples, ridge_penalty=ridge_penalty)
    evaluation = evaluate_two_point_model_grouped_by_package(loaded.examples, ridge_penalty=ridge_penalty)
    (
        inverse_field_means,
        inverse_response_means,
        inverse_response_coefficients,
        inverse_response_score_bounds,
    ) = _fit_two_point_conditional_inverse(
        loaded.examples,
        make_fit.coefficients,
        rate_fit.coefficients,
    )
    artifact = TwoPointShootingArtifact(
        schema_version=TWO_POINT_ARTIFACT_SCHEMA_VERSION,
        field_keys=TWO_POINT_RUNTIME_FIELDS,
        feature_names=TWO_POINT_FEATURE_NAMES,
        make_probability_coefficients=make_fit.coefficients,
        attempts_per_36_coefficients=rate_fit.coefficients,
        inverse_field_means=inverse_field_means,
        inverse_response_means=inverse_response_means,
        inverse_response_coefficients=inverse_response_coefficients,
        inverse_response_score_bounds=inverse_response_score_bounds,
        ridge_penalty=ridge_penalty,
        pool_fingerprint=loaded.pool_fingerprint,
        training_summary={
            "candidate_packages": loaded.candidate_packages,
            "attempt_rate_packages": len(loaded.examples),
            "make_probability_packages": len(make_examples),
            "training_runs": len({example.run_id for example in loaded.examples}),
            "two_points_made": sum(example.two_points_made for example in loaded.examples),
            "two_points_attempted": sum(example.two_points_attempted for example in loaded.examples),
            "minutes": sum(example.minutes for example in loaded.examples),
            "input_field_count": len(TWO_POINT_RUNTIME_FIELDS),
            "attribute_field_count": len(TWO_POINT_ATTRIBUTE_FIELDS),
            "tendency_field_count": len(TWO_POINT_TENDENCY_FIELDS),
            "inverse_method": "master_action_mixture_then_conditional_attribute_solve",
            "inverse_training_packages": len(loaded.examples),
            "inverse_identity_features": False,
            "make_head_iterations": make_fit.iterations,
            "make_head_converged": make_fit.converged,
            "attempt_rate_head_iterations": rate_fit.iterations,
            "attempt_rate_head_converged": rate_fit.converged,
            "excluded_missing_input_fields": loaded.excluded_missing_input_fields,
            "excluded_invalid_input_values": loaded.excluded_invalid_input_values,
            "excluded_missing_stats": loaded.excluded_missing_stats,
            "excluded_missing_stat_values": loaded.excluded_missing_stat_values,
            "excluded_missing_context": loaded.excluded_missing_context,
            "excluded_invalid_context": loaded.excluded_invalid_context,
            "excluded_nonpositive_minutes": loaded.excluded_nonpositive_minutes,
            "excluded_invalid_totals": loaded.excluded_invalid_totals,
            "pool_file_hashes": dict(loaded.pool_file_hashes),
            "pool_files_unchanged": loaded.pool_files_unchanged,
            "identity_features": False,
            "physical_position_context_features": True,
            "physical_position_direct_response_terms": False,
            "master_stat_inputs": False,
            "runtime_master_source_composition": list(TWO_POINT_SOURCE_PROFILE_FIELDS),
        },
        evaluation_summary=evaluation,
    )
    artifact.write(artifact_path)
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build one offline Player Generator response artifact")
    parser.add_argument("--slice", choices=("free_throw", "three_point", "two_point"), default="free_throw")
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL_PATH)
    parser.add_argument("--artifact", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.slice == "two_point":
        artifact_path = arguments.artifact or DEFAULT_TWO_POINT_ARTIFACT_PATH
        two_point_artifact = build_two_point_shooting_artifact(arguments.pool, artifact_path)
        payload = {
            "artifact": str(artifact_path.resolve()),
            "field_keys": list(two_point_artifact.field_keys),
            "pool_fingerprint": two_point_artifact.pool_fingerprint,
            "training_summary": dict(two_point_artifact.training_summary),
            "evaluation_summary": dict(two_point_artifact.evaluation_summary),
        }
    elif arguments.slice == "three_point":
        artifact_path = arguments.artifact or DEFAULT_THREE_POINT_ARTIFACT_PATH
        three_point_artifact = build_three_point_shooting_artifact(arguments.pool, artifact_path)
        payload = {
            "artifact": str(artifact_path.resolve()),
            "field_keys": list(three_point_artifact.field_keys),
            "pool_fingerprint": three_point_artifact.pool_fingerprint,
            "training_summary": dict(three_point_artifact.training_summary),
            "evaluation_summary": dict(three_point_artifact.evaluation_summary),
        }
    else:
        artifact_path = arguments.artifact or DEFAULT_FREE_THROW_ARTIFACT_PATH
        free_throw_artifact = build_free_throw_execution_artifact(arguments.pool, artifact_path)
        payload = {
            "artifact": str(artifact_path.resolve()),
            "field_key": free_throw_artifact.field_key,
            "pool_fingerprint": free_throw_artifact.pool_fingerprint,
            "training_summary": dict(free_throw_artifact.training_summary),
            "evaluation_summary": dict(free_throw_artifact.evaluation_summary),
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
