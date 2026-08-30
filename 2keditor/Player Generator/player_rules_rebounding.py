from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import statistics
from typing import Any

from player_evidence import PlayerEvidence


# Percentile -> value ladders taken from the ATD committee sheet's Putback scale:
# NBA Norm 10-35, Interior Finisher 35-55, Specialist 60-65, Absolute Cap 70. The
# rank quartiles are laid on the norm band (p25 -> 10, p50 -> 22, p75 -> 35) and the
# upper tail walks the sheet's named tiers to the cap, so the curve reproduces the
# committee scale instead of the captured-roster distribution it used to carry.
_PUTBACK_CURVE: tuple[tuple[float, float], ...] = (
    (0.000, 0.00),
    (0.010, 0.00),
    (0.050, 3.00),
    (0.100, 5.00),
    (0.250, 10.00),
    (0.500, 22.00),
    (0.750, 35.00),
    (0.900, 45.00),
    (0.950, 55.00),
    (0.975, 60.00),
    (0.990, 65.00),
    (0.995, 68.00),
    (1.000, 70.00),
)

# PUTBACKDUNK is a separate live 2K26 field that the committee sheet does not name;
# it is a slice of Putback and inherits its cap. The captures put it at roughly 85%
# of Putback at the median (32.2 vs 38.0 on the old pool ladder), so the ATD Putback
# ladder is carried over at that ratio and clipped to the same cap.
_PUTBACK_DUNK_CURVE: tuple[tuple[float, float], ...] = (
    (0.000, 0.00),
    (0.010, 0.00),
    (0.050, 2.50),
    (0.100, 4.25),
    (0.250, 8.50),
    (0.500, 18.70),
    (0.750, 29.75),
    (0.900, 38.25),
    (0.950, 46.75),
    (0.975, 51.00),
    (0.990, 55.25),
    (0.995, 57.80),
    (1.000, 59.50),
)

# Empirical body quantiles from the same 1,261 captured packages. These are
# continuous calibration axes, not position bands or historical body templates.
_POOL_HEIGHT_PERCENTILES: tuple[tuple[float, float], ...] = (
    (64.0, 0.00),
    (71.0, 0.05),
    (72.0, 0.10),
    (74.0, 0.25),
    (77.0, 0.50),
    (80.0, 0.75),
    (82.0, 0.90),
    (83.0, 0.95),
    (90.0, 1.00),
)
_POOL_WEIGHT_PERCENTILES: tuple[tuple[float, float], ...] = (
    (115.0, 0.00),
    (170.0, 0.05),
    (175.0, 0.10),
    (185.29, 0.25),
    (205.0, 0.50),
    (220.0, 0.75),
    (237.0, 0.90),
    (249.0, 0.95),
    (310.0, 1.00),
)

_POSITION_INTERIOR_SCORE: dict[str, float] = {
    "PG": 0.00,
    "G": 0.10,
    "SG": 0.20,
    "SF": 0.48,
    "F": 0.60,
    "PF": 0.78,
    "C": 1.00,
}

# Distinct sparse-era models prevent one generic rebound baseline from being
# written into five semantically different fields. All coefficients are smooth
# context weights. The 2026 Pool is the 1.0 era endpoint; 1947 is the 0.0
# endpoint, so sparse 1947 evidence cannot reach an unsupported elite extreme.
_SPARSE_CONTEXT_MODELS: dict[str, tuple[float, float, float, float, float]] = {
    "offensive_rebound": (0.18, 0.52, 0.18, 0.08, 0.04),
    "defensive_rebound": (0.20, 0.48, 0.22, 0.06, 0.04),
    "putback": (0.25, 0.30, 0.16, 0.11, 0.18),
    "putback_dunk": (0.06, 0.28, 0.16, 0.06, 0.44),
}

_POSITION_PERCENT_KEYS: tuple[tuple[str, str], ...] = (
    ("PG", "pg_percent"),
    ("SG", "sg_percent"),
    ("SF", "sf_percent"),
    ("PF", "pf_percent"),
    ("C", "c_percent"),
)


@dataclass(frozen=True)
class _RankSignal:
    value: float
    population: tuple[float, ...]
    evidence_keys: tuple[str, ...]
    source_label: str
    historical_substitute: str | None = None


@dataclass(frozen=True)
class _SparseReboundContext:
    position: float
    body: float
    role: float
    era: float
    evidence_keys: tuple[str, ...]


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _source(evidence: PlayerEvidence, namespace: str) -> Mapping[str, Any]:
    value = getattr(evidence, namespace, None)
    return value if isinstance(value, Mapping) else {}


def _source_number(evidence: PlayerEvidence, source_path: str) -> float | None:
    namespace, separator, key = source_path.partition(".")
    if not separator:
        return None
    return _optional_number(_source(evidence, namespace).get(key))


def _row_number(row: Mapping[str, Any], paths: Sequence[str]) -> float | None:
    for path in paths:
        value = _optional_number(row.get(path))
        if value is not None:
            return value
    return None


def _usable_games(evidence: PlayerEvidence) -> bool:
    games = _source_number(evidence, "per_game.g")
    return games is not None and games > 0.0


