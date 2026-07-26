from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

FREE_THROW_FIELD_KEY = "Attributes/FREETHROW"
FREE_THROW_RESPONSE_OUTPUT = "free_throw_make_probability"
FREE_THROW_ARTIFACT_SCHEMA_VERSION = 1
FREE_THROW_RATING_DOMAIN = tuple(range(25, 100))

DEFAULT_FREE_THROW_ARTIFACT_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_models"
    / "free_throw_execution_response.json"
)


def _write_json_artifact(path_value: str | Path, payload: Mapping[str, Any]) -> Path:
    path = Path(path_value).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


@dataclass(frozen=True)
class FreeThrowInverseResult:
    resolved: bool
    target_make_probability: float | None
    rating: int | None
    predicted_make_probability: float | None
    absolute_error: float | None
    tied_ratings: tuple[int, ...] = ()
    boundary_limited: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class FreeThrowExecutionArtifact:
    schema_version: int
    field_key: str
    response_output: str
    curve: tuple[tuple[int, float], ...]
    pool_fingerprint: str
    training_summary: Mapping[str, Any]
    evaluation_summary: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != FREE_THROW_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Free Throw artifact schema: {self.schema_version}")
        if self.field_key != FREE_THROW_FIELD_KEY:
            raise ValueError(f"Unexpected Free Throw field key: {self.field_key!r}")
        if self.response_output != FREE_THROW_RESPONSE_OUTPUT:
            raise ValueError(f"Unexpected Free Throw response output: {self.response_output!r}")
        ratings = tuple(rating for rating, _probability in self.curve)
        if not ratings or ratings != tuple(sorted(set(ratings))):
            raise ValueError("Free Throw artifact ratings must be unique and ordered")
        if any(rating not in FREE_THROW_RATING_DOMAIN for rating in ratings):
            raise ValueError("Free Throw artifact ratings must stay inside 25 through 99")
        previous = -1.0
        for rating, probability in self.curve:
            if isinstance(rating, bool) or not isinstance(rating, int):
                raise ValueError("Free Throw ratings must be integers")
            if isinstance(probability, bool) or not math.isfinite(float(probability)):
                raise ValueError(f"Invalid Free Throw probability for rating {rating}")
            numeric_probability = float(probability)
            if not 0.0 <= numeric_probability <= 1.0:
                raise ValueError(f"Free Throw probability outside 0..1 for rating {rating}")
            if numeric_probability < previous:
                raise ValueError("Free Throw response curve must be monotone nondecreasing")
            previous = numeric_probability
        if not str(self.pool_fingerprint).strip():
            raise ValueError("Free Throw artifact requires a Pool fingerprint")

    def predict_make_probability(self, rating: int) -> float:
        if isinstance(rating, bool) or not isinstance(rating, int):
            raise ValueError("Free Throw rating must be an integer from 25 through 99")
        if rating < 25 or rating > 99:
            raise ValueError("Free Throw rating must be an integer from 25 through 99")
        probabilities = dict(self.curve)
        if rating not in probabilities:
            raise ValueError(f"Free Throw response is unresolved for exact rating {rating}")
        return float(probabilities[rating])

    def solve_rating(self, target_make_probability: Any) -> FreeThrowInverseResult:
        try:
            target = float(target_make_probability)
        except (TypeError, ValueError):
            return FreeThrowInverseResult(False, None, None, None, None, reason="missing_or_non_numeric_target")
        if isinstance(target_make_probability, bool) or not math.isfinite(target) or target < 0.0 or target > 1.0:
            return FreeThrowInverseResult(
                False,
                target if math.isfinite(target) else None,
                None,
                None,
                None,
                reason="target_outside_probability_domain",
            )

        scored = tuple((rating, probability, abs(probability - target)) for rating, probability in self.curve)
        best_error = min(error for _rating, _probability, error in scored)
        tied = tuple(
            (rating, probability)
            for rating, probability, error in scored
            if math.isclose(error, best_error, rel_tol=0.0, abs_tol=1e-15)
        )
        tied_midpoint = (tied[0][0] + tied[-1][0]) / 2.0
        rating, probability = min(tied, key=lambda point: (abs(point[0] - tied_midpoint), point[0]))
        return FreeThrowInverseResult(
            True,
            target,
            rating,
            probability,
            abs(probability - target),
            tied_ratings=tuple(point[0] for point in tied),
            boundary_limited=target < self.curve[0][1] or target > self.curve[-1][1],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "technical_readiness": "self-contained runtime inverse author for Attributes/FREETHROW",
            "simulation_evaluation_status": "not run; explicit user approval is required before every game simulation",
            "product_verdict": "Free Throw field author only; other model families remain separate",
            "model_family": "attempt_weighted_isotonic_free_throw_execution",
            "master_stat_inputs": [
                "PlayerEvidence.per_game.ft_percent",
                "PlayerEvidence.per_game.fta_per_game",
            ],
            "runtime_inverse_author": True,
            "field_key": self.field_key,
            "response_output": self.response_output,
            "input_contract": {
                "captured_field": "Offense / Free Throws",
                "runtime_field": self.field_key,
                "rating_domain": [25, 99],
                "supported_ratings": [rating for rating, _probability in self.curve],
                "unresolved_ratings": [
                    rating for rating in FREE_THROW_RATING_DOMAIN if rating not in {point[0] for point in self.curve}
                ],
                "names_are_features": False,
                "tendencies_are_inputs": False,
            },
            "output_contract": {
                "made_stat": "Free Throws Made",
                "attempted_stat": "Free Throws Attempted",
                "probability": self.response_output,
            },
            "curve": [{"rating": rating, "make_probability": probability} for rating, probability in self.curve],
            "pool_fingerprint": self.pool_fingerprint,
            "training_summary": dict(self.training_summary),
            "evaluation_summary": dict(self.evaluation_summary),
        }

    def write(self, artifact_path: str | Path = DEFAULT_FREE_THROW_ARTIFACT_PATH) -> Path:
        return _write_json_artifact(artifact_path, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FreeThrowExecutionArtifact":
        curve_payload = payload.get("curve")
        if not isinstance(curve_payload, list):
            raise ValueError("Free Throw artifact curve must be a list")
        curve_points: list[tuple[int, float]] = []
        for index, point in enumerate(curve_payload):
            if not isinstance(point, Mapping):
                raise ValueError(f"Free Throw artifact curve point {index} must be an object")
            if "rating" not in point or "make_probability" not in point:
                raise ValueError(f"Free Throw artifact curve point {index} is incomplete")
            curve_points.append((int(point["rating"]), float(point["make_probability"])))
        return cls(
            schema_version=int(payload.get("schema_version", 0)),
            field_key=str(payload.get("field_key", "")),
            response_output=str(payload.get("response_output", "")),
            curve=tuple(curve_points),
            pool_fingerprint=str(payload.get("pool_fingerprint", "")),
            training_summary=dict(payload.get("training_summary") or {}),
            evaluation_summary=dict(payload.get("evaluation_summary") or {}),
        )


def load_free_throw_execution_artifact(
    artifact_path: str | Path = DEFAULT_FREE_THROW_ARTIFACT_PATH,
) -> FreeThrowExecutionArtifact:
    path = Path(artifact_path).resolve()
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("Free Throw artifact root must be an object")
    return FreeThrowExecutionArtifact.from_dict(payload)


__all__ = [
    "DEFAULT_FREE_THROW_ARTIFACT_PATH",
    "FREE_THROW_ARTIFACT_SCHEMA_VERSION",
    "FREE_THROW_FIELD_KEY",
    "FREE_THROW_RATING_DOMAIN",
    "FREE_THROW_RESPONSE_OUTPUT",
    "FreeThrowExecutionArtifact",
    "FreeThrowInverseResult",
    "_write_json_artifact",
    "load_free_throw_execution_artifact",
]
