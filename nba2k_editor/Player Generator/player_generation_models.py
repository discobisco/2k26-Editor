from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from player_generation_master_bridge import (
    PLAYER_FEATURE_RUNTIME_SOURCES,
    runtime_player_feature_vector,
)
from player_generation_model_training import (
    FOLD_SEED,
    MIN_TRAIN_ROWS,
    MODEL_FAMILY,
    PLAYER_MASTER_FEATURES,
    POSITIONS,
    _fit_ridge,
    _predict,
    load_attribute_spike_data,
)
from player_generation_training_data import load_pool_analysis_data, sha256_file


ARTIFACT_FORMAT = "player-generation-learned-model-v1"
ARTIFACT_ID = "player-generation-phase-3-ridge-v1"
FIELD_RANGES = {
    "Attribute": (25, 99),
    "Tendency": (0, 100),
}
DIRECT_FIELD_KEYS = {
    "Attributes/FREETHROW": "PlayerEvidence.per_game.ft_percent -> round(percent * 100), clamp 25..99",
    "Attributes/STAMINA": "PlayerEvidence minutes-per-game under the existing direct stamina contract",
}
NON_NUMERIC_FIELD_KEYS = {
    "Tendencies/CLOSELEFT",
    "Tendencies/CLOSEMIDDLE",
    "Tendencies/CLOSERIGHT",
    "Tendencies/MIDRANGECENTER",
    "Tendencies/MIDRANGELEFT",
    "Tendencies/MIDRANGELEFTCENTER",
    "Tendencies/MIDRANGERIGHT",
    "Tendencies/MIDRANGERIGHTCENTER",
    "Tendencies/UNDERBASKET",
}
THREE_POINT_LEARNED_FIELDS = {
    "Attributes/3POINT",
    "Tendencies/3POINTCENTERLEFTSHOT",
    "Tendencies/3POINTCENTERRIGHTSHOT",
    "Tendencies/3POINTCENTERSHOT",
    "Tendencies/3POINTLEFTSHOT",
    "Tendencies/3POINTOFFSCREENSHOT",
    "Tendencies/3POINTRIGHTSHOT",
    "Tendencies/3POINTSHOT",
    "Tendencies/3POINTSPOTUPSHOT",
    "Tendencies/CONTESTEDJUMPER3POINT",
    "Tendencies/DRIVEPULLUP3POINT",
    "Tendencies/STEPBACKJUMPER3POINT",
    "Tendencies/TRANSITIONPULLUP3POINT",
}


class LearnedModelArtifactError(ValueError):
    pass


def _model_key(position: str, field_key: str, feature_signature: str) -> str:
    return f"{position}|{field_key}|{feature_signature}"


def _feature_signature(values: np.ndarray) -> str:
    return "".join("1" if math.isfinite(float(value)) else "0" for value in values)


def _signature_indices(feature_signature: str) -> tuple[int, ...]:
    return tuple(index for index, flag in enumerate(feature_signature) if flag == "1")


def _signature_is_available(feature_signature: str, available_signature: str) -> bool:
    return all(required == "0" or available == "1" for required, available in zip(feature_signature, available_signature, strict=True))


def _evidence_league(evidence: Any) -> str:
    season_info = getattr(evidence, "season_info", {})
    if isinstance(season_info, Mapping):
        return str(season_info.get("lg") or season_info.get("league") or "").strip().upper()
    return ""


def _direct_source(field_key: str) -> str | None:
    if field_key in DIRECT_FIELD_KEYS:
        return DIRECT_FIELD_KEYS[field_key]
    if field_key.startswith("Attributes/") and "DURABILITY" in field_key:
        return "PlayerEvidence games played under the existing direct durability contract"
    return None