def _row_has_usable_games(row: Mapping[str, Any]) -> bool:
    games = _row_number(row, ("player_per_game.g", "per_game.g"))
    return games is not None and games > 0.0


def _usable_rows(
    evidence: PlayerEvidence,
    league_player_rows: Iterable[dict[str, Any]] | None,
) -> tuple[Mapping[str, Any], ...]:
    return tuple(row for row in (league_player_rows or ()) if _row_has_usable_games(row))


def _midrank_percentile(value: float, population: Sequence[float]) -> float | None:
    ordered = sorted(number for number in population if number >= 0.0)
    if not ordered:
        return None
    left = bisect_left(ordered, value)
    right = bisect_right(ordered, value)
    return (left + right) / (2.0 * len(ordered))


def _curve_value(percentile: float, curve: Sequence[tuple[float, float]]) -> int:
    bounded = max(0.0, min(1.0, percentile))
    for index in range(1, len(curve)):
        right_percentile, right_value = curve[index]
        if bounded > right_percentile:
            continue
        left_percentile, left_value = curve[index - 1]
        width = right_percentile - left_percentile
        if width <= 0.0:
            return int(round(right_value))
        share = (bounded - left_percentile) / width
        return int(round(left_value + (right_value - left_value) * share))
    return int(round(curve[-1][1]))


def _rank_attribute_value(percentile: float) -> int:
    bounded = max(0.0, min(1.0, percentile))
    return int(round(25.0 + 74.0 * bounded))


def _percentile_from_calibration(
    value: float,
    calibration: Sequence[tuple[float, float]],
) -> float:
    if value <= calibration[0][0]:
        return calibration[0][1]
    for index in range(1, len(calibration)):
        right_value, right_percentile = calibration[index]
        if value > right_value:
            continue
        left_value, left_percentile = calibration[index - 1]
        width = right_value - left_value
        if width <= 0.0:
            return right_percentile
        share = (value - left_value) / width
        return left_percentile + (right_percentile - left_percentile) * share
    return calibration[-1][1]


def _raw_position_tokens(value: Any) -> tuple[str, ...]:
    text = str(value or "").upper().replace("/", "-").replace(" ", "")
    return tuple(token for token in text.split("-") if token in _POSITION_INTERIOR_SCORE)


def _position_family(token: str) -> str:
    if token in {"PG", "SG", "G"}:
        return "G"
    if token in {"SF", "PF", "F"}:
        return "F"
    return token


def _sparse_position_context(evidence: PlayerEvidence) -> tuple[float, tuple[str, ...]] | None:
    season_tokens = _raw_position_tokens(_source(evidence, "season_info").get("pos"))
    identity_tokens = _raw_position_tokens(_source(evidence, "identity").get("pos"))
    tokens = list(season_tokens or identity_tokens)
    if season_tokens:
        for token in identity_tokens:
            if token in tokens:
                continue
            if token in {"G", "F"} and any(_position_family(existing) == token for existing in tokens):
                continue
            tokens.append(token)
            if len(tokens) == 2:
                break
    if not tokens:
        return None
    primary = _POSITION_INTERIOR_SCORE[tokens[0]]
    position = primary
    if len(tokens) > 1:
        secondary = _POSITION_INTERIOR_SCORE[tokens[1]]
        position = 0.72 * primary + 0.28 * secondary
    keys: list[str] = []
    if season_tokens:
        keys.append("season_info.pos")
    if identity_tokens:
        keys.append("identity.pos")
    keys.append("position_context=exact_primary_secondary_continuous_blend_0.72_0.28")
    return position, tuple(keys)


def _primary_position_is_guard(evidence: PlayerEvidence) -> bool:
    season_tokens = _raw_position_tokens(_source(evidence, "season_info").get("pos"))
    identity_tokens = _raw_position_tokens(_source(evidence, "identity").get("pos"))
    tokens = season_tokens or identity_tokens
    return bool(tokens and _position_family(tokens[0]) == "G")


def _sparse_body_context(evidence: PlayerEvidence) -> tuple[float, tuple[str, ...]] | None:
    values: list[float] = []
    keys: list[str] = []
    height = _source_number(evidence, "identity.ht_in_in")
    if height is not None and height > 0.0:
        values.append(_percentile_from_calibration(height, _POOL_HEIGHT_PERCENTILES))
        keys.append("identity.ht_in_in")
    weight = _source_number(evidence, "identity.wt")
    if weight is not None and weight > 0.0:
        values.append(_percentile_from_calibration(weight, _POOL_WEIGHT_PERCENTILES))
        keys.append("identity.wt")
    if not values:
        return None
    keys.append("body_context=continuous_2026_pool_height_weight_percentiles")
    return sum(values) / len(values), tuple(keys)


