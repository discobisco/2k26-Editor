from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

FREE_THROW_FIELD_KEY = "Attributes/FREETHROW"
FREE_THROW_RESPONSE_OUTPUT = "free_throw_make_probability"
FREE_THROW_ARTIFACT_SCHEMA_VERSION = 1
FREE_THROW_RATING_DOMAIN = tuple(range(25, 100))
THREE_POINT_ARTIFACT_SCHEMA_VERSION = 1
THREE_POINT_FIELD_CONTRACTS: tuple[tuple[str, str, str, int, int], ...] = (
    ("Attributes/3POINT", "Attribute", "Offense / 3pt Shot", 25, 99),
    (
        "Tendencies/CONTESTEDJUMPER3POINT",
        "Tendency",
        "Jump Shooting / Contested Jumper 3pt",
        0,
        100,
    ),
    (
        "Tendencies/DRIVEPULLUP3POINT",
        "Tendency",
        "Jump Shooting / Drive Pull Up 3pt",
        0,
        100,
    ),
    (
        "Tendencies/3POINTOFFSCREENSHOT",
        "Tendency",
        "Jump Shooting / Off Screen Shot 3pt",
        0,
        100,
    ),
    ("Tendencies/3POINTSHOT", "Tendency", "Jump Shooting / Shot 3pt", 0, 100),
    (
        "Tendencies/3POINTCENTERSHOT",
        "Tendency",
        "Jump Shooting / Shot 3pt Center",
        0,
        100,
    ),
    (
        "Tendencies/3POINTLEFTSHOT",
        "Tendency",
        "Jump Shooting / Shot 3pt Left",
        0,
        100,
    ),
    (
        "Tendencies/3POINTCENTERLEFTSHOT",
        "Tendency",
        "Jump Shooting / Shot 3pt Left Center",
        0,
        100,
    ),
    (
        "Tendencies/3POINTRIGHTSHOT",
        "Tendency",
        "Jump Shooting / Shot 3pt Right",
        0,
        100,
    ),
    (
        "Tendencies/3POINTCENTERRIGHTSHOT",
        "Tendency",
        "Jump Shooting / Shot 3pt Right Center",
        0,
        100,
    ),
    (
        "Tendencies/3POINTSPOTUPSHOT",
        "Tendency",
        "Jump Shooting / Spot Up Shot 3pt",
        0,
        100,
    ),
    ("Tendencies/STEPTHROUGH", "Tendency", "Jump Shooting / Step Through Shot", 0, 100),
    (
        "Tendencies/STEPBACKJUMPER3POINT",
        "Tendency",
        "Jump Shooting / Stepback Jumper 3pt",
        0,
        100,
    ),
    (
        "Tendencies/TRANSITIONPULLUP3POINT",
        "Tendency",
        "Jump Shooting / Transition Pull Up 3pt",
        0,
        100,
    ),
)
THREE_POINT_RUNTIME_FIELDS = tuple(contract[0] for contract in THREE_POINT_FIELD_CONTRACTS)
THREE_POINT_CAPTURE_FIELDS = tuple(contract[2] for contract in THREE_POINT_FIELD_CONTRACTS)
THREE_POINT_LOCATION_TENDENCY_FIELDS = (
    "Tendencies/3POINTCENTERSHOT",
    "Tendencies/3POINTLEFTSHOT",
    "Tendencies/3POINTCENTERLEFTSHOT",
    "Tendencies/3POINTRIGHTSHOT",
    "Tendencies/3POINTCENTERRIGHTSHOT",
)
THREE_POINT_FEATURE_NAMES = (
    "intercept",
    *THREE_POINT_RUNTIME_FIELDS,
    *(
        f"Attributes/3POINT*{field_key}"
        for field_key in THREE_POINT_RUNTIME_FIELDS
        if field_key.startswith("Tendencies/")
    ),
)
TWO_POINT_ARTIFACT_SCHEMA_VERSION = 3
TWO_POINT_FIELD_CONTRACTS: tuple[tuple[str, str, str, int, int], ...] = (
    ("Attributes/CLOSESHOT", "Attribute", "Offense / Close Shot", 25, 99),
    ("Attributes/MIDRANGE", "Attribute", "Offense / Midrange Shot", 25, 99),
    ("Attributes/DRIVINGLAYUP", "Attribute", "Offense / Driving Layup", 25, 99),
    ("Attributes/DRIVINGDUNK", "Attribute", "Offense / Driving Dunk", 25, 99),
    ("Attributes/STANDINGDUNK", "Attribute", "Offense / Standing Dunk", 25, 99),
    ("Attributes/POSTFADE", "Attribute", "Offense / Post Fade", 25, 99),
    ("Attributes/POSTHOOK", "Attribute", "Offense / Post Hook", 25, 99),
    ("Attributes/POSTCONTROL", "Attribute", "Offense / Post Moves", 25, 99),
    ("Tendencies/BASKETUNDERSHOT", "Tendency", "Jump Shooting / Shot Under Basket", 0, 100),
    ("Tendencies/CLOSESHOT", "Tendency", "Jump Shooting / Shot Close", 0, 100),
    ("Tendencies/CLOSELEFTSHOT", "Tendency", "Jump Shooting / Shot Close Left", 0, 100),
    ("Tendencies/CLOSEMIDDLESHOT", "Tendency", "Jump Shooting / Shot Close Middle", 0, 100),
    ("Tendencies/CLOSERIGHTSHOT", "Tendency", "Jump Shooting / Shot Close Right", 0, 100),
    ("Tendencies/MIDSHOT", "Tendency", "Jump Shooting / Shot Mid", 0, 100),
    ("Tendencies/CENTERMIDSHOT", "Tendency", "Jump Shooting / Shot Mid Center", 0, 100),
    ("Tendencies/LEFTMIDSHOT", "Tendency", "Jump Shooting / Shot Mid Left", 0, 100),
    ("Tendencies/CENTERLEFTMIDSHOT", "Tendency", "Jump Shooting / Shot Mid Left Center", 0, 100),
    ("Tendencies/MIDRIGHTSHOT", "Tendency", "Jump Shooting / Shot Mid Right", 0, 100),
    ("Tendencies/CENTERMIDRIGHTSHOT", "Tendency", "Jump Shooting / Shot Mid Right Center", 0, 100),
    (
        "Tendencies/CONTESTEDJUMPERMIDRANGE",
        "Tendency",
        "Jump Shooting / Contested Jumper Mid-Range",
        0,
        100,
    ),
    (
        "Tendencies/DRIVEPULLUPMIDRANGE",
        "Tendency",
        "Jump Shooting / Drive Pull Up Mid-Range",
        0,
        100,
    ),
    ("Tendencies/MIDOFFSCREENSHOT", "Tendency", "Jump Shooting / Off Screen Shot Mid", 0, 100),
    ("Tendencies/SPINJUMPER", "Tendency", "Jump Shooting / Spin Jumper Tendency", 0, 100),
    ("Tendencies/MIDSPOTUPSHOT", "Tendency", "Jump Shooting / Spot Up Shot Mid", 0, 100),
    ("Tendencies/STEPTHROUGH", "Tendency", "Jump Shooting / Step Through Shot", 0, 100),
    (
        "Tendencies/STEPBACKJUMPERMIDRANGE",
        "Tendency",
        "Jump Shooting / Stepback Jumper Mid-Range",
        0,
        100,
    ),
    ("Tendencies/USEGLASS", "Tendency", "Jump Shooting / Use Glass", 0, 100),
    ("Tendencies/ALLEYOOP", "Tendency", "Layups And Dunks / Alley-Oop", 0, 100),
    ("Tendencies/DRIVINGDUNK", "Tendency", "Layups And Dunks / Driving Dunk Tendency", 0, 100),
    ("Tendencies/DRIVINGLAYUP", "Tendency", "Layups And Dunks / Driving Layup Tendency", 0, 100),
    ("Tendencies/EUROSTEPLAYUP", "Tendency", "Layups And Dunks / Euro Step Layup", 0, 100),
    ("Tendencies/FLASHYDUNK", "Tendency", "Layups And Dunks / Flashy Dunk", 0, 100),
    ("Tendencies/FLOATER", "Tendency", "Layups And Dunks / Floater", 0, 100),
    ("Tendencies/HOPSTEPLAYUP", "Tendency", "Layups And Dunks / Hop Step Layup", 0, 100),
    ("Tendencies/PUTBACK", "Tendency", "Layups And Dunks / Putback", 0, 100),
    ("Tendencies/SPINLAYUP", "Tendency", "Layups And Dunks / Spin Layup", 0, 100),
    (
        "Tendencies/STANDINGDUNK",
        "Tendency",
        "Layups And Dunks / Standing Dunk Tendency",
        0,
        100,
    ),
    ("Tendencies/POSTDROPSTEP", "Tendency", "Post Game / Post Drop Step", 0, 100),
    ("Tendencies/POSTFADELEFT", "Tendency", "Post Game / Post Fade Left", 0, 100),
    ("Tendencies/POSTFADERIGHT", "Tendency", "Post Game / Post Fade Right", 0, 100),
    ("Tendencies/POSTHOOKLEFT", "Tendency", "Post Game / Post Hook Left", 0, 100),
    ("Tendencies/POSTHOOKRIGHT", "Tendency", "Post Game / Post Hook Right", 0, 100),
    ("Tendencies/HOPPOSTSHOT", "Tendency", "Post Game / Post Hop Shot Tendency", 0, 100),
    ("Tendencies/POSTSHIMMYSHOT", "Tendency", "Post Game / Post Shimmy Shot", 0, 100),
    ("Tendencies/POSTSTEPBACKSHOT", "Tendency", "Post Game / Post Step Back Shot", 0, 100),
    ("Tendencies/POSTUPANDUNDER", "Tendency", "Post Game / Post Up And Under", 0, 100),
    ("Tendencies/FROMPOSTSHOT", "Tendency", "Post Game / Shoot From Post", 0, 100),
)
TWO_POINT_RUNTIME_FIELDS = tuple(contract[0] for contract in TWO_POINT_FIELD_CONTRACTS)
TWO_POINT_CAPTURE_FIELDS = tuple(contract[2] for contract in TWO_POINT_FIELD_CONTRACTS)
TWO_POINT_ATTRIBUTE_FIELDS = tuple(
    contract[0] for contract in TWO_POINT_FIELD_CONTRACTS if contract[1] == "Attribute"
)
TWO_POINT_TENDENCY_FIELDS = tuple(
    contract[0] for contract in TWO_POINT_FIELD_CONTRACTS if contract[1] == "Tendency"
)
CLOSE_SHOT_LOCATION_TENDENCY_FIELDS = (
    "Tendencies/CLOSELEFTSHOT",
    "Tendencies/CLOSEMIDDLESHOT",
    "Tendencies/CLOSERIGHTSHOT",
)
MID_SHOT_LOCATION_TENDENCY_FIELDS = (
    "Tendencies/CENTERMIDSHOT",
    "Tendencies/LEFTMIDSHOT",
    "Tendencies/CENTERLEFTMIDSHOT",
    "Tendencies/MIDRIGHTSHOT",
    "Tendencies/CENTERMIDRIGHTSHOT",
)
SHOT_LOCATION_TENDENCY_GROUPS = (
    CLOSE_SHOT_LOCATION_TENDENCY_FIELDS,
    MID_SHOT_LOCATION_TENDENCY_FIELDS,
    THREE_POINT_LOCATION_TENDENCY_FIELDS,
)
TWO_POINT_CONTEXT_FIELDS = (
    "height_inches",
    "weight_pounds",
    "position_PG",
    "position_SG",
    "position_SF",
    "position_PF",
    "position_C",
)
# Explicit action contract. A 0..100 Tendency is the chance/frequency of selecting
# that action; Attributes enter the fitted response only through the action(s)
# whose execution they govern. POSTCONTROL is enabling context for post actions,
# not a hook/fade make percentage of its own.
TWO_POINT_ACTION_ATTRIBUTE_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tendencies/BASKETUNDERSHOT", ("Attributes/CLOSESHOT",)),
    ("Tendencies/CLOSESHOT", ("Attributes/CLOSESHOT",)),
    ("Tendencies/CLOSELEFTSHOT", ("Attributes/CLOSESHOT",)),
    ("Tendencies/CLOSEMIDDLESHOT", ("Attributes/CLOSESHOT",)),
    ("Tendencies/CLOSERIGHTSHOT", ("Attributes/CLOSESHOT",)),
    ("Tendencies/MIDSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/CENTERMIDSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/LEFTMIDSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/CENTERLEFTMIDSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/MIDRIGHTSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/CENTERMIDRIGHTSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/CONTESTEDJUMPERMIDRANGE", ("Attributes/MIDRANGE",)),
    ("Tendencies/DRIVEPULLUPMIDRANGE", ("Attributes/MIDRANGE",)),
    ("Tendencies/MIDOFFSCREENSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/SPINJUMPER", ("Attributes/MIDRANGE",)),
    ("Tendencies/MIDSPOTUPSHOT", ("Attributes/MIDRANGE",)),
    ("Tendencies/STEPTHROUGH", ("Attributes/MIDRANGE",)),
    ("Tendencies/STEPBACKJUMPERMIDRANGE", ("Attributes/MIDRANGE",)),
    ("Tendencies/USEGLASS", ("Attributes/DRIVINGLAYUP",)),
    ("Tendencies/ALLEYOOP", ("Attributes/DRIVINGDUNK",)),
    ("Tendencies/DRIVINGDUNK", ("Attributes/DRIVINGDUNK",)),
    ("Tendencies/DRIVINGLAYUP", ("Attributes/DRIVINGLAYUP",)),
    ("Tendencies/EUROSTEPLAYUP", ("Attributes/DRIVINGLAYUP",)),
    ("Tendencies/FLASHYDUNK", ("Attributes/DRIVINGDUNK",)),
    ("Tendencies/FLOATER", ("Attributes/DRIVINGLAYUP", "Attributes/CLOSESHOT")),
    ("Tendencies/HOPSTEPLAYUP", ("Attributes/DRIVINGLAYUP",)),
    ("Tendencies/PUTBACK", ("Attributes/CLOSESHOT", "Attributes/STANDINGDUNK")),
    ("Tendencies/SPINLAYUP", ("Attributes/DRIVINGLAYUP",)),
    ("Tendencies/STANDINGDUNK", ("Attributes/STANDINGDUNK",)),
    ("Tendencies/POSTDROPSTEP", ("Attributes/CLOSESHOT", "Attributes/POSTCONTROL")),
    ("Tendencies/POSTFADELEFT", ("Attributes/POSTFADE", "Attributes/POSTCONTROL")),
    ("Tendencies/POSTFADERIGHT", ("Attributes/POSTFADE", "Attributes/POSTCONTROL")),
    ("Tendencies/POSTHOOKLEFT", ("Attributes/POSTHOOK", "Attributes/POSTCONTROL")),
    ("Tendencies/POSTHOOKRIGHT", ("Attributes/POSTHOOK", "Attributes/POSTCONTROL")),
    ("Tendencies/HOPPOSTSHOT", ("Attributes/POSTFADE", "Attributes/POSTCONTROL")),
    ("Tendencies/POSTSHIMMYSHOT", ("Attributes/POSTFADE", "Attributes/POSTCONTROL")),
    ("Tendencies/POSTSTEPBACKSHOT", ("Attributes/POSTFADE", "Attributes/POSTCONTROL")),
    ("Tendencies/POSTUPANDUNDER", ("Attributes/CLOSESHOT", "Attributes/POSTCONTROL")),
    ("Tendencies/FROMPOSTSHOT", ("Attributes/POSTCONTROL",)),
)
TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS = (
    "Tendencies/USEGLASS",
    "Tendencies/ALLEYOOP",
    "Tendencies/DRIVINGDUNK",
    "Tendencies/DRIVINGLAYUP",
    "Tendencies/EUROSTEPLAYUP",
    "Tendencies/FLASHYDUNK",
    "Tendencies/FLOATER",
    "Tendencies/HOPSTEPLAYUP",
    "Tendencies/PUTBACK",
    "Tendencies/SPINLAYUP",
    "Tendencies/STANDINGDUNK",
    "Tendencies/POSTDROPSTEP",
    "Tendencies/POSTFADELEFT",
    "Tendencies/POSTFADERIGHT",
    "Tendencies/POSTHOOKLEFT",
    "Tendencies/POSTHOOKRIGHT",
    "Tendencies/HOPPOSTSHOT",
    "Tendencies/POSTSHIMMYSHOT",
    "Tendencies/POSTSTEPBACKSHOT",
    "Tendencies/POSTUPANDUNDER",
    "Tendencies/FROMPOSTSHOT",
)
TWO_POINT_SOURCE_TENDENCY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "rim_non_dunk",
        (
            "Tendencies/BASKETUNDERSHOT",
            "Tendencies/USEGLASS",
            "Tendencies/DRIVINGLAYUP",
            "Tendencies/EUROSTEPLAYUP",
            "Tendencies/HOPSTEPLAYUP",
            "Tendencies/SPINLAYUP",
        ),
    ),
    (
        "dunk",
        (
            "Tendencies/ALLEYOOP",
            "Tendencies/DRIVINGDUNK",
            "Tendencies/FLASHYDUNK",
            "Tendencies/PUTBACK",
            "Tendencies/STANDINGDUNK",
        ),
    ),
    (
        "close",
        (
            "Tendencies/CLOSESHOT",
            "Tendencies/CLOSELEFTSHOT",
            "Tendencies/CLOSEMIDDLESHOT",
            "Tendencies/CLOSERIGHTSHOT",
            "Tendencies/FLOATER",
            "Tendencies/POSTDROPSTEP",
            "Tendencies/POSTHOOKLEFT",
            "Tendencies/POSTHOOKRIGHT",
            "Tendencies/POSTUPANDUNDER",
            "Tendencies/FROMPOSTSHOT",
        ),
    ),
    (
        "mid",
        (
            "Tendencies/MIDSHOT",
            "Tendencies/CENTERMIDSHOT",
            "Tendencies/LEFTMIDSHOT",
            "Tendencies/CENTERLEFTMIDSHOT",
            "Tendencies/MIDRIGHTSHOT",
            "Tendencies/CENTERMIDRIGHTSHOT",
            "Tendencies/CONTESTEDJUMPERMIDRANGE",
            "Tendencies/DRIVEPULLUPMIDRANGE",
            "Tendencies/MIDOFFSCREENSHOT",
            "Tendencies/SPINJUMPER",
            "Tendencies/MIDSPOTUPSHOT",
            "Tendencies/STEPTHROUGH",
            "Tendencies/STEPBACKJUMPERMIDRANGE",
            "Tendencies/POSTFADELEFT",
            "Tendencies/POSTFADERIGHT",
            "Tendencies/HOPPOSTSHOT",
            "Tendencies/POSTSHIMMYSHOT",
            "Tendencies/POSTSTEPBACKSHOT",
        ),
    ),
)
TWO_POINT_SOURCE_PROFILE_FIELDS = (
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
)
TWO_POINT_FEATURE_NAMES = (
    "intercept",
    *(f"action_probability:{tendency}" for tendency in TWO_POINT_TENDENCY_FIELDS),
    *(
        f"action_effectiveness:{tendency_field}*{attribute_field}"
        for tendency_field, attribute_fields in TWO_POINT_ACTION_ATTRIBUTE_MAP
        for attribute_field in attribute_fields
    ),
    *(
        f"unresolved_action_context:{tendency_field}*{context_field}"
        for tendency_field in TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS
        for context_field in TWO_POINT_CONTEXT_FIELDS
    ),
)
DEFAULT_FREE_THROW_ARTIFACT_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_models"
    / "free_throw_execution_response.json"
)
DEFAULT_THREE_POINT_ARTIFACT_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_models"
    / "three_point_shooting_response.json"
)
DEFAULT_TWO_POINT_ARTIFACT_PATH = (
    Path(__file__).resolve().parent
    / "NBA Player Data"
    / "player_generation_models"
    / "two_point_shooting_response.json"
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
    """Self-contained forward response curve for the Free Throw attribute."""

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
        """Solve the supported rating with minimum forward-response error."""

        try:
            target = float(target_make_probability)
        except (TypeError, ValueError):
            return FreeThrowInverseResult(
                False, None, None, None, None, reason="missing_or_non_numeric_target"
            )
        if (
            isinstance(target_make_probability, bool)
            or not math.isfinite(target)
            or target < 0.0
            or target > 1.0
        ):
            return FreeThrowInverseResult(
                False,
                target if math.isfinite(target) else None,
                None,
                None,
                None,
                reason="target_outside_probability_domain",
            )

        scored = tuple(
            (rating, probability, abs(probability - target))
            for rating, probability in self.curve
        )
        best_error = min(error for _rating, _probability, error in scored)
        tied = tuple(
            (rating, probability)
            for rating, probability, error in scored
            if math.isclose(error, best_error, rel_tol=0.0, abs_tol=1e-15)
        )
        tied_midpoint = (tied[0][0] + tied[-1][0]) / 2.0
        rating, probability = min(
            tied,
            key=lambda point: (abs(point[0] - tied_midpoint), point[0]),
        )
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
                    rating
                    for rating in FREE_THROW_RATING_DOMAIN
                    if rating not in {point[0] for point in self.curve}
                ],
                "names_are_features": False,
                "tendencies_are_inputs": False,
            },
            "output_contract": {
                "made_stat": "Free Throws Made",
                "attempted_stat": "Free Throws Attempted",
                "probability": self.response_output,
            },
            "curve": [
                {"rating": rating, "make_probability": probability}
                for rating, probability in self.curve
            ],
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
    """Load the published runtime artifact without opening or hashing the Pool."""

    path = Path(artifact_path).resolve()
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("Free Throw artifact root must be an object")
    return FreeThrowExecutionArtifact.from_dict(payload)