def build_learned_model_artifact(
    pool_path: Path | str | None = None,
    *,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    """Train deterministic final-fit models for every learned-owned exact field."""
    feature_data = load_attribute_spike_data(pool_path, source_path=source_path)
    target_data = load_pool_analysis_data(pool_path)
    if feature_data.pool_sha256 != target_data.pool_sha256:
        raise LearnedModelArtifactError("feature and target views do not share the same Pool signature")
    if feature_data.package_keys != target_data.package_keys:
        raise LearnedModelArtifactError("feature and target package order differs")
    if not np.array_equal(feature_data.positions, target_data.positions):
        raise LearnedModelArtifactError("feature and target position order differs")

    field_types = dict(zip(target_data.field_keys, target_data.field_types, strict=True))
    field_ownership = []
    learned_field_keys = []
    for field_key in target_data.field_keys:
        direct_source = _direct_source(field_key)
        owner = (
            "non_numeric"
            if field_key in NON_NUMERIC_FIELD_KEYS
            else "direct"
            if direct_source is not None
            else "learned"
        )
        if owner == "learned":
            learned_field_keys.append(field_key)
        field_ownership.append(
            {
                "field_key": field_key,
                "field_type": field_types[field_key],
                "owner": owner,
                "position_models_required": list(POSITIONS) if owner == "learned" else [],
                "runtime_source_contract": (
                    "exact authored Cold/Neutral/Hot dropdown operation"
                    if owner == "non_numeric"
                    else direct_source or "exact learned position model from the artifact feature contract"
                ),
            }
        )

    runtime_feature_values = np.full_like(feature_data.feature_values, np.nan)
    package_index = {package_key: row_index for row_index, package_key in enumerate(feature_data.package_keys)}
    for package_key, runtime_vector in feature_data.runtime_alignment.runtime_vectors.items():
        row_index = package_index.get(package_key)
        if row_index is not None:
            runtime_feature_values[row_index] = runtime_vector

    position_signatures = {
        position: tuple(
            sorted(
                {
                    _feature_signature(runtime_feature_values[row_index])
                    for row_index in np.flatnonzero(feature_data.positions == position)
                    if np.isfinite(runtime_feature_values[row_index]).any()
                },
                key=lambda signature: (-signature.count("1"), signature),
            )
        )
        for position in POSITIONS
    }
    runtime_signatures = np.asarray(
        [_feature_signature(runtime_feature_values[row_index]) for row_index in range(len(feature_data.package_keys))],
        dtype=object,
    )

    models: dict[str, dict[str, Any]] = {}
    blockers: list[dict[str, Any]] = []
    field_index = {field_key: index for index, field_key in enumerate(target_data.field_keys)}
    for field_key in learned_field_keys:
        field_type = field_types[field_key]
        minimum, maximum = FIELD_RANGES[field_type]
        target = target_data.field_values[:, field_index[field_key]]
        for position in POSITIONS:
            variant_count = 0
            for feature_signature in position_signatures[position]:
                feature_indices = _signature_indices(feature_signature)
                if not feature_indices:
                    continue
                selected_features = runtime_feature_values[:, feature_indices]
                exact_complete = (
                    (feature_data.positions == position)
                    & np.isfinite(target)
                    & (runtime_signatures == feature_signature)
                    & np.all(np.isfinite(selected_features), axis=1)
                )
                exact_training_count = int(exact_complete.sum())
                if exact_training_count >= MIN_TRAIN_ROWS:
                    complete = exact_complete
                    training_availability_policy = "exact_observed_stat_mask"
                else:
                    complete = (
                        (feature_data.positions == position)
                        & np.isfinite(target)
                        & np.all(np.isfinite(selected_features), axis=1)
                    )
                    training_availability_policy = "available_stat_superset_for_sparse_exact_mask"
                training_count = int(complete.sum())
                if training_count < MIN_TRAIN_ROWS:
                    continue
                fitted = _fit_ridge(selected_features[complete], target[complete])
                models[_model_key(position, field_key, feature_signature)] = {
                    "position": position,
                    "field_key": field_key,
                    "field_type": field_type,
                    "minimum": minimum,
                    "maximum": maximum,
                    "training_count": training_count,
                    "exact_mask_training_count": exact_training_count,
                    "training_availability_policy": training_availability_policy,
                    "feature_signature": feature_signature,
                    "feature_indices": list(feature_indices),
                    "feature_columns": [PLAYER_MASTER_FEATURES[index] for index in feature_indices],
                    "feature_mean": fitted["feature_mean"].tolist(),
                    "feature_scale": fitted["feature_scale"].tolist(),
                    "coefficients": fitted["coefficients"].tolist(),
                }
                variant_count += 1
            if variant_count == 0:
                blockers.append(
                    {
                        "position": position,
                        "field_key": field_key,
                        "reason": "no_trainable_runtime_feature_subset",
                        "required_count": MIN_TRAIN_ROWS,
                    }
                )

    model_signatures: dict[tuple[str, str], tuple[str, ...]] = {}
    for position in POSITIONS:
        for field_key in learned_field_keys:
            model_signatures[(position, field_key)] = tuple(
                str(model["feature_signature"])
                for model in models.values()
                if model["position"] == position and model["field_key"] == field_key
            )

    runtime_row_count = 0
    routable_runtime_row_count = 0
    unroutable_runtime_examples: list[dict[str, Any]] = []
    for row_index, package_key in enumerate(feature_data.package_keys):
        runtime_vector = runtime_feature_values[row_index]
        if not np.isfinite(runtime_vector).any():
            continue
        runtime_row_count += 1
        position = str(feature_data.positions[row_index])
        available_signature = _feature_signature(runtime_vector)
        missing_fields = [
            field_key
            for field_key in learned_field_keys
            if not any(
                _signature_is_available(signature, available_signature)
                for signature in model_signatures[(position, field_key)]
            )
        ]
        if not missing_fields:
            routable_runtime_row_count += 1
        elif len(unroutable_runtime_examples) < 10:
            unroutable_runtime_examples.append(
                {
                    "package_key": list(package_key),
                    "position": position,
                    "available_signature": available_signature,
                    "missing_field_count": len(missing_fields),
                }
            )
    if routable_runtime_row_count != runtime_row_count:
        blockers.append(
            {
                "scope": "runtime_coverage",
                "reason": "not_all_runtime_feature_masks_are_routable",
                "runtime_row_count": runtime_row_count,
                "routable_runtime_row_count": routable_runtime_row_count,
                "unroutable_examples": unroutable_runtime_examples,
            }
        )

    feature_availability_by_season: dict[str, dict[str, dict[str, int]]] = {}
    for feature_index, feature_name in enumerate(PLAYER_MASTER_FEATURES):
        season_counts: dict[str, dict[str, int]] = {}
        for row_index, package_key in enumerate(feature_data.package_keys):
            match = feature_data.runtime_alignment.source_matches.get(package_key)
            if match is None:
                continue
            season = str(int(match.season))
            counts = season_counts.setdefault(season, {"available": 0, "missing": 0})
            counts["available" if math.isfinite(float(runtime_feature_values[row_index, feature_index])) else "missing"] += 1
        feature_availability_by_season[feature_name] = dict(sorted(season_counts.items(), key=lambda item: int(item[0])))

    x3pa_feature_index = PLAYER_MASTER_FEATURES.index("master_x3pa_per36")
    x3pa_availability_by_league_season: dict[str, dict[str, dict[str, int]]] = {}
    for row_index, package_key in enumerate(feature_data.package_keys):
        match = feature_data.runtime_alignment.source_matches.get(package_key)
        evidence = feature_data.runtime_alignment.evidence_by_package.get(package_key)
        if match is None or evidence is None:
            continue
        league = _evidence_league(evidence)
        if not league:
            continue
        season = str(int(match.season))
        counts = x3pa_availability_by_league_season.setdefault(league, {}).setdefault(
            season,
            {"available": 0, "missing": 0},
        )
        counts[
            "available"
            if math.isfinite(float(runtime_feature_values[row_index, x3pa_feature_index]))
            else "missing"
        ] += 1
    three_point_stat_availability = {}
    for league, season_rows in sorted(x3pa_availability_by_league_season.items()):
        observed_seasons = sorted(int(season) for season in season_rows)
        available_seasons = sorted(
            int(season)
            for season, counts in season_rows.items()
            if counts["available"] > 0
        )
        three_point_stat_availability[league] = {
            "minimum_observed_season": min(observed_seasons),
            "maximum_observed_season": max(observed_seasons),
            "first_observed_x3pa_season": min(available_seasons) if available_seasons else None,
            "availability_by_season": dict(sorted(season_rows.items(), key=lambda item: int(item[0]))),
        }

    if sha256_file(feature_data.pool_path) != feature_data.pool_sha256:
        raise LearnedModelArtifactError("Pool changed while building the learned model artifact")

    return {
        "artifact_format": ARTIFACT_FORMAT,
        "artifact_id": ARTIFACT_ID,
        "model_family": MODEL_FAMILY,
        "fold_seed": FOLD_SEED,
        "pool_sha256": feature_data.pool_sha256,
        "feature_contract": {
            "ordered_columns": list(PLAYER_MASTER_FEATURES),
            "runtime_sources": dict(PLAYER_FEATURE_RUNTIME_SOURCES),
            "missing_data_policy": "availability-routed exact feature-subset ridge; no imputation and no fallback",
            "routing_policy": "choose the trainable subset with the most actually available statistics, then the largest training count, then lexical signature",
            "identity_features": False,
            "sim_features": False,
        },
        "output_contract": {
            "ranges": {field_type: list(bounds) for field_type, bounds in FIELD_RANGES.items()},
            "rounding": "nearest integer after prediction, then field-type legal-range clamp",
        },
        "field_ownership": field_ownership,
        "target_fields": learned_field_keys,
        "direct_fields": [row["field_key"] for row in field_ownership if row["owner"] == "direct"],
        "non_numeric_fields": [row["field_key"] for row in field_ownership if row["owner"] == "non_numeric"],

        "positions": list(POSITIONS),
        "models": models,
        "runtime_coverage": {
            "runtime_feature_rows": runtime_row_count,
            "routable_runtime_feature_rows": routable_runtime_row_count,
            "unroutable_runtime_feature_rows": runtime_row_count - routable_runtime_row_count,
        },
        "feature_availability_by_season": feature_availability_by_season,
        "stat_applicability": {
            "three_point_action": {
                "source_feature": "master_x3pa_per36",
                "by_league": three_point_stat_availability,
                "gate_rule": "inapplicable before that league's first observed X3PA season when earlier league seasons are present; inapplicable for a league with no observed X3PA",
                "attribute_value_when_inapplicable": 25,
                "tendency_value_when_inapplicable": 0,
            }
        },
        "technical_blockers": blockers,
        "technical_readiness": "ready" if not blockers else "blocked",
        "field_coverage": "all_current_exact_numeric_fields_with_explicit_direct_ownership",
        "offline_metrics_are_product_failure_gates": False,
        "simulation_evaluation_status": "not_run",
        "product_verdict": "not_evaluated",
        "old_generator_fallback": False,
    }


def write_learned_model_artifact(
    output_path: Path | str,
    pool_path: Path | str | None = None,
    *,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    artifact = build_learned_model_artifact(pool_path, source_path=source_path)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "model_count": len(artifact["models"]),
        "technical_blocker_count": len(artifact["technical_blockers"]),
        "technical_readiness": artifact["technical_readiness"],
        "simulation_evaluation_status": artifact["simulation_evaluation_status"],
        "product_verdict": artifact["product_verdict"],
    }


def load_learned_model_artifact(
    path: Path | str,
    *,
    expected_pool_sha256: str | None = None,
) -> dict[str, Any]:
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    if artifact.get("artifact_format") != ARTIFACT_FORMAT:
        raise LearnedModelArtifactError("unsupported learned model artifact format")
    if artifact.get("artifact_id") != ARTIFACT_ID:
        raise LearnedModelArtifactError("unexpected learned model artifact id")
    if expected_pool_sha256 is not None and artifact.get("pool_sha256") != expected_pool_sha256:
        raise LearnedModelArtifactError("learned model artifact Pool signature mismatch")

    feature_contract = artifact.get("feature_contract")
    ordered_columns = feature_contract.get("ordered_columns") if isinstance(feature_contract, dict) else None
    if ordered_columns != list(PLAYER_MASTER_FEATURES):
        raise LearnedModelArtifactError("learned model artifact feature order mismatch")
    expected_feature_count = len(PLAYER_MASTER_FEATURES)
    models = artifact.get("models")
    if not isinstance(models, dict):
        raise LearnedModelArtifactError("learned model artifact has no model map")
    for key, model in models.items():
        if not isinstance(model, dict):
            raise LearnedModelArtifactError(f"invalid learned model key: {key}")
        feature_signature = str(model.get("feature_signature", ""))
        feature_indices = tuple(model.get("feature_indices", ()))
        if len(feature_signature) != expected_feature_count or any(flag not in "01" for flag in feature_signature):
            raise LearnedModelArtifactError(f"invalid feature signature for {key}")
        if feature_indices != _signature_indices(feature_signature):
            raise LearnedModelArtifactError(f"feature-index mismatch for {key}")
        if key != _model_key(str(model.get("position")), str(model.get("field_key")), feature_signature):
            raise LearnedModelArtifactError(f"invalid learned model key: {key}")
        selected_feature_count = len(feature_indices)
        if len(model.get("feature_mean", ())) != selected_feature_count:
            raise LearnedModelArtifactError(f"feature-mean size mismatch for {key}")
        if len(model.get("feature_scale", ())) != selected_feature_count:
            raise LearnedModelArtifactError(f"feature-scale size mismatch for {key}")
        if len(model.get("coefficients", ())) != selected_feature_count + 1:
            raise LearnedModelArtifactError(f"coefficient size mismatch for {key}")
        field_type = str(model.get("field_type"))
        if field_type not in FIELD_RANGES:
            raise LearnedModelArtifactError(f"invalid field type for {key}: {field_type}")
        if (model.get("minimum"), model.get("maximum")) != FIELD_RANGES[field_type]:
            raise LearnedModelArtifactError(f"field range mismatch for {key}")
    return artifact


def predict_learned_fields(
    artifact: Mapping[str, Any],
    *,
    position: str,
    feature_values: Sequence[float],
) -> dict[str, Any]:
    ordered_columns = tuple(artifact["feature_contract"]["ordered_columns"])
    values = np.asarray(tuple(feature_values), dtype=np.float64)
    if values.shape != (len(ordered_columns),):
        return {
            "status": "unresolved_runtime_feature_shape",
            "position": position,
            "values": {},
            "raw_values": {},
            "old_generator_fallback_used": False,
        }
    available_signature = _feature_signature(values)
    raw_values: dict[str, float] = {}
    final_values: dict[str, int] = {}
    routing_signatures: dict[str, str] = {}
    missing_model_fields: list[str] = []
    models_by_field: dict[str, list[Mapping[str, Any]]] = {field_key: [] for field_key in artifact["target_fields"]}
    for model in artifact["models"].values():
        if str(model["position"]) == position:
            models_by_field[str(model["field_key"])].append(model)
    for field_key in artifact["target_fields"]:
        candidates = [
            model
            for model in models_by_field[field_key]
            if _signature_is_available(str(model["feature_signature"]), available_signature)
        ]
        if not candidates:
            missing_model_fields.append(field_key)
            continue
        model = max(
            candidates,
            key=lambda candidate: (
                len(candidate["feature_indices"]),
                int(candidate["training_count"]),
                str(candidate["feature_signature"]),
            ),
        )
        feature_indices = np.asarray(model["feature_indices"], dtype=np.int64)
        selected_values = values[feature_indices]
        fitted = {
            "feature_mean": np.asarray(model["feature_mean"], dtype=np.float64),
            "feature_scale": np.asarray(model["feature_scale"], dtype=np.float64),
            "coefficients": np.asarray(model["coefficients"], dtype=np.float64),
        }
        raw = float(_predict(fitted, selected_values.reshape(1, -1))[0])
        raw_values[field_key] = raw
        final_values[field_key] = int(np.rint(np.clip(raw, model["minimum"], model["maximum"])))
        routing_signatures[field_key] = str(model["feature_signature"])
    if missing_model_fields:
        return {
            "status": "unresolved_no_compatible_feature_subset",
            "position": position,
            "available_signature": available_signature,
            "missing_model_fields": sorted(missing_model_fields),
            "values": {},
            "raw_values": {},
            "old_generator_fallback_used": False,
        }
    return {
        "status": "ok",
        "position": position,
        "available_signature": available_signature,
        "routing_signatures": dict(sorted(routing_signatures.items())),
        "values": dict(sorted(final_values.items())),
        "raw_values": dict(sorted(raw_values.items())),
        "old_generator_fallback_used": False,
    }


def predict_learned_fields_for_positions(
    artifact: Mapping[str, Any],
    *,
    position_weights: Sequence[tuple[str, float]],
    feature_values: Sequence[float],
) -> dict[str, Any]:
    rows = tuple((str(position), float(weight)) for position, weight in position_weights)
    if not rows or len({position for position, _weight in rows}) != len(rows):
        return {
            "status": "unresolved_position_weights",
            "position_weights": rows,
            "values": {},
            "raw_values": {},
            "old_generator_fallback_used": False,
        }
    if any(position not in POSITIONS or not math.isfinite(weight) or weight <= 0.0 for position, weight in rows):
        return {
            "status": "unresolved_position_weights",
            "position_weights": rows,
            "values": {},
            "raw_values": {},
            "old_generator_fallback_used": False,
        }
    total = sum(weight for _position, weight in rows)
    normalized = tuple((position, weight / total) for position, weight in rows)
    predictions = []
    for position, weight in normalized:
        prediction = predict_learned_fields(artifact, position=position, feature_values=feature_values)
        if prediction["status"] != "ok":
            prediction["position_weights"] = normalized
            return prediction
        predictions.append((weight, prediction))

    target_fields = tuple(artifact["target_fields"])
    model_by_field = {
        str(model["field_key"]): model
        for model in artifact["models"].values()
        if str(model["position"]) == normalized[0][0]
    }
    raw_values = {
        field_key: sum(weight * float(prediction["raw_values"][field_key]) for weight, prediction in predictions)
        for field_key in target_fields
    }
    final_values = {
        field_key: int(
            np.rint(
                np.clip(
                    raw,
                    model_by_field[field_key]["minimum"],
                    model_by_field[field_key]["maximum"],
                )
            )
        )
        for field_key, raw in raw_values.items()
    }
    return {
        "status": "ok",
        "position_weights": normalized,
        "values": dict(sorted(final_values.items())),
        "raw_values": dict(sorted(raw_values.items())),
        "old_generator_fallback_used": False,
    }


def predict_learned_fields_from_evidence(
    artifact: Mapping[str, Any],
    *,
    position_weights: Sequence[tuple[str, float]],
    evidence: Any,
) -> dict[str, Any]:
    return predict_learned_fields_for_positions(
        artifact,
        position_weights=position_weights,
        feature_values=runtime_player_feature_vector(evidence),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic reloadable Option C candidate model artifact")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pool", type=Path, default=None)
    parser.add_argument("--source", type=Path, default=None)
    args = parser.parse_args()
    result = write_learned_model_artifact(args.output, args.pool, source_path=args.source)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