def _ratio_rank(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    player_path: str,
    team_path: str,
    player_row_paths: Sequence[str],
    team_row_paths: Sequence[str],
) -> float | None:
    player_value = _source_number(evidence, player_path)
    team_value = _source_number(evidence, team_path)
    if player_value is None or player_value < 0.0 or team_value is None or team_value <= 0.0:
        return None
    population: list[float] = []
    for row in rows:
        candidate_player = _row_number(row, player_row_paths)
        candidate_team = _row_number(row, team_row_paths)
        if candidate_player is None or candidate_player < 0.0 or candidate_team is None or candidate_team <= 0.0:
            continue
        population.append(candidate_player / candidate_team)
    return _midrank_percentile(player_value / team_value, population)


def _sparse_role_context(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[float, tuple[str, ...]] | None:
    # Ordered substitutes keep missing historical columns from silently changing
    # weights: FGA share is preferred, then scoring share, then schedule share.
    specs = (
        (
            "per_game.fga_per_game",
            "team_stats_per_game.fga_per_game",
            ("player_per_game.fga_per_game",),
            ("team_stats_per_game.fga_per_game",),
            "fga_team_share_rank",
        ),
        (
            "per_game.pts_per_game",
            "team_stats_per_game.pts_per_game",
            ("player_per_game.pts_per_game",),
            ("team_stats_per_game.pts_per_game",),
            "points_team_share_rank",
        ),
        (
            "per_game.g",
            "team_stats_per_game.g",
            ("player_per_game.g",),
            ("team_stats_per_game.g",),
            "schedule_share_rank",
        ),
    )
    for player_path, team_path, player_rows, team_rows, label in specs:
        percentile = _ratio_rank(
            evidence,
            rows,
            player_path=player_path,
            team_path=team_path,
            player_row_paths=player_rows,
            team_row_paths=team_rows,
        )
        if percentile is not None:
            return percentile, (player_path, team_path, f"role_source={label}")
    return None


def _sparse_rebound_context(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
) -> _SparseReboundContext | None:
    if not _usable_games(evidence):
        return None
    position = _sparse_position_context(evidence)
    body = _sparse_body_context(evidence)
    role = _sparse_role_context(evidence, rows)
    season = int(getattr(evidence, "season", 0) or 0)
    if position is None or body is None or role is None or season <= 0:
        return None
    position_value, position_keys = position
    body_value, body_keys = body
    role_value, role_keys = role
    era = max(0.0, min(1.0, (season - 1947.0) / (2026.0 - 1947.0)))
    return _SparseReboundContext(
        position=position_value,
        body=body_value,
        role=role_value,
        era=era,
        evidence_keys=(
            "per_game.g",
            *position_keys,
            *body_keys,
            *role_keys,
            "season_info.season",
            "era_context=continuous_1947_to_2026_pool_capture_endpoint",
        ),
    )


def _sparse_context_result(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    field: str,
    curve: Sequence[tuple[float, float]] | None,
    source_rule: str,
    unavailable_direct_source: str,
) -> dict[str, Any] | None:
    context = _sparse_rebound_context(evidence, rows)
    if context is None:
        return None
    intercept, position_weight, body_weight, role_weight, era_weight = _SPARSE_CONTEXT_MODELS[field]
    score = max(
        0.0,
        min(
            1.0,
            intercept
            + position_weight * context.position
            + body_weight * context.body
            + role_weight * context.role
            + era_weight * context.era,
        ),
    )
    return {
        "value": _rank_attribute_value(score) if curve is None else _curve_value(score, curve),
        "score": score,
        "source_rule": f"{source_rule}_field_specific_context_substitute",
        "evidence_keys": tuple(
            dict.fromkeys(
                (
                    *context.evidence_keys,
                    f"unavailable_direct_source={unavailable_direct_source}",
                    "substitute_source=exact_position_secondary+pool_scaled_body+era_relative_role+season",
                    "validity=conservative_context_only; no direct rebound recovery or putback attempt claim",
                    (
                        f"context_model={field}:intercept={intercept:.2f},position={position_weight:.2f},"
                        f"body={body_weight:.2f},role={role_weight:.2f},era={era_weight:.2f}"
                    ),
                    "pool_calibration_sha256=0acfd7ab0560e563737f743c9c1a6b1ccbd59c5e4415d2f32d9360aaea7dfac9",
                    *(
                        ("mapping=round(25+74*same_season_same_league_rank_score)",)
                        if curve is None
                        else ()
                    ),
                    "identity_features=position_and_body_only; player_name_and_id_excluded",
                )
            )
        ),
    }


def _direct_signal(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    source_path: str,
    row_paths: Sequence[str],
    source_label: str,
    historical_substitute: str | None = None,
) -> _RankSignal | None:
    value = _source_number(evidence, source_path)
    if value is None or value < 0.0:
        return None
    population = tuple(
        candidate
        for row in rows
        if (candidate := _row_number(row, row_paths)) is not None and candidate >= 0.0
    )
    if not population:
        return None
    return _RankSignal(
        value=value,
        population=population,
        evidence_keys=(source_path,),
        source_label=source_label,
        historical_substitute=historical_substitute,
    )


def _share_signal(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    player_path: str,
    team_path: str,
    player_row_paths: Sequence[str],
    team_row_paths: Sequence[str],
    source_label: str,
    historical_substitute: str | None = None,
) -> _RankSignal | None:
    player_value = _source_number(evidence, player_path)
    team_value = _source_number(evidence, team_path)
    if player_value is None or player_value < 0.0 or team_value is None or team_value <= 0.0:
        return None
    population: list[float] = []
    for row in rows:
        candidate_player = _row_number(row, player_row_paths)
        candidate_team = _row_number(row, team_row_paths)
        if candidate_player is None or candidate_player < 0.0 or candidate_team is None or candidate_team <= 0.0:
            continue
        population.append(candidate_player / candidate_team)
    if not population:
        return None
    return _RankSignal(
        value=player_value / team_value,
        population=tuple(population),
        evidence_keys=(player_path, team_path),
        source_label=source_label,
        historical_substitute=historical_substitute,
    )


def _rebound_signal(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    side: str,
) -> _RankSignal | None:
    """Use only the requested rebound-rate evidence: ORB% or DRB%."""
    if side not in {"orb", "drb"}:
        raise ValueError(f"unsupported rebound side: {side}")
    return _direct_signal(
        evidence,
        rows,
        source_path=f"advanced.{side}_percent",
        row_paths=(f"advanced.{side}_percent",),
        source_label=f"direct_{side}_percent",
    )


def _historical_rebound_signal(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    side: str,
) -> _RankSignal | None:
    if side not in {"orb", "drb"}:
        raise ValueError(f"unsupported rebound side: {side}")

    side_name = "offensive" if side == "orb" else "defensive"
    direct_specs = (
        (
            f"advanced.{side}_percent",
            (f"advanced.{side}_percent",),
            f"direct_{side}_percent",
        ),
        (
            f"per_100.{side}_per_100_poss",
            (f"player_per_100_poss.{side}_per_100_poss",),
            f"direct_{side}_per_100",
        ),
        (
            f"per_36.{side}_per_36_min",
            (f"player_per_36_min.{side}_per_36_min",),
            f"direct_{side}_per_36",
        ),
    )
    for source_path, row_paths, source_label in direct_specs:
        signal = _direct_signal(
            evidence,
            rows,
            source_path=source_path,
            row_paths=row_paths,
            source_label=source_label,
        )
        if signal is not None:
            return signal

    split_share = _share_signal(
        evidence,
        rows,
        player_path=f"per_game.{side}_per_game",
        team_path=f"team_stats_per_game.{side}_per_game",
        player_row_paths=(f"player_per_game.{side}_per_game",),
        team_row_paths=(f"team_stats_per_game.{side}_per_game",),
        source_label=f"direct_{side}_team_share",
    )
    if split_share is not None:
        return split_share

    unavailable = f"individual {side_name} rebound split/rate is unavailable"
    total_specs = (
        (
            "advanced.trb_percent",
            ("advanced.trb_percent",),
            "historical_total_rebound_percent",
            f"{unavailable}; TRB% is valid demonstrated all-glass recovery rate",
        ),
        (
            "per_100.trb_per_100_poss",
            ("player_per_100_poss.trb_per_100_poss",),
            "historical_total_rebound_per_100",
            f"{unavailable}; TRB per 100 is valid pace-normalized demonstrated recovery",
        ),
        (
            "per_36.trb_per_36_min",
            ("player_per_36_min.trb_per_36_min",),
            "historical_total_rebound_per_36",
            f"{unavailable}; TRB per 36 is valid minutes-normalized demonstrated recovery",
        ),
    )
    for source_path, row_paths, source_label, substitute in total_specs:
        signal = _direct_signal(
            evidence,
            rows,
            source_path=source_path,
            row_paths=row_paths,
            source_label=source_label,
            historical_substitute=substitute,
        )
        if signal is not None:
            return signal

    return _share_signal(
        evidence,
        rows,
        player_path="per_game.trb_per_game",
        team_path="team_stats_per_game.trb_per_game",
        player_row_paths=("player_per_game.trb_per_game",),
        team_row_paths=("team_stats_per_game.trb_per_game",),
        source_label="historical_total_rebound_team_share",
        historical_substitute=(
            f"{unavailable}; player/team TRB share is the documented 1951-era substitute "
            "because player minutes and split rebounds are absent while both team and player totals exist"
        ),
    )


def _historical_win_share_rank(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    side: str,
) -> tuple[float, tuple[str, ...]] | None:
    if side not in {"orb", "drb"}:
        raise ValueError(f"unsupported rebound side: {side}")
    field = "ows" if side == "orb" else "dws"
    source_path = f"advanced.{field}"
    value = _source_number(evidence, source_path)
    if value is None:
        return None
    population = sorted(
        candidate
        for row in rows
        if (candidate := _row_number(row, (source_path,))) is not None
    )
    if not population:
        return None
    left = bisect_left(population, value)
    right = bisect_right(population, value)
    rank = (left + right) / (2.0 * len(population))
    return rank, (source_path, f"{field}_same_season_same_league_rank={rank:.8f}")


def _pretracking_attribute_result(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    *,
    side: str,
    source_rule: str,
    rebound_signal: _RankSignal | None,
) -> dict[str, Any] | None:
    position = _sparse_position_context(evidence)
    if position is None:
        return None
    position_score, position_keys = position

    components: list[tuple[float, float, str]] = [(position_score, 0.50, "position")]
    evidence_keys: list[str] = ["per_game.g", *position_keys]
    if rebound_signal is not None:
        rebound_score = _midrank_percentile(rebound_signal.value, rebound_signal.population)
        if rebound_score is None:
            return None
        components.append((rebound_score, 0.35, "demonstrated_total_rebound"))
        evidence_keys.extend(
            (
                *rebound_signal.evidence_keys,
                f"demonstrated_total_rebound_rank={rebound_score:.8f}",
                f"source_mode={rebound_signal.source_label}",
            )
        )
        if rebound_signal.historical_substitute:
            evidence_keys.append(f"historical_substitute={rebound_signal.historical_substitute}")
    else:
        body = _sparse_body_context(evidence)
        if body is None:
            return None
        body_score, body_keys = body
        components.append((body_score, 0.35, "body"))
        evidence_keys.extend((*body_keys, f"body_rank={body_score:.8f}"))

    win_shares = _historical_win_share_rank(evidence, rows, side=side)
    if win_shares is not None:
        win_share_score, win_share_keys = win_shares
        components.append((win_share_score, 0.15, "ows" if side == "orb" else "dws"))
        evidence_keys.extend(win_share_keys)
    else:
        evidence_keys.append(
            f"missing_{'ows' if side == 'orb' else 'dws'}_policy=omit_and_renormalize_available_authored_weights"
        )

    available_weight = sum(weight for _score, weight, _label in components)
    if available_weight <= 0.0:
        return None
    score = sum(component_score * weight for component_score, weight, _label in components) / available_weight
    if rebound_signal is None and _primary_position_is_guard(evidence):
        raw_inferred_value = _rank_attribute_value(score)
        score *= 1.10
        scaled_uncapped_value = _rank_attribute_value(score)
        guard_ceiling_score = (55.0 - 25.0) / 74.0
        score = min(score, guard_ceiling_score)
        normalized_guard_score = score / guard_ceiling_score
        if normalized_guard_score < 0.90:
            normalized_guard_score = 0.90 * ((normalized_guard_score / 0.90) ** 4)
            score = guard_ceiling_score * normalized_guard_score
        curved_value = _rank_attribute_value(score)
        evidence_keys.extend(
            (
                "no_total_rebound_primary_guard_distribution_scale=1.10",
                "no_total_rebound_primary_guard_ceiling=55",
                "no_total_rebound_primary_guard_drop_curve=preserve_top_10_percent_of_25_to_55_span;below_90_percent_use_fourth_power",
                f"no_total_rebound_primary_guard_raw_value={raw_inferred_value}",
                f"no_total_rebound_primary_guard_scaled_uncapped_value={scaled_uncapped_value}",
                f"no_total_rebound_primary_guard_curved_value={curved_value}",
                "first_tracked_anchor=1951_NBA_TRB;1947_BAA_guard_overlap=7;max_TRB_per_game=5.0",
            )
        )
    component_weights = ",".join(f"{label}:{weight:.2f}" for _score, weight, label in components)
    evidence_keys.extend(
        (
            f"pre_tracking_rebound_weights={component_weights}",
            f"available_weight={available_weight:.2f}",
            "pre_tracking_guard_control=absolute_primary_secondary_position_weight_0.50;no_TRB_primary_guard_ceiling_55",
            "pre_tracking_role_and_scoring_share_excluded=true",
            "comparison_scope=same_season_same_league_gp_positive",
            "mapping=round(25+74*same_season_same_league_rank_score)",
        )
    )
    return {
        "value": _rank_attribute_value(score),
        "score": score,
        "source_rule": f"{source_rule}_pre_tracking_position_win_shares",
        "evidence_keys": tuple(dict.fromkeys(evidence_keys)),
    }


def _historical_sparse_rebound_context_allowed(
    rows: Sequence[Mapping[str, Any]],
    *,
    required_sides: tuple[str, ...],
) -> bool:
    """Use the old context rule when an entire era lacks a required split rate."""
    return any(
        not any(
            _row_number(row, (f"advanced.{side}_percent",)) is not None
            for row in rows
        )
        for side in required_sides
    )


def _parse_position_label(value: Any) -> tuple[str, ...]:
    text = str(value or "").upper().replace("/", "-").replace(" ", "")
    if not text:
        return ()
    positions: list[str] = []
    for token in text.split("-"):
        expanded = {
            "PG": ("PG",),
            "SG": ("SG",),
            "SF": ("SF",),
            "PF": ("PF",),
            "C": ("C",),
            "G": ("PG", "SG"),
            "F": ("SF", "PF"),
        }.get(token, ())
        for position in expanded:
            if position not in positions:
                positions.append(position)
    return tuple(positions)


def _evidence_positions(evidence: PlayerEvidence) -> tuple[str, ...]:
    percentages = []
    play_by_play = _source(evidence, "play_by_play")
    for position, key in _POSITION_PERCENT_KEYS:
        value = _optional_number(play_by_play.get(key))
        if value is not None and value > 0.0:
            percentages.append((value, position))
    if percentages:
        percentages.sort(reverse=True)
        return tuple(position for _, position in percentages[:2])
    for namespace in ("season_info", "identity"):
        positions = _parse_position_label(_source(evidence, namespace).get("pos"))
        if positions:
            return positions
    return ()


def _row_positions(row: Mapping[str, Any]) -> tuple[str, ...]:
    percentages = []
    for position, key in _POSITION_PERCENT_KEYS:
        value = _row_number(row, (f"player_play_by_play.{key}",))
        if value is not None and value > 0.0:
            percentages.append((value, position))
    if percentages:
        percentages.sort(reverse=True)
        return tuple(position for _, position in percentages[:2])
    for path in ("player_season_info.pos", "player_per_game.pos", "player_info.pos"):
        positions = _parse_position_label(row.get(path))
        if positions:
            return positions
    return ()


def _attribute_result(
    evidence: PlayerEvidence,
    league_player_rows: Iterable[dict[str, Any]] | None,
    *,
    side: str,
    source_rule: str,
) -> dict[str, Any] | None:
    if not _usable_games(evidence):
        return None
    rows = _usable_rows(evidence, league_player_rows)
    signal = _rebound_signal(evidence, rows, side=side)
    if signal is None:
        if not _historical_sparse_rebound_context_allowed(rows, required_sides=(side,)):
            return None
        return _pretracking_attribute_result(
            evidence,
            rows,
            side=side,
            source_rule=source_rule,
            rebound_signal=_historical_rebound_signal(evidence, rows, side=side),
        )
    performance = _midrank_percentile(signal.value, signal.population)
    if performance is None:
        return None
    percentile, minutes_evidence = _minutes_context_adjustment(evidence, rows, signal, performance)
    return {
        "value": _rank_attribute_value(percentile),
        "score": percentile,
        "source_rule": source_rule,
        "evidence_keys": (
            "per_game.g",
            *signal.evidence_keys,
            *minutes_evidence,
            f"source_mode={signal.source_label}",
            "comparison_scope=same_season_same_league_gp_positive",
            "rebound_contract=ORB_percent_for_offense;DRB_percent_for_defense;minutes_only_for_low_volume_shrink",
            "position_and_MPG_are_context_for_low_volume_shrink_only",
            "height_weight_raw_rebounds_and_total_rebound_rate_excluded=true",
            "mapping=round(25+74*same_season_same_league_rank_score)",
        ),
    }


def derive_attribute_offensiverebound(
    evidence: PlayerEvidence,
    *,
    league_player_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    return _attribute_result(
        evidence,
        league_player_rows,
        side="orb",
        source_rule="derive_attribute_offensiverebound",
    )


def derive_attribute_defensiverebound(
    evidence: PlayerEvidence,
    *,
    league_player_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    return _attribute_result(
        evidence,
        league_player_rows,
        side="drb",
        source_rule="derive_attribute_defensiverebound",
    )


def _direct_putback_signal(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
) -> _RankSignal | None:
    """Return demonstrated offensive-glass activity, never a TRB substitute."""
    signal = _rebound_signal(evidence, rows, side="orb")
    if signal is None or signal.historical_substitute is not None:
        return None
    return signal


def _minutes_context_adjustment(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
    signal: _RankSignal,
    performance: float,
) -> tuple[float, tuple[str, ...]]:
    """Shrink low-minute ORB%/DRB% outliers toward position/MPG context."""
    side = "orb" if signal.source_label == "direct_orb_percent" else "drb" if signal.source_label == "direct_drb_percent" else ""
    if not side:
        return performance, ("minutes_context=not_applied;source_is_not_ORB_or_DRB_percent",)
    games = _source_number(evidence, "per_game.g")
    mpg = _source_number(evidence, "per_game.mp_per_game")
    total_minutes = _source_number(evidence, "totals.mp")
    if total_minutes is None and games is not None and mpg is not None:
        total_minutes = games * mpg
    positions = set(_evidence_positions(evidence))
    if mpg is None or mpg < 0.0 or total_minutes is None or total_minutes < 0.0 or not positions:
        return performance, ("minutes_context=not_applied;missing_minutes_or_position",)

    peers: list[tuple[float, float, float]] = []
    for row in rows:
        if not positions.intersection(_row_positions(row)):
            continue
        peer_rate = _row_number(row, (f"advanced.{side}_percent",))
        peer_games = _row_number(row, ("player_per_game.g", "per_game.g"))
        peer_mpg = _row_number(row, ("player_per_game.mp_per_game", "per_game.mp_per_game"))
        peer_minutes = _row_number(row, ("player_totals.mp", "totals.mp"))
        if peer_minutes is None and peer_games is not None and peer_mpg is not None:
            peer_minutes = peer_games * peer_mpg
        if peer_rate is None or peer_mpg is None or peer_minutes is None or peer_minutes < 0.0:
            continue
        peer_percentile = _midrank_percentile(peer_rate, signal.population)
        if peer_percentile is not None:
            peers.append((peer_mpg, peer_minutes, peer_percentile))
    if len(peers) < 5:
        return performance, ("minutes_context=not_applied;fewer_than_5_position_peers",)

    mean_x = sum(item[0] for item in peers) / len(peers)
    mean_y = sum(item[2] for item in peers) / len(peers)
    variance = sum((item[0] - mean_x) ** 2 for item in peers)
    slope = sum((item[0] - mean_x) * (item[2] - mean_y) for item in peers) / variance if variance > 0.0 else 0.0
    baseline = max(0.0, min(1.0, mean_y + slope * (mpg - mean_x)))
    median_minutes = statistics.median(item[1] for item in peers)
    if median_minutes <= 0.0:
        return performance, ("minutes_context=not_applied;nonpositive_position_median_minutes",)
    reliability = max(0.0, min(1.0, total_minutes / median_minutes))
    adjusted = reliability * performance + (1.0 - reliability) * baseline
    return adjusted, (
        f"minutes_context=low_volume_{side.upper()}_percent_outlier_shrink",
        f"player_mpg={mpg:.8f}",
        f"player_total_minutes={total_minutes:.8f}",
        f"position_peer_median_total_minutes={median_minutes:.8f}",
        f"position_mpg_{side.upper()}_percentile_baseline={baseline:.8f}",
        f"minutes_reliability=min(1,total_minutes/position_peer_median)={reliability:.8f}",
        f"unshrunk_{side.upper()}_percentile={performance:.8f}",
        f"minutes_adjusted_{side.upper()}_percentile={adjusted:.8f}",
    )


def _normalized_assisted_rate(value: float | None) -> float | None:
    if value is None or value < 0.0:
        return None
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def _unassisted_two_makes_per_game(evidence: PlayerEvidence) -> float | None:
    assisted = _normalized_assisted_rate(_source_number(evidence, "shooting.percent_assisted_x2p_fg"))
    games = _source_number(evidence, "per_game.g")
    if assisted is None or games is None or games <= 0.0:
        return None
    two_makes = _source_number(evidence, "per_game.x2p_per_game")
    if two_makes is None:
        total_two = _source_number(evidence, "totals.x2p")
        if total_two is None:
            total_fg = _source_number(evidence, "totals.fg")
            total_three = _source_number(evidence, "totals.x3p")
            if total_fg is not None and total_three is not None:
                total_two = max(0.0, total_fg - total_three)
        if total_two is not None:
            two_makes = total_two / games
    if two_makes is None or two_makes < 0.0:
        return None
    return two_makes * (1.0 - assisted)


def _row_unassisted_two_makes_per_game(row: Mapping[str, Any]) -> float | None:
    assisted = _normalized_assisted_rate(_row_number(row, ("player_shooting.percent_assisted_x2p_fg",)))
    games = _row_number(row, ("player_per_game.g", "player_totals.g"))
    if assisted is None or games is None or games <= 0.0:
        return None
    two_makes = _row_number(row, ("player_per_game.x2p_per_game",))
    if two_makes is None:
        total_two = _row_number(row, ("player_totals.x2p",))
        if total_two is None:
            total_fg = _row_number(row, ("player_totals.fg",))
            total_three = _row_number(row, ("player_totals.x3p",))
            if total_fg is not None and total_three is not None:
                total_two = max(0.0, total_fg - total_three)
        if total_two is not None:
            two_makes = total_two / games
    if two_makes is None or two_makes < 0.0:
        return None
    return two_makes * (1.0 - assisted)


def _putback_score(
    evidence: PlayerEvidence,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[float, tuple[str, ...]] | None:
    rebound = _direct_putback_signal(evidence, rows)
    rim = _direct_signal(
        evidence,
        rows,
        source_path="shooting.percent_fga_from_x0_3_range",
        row_paths=("player_shooting.percent_fga_from_x0_3_range",),
        source_label="direct_zero_to_three_attempt_share",
    )
    unassisted_value = _unassisted_two_makes_per_game(evidence)
    unassisted_population = tuple(
        value
        for row in rows
        if (value := _row_unassisted_two_makes_per_game(row)) is not None
    )
    if rebound is None or rim is None or unassisted_value is None or not unassisted_population:
        return None
    rebound_percentile = _midrank_percentile(rebound.value, rebound.population)
    rim_percentile = _midrank_percentile(rim.value, rim.population)
    unassisted_percentile = _midrank_percentile(unassisted_value, unassisted_population)
    if rebound_percentile is None or rim_percentile is None or unassisted_percentile is None:
        return None
    adjusted_rebound, minutes_evidence = _minutes_context_adjustment(
        evidence,
        rows,
        rebound,
        rebound_percentile,
    )
    score = 0.50 * adjusted_rebound + 0.30 * rim_percentile + 0.20 * unassisted_percentile
    return score, (
        *rebound.evidence_keys,
        *rim.evidence_keys,
        "per_game.x2p_per_game|totals.x2p|totals.fg-minus-totals.x3p",
        "shooting.percent_assisted_x2p_fg",
        *minutes_evidence,
        f"minutes_adjusted_ORB_percentile={adjusted_rebound:.8f}",
        f"zero_to_three_attempt_share_percentile={rim_percentile:.8f}",
        f"unassisted_two_makes_per_game={unassisted_value:.8f}",
        f"unassisted_two_makes_per_game_percentile={unassisted_percentile:.8f}",
        "putback_formula=0.50*minutes_adjusted_ORB_percentile+0.30*zero_to_three_attempt_share_percentile+0.20*unassisted_two_makes_per_game_percentile",
        "unassisted_amount_contract=unassisted_2P_makes_per_game;public_source_has_no_unassisted_attempt_count",
    )


def derive_tendency_putback(
    evidence: PlayerEvidence,
    *,
    league_player_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not _usable_games(evidence):
        return None
    rows = _usable_rows(evidence, league_player_rows)
    scored = _putback_score(evidence, rows)
    if scored is None:
        if not _historical_sparse_rebound_context_allowed(rows, required_sides=("orb",)):
            return None
        return _sparse_context_result(
            evidence,
            rows,
            field="putback",
            curve=_PUTBACK_CURVE,
            source_rule="derive_tendency_putback",
            unavailable_direct_source=(
                "advanced.orb_percent+shooting.percent_fga_from_x0_3_range+"
                "shooting.percent_assisted_x2p_fg"
            ),
        )
    percentile, formula_evidence = scored
    return {
        "value": _curve_value(percentile, _PUTBACK_CURVE),
        "score": percentile,
        "source_rule": "derive_tendency_putback_direct_offensive_recovery_frequency",
        "evidence_keys": (
            "per_game.g",
            *formula_evidence,
            "source_mode=ORB_percent_plus_zero_to_three_share_plus_unassisted_two_make_amount",
            "comparison_scope=same_season_same_league_gp_positive",
            "behavior_contract=offensive_recovery_plus_rim_location_plus_unassisted_finish_volume_authors_putback_opportunity",
            "historical_total_rebound_substitute=forbidden",
            "pool_calibration=field-exact Putback target distribution;765 GP-valid packages;identity=(run_id,player_index)",
            "mapping=field_exact_pool_quantile_curve",
        ),
    }


def derive_tendency_putbackdunk(
    evidence: PlayerEvidence,
    *,
    league_player_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not _usable_games(evidence):
        return None
    rows = _usable_rows(evidence, league_player_rows)
    if _putback_score(evidence, rows) is None:
        if not _historical_sparse_rebound_context_allowed(rows, required_sides=("orb",)):
            return None
        return _sparse_context_result(
            evidence,
            rows,
            field="putback_dunk",
            curve=_PUTBACK_DUNK_CURVE,
            source_rule="derive_tendency_putbackdunk",
            unavailable_direct_source=(
                "advanced.orb_percent+shooting.percent_fga_from_x0_3_range+"
                "shooting.percent_assisted_x2p_fg+literal_stationary_finish_split"
            ),
        )
    putback = derive_tendency_putback(
        evidence,
        league_player_rows=rows,  # type: ignore[arg-type] - filtered immutable mappings are valid rule rows
    )
    if putback is None:
        return None
    import player_rules_offense

    standing_dunk_rule = getattr(player_rules_offense, "derive_tendency_standingdunk")
    standing_dunk = standing_dunk_rule(evidence, league_player_rows=rows)
    if standing_dunk is None:
        return None
    stationary_finish = max(0.0, min(1.0, float(standing_dunk["value"]) / 100.0))
    putback_behavior = max(0.0, min(1.0, float(putback["score"])))
    score = 0.60 * putback_behavior + 0.40 * stationary_finish
    return {
        "value": _curve_value(score, _PUTBACK_DUNK_CURVE),
        "score": score,
        "source_rule": "derive_tendency_putbackdunk_offensive_recovery_stationary_finish_context_substitute",
        "evidence_keys": (
            "per_game.g",
            *tuple(putback["evidence_keys"]),
            *tuple(standing_dunk["evidence_keys"]),
            "comparison_scope=same_season_same_league_gp_positive",
            "formula=0.60*generated_PUTBACK_behavior_score+0.40*generated_STANDINGDUNK_tendency/100",
            "unavailable_direct_source=putback-dunk event count and literal stationary finish split",
            "substitute_source=demonstrated offensive recovery frequency plus separately authored literal STANDINGDUNK tendency",
            "validity=putback opportunity must be demonstrated; stationary-finish tendency affects dunk choice only and never creates a rebound",
            "broad_or_moving_dunk_totals_excluded=true",
            "historical_total_rebound_substitute=forbidden",
            "pool_calibration=field-exact PutbackDunk target distribution;765 GP-valid packages;identity=(run_id,player_index)",
            "mapping=field_exact_pool_quantile_curve",
        ),
    }


__all__ = [
    "derive_attribute_defensiverebound",
    "derive_attribute_offensiverebound",
    "derive_tendency_putback",
    "derive_tendency_putbackdunk",
]