@dataclass(frozen=True)
class ThreePointResponsePrediction:
    resolved: bool
    make_probability: float | None
    attempt_share: float | None
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThreePointShootingArtifact:
    """Self-contained joint response model for all 3PT Attributes/Tendencies."""

    schema_version: int
    field_keys: tuple[str, ...]
    feature_names: tuple[str, ...]
    make_probability_coefficients: tuple[float, ...]
    attempt_share_coefficients: tuple[float, ...]
    ridge_penalty: float
    pool_fingerprint: str
    training_summary: Mapping[str, Any]
    evaluation_summary: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != THREE_POINT_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported 3PT artifact schema: {self.schema_version}")
        if self.field_keys != THREE_POINT_RUNTIME_FIELDS:
            raise ValueError("3PT artifact field order does not match the canonical field contract")
        if self.feature_names != THREE_POINT_FEATURE_NAMES:
            raise ValueError("3PT artifact feature order does not match the canonical feature contract")
        expected = len(self.feature_names)
        for label, coefficients in (
            ("make probability", self.make_probability_coefficients),
            ("attempt share", self.attempt_share_coefficients),
        ):
            if len(coefficients) != expected:
                raise ValueError(f"3PT {label} coefficient count does not match feature count")
            if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in coefficients):
                raise ValueError(f"3PT {label} coefficients must be finite numbers")
        if not math.isfinite(float(self.ridge_penalty)) or self.ridge_penalty < 0.0:
            raise ValueError("3PT ridge penalty must be a finite nonnegative number")
        if not str(self.pool_fingerprint).strip():
            raise ValueError("3PT artifact requires a Pool fingerprint")

    def predict(self, field_values: Mapping[str, Any]) -> ThreePointResponsePrediction:
        missing = tuple(field for field in self.field_keys if field not in field_values)
        if missing:
            return ThreePointResponsePrediction(False, None, None, missing_fields=missing)
        parsed: list[int] = []
        invalid: list[str] = []
        contract_by_field = {contract[0]: contract for contract in THREE_POINT_FIELD_CONTRACTS}
        for field in self.field_keys:
            raw = field_values[field]
            contract = contract_by_field[field]
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                invalid.append(field)
                continue
            if (
                isinstance(raw, bool)
                or not math.isfinite(numeric)
                or not numeric.is_integer()
                or numeric < contract[3]
                or numeric > contract[4]
            ):
                invalid.append(field)
                continue
            parsed.append(int(numeric))
        if invalid:
            return ThreePointResponsePrediction(False, None, None, invalid_fields=tuple(invalid))
        features = three_point_feature_vector(tuple(parsed))
        make_probability = _logistic(sum(value * coefficient for value, coefficient in zip(
            features, self.make_probability_coefficients, strict=True
        )))
        attempt_share = _logistic(sum(value * coefficient for value, coefficient in zip(
            features, self.attempt_share_coefficients, strict=True
        )))
        return ThreePointResponsePrediction(True, make_probability, attempt_share)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "technical_readiness": "offline joint 3PT Attribute/Tendency slice only",
            "product_verdict": "not a complete player generator; inverse generation and Preview are not wired",
            "model_family": "ridge_binomial_logistic_joint_three_point_response",
            "field_keys": list(self.field_keys),
            "feature_names": list(self.feature_names),
            "field_contract": [
                {
                    "runtime_field": runtime_field,
                    "field_type": field_type,
                    "captured_field": captured_field,
                    "minimum": minimum,
                    "maximum": maximum,
                }
                for runtime_field, field_type, captured_field, minimum, maximum in THREE_POINT_FIELD_CONTRACTS
            ],
            "output_contract": {
                "make_probability": "Three Pointers Made / Three Pointers Attempted",
                "attempt_share": "Three Pointers Attempted / Field Goals Attempted",
                "zero_three_point_attempts": "attempt-share evidence only; make probability unresolved",
            },
            "make_probability_coefficients": list(self.make_probability_coefficients),
            "attempt_share_coefficients": list(self.attempt_share_coefficients),
            "ridge_penalty": self.ridge_penalty,
            "pool_fingerprint": self.pool_fingerprint,
            "training_summary": dict(self.training_summary),
            "evaluation_summary": dict(self.evaluation_summary),
        }

    def write(self, artifact_path: str | Path = DEFAULT_THREE_POINT_ARTIFACT_PATH) -> Path:
        return _write_json_artifact(artifact_path, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ThreePointShootingArtifact":
        required_lists = (
            "field_keys",
            "feature_names",
            "make_probability_coefficients",
            "attempt_share_coefficients",
        )
        if any(not isinstance(payload.get(key), list) for key in required_lists):
            raise ValueError("3PT artifact field, feature, and coefficient payloads must be lists")
        return cls(
            schema_version=int(payload.get("schema_version", 0)),
            field_keys=tuple(str(value) for value in payload["field_keys"]),
            feature_names=tuple(str(value) for value in payload["feature_names"]),
            make_probability_coefficients=tuple(float(value) for value in payload["make_probability_coefficients"]),
            attempt_share_coefficients=tuple(float(value) for value in payload["attempt_share_coefficients"]),
            ridge_penalty=float(payload.get("ridge_penalty", -1.0)),
            pool_fingerprint=str(payload.get("pool_fingerprint", "")),
            training_summary=dict(payload.get("training_summary") or {}),
            evaluation_summary=dict(payload.get("evaluation_summary") or {}),
        )


def three_point_feature_vector(field_values: tuple[int, ...]) -> tuple[float, ...]:
    if len(field_values) != len(THREE_POINT_FIELD_CONTRACTS):
        raise ValueError("3PT feature vector requires every canonical field")
    normalized = tuple(
        (value - minimum) / (maximum - minimum)
        for value, (_runtime, _type, _capture, minimum, maximum) in zip(
            field_values, THREE_POINT_FIELD_CONTRACTS, strict=True
        )
    )
    attribute = normalized[0]
    return (1.0, *normalized, *(attribute * tendency for tendency in normalized[1:]))


def _logistic(score: float) -> float:
    if score >= 0.0:
        inverse = math.exp(-score)
        return 1.0 / (1.0 + inverse)
    exponent = math.exp(score)
    return exponent / (1.0 + exponent)


def load_three_point_shooting_artifact(
    artifact_path: str | Path = DEFAULT_THREE_POINT_ARTIFACT_PATH,
) -> ThreePointShootingArtifact:
    """Load the published 3PT artifact without opening or hashing the Pool."""

    path = Path(artifact_path).resolve()
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("3PT artifact root must be an object")
    return ThreePointShootingArtifact.from_dict(payload)


@dataclass(frozen=True)
class TwoPointResponsePrediction:
    resolved: bool
    make_probability: float | None
    attempts_per_36: float | None
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class TwoPointInverseSolution:
    resolved: bool
    field_values: Mapping[str, int] | None
    target_make_probability: float | None
    target_attempts_per_36: float | None
    predicted_make_probability: float | None
    predicted_attempts_per_36: float | None
    boundary_limited_targets: tuple[str, ...] = ()
    source_conditioning_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class TwoPointShootingArtifact:
    """Self-contained joint response model for all direct 2PT fields."""

    schema_version: int
    field_keys: tuple[str, ...]
    feature_names: tuple[str, ...]
    make_probability_coefficients: tuple[float, ...]
    attempts_per_36_coefficients: tuple[float, ...]
    inverse_field_means: tuple[float, ...]
    inverse_response_means: tuple[float, float]
    inverse_response_coefficients: tuple[tuple[float, float], ...]
    inverse_response_score_bounds: tuple[tuple[float, float], tuple[float, float]]
    ridge_penalty: float
    pool_fingerprint: str
    training_summary: Mapping[str, Any]
    evaluation_summary: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != TWO_POINT_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported 2PT artifact schema: {self.schema_version}")
        if self.field_keys != TWO_POINT_RUNTIME_FIELDS:
            raise ValueError("2PT artifact field order does not match the canonical field contract")
        if self.feature_names != TWO_POINT_FEATURE_NAMES:
            raise ValueError("2PT artifact feature order does not match the canonical feature contract")
        if tuple(tendency for tendency, _attributes in TWO_POINT_ACTION_ATTRIBUTE_MAP) != TWO_POINT_TENDENCY_FIELDS:
            raise ValueError("2PT action-effectiveness map must cover every Tendency exactly once in runtime order")
        source_family_fields = tuple(
            field for _name, fields in TWO_POINT_SOURCE_TENDENCY_GROUPS for field in fields
        )
        if len(source_family_fields) != len(set(source_family_fields)) or set(source_family_fields) != set(TWO_POINT_TENDENCY_FIELDS):
            raise ValueError("2PT Master action families must partition every Tendency exactly once")
        allowed_attributes = set(TWO_POINT_ATTRIBUTE_FIELDS)
        if any(
            not attributes or any(attribute not in allowed_attributes for attribute in attributes)
            for _tendency, attributes in TWO_POINT_ACTION_ATTRIBUTE_MAP
        ):
            raise ValueError("2PT action map contains an invalid conditional-effectiveness Attribute")
        expected = len(self.feature_names)
        for label, coefficients in (
            ("make probability", self.make_probability_coefficients),
            ("attempts per 36", self.attempts_per_36_coefficients),
        ):
            if len(coefficients) != expected:
                raise ValueError(f"2PT {label} coefficient count does not match feature count")
            if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in coefficients):
                raise ValueError(f"2PT {label} coefficients must be finite numbers")
        if not math.isfinite(float(self.ridge_penalty)) or self.ridge_penalty < 0.0:
            raise ValueError("2PT ridge penalty must be a finite nonnegative number")
        if not str(self.pool_fingerprint).strip():
            raise ValueError("2PT artifact requires a Pool fingerprint")
        if len(self.inverse_field_means) != len(TWO_POINT_FIELD_CONTRACTS):
            raise ValueError("2PT inverse field-mean count does not match the canonical contract")
        if len(self.inverse_response_means) != 2:
            raise ValueError("2PT inverse requires both response means")
        if len(self.inverse_response_coefficients) != len(TWO_POINT_FIELD_CONTRACTS):
            raise ValueError("2PT inverse coefficient row count does not match the canonical contract")
        if any(len(row) != 2 for row in self.inverse_response_coefficients):
            raise ValueError("2PT inverse coefficient rows must contain both response heads")
        if len(self.inverse_response_score_bounds) != 2 or any(
            len(bounds) != 2 for bounds in self.inverse_response_score_bounds
        ):
            raise ValueError("2PT inverse response-score bounds must cover both heads")
        inverse_values = (
            *self.inverse_field_means,
            *self.inverse_response_means,
            *(value for row in self.inverse_response_coefficients for value in row),
            *(value for bounds in self.inverse_response_score_bounds for value in bounds),
        )
        if any(not math.isfinite(float(value)) for value in inverse_values):
            raise ValueError("2PT inverse parameters must be finite")
        if any(not 0.0 <= value <= 1.0 for value in self.inverse_field_means):
            raise ValueError("2PT inverse field means must be normalized")
        if any(lower > upper for lower, upper in self.inverse_response_score_bounds):
            raise ValueError("2PT inverse response-score bounds are reversed")

    def predict(
        self,
        field_values: Mapping[str, Any],
        player_context: Mapping[str, Any] | None,
    ) -> TwoPointResponsePrediction:
        missing = tuple(field for field in self.field_keys if field not in field_values)
        if missing:
            return TwoPointResponsePrediction(False, None, None, missing_fields=missing)
        parsed: list[int] = []
        invalid: list[str] = []
        contract_by_field = {contract[0]: contract for contract in TWO_POINT_FIELD_CONTRACTS}
        for field in self.field_keys:
            raw = field_values[field]
            contract = contract_by_field[field]
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                invalid.append(field)
                continue
            if (
                isinstance(raw, bool)
                or not math.isfinite(numeric)
                or not numeric.is_integer()
                or numeric < contract[3]
                or numeric > contract[4]
            ):
                invalid.append(field)
                continue
            parsed.append(int(numeric))
        if invalid:
            return TwoPointResponsePrediction(False, None, None, invalid_fields=tuple(invalid))
        context_values = two_point_context_vector(player_context)
        if context_values is None:
            return TwoPointResponsePrediction(
                False,
                None,
                None,
                missing_fields=("context/height_inches", "context/weight_pounds", "context/position"),
            )
        features = two_point_feature_vector(tuple(parsed), context_values)
        make_probability = _logistic(sum(
            value * coefficient
            for value, coefficient in zip(features, self.make_probability_coefficients, strict=True)
        ))
        rate_score = sum(
            value * coefficient
            for value, coefficient in zip(features, self.attempts_per_36_coefficients, strict=True)
        )
        attempts_per_36 = math.exp(max(min(rate_score, 35.0), -35.0))
        return TwoPointResponsePrediction(True, make_probability, attempts_per_36)

    def solve_package(
        self,
        target_make_probability: Any,
        target_attempts_per_36: Any,
        source_shooting: Mapping[str, Any] | None = None,
        player_context: Mapping[str, Any] | None = None,
    ) -> TwoPointInverseSolution:
        """Solve one action-probability package and conditional effectiveness package."""

        try:
            target_make = float(target_make_probability)
            target_rate = float(target_attempts_per_36)
        except (TypeError, ValueError):
            return TwoPointInverseSolution(False, None, None, None, None, None)
        if (
            isinstance(target_make_probability, bool)
            or isinstance(target_attempts_per_36, bool)
            or not math.isfinite(target_make)
            or not math.isfinite(target_rate)
            or not 0.0 <= target_make <= 1.0
            or target_rate < 0.0
        ):
            return TwoPointInverseSolution(False, None, None, None, None, None)
        context_values = two_point_context_vector(player_context)
        if context_values is None:
            return TwoPointInverseSolution(False, None, None, None, None, None)

        make_bounds, rate_bounds = self.inverse_response_score_bounds
        if target_make <= 0.0:
            raw_make_score = make_bounds[0]
        elif target_make >= 1.0:
            raw_make_score = make_bounds[1]
        else:
            raw_make_score = math.log(target_make / (1.0 - target_make))
        raw_rate_score = rate_bounds[0] if target_rate <= 0.0 else math.log(target_rate)
        make_score = min(max(raw_make_score, make_bounds[0]), make_bounds[1])
        rate_score = min(max(raw_rate_score, rate_bounds[0]), rate_bounds[1])
        boundary_labels = []
        if target_make in {0.0, 1.0}:
            boundary_labels.append("make_probability")
        if target_rate == 0.0:
            boundary_labels.append("attempts_per_36")
        boundary_labels.extend(
            label
            for label, raw, bounded in (
                ("make_probability", raw_make_score, make_score),
                ("attempts_per_36", raw_rate_score, rate_score),
            )
            if raw != bounded
        )
        boundary_limited = tuple(dict.fromkeys(boundary_labels))
        make_delta = make_score - self.inverse_response_means[0]
        rate_delta = rate_score - self.inverse_response_means[1]
        field_values: dict[str, int] = {}
        for field_mean, coefficients, contract in zip(
            self.inverse_field_means,
            self.inverse_response_coefficients,
            TWO_POINT_FIELD_CONTRACTS,
            strict=True,
        ):
            normalized = field_mean + coefficients[0] * make_delta + coefficients[1] * rate_delta
            normalized = min(max(normalized, 0.0), 1.0)
            minimum, maximum = contract[3], contract[4]
            field_values[contract[0]] = int(round(minimum + normalized * (maximum - minimum)))
        source_conditioned, source_conditioning_fields = condition_two_point_package_from_source(
            field_values,
            source_shooting,
            context_values=context_values,
            attempts_per_36_coefficients=self.attempts_per_36_coefficients,
        )
        source_conditioned = normalize_shot_location_tendency_percentages(
            source_conditioned,
            (
                CLOSE_SHOT_LOCATION_TENDENCY_FIELDS,
                MID_SHOT_LOCATION_TENDENCY_FIELDS,
            ),
        )
        source_conditioned["Tendencies/BASKETUNDERSHOT"] = 100
        # Master location evidence fixes the broad action mixture first. The
        # fitted forward model then solves only conditional effectiveness while
        # those action probabilities remain fixed.
        field_values = _solve_two_point_attributes_for_fixed_actions(
            source_conditioned,
            context_values,
            make_score,
            rate_score,
            self.make_probability_coefficients,
            self.attempts_per_36_coefficients,
        )
        prediction = self.predict(field_values, player_context)
        if not prediction.resolved:
            return TwoPointInverseSolution(False, None, None, None, None, None)
        return TwoPointInverseSolution(
            resolved=True,
            field_values=field_values,
            target_make_probability=target_make,
            target_attempts_per_36=target_rate,
            predicted_make_probability=prediction.make_probability,
            predicted_attempts_per_36=prediction.attempts_per_36,
            boundary_limited_targets=boundary_limited,
            source_conditioning_fields=source_conditioning_fields,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "technical_readiness": "self-contained action-probability 2PT response and fitted conditional inverse",
            "product_verdict": "ready for exclusive correlated 2PT proposal ownership",
            "model_family": "tendency_weighted_action_effectiveness_binomial_plus_poisson_with_conditional_inverse",
            "field_keys": list(self.field_keys),
            "feature_names": list(self.feature_names),
            "field_contract": [
                {
                    "runtime_field": runtime_field,
                    "field_type": field_type,
                    "captured_field": captured_field,
                    "minimum": minimum,
                    "maximum": maximum,
                }
                for runtime_field, field_type, captured_field, minimum, maximum in TWO_POINT_FIELD_CONTRACTS
            ],
            "output_contract": {
                "two_points_made": "Field Goals Made - Three Pointers Made",
                "two_points_attempted": "Field Goals Attempted - Three Pointers Attempted",
                "make_probability": "two_points_made / two_points_attempted",
                "attempts_per_36": "36 * two_points_attempted / Minutes",
                "zero_two_point_attempts": "attempt-rate evidence only; make probability unresolved",
            },
            "make_probability_coefficients": list(self.make_probability_coefficients),
            "attempts_per_36_coefficients": list(self.attempts_per_36_coefficients),
            "inverse_contract": {
                "method": "Master action mixture followed by conditional Attribute solve against both fitted forward-response scores",
                "fit": "Pool Tendencies are normalized 0..1 action probabilities; mapped Attribute*Tendency terms fit action-conditional effectiveness against aggregate simulated 2PT outcomes",
                "source_composition": "direct Master shot-location shares set broad Tendency probability mass; fitted Pool height/weight/position action interactions split only Master-unresolved subtypes inside each family; direct zone efficiencies seed layup, close, and mid Attributes; the conditional solver then holds all Tendencies fixed",
                "source_profile_fields": list(TWO_POINT_SOURCE_PROFILE_FIELDS),
                "source_action_families": {
                    name: list(fields) for name, fields in TWO_POINT_SOURCE_TENDENCY_GROUPS
                },
                "physical_context": "height, weight, and position appear only as interactions with unresolved dunk, layup, and post action probabilities",
                "unsupported_source_splits": ["direct standing_vs_driving_dunk observation", "direct hook_vs_fade observation", "direct left_vs_right_post_move observation"],
                "underidentification": "Master separates observed broad location families; fitted physical context can contextualize but cannot claim direct subtype observation",
                "requires_both_targets": True,
            },
            "action_contract": [
                {"tendency": tendency, "conditional_attributes": list(attributes)}
                for tendency, attributes in TWO_POINT_ACTION_ATTRIBUTE_MAP
            ],
            "context_contract": {
                "fields": list(TWO_POINT_CONTEXT_FIELDS),
                "direct_response_terms": False,
                "contextualized_tendencies": list(TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS),
            },
            "inverse_field_means": list(self.inverse_field_means),
            "inverse_response_means": list(self.inverse_response_means),
            "inverse_response_coefficients": [list(row) for row in self.inverse_response_coefficients],
            "inverse_response_score_bounds": [list(bounds) for bounds in self.inverse_response_score_bounds],
            "ridge_penalty": self.ridge_penalty,
            "pool_fingerprint": self.pool_fingerprint,
            "training_summary": dict(self.training_summary),
            "evaluation_summary": dict(self.evaluation_summary),
        }

    def write(self, artifact_path: str | Path = DEFAULT_TWO_POINT_ARTIFACT_PATH) -> Path:
        return _write_json_artifact(artifact_path, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TwoPointShootingArtifact":
        required_lists = (
            "field_keys",
            "feature_names",
            "make_probability_coefficients",
            "attempts_per_36_coefficients",
            "inverse_field_means",
            "inverse_response_means",
            "inverse_response_coefficients",
            "inverse_response_score_bounds",
        )
        if any(not isinstance(payload.get(key), list) for key in required_lists):
            raise ValueError("2PT artifact field, feature, coefficient, and inverse payloads must be lists")
        return cls(
            schema_version=int(payload.get("schema_version", 0)),
            field_keys=tuple(str(value) for value in payload["field_keys"]),
            feature_names=tuple(str(value) for value in payload["feature_names"]),
            make_probability_coefficients=tuple(float(value) for value in payload["make_probability_coefficients"]),
            attempts_per_36_coefficients=tuple(float(value) for value in payload["attempts_per_36_coefficients"]),
            inverse_field_means=tuple(float(value) for value in payload["inverse_field_means"]),
            inverse_response_means=tuple(float(value) for value in payload["inverse_response_means"]),
            inverse_response_coefficients=tuple(
                tuple(float(value) for value in row)
                for row in payload["inverse_response_coefficients"]
            ),
            inverse_response_score_bounds=tuple(
                tuple(float(value) for value in bounds)
                for bounds in payload["inverse_response_score_bounds"]
            ),
            ridge_penalty=float(payload.get("ridge_penalty", -1.0)),
            pool_fingerprint=str(payload.get("pool_fingerprint", "")),
            training_summary=dict(payload.get("training_summary") or {}),
            evaluation_summary=dict(payload.get("evaluation_summary") or {}),
        )


def two_point_context_vector(player_context: Mapping[str, Any] | None) -> tuple[float, ...] | None:
    """Return physical/position context used only inside unresolved action terms."""

    if not player_context:
        return None
    try:
        height = float(player_context["height_inches"])
        weight = float(player_context["weight_pounds"])
        position = str(player_context["position"]).strip().upper()
    except (KeyError, TypeError, ValueError):
        return None
    if (
        not math.isfinite(height)
        or not math.isfinite(weight)
        or position not in {"PG", "SG", "SF", "PF", "C"}
    ):
        return None
    # Fixed physical domains keep runtime scaling self-contained. They do not
    # create a direct height/weight effect: these values are multiplied only by
    # explicitly unresolved dunk/layup/post action probabilities below.
    height_scaled = min(max((height - 60.0) / 30.0, 0.0), 1.0)
    weight_scaled = min(max((weight - 140.0) / 260.0, 0.0), 1.0)
    return (
        height_scaled,
        weight_scaled,
        *(1.0 if position == label else 0.0 for label in ("PG", "SG", "SF", "PF", "C")),
    )


def two_point_feature_vector(
    field_values: tuple[int, ...],
    context_values: tuple[float, ...],
) -> tuple[float, ...]:
    if len(field_values) != len(TWO_POINT_FIELD_CONTRACTS):
        raise ValueError("2PT feature vector requires every canonical field")
    if len(context_values) != len(TWO_POINT_CONTEXT_FIELDS):
        raise ValueError("2PT feature vector requires exact physical/position context")
    normalized = tuple(
        (value - minimum) / (maximum - minimum)
        for value, (_runtime, _type, _capture, minimum, maximum) in zip(
            field_values, TWO_POINT_FIELD_CONTRACTS, strict=True
        )
    )
    by_field = dict(zip(TWO_POINT_RUNTIME_FIELDS, normalized, strict=True))
    action_probabilities = tuple(by_field[field] for field in TWO_POINT_TENDENCY_FIELDS)
    action_effectiveness = tuple(
        by_field[tendency] * by_field[attribute]
        for tendency, attributes in TWO_POINT_ACTION_ATTRIBUTE_MAP
        for attribute in attributes
    )
    unresolved_context = tuple(
        by_field[tendency] * context
        for tendency in TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS
        for context in context_values
    )
    return (1.0, *action_probabilities, *action_effectiveness, *unresolved_context)


def condition_two_point_package_from_source(
    field_values: Mapping[str, int],
    source_shooting: Mapping[str, Any] | None,
    *,
    context_values: tuple[float, ...] | None = None,
    attempts_per_36_coefficients: tuple[float, ...] | None = None,
) -> tuple[dict[str, int], tuple[str, ...]]:
    """Apply Master family mass, then use fitted context terms only for subtype splits."""

    conditioned = dict(field_values)
    if not source_shooting:
        return conditioned, ()
    observed = {
        field: _bounded_source_fraction(source_shooting.get(field))
        for field in TWO_POINT_SOURCE_PROFILE_FIELDS
    }
    used: list[str] = []

    shares = tuple(
        observed[field]
        for field in TWO_POINT_SOURCE_PROFILE_FIELDS[:4]
    )
    dunk_share = observed["percent_dunks_of_fga"]
    if all(value is not None for value in shares) and dunk_share is not None:
        rim, close, mid_short, mid_long = (float(value) for value in shares)
        dunk = min(dunk_share, rim)
        components = (max(rim - dunk, 0.0), dunk, close, mid_short + mid_long)
        component_total = sum(components)
        if component_total > 0.0:
            group_masses = tuple(
                sum(conditioned[field] for field in fields)
                for _name, fields in TWO_POINT_SOURCE_TENDENCY_GROUPS
            )
            action_mass_budget = sum(group_masses)
            if action_mass_budget > 0.0:
                feature_indexes = {name: index for index, name in enumerate(TWO_POINT_FEATURE_NAMES)}
                for component, base_mass, (_name, fields) in zip(
                    components,
                    group_masses,
                    TWO_POINT_SOURCE_TENDENCY_GROUPS,
                    strict=True,
                ):
                    desired_mass = action_mass_budget * component / component_total
                    contextual_weights: list[float] = []
                    for field in fields:
                        weight = float(conditioned[field])
                        if (
                            weight > 0.0
                            and context_values is not None
                            and attempts_per_36_coefficients is not None
                            and field in TWO_POINT_CONTEXTUAL_TENDENCY_FIELDS
                        ):
                            affinity = sum(
                                attempts_per_36_coefficients[
                                    feature_indexes[f"unresolved_action_context:{field}*{context_field}"]
                                ]
                                * context
                                for context_field, context in zip(
                                    TWO_POINT_CONTEXT_FIELDS, context_values, strict=True
                                )
                            )
                            weight *= math.exp(min(max(affinity, -5.0), 5.0))
                        contextual_weights.append(weight)
                    if base_mass <= 0.0 or sum(contextual_weights) <= 0.0:
                        continue
                    allocated = _allocate_action_probability_mass(contextual_weights, desired_mass)
                    for field, value in zip(fields, allocated, strict=True):
                        conditioned[field] = value
                used.extend((*TWO_POINT_SOURCE_PROFILE_FIELDS[:4], "percent_dunks_of_fga"))

    rim_efficiency = observed["fg_percent_from_x0_3_range"]
    close_efficiency = observed["fg_percent_from_x3_10_range"]
    mid_short_efficiency = observed["fg_percent_from_x10_16_range"]
    mid_long_efficiency = observed["fg_percent_from_x16_3p_range"]
    overall_efficiency = observed["fg_percent_from_x2p_range"]
    mid_short_share = observed["percent_fga_from_x10_16_range"]
    mid_long_share = observed["percent_fga_from_x16_3p_range"]
    if (
        rim_efficiency is not None
        and close_efficiency is not None
        and mid_short_efficiency is not None
        and mid_long_efficiency is not None
        and overall_efficiency is not None
        and overall_efficiency > 0.0
        and mid_short_share is not None
        and mid_long_share is not None
        and mid_short_share + mid_long_share > 0.0
    ):
        mid_efficiency = (
            mid_short_efficiency * mid_short_share + mid_long_efficiency * mid_long_share
        ) / (mid_short_share + mid_long_share)
        skill_fields = (
            ("Attributes/DRIVINGLAYUP", rim_efficiency),
            ("Attributes/CLOSESHOT", close_efficiency),
            ("Attributes/MIDRANGE", mid_efficiency),
        )
        aggregate_skill = sum((conditioned[field] - 25) / 74.0 for field, _value in skill_fields) / len(skill_fields)
        for field, zone_efficiency in skill_fields:
            normalized = aggregate_skill * zone_efficiency / overall_efficiency
            conditioned[field] = int(round(25 + 74 * min(max(normalized, 0.0), 1.0)))
        used.extend((
            "fg_percent_from_x0_3_range",
            "fg_percent_from_x3_10_range",
            "fg_percent_from_x10_16_range",
            "fg_percent_from_x16_3p_range",
            "fg_percent_from_x2p_range",
        ))
    return conditioned, tuple(dict.fromkeys(used))


def _allocate_action_probability_mass(weights: Sequence[float], desired_mass: float) -> tuple[int, ...]:
    """Preserve family probability mass while respecting each 0-100 action bound."""

    allocations = [0.0] * len(weights)
    active = {index for index, weight in enumerate(weights) if weight > 0.0}
    remaining = min(max(desired_mass, 0.0), 100.0 * len(active))
    while active and remaining > 0.0:
        weight_total = sum(weights[index] for index in active)
        if weight_total <= 0.0:
            break
        capped = {
            index
            for index in active
            if remaining * weights[index] / weight_total >= 100.0
        }
        if not capped:
            for index in active:
                allocations[index] = remaining * weights[index] / weight_total
            remaining = 0.0
            break
        for index in capped:
            allocations[index] = 100.0
            remaining -= 100.0
        active.difference_update(capped)

    integer_allocations = [int(math.floor(value)) for value in allocations]
    integer_target = min(int(round(min(max(desired_mass, 0.0), 100.0 * sum(weight > 0.0 for weight in weights)))), 100 * len(weights))
    remainder_order = sorted(
        range(len(weights)),
        key=lambda index: (allocations[index] - integer_allocations[index], weights[index], -index),
        reverse=True,
    )
    for index in remainder_order:
        if sum(integer_allocations) >= integer_target:
            break
        if integer_allocations[index] < 100 and weights[index] > 0.0:
            integer_allocations[index] += 1
    return tuple(integer_allocations)


def normalize_shot_location_tendency_percentages(
    field_values: Mapping[str, int],
    groups: Sequence[Sequence[str]] = SHOT_LOCATION_TENDENCY_GROUPS,
) -> dict[str, int]:
    """Convert each active directional shot-location group to integer percentages."""

    normalized = dict(field_values)
    for fields in groups:
        weights = tuple(int(normalized[field]) for field in fields)
        total = sum(weights)
        if total <= 0:
            continue
        exact = tuple(100.0 * weight / total for weight in weights)
        allocated = [int(math.floor(value)) for value in exact]
        remainder_order = sorted(
            range(len(fields)),
            key=lambda index: (exact[index] - allocated[index], weights[index], -index),
            reverse=True,
        )
        for index in remainder_order[: 100 - sum(allocated)]:
            allocated[index] += 1
        for field, value in zip(fields, allocated, strict=True):
            normalized[field] = value
    return normalized


def _solve_two_point_attributes_for_fixed_actions(
    source_values: Mapping[str, int],
    context_values: tuple[float, ...],
    target_make_score: float,
    target_rate_score: float,
    make_coefficients: tuple[float, ...],
    rate_coefficients: tuple[float, ...],
) -> dict[str, int]:
    """Fit conditional effectiveness while preserving all source action chances."""

    solved = dict(source_values)

    def scores(values: Mapping[str, int]) -> tuple[float, float]:
        vector = two_point_feature_vector(
            tuple(values[field] for field in TWO_POINT_RUNTIME_FIELDS),
            context_values,
        )
        return (
            sum(value * coefficient for value, coefficient in zip(vector, make_coefficients, strict=True)),
            sum(value * coefficient for value, coefficient in zip(vector, rate_coefficients, strict=True)),
        )

    # The feature contract is affine in Attributes once action probabilities
    # and context are fixed. These full-domain score differences are therefore
    # exact derivatives with respect to each normalized Attribute.
    make_gradient: list[float] = []
    rate_gradient: list[float] = []
    for field in TWO_POINT_ATTRIBUTE_FIELDS:
        low = dict(solved)
        high = dict(solved)
        low[field] = 25
        high[field] = 99
        low_make, low_rate = scores(low)
        high_make, high_rate = scores(high)
        make_gradient.append(high_make - low_make)
        rate_gradient.append(high_rate - low_rate)

    for _iteration in range(8):
        current_make, current_rate = scores(solved)
        make_delta = target_make_score - current_make
        rate_delta = target_rate_score - current_rate
        if abs(make_delta) <= 1e-8 and abs(rate_delta) <= 1e-8:
            break
        a00 = sum(value * value for value in make_gradient)
        a01 = sum(left * right for left, right in zip(make_gradient, rate_gradient, strict=True))
        a11 = sum(value * value for value in rate_gradient)
        determinant = a00 * a11 - a01 * a01
        if abs(determinant) <= 1e-15:
            break
        multiplier_make = (make_delta * a11 - rate_delta * a01) / determinant
        multiplier_rate = (a00 * rate_delta - a01 * make_delta) / determinant
        changed = False
        for index, field in enumerate(TWO_POINT_ATTRIBUTE_FIELDS):
            current = (solved[field] - 25.0) / 74.0
            movement = (
                make_gradient[index] * multiplier_make
                + rate_gradient[index] * multiplier_rate
            )
            value = int(round(25.0 + 74.0 * min(max(current + movement, 0.0), 1.0)))
            changed = changed or value != solved[field]
            solved[field] = value
        if not changed:
            break
    return solved


def _bounded_source_fraction(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        return None
    return numeric


def load_two_point_shooting_artifact(
    artifact_path: str | Path = DEFAULT_TWO_POINT_ARTIFACT_PATH,
) -> TwoPointShootingArtifact:
    """Load the published 2PT artifact without opening or hashing the Pool."""

    path = Path(artifact_path).resolve()
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("2PT artifact root must be an object")
    return TwoPointShootingArtifact.from_dict(payload)
