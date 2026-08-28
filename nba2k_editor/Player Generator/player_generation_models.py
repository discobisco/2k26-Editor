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

THREE_POINT_EXACT_FIELD_ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ThreePointExactFieldContract:
    field_key: str
    field_type: str
    capture_field: str
    minimum: int
    maximum: int
    input_stats: tuple[str, ...]


THREE_POINT_EXACT_FIELD_CONTRACTS = (
    ThreePointExactFieldContract("Attributes/3POINT", "Attribute", "Offense / 3pt Shot", 25, 99, ("x3p_pct", "x3pa_per36", "games", "mp_per_game")),
    ThreePointExactFieldContract("Tendencies/CONTESTEDJUMPER3POINT", "Tendency", "Jump Shooting / Contested Jumper 3pt", 0, 100, ("x3pa_per36", "fga_per36", "pts_per36", "fta_per36", "ast_per36", "tov_per36")),
    ThreePointExactFieldContract("Tendencies/DRIVEPULLUP3POINT", "Tendency", "Jump Shooting / Drive Pull Up 3pt", 0, 100, ("x3pa_per36", "fta_per36", "ast_per36", "tov_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTOFFSCREENSHOT", "Tendency", "Jump Shooting / Off Screen Shot 3pt", 0, 100, ("x3pa_per36", "pts_per36", "ast_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTSHOT", "Tendency", "Jump Shooting / Shot 3pt", 0, 100, ("x3pa_per36", "fga_per36", "pts_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTCENTERSHOT", "Tendency", "Jump Shooting / Shot 3pt Center", 0, 100, ("x3pa_per36", "fga_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTLEFTSHOT", "Tendency", "Jump Shooting / Shot 3pt Left", 0, 100, ("x3pa_per36", "fga_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTCENTERLEFTSHOT", "Tendency", "Jump Shooting / Shot 3pt Left Center", 0, 100, ("x3pa_per36", "fga_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTRIGHTSHOT", "Tendency", "Jump Shooting / Shot 3pt Right", 0, 100, ("x3pa_per36", "fga_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTCENTERRIGHTSHOT", "Tendency", "Jump Shooting / Shot 3pt Right Center", 0, 100, ("x3pa_per36", "fga_per36")),
    ThreePointExactFieldContract("Tendencies/3POINTSPOTUPSHOT", "Tendency", "Jump Shooting / Spot Up Shot 3pt", 0, 100, ("x3pa_per36", "pts_per36", "ast_per36")),
    ThreePointExactFieldContract("Tendencies/STEPTHROUGH", "Tendency", "Jump Shooting / Step Through Shot", 0, 100, ("fga_per36", "x3pa_per36", "pts_per36", "fta_per36", "ast_per36", "tov_per36")),
    ThreePointExactFieldContract("Tendencies/STEPBACKJUMPER3POINT", "Tendency", "Jump Shooting / Stepback Jumper 3pt", 0, 100, ("x3pa_per36", "fta_per36", "ast_per36", "tov_per36")),
    ThreePointExactFieldContract("Tendencies/TRANSITIONPULLUP3POINT", "Tendency", "Jump Shooting / Transition Pull Up 3pt", 0, 100, ("x3pa_per36", "pts_per36", "ast_per36", "tov_per36")),
)
THREE_POINT_RUNTIME_FIELDS = tuple(contract.field_key for contract in THREE_POINT_EXACT_FIELD_CONTRACTS)

DEFAULT_FREE_THROW_ARTIFACT_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_models"
    / "free_throw_execution_response.json"
)
DEFAULT_THREE_POINT_EXACT_FIELD_ARTIFACT_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_models"
    / "three_point_exact_field_models.json"
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
    finally:
        temporary_path.unlink(missing_ok=True)
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

    def predict_make_probability(self, rating: int) -> float | None:
        probability = dict(self.curve).get(rating)
        return float(probability) if probability is not None else None

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
        curve_payload = payload.get("curve") or ()
        curve_points: list[tuple[int, float]] = []
        for point in curve_payload:
            if not isinstance(point, Mapping):
                continue
            rating = _finite_number(point.get("rating"))
            probability = _finite_number(point.get("make_probability"))
            if rating is None or probability is None or not rating.is_integer():
                continue
            curve_points.append((int(rating), probability))
        return cls(
            schema_version=int(payload.get("schema_version", 0)),
            field_key=str(payload.get("field_key", "")),
            response_output=str(payload.get("response_output", "")),
            curve=tuple(curve_points),
            pool_fingerprint=str(payload.get("pool_fingerprint", "")),
            training_summary=dict(payload.get("training_summary") or {}),
            evaluation_summary=dict(payload.get("evaluation_summary") or {}),
        )


@dataclass(frozen=True)
class ExactFieldLinearModel:
    field_key: str
    field_type: str
    capture_field: str
    minimum: int
    maximum: int
    input_stats: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    ridge_alpha: float
    training_packages: int
    evaluation: Mapping[str, Any]

    def predict(self, features: Mapping[str, Any]) -> int | None:
        if self.field_key == "Attributes/3POINT":
            attempts = _finite_number(features.get("x3pa_per36"))
            if attempts is not None and attempts <= 0.0:
                return 25
        values: list[float] = []
        for stat in self.input_stats:
            value = _finite_number(features.get(stat))
            if value is None:
                return None
            values.append(value)
        prediction = self.intercept + sum(
            coefficient * ((value - mean) / scale)
            for value, mean, scale, coefficient in zip(values, self.means, self.scales, self.coefficients)
        )
        return max(self.minimum, min(self.maximum, int(round(prediction))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "field_type": self.field_type,
            "capture_field": self.capture_field,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "input_stats": list(self.input_stats),
            "means": list(self.means),
            "scales": list(self.scales),
            "coefficients": list(self.coefficients),
            "intercept": self.intercept,
            "ridge_alpha": self.ridge_alpha,
            "training_packages": self.training_packages,
            "evaluation": dict(self.evaluation),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExactFieldLinearModel":
        return cls(
            field_key=str(payload.get("field_key", "")),
            field_type=str(payload.get("field_type", "")),
            capture_field=str(payload.get("capture_field", "")),
            minimum=int(payload.get("minimum", 0)),
            maximum=int(payload.get("maximum", 0)),
            input_stats=tuple(str(value) for value in payload.get("input_stats", ())),
            means=tuple(float(value) for value in payload.get("means", ())),
            scales=tuple(float(value) for value in payload.get("scales", ())),
            coefficients=tuple(float(value) for value in payload.get("coefficients", ())),
            intercept=float(payload.get("intercept", 0.0)),
            ridge_alpha=float(payload.get("ridge_alpha", 0.0)),
            training_packages=int(payload.get("training_packages", 0)),
            evaluation=dict(payload.get("evaluation") or {}),
        )


@dataclass(frozen=True)
class ThreePointExactFieldArtifact:
    schema_version: int
    models: tuple[ExactFieldLinearModel, ...]
    pool_fingerprint: str
    training_summary: Mapping[str, Any]

    def predict_fields(self, features: Mapping[str, Any]) -> dict[str, int]:
        resolved: dict[str, int] = {}
        for model in self.models:
            value = model.predict(features)
            if value is not None:
                resolved[model.field_key] = value
        return resolved

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "technical_readiness": "self-contained stats-to-exact-field runtime author for the complete 3PT lane",
            "model_family": "independent_standardized_ridge_per_exact_field",
            "learning_direction": "Pool simulation/player statistics -> one exact captured 2K field",
            "identity_features": False,
            "shared_model_state": False,
            "pool_fingerprint": self.pool_fingerprint,
            "training_summary": dict(self.training_summary),
            "models": [model.to_dict() for model in self.models],
        }

    def write(self, artifact_path: str | Path = DEFAULT_THREE_POINT_EXACT_FIELD_ARTIFACT_PATH) -> Path:
        return _write_json_artifact(artifact_path, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ThreePointExactFieldArtifact":
        models_payload = payload.get("models") or ()
        return cls(
            schema_version=int(payload.get("schema_version", 0)),
            models=tuple(ExactFieldLinearModel.from_dict(row) for row in models_payload if isinstance(row, Mapping)),
            pool_fingerprint=str(payload.get("pool_fingerprint", "")),
            training_summary=dict(payload.get("training_summary") or {}),
        )


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_three_point_exact_field_artifact(
    artifact_path: str | Path = DEFAULT_THREE_POINT_EXACT_FIELD_ARTIFACT_PATH,
) -> ThreePointExactFieldArtifact:
    path = Path(artifact_path).resolve()
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    return ThreePointExactFieldArtifact.from_dict(payload if isinstance(payload, Mapping) else {})


def load_free_throw_execution_artifact(
    artifact_path: str | Path = DEFAULT_FREE_THROW_ARTIFACT_PATH,
) -> FreeThrowExecutionArtifact:
    path = Path(artifact_path).resolve()
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    return FreeThrowExecutionArtifact.from_dict(payload if isinstance(payload, Mapping) else {})


__all__ = [
    "DEFAULT_FREE_THROW_ARTIFACT_PATH",
    "DEFAULT_THREE_POINT_EXACT_FIELD_ARTIFACT_PATH",
    "FREE_THROW_ARTIFACT_SCHEMA_VERSION",
    "FREE_THROW_FIELD_KEY",
    "FREE_THROW_RATING_DOMAIN",
    "FREE_THROW_RESPONSE_OUTPUT",
    "THREE_POINT_EXACT_FIELD_ARTIFACT_SCHEMA_VERSION",
    "THREE_POINT_EXACT_FIELD_CONTRACTS",
    "THREE_POINT_RUNTIME_FIELDS",
    "ExactFieldLinearModel",
    "ThreePointExactFieldArtifact",
    "ThreePointExactFieldContract",
    "FreeThrowExecutionArtifact",
    "FreeThrowInverseResult",
    "_write_json_artifact",
    "load_free_throw_execution_artifact",
    "load_three_point_exact_field_artifact",
]
