from __future__ import annotations

import random
from dataclasses import dataclass

from ..api.v1.models import AiDecisionContext, TeamAiProfile


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


@dataclass(frozen=True)
class DirectionResult:
    direction: str
    confidence: float
    trigger_factors: list[str]
    breakdown: dict[str, float]


class FranchiseDirectionEngine:
    DIRECTIONS = ("contender", "pretender", "rebuilder", "tanking", "retooling")

    @staticmethod
    def _parse_record(record: str) -> tuple[int, int]:
        raw = str(record or "").strip()
        if "-" not in raw:
            return (0, 0)
        wins_raw, losses_raw = raw.split("-", 1)
        try:
            return (max(0, int(wins_raw)), max(0, int(losses_raw)))
        except ValueError:
            return (0, 0)

    def classify(
        self,
        *,
        context: AiDecisionContext,
        profile: TeamAiProfile,
    ) -> DirectionResult:
        wins, losses = self._parse_record(context.current_record)
        games = wins + losses
        win_pct = _safe_ratio(wins, games) if games > 0 else 0.5

        roster = context.roster_assets
        avg_overall = _safe_ratio(sum(player.overall for player in roster), len(roster))
        avg_potential = _safe_ratio(sum(player.potential for player in roster), len(roster))
        avg_age = _safe_ratio(sum(player.age for player in roster), len(roster)) if roster else 26.0
        star_count = sum(1 for player in roster if player.overall >= 88)
        youth_count = sum(1 for player in roster if player.age <= 24)
        payroll = sum(player.salary for player in roster)

        avg_overall_n = _clamp(avg_overall / 100.0)
        avg_potential_n = _clamp(avg_potential / 100.0)
        youth_ratio = _safe_ratio(youth_count, len(roster))
        star_ratio = _safe_ratio(star_count, max(1, len(roster)))
        cap_pressure = _safe_ratio(payroll, max(1.0, profile.owner_profile.spending_limit))

        contender_score = (
            (win_pct * 0.44)
            + (avg_overall_n * 0.31)
            + (star_ratio * 0.18)
            + (profile.gm_personality.star_bias_weight * 0.07)
        )
        pretender_score = (
            (_clamp(1.0 - abs(win_pct - 0.55) * 3.0) * 0.45)
            + (_clamp(avg_overall_n - star_ratio) * 0.35)
            + (_clamp(cap_pressure) * 0.20)
        )
        rebuilder_score = (
            (youth_ratio * 0.35)
            + (avg_potential_n * 0.28)
            + (_clamp(1.0 - win_pct) * 0.25)
            + (profile.gm_personality.youth_development_weight * 0.12)
        )
        tanking_score = (
            (_clamp(0.52 - win_pct) * 0.8)
            + (_clamp(0.68 - avg_overall_n) * 0.35)
            + (_clamp(1.0 - profile.owner_profile.patience_level) * 0.15)
        )
        retooling_score = (
            (_clamp(1.0 - abs(win_pct - 0.5) * 3.2) * 0.34)
            + (_clamp(0.9 - cap_pressure) * 0.23)
            + (_clamp((avg_potential_n + youth_ratio) / 2.0) * 0.23)
            + (_clamp(profile.gm_personality.risk_tolerance) * 0.20)
        )

        trigger_factors: list[str] = []
        dynasty_bias = 0.0
        if context.rings_last_6_years >= 3:
            dynasty_bias = 0.12
            trigger_factors.append("dynasty_preservation")
        drought_bias = 0.0
        if context.title_drought_years >= 10:
            drought_bias = 0.14
            trigger_factors.append("drought_desperation")

        contender_score += dynasty_bias + (drought_bias * 0.55)
        retooling_score += dynasty_bias * 0.6
        rebuilder_score += (profile.owner_profile.patience_level * 0.08)
        tanking_score += (drought_bias * 0.35) - (profile.owner_profile.championship_demand * 0.10)
        pretender_score += (_clamp(1.0 - profile.owner_profile.patience_level) * 0.08)

        if avg_age <= 24.5:
            trigger_factors.append("young_roster_curve")
        if cap_pressure >= 1.05:
            trigger_factors.append("cap_pressure")
        if star_count >= 2:
            trigger_factors.append("multi_star_core")
        if win_pct >= 0.62:
            trigger_factors.append("strong_record")
        if win_pct <= 0.35:
            trigger_factors.append("weak_record")

        scores = {
            "contender": _clamp(contender_score),
            "pretender": _clamp(pretender_score),
            "rebuilder": _clamp(rebuilder_score),
            "tanking": _clamp(tanking_score),
            "retooling": _clamp(retooling_score),
        }
        seeded_rng = random.Random(context.seed)
        ranked = sorted(scores.items(), key=lambda item: (item[1], seeded_rng.random()), reverse=True)
        top_direction, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = _clamp(0.5 + ((top_score - second_score) * 0.75))

        return DirectionResult(
            direction=top_direction,
            confidence=confidence,
            trigger_factors=sorted(set(trigger_factors)),
            breakdown={key: round(value, 5) for key, value in scores.items()},
        )
