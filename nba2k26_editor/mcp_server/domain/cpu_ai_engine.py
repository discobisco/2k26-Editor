from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from ..adapters.ai_profile_repository import AiProfileRepository
from ..adapters.team_id_resolver import TeamIdResolver
from ..api.v1.models import (
    AiDecisionContext,
    AiDraftDecisionRequest,
    AiDraftDecisionResponse,
    AiFreeAgencyDecisionRequest,
    AiFreeAgencyDecisionResponse,
    AiFranchiseDirectionRequest,
    AiFranchiseDirectionResponse,
    AiProfileResponse,
    AiTradeDecisionRequest,
    AiTradeDecisionResponse,
    GmPersonality,
    NextProfileRecommendation,
    TeamAiProfile,
)
from .franchise_direction_engine import FranchiseDirectionEngine


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


def _logistic(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


class _LruTtlComputeCache:
    def __init__(self, *, max_entries: int, ttl_seconds: int) -> None:
        self._max_entries = max(32, int(max_entries))
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._cache_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def _get_unlocked(self, key: str) -> dict[str, Any] | None:
        now = time.time()
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= now:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key, last=True)
        return copy.deepcopy(value)

    def _set_unlocked(self, key: str, value: dict[str, Any]) -> None:
        expires_at = time.time() + self._ttl_seconds
        self._entries[key] = (expires_at, copy.deepcopy(value))
        self._entries.move_to_end(key, last=True)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get_or_compute(self, key: str, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        key_lock = self._get_key_lock(key)
        with key_lock:
            with self._cache_lock:
                cached = self._get_unlocked(key)
            if cached is not None:
                return cached
            computed = compute()
            with self._cache_lock:
                self._set_unlocked(key, computed)
            return copy.deepcopy(computed)


class CpuAiEngine:
    def __init__(
        self,
        *,
        profile_repository: AiProfileRepository,
        team_resolver: TeamIdResolver,
        direction_engine: FranchiseDirectionEngine,
        default_seed: int,
        cache_max_entries: int,
        cache_ttl_seconds: int,
    ) -> None:
        self._profiles = profile_repository
        self._team_resolver = team_resolver
        self._direction_engine = direction_engine
        self._default_seed = default_seed
        self._cache = _LruTtlComputeCache(max_entries=cache_max_entries, ttl_seconds=cache_ttl_seconds)

    @staticmethod
    def _request_hash(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _cache_key(self, *, endpoint: str, team_key: str, payload: dict[str, Any], seed: int) -> str:
        return f"{endpoint}|{team_key}|{seed}|{self._request_hash(payload)}"

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

    def resolve_profile(self, *, context: AiDecisionContext) -> TeamAiProfile:
        team_key = self._team_resolver.normalize(context.team_id, season=context.season)
        return self._profiles.resolve_profile(
            team_key=team_key,
            season=context.season,
            explicit_personality=context.gm_personality,
            explicit_owner=context.owner_profile,
            era=context.era,
        )

    def profile_lookup(
        self,
        *,
        team_id: str | int,
        era: str,
        season: str,
        gm_personality: GmPersonality | None = None,
    ) -> AiProfileResponse:
        team_key = self._team_resolver.normalize(team_id, season=season)
        profile = self._profiles.resolve_profile(
            team_key=team_key,
            season=season,
            explicit_personality=gm_personality,
            explicit_owner=None,
            era=era,
        )
        return AiProfileResponse(
            team_key=team_key,
            season=season,
            profile=profile,
            required_context_fields=[
                "checkpoint",
                "rings_last_6_years",
                "title_drought_years",
                "media_context",
            ],
            capability_flag="cpu_ai_personality_v1",
        )

    def _common_roster_metrics(self, *, context: AiDecisionContext, profile: TeamAiProfile) -> dict[str, float]:
        roster = context.roster_assets
        wins, losses = self._parse_record(context.current_record)
        games = wins + losses
        win_pct = _safe_ratio(wins, games) if games > 0 else 0.5

        avg_overall = _safe_ratio(sum(p.overall for p in roster), len(roster))
        avg_potential = _safe_ratio(sum(p.potential for p in roster), len(roster))
        avg_age = _safe_ratio(sum(p.age for p in roster), len(roster)) if roster else 26.0
        payroll = sum(p.salary for p in roster)
        star_count = sum(1 for player in roster if player.overall >= 88)
        youth_count = sum(1 for player in roster if player.age <= 24)

        return {
            "win_pct": _clamp(win_pct),
            "avg_overall_n": _clamp(avg_overall / 100.0),
            "avg_potential_n": _clamp(avg_potential / 100.0),
            "avg_age_n": _clamp(avg_age / 40.0),
            "cap_pressure": _safe_ratio(payroll, max(1.0, profile.owner_profile.spending_limit)),
            "star_ratio": _safe_ratio(star_count, max(1, len(roster))),
            "youth_ratio": _safe_ratio(youth_count, max(1, len(roster))),
            "roster_size": float(len(roster)),
        }

    @staticmethod
    def _urgency_from_media(context: AiDecisionContext, profile: TeamAiProfile) -> float:
        media = context.media_context
        base = (
            (media.media_criticism_index * 0.42)
            + ((1.0 - media.fan_sentiment) * 0.20)
            + ((1.0 - media.recent_playoff_success) * 0.22)
            + (media.market_size_factor * 0.16)
        )
        multiplier = 0.75 + (profile.gm_personality.media_pressure_sensitivity * 0.65)
        return _clamp(base * multiplier)

    @staticmethod
    def _dynasty_drought_adjustment(
        *,
        context: AiDecisionContext,
        profile: TeamAiProfile,
    ) -> tuple[float, list[str]]:
        rules: list[str] = []
        adjustment = 0.0
        if context.rings_last_6_years >= 3:
            adjustment += 0.08 + (profile.gm_personality.loyalty_bias * 0.06)
            rules.append("dynasty_preservation")
        if context.title_drought_years >= 10:
            adjustment += 0.10 + (profile.gm_personality.risk_tolerance * 0.08)
            rules.append("drought_desperation")
        return (_clamp(adjustment, -0.25, 0.25), rules)

    @staticmethod
    def _ownership_adjustment(profile: TeamAiProfile) -> float:
        owner = profile.owner_profile
        return (
            ((owner.championship_demand - owner.patience_level) * 0.26)
            + ((owner.luxury_tax_tolerance - 0.5) * 0.16)
            + (_clamp(owner.spending_limit / 250_000_000.0) * 0.08)
        )

    @staticmethod
    def _era_adjustment(profile: TeamAiProfile) -> float:
        gm = profile.gm_personality
        era = profile.era_modifier
        return (
            ((era.trade_aggression_multiplier - 1.0) * gm.trade_frequency * 0.45)
            + ((era.star_movement_probability - 0.5) * gm.star_bias_weight * 0.20)
            + ((era.loyalty_bias_boost) * gm.loyalty_bias * 0.18)
        )

    def _build_next_profile_recommendation(
        self,
        *,
        profile: TeamAiProfile,
        context: AiDecisionContext,
        urgency: float,
        direction_hint: str,
    ) -> NextProfileRecommendation:
        gm = profile.gm_personality
        owner = profile.owner_profile

        checkpoint_boost = {"regular": 0.015, "trade_deadline": 0.05, "offseason": 0.03}.get(context.checkpoint, 0.015)
        max_delta = 0.08 if context.checkpoint == "trade_deadline" else 0.05
        drought_pressure = 0.06 if context.title_drought_years >= 10 else 0.0
        dynasty_calm = -0.04 if context.rings_last_6_years >= 3 else 0.0

        def shift(current: float, delta: float) -> float:
            bounded = max(-max_delta, min(max_delta, delta))
            return _clamp(current + bounded)

        target_trade_freq = shift(
            gm.trade_frequency,
            (urgency - 0.5) * 0.12 + checkpoint_boost + drought_pressure + dynasty_calm,
        )
        target_risk = shift(
            gm.risk_tolerance,
            (urgency - 0.45) * 0.10 + (owner.championship_demand - 0.5) * 0.05 + drought_pressure,
        )
        target_pick_weight = shift(
            gm.draft_pick_value_weight,
            -((urgency - 0.45) * 0.10) - (owner.championship_demand - owner.patience_level) * 0.04,
        )
        target_star_bias = shift(
            gm.star_bias_weight,
            (urgency - 0.4) * 0.08 + (profile.era_modifier.star_movement_probability - 0.5) * 0.08,
        )
        target_cap_sens = shift(
            gm.cap_sensitivity,
            (0.5 - owner.luxury_tax_tolerance) * 0.10 + (0.5 - owner.spending_limit / 250_000_000.0) * 0.08,
        )
        target_loyalty = shift(
            gm.loyalty_bias,
            (profile.era_modifier.loyalty_bias_boost * 0.10) - ((urgency - 0.5) * 0.06),
        )

        rationale = [
            f"checkpoint={context.checkpoint}",
            f"direction_hint={direction_hint}",
            f"urgency={urgency:.3f}",
            "request-driven drift only; no server-side profile persistence",
        ]
        if context.title_drought_years >= 10:
            rationale.append("drought_desperation_shift")
        if context.rings_last_6_years >= 3:
            rationale.append("dynasty_preservation_shift")

        suggested = GmPersonality(
            id=gm.id,
            archetype=gm.archetype,
            risk_tolerance=target_risk,
            trade_frequency=target_trade_freq,
            draft_pick_value_weight=target_pick_weight,
            star_bias_weight=target_star_bias,
            youth_development_weight=gm.youth_development_weight,
            cap_sensitivity=target_cap_sens,
            loyalty_bias=target_loyalty,
            media_pressure_sensitivity=gm.media_pressure_sensitivity,
        )
        return NextProfileRecommendation(
            team_key=profile.team_key,
            phase=context.checkpoint,
            suggested_personality=suggested,
            rationale=rationale,
        )

    @staticmethod
    def _normalized_request_payload(request: Any) -> dict[str, Any]:
        payload = request.model_dump(mode="json")
        payload.pop("apply_live_changes", None)
        payload.pop("live_operations", None)
        return payload

    def trade_decision(self, *, request: AiTradeDecisionRequest) -> AiTradeDecisionResponse:
        profile = self.resolve_profile(context=request.context)
        payload = self._normalized_request_payload(request)
        payload["context"]["team_id"] = profile.team_key
        seed = request.context.seed or self._default_seed
        cache_key = self._cache_key(endpoint="ai_trade_decision", team_key=profile.team_key, payload=payload, seed=seed)

        def compute() -> dict[str, Any]:
            metrics = self._common_roster_metrics(context=request.context, profile=profile)
            gm = profile.gm_personality
            urgency = self._urgency_from_media(request.context, profile)
            dynasty_adjustment, triggered = self._dynasty_drought_adjustment(context=request.context, profile=profile)

            championship_window = _clamp((metrics["win_pct"] * 0.65) + (metrics["star_ratio"] * 0.35))
            star_need = _clamp(0.45 - metrics["star_ratio"])

            player_term = (metrics["avg_overall_n"] * 0.40) + (metrics["star_ratio"] * 0.20)
            contract_term = _clamp(1.0 - metrics["cap_pressure"], -1.0, 1.0) * 0.20
            potential_term = metrics["avg_potential_n"] * gm.youth_development_weight
            window_term = championship_window * ((1.0 - gm.youth_development_weight) * 0.55 + (profile.owner_profile.championship_demand * 0.45))
            tax_penalty = max(0.0, metrics["cap_pressure"] - 1.0) * gm.cap_sensitivity
            star_bonus = star_need * gm.star_bias_weight * profile.era_modifier.star_movement_probability
            pressure_urgency = urgency
            ownership_adjustment = self._ownership_adjustment(profile)
            era_adjustment = self._era_adjustment(profile)
            personality_adjustment = (
                (gm.trade_frequency * 0.28)
                + (gm.risk_tolerance * 0.18)
                - (gm.draft_pick_value_weight * 0.14)
                - (gm.cap_sensitivity * 0.10)
            )

            total_score = (
                player_term
                + contract_term
                + potential_term
                + window_term
                - tax_penalty
                + star_bonus
                + pressure_urgency
                + ownership_adjustment
                + era_adjustment
                + personality_adjustment
                + dynasty_adjustment
            )
            aggressiveness_score = _clamp(_logistic((total_score - 1.0) * 1.55))

            if aggressiveness_score >= 0.78:
                decision = "Package future assets for immediate star-level upgrade."
            elif aggressiveness_score >= 0.58:
                decision = "Explore two-for-one veteran consolidation trade."
            elif aggressiveness_score >= 0.40:
                decision = "Seek balanced value trade without core disruption."
            else:
                decision = "Hold current core and preserve future flexibility."

            future_pick_included = bool(aggressiveness_score >= 0.62 and gm.draft_pick_value_weight <= 0.58)
            if future_pick_included:
                triggered.append("future_pick_tradeoff")

            next_profile = self._build_next_profile_recommendation(
                profile=profile,
                context=request.context,
                urgency=urgency,
                direction_hint="trade_window",
            )
            justification = (
                f"{gm.archetype} GM with pressure={urgency:.2f}, cap_pressure={metrics['cap_pressure']:.2f}, "
                f"win_pct={metrics['win_pct']:.2f}."
            )
            response = AiTradeDecisionResponse(
                team_key=profile.team_key,
                decision=decision,
                aggressiveness_score=aggressiveness_score,
                future_pick_included=future_pick_included,
                justification=justification,
                decision_breakdown={
                    "playerTerm": round(player_term, 6),
                    "contractTerm": round(contract_term, 6),
                    "potentialTerm": round(potential_term, 6),
                    "windowTerm": round(window_term, 6),
                    "taxPenalty": round(tax_penalty, 6),
                    "starBonus": round(star_bonus, 6),
                    "pressureUrgency": round(pressure_urgency, 6),
                    "ownershipAdjustment": round(ownership_adjustment, 6),
                    "eraAdjustment": round(era_adjustment, 6),
                    "personalityAdjustment": round(personality_adjustment, 6),
                    "dynastyAdjustment": round(dynasty_adjustment, 6),
                    "totalScore": round(total_score, 6),
                    "triggeredRuleCount": float(len(set(triggered))),
                },
                next_profile_recommendation=next_profile,
            )
            return response.model_dump()

        result = self._cache.get_or_compute(cache_key, compute)
        return AiTradeDecisionResponse.model_validate(result)

    def draft_decision(self, *, request: AiDraftDecisionRequest) -> AiDraftDecisionResponse:
        profile = self.resolve_profile(context=request.context)
        payload = self._normalized_request_payload(request)
        payload["context"]["team_id"] = profile.team_key
        seed = request.context.seed or self._default_seed
        cache_key = self._cache_key(endpoint="ai_draft_decision", team_key=profile.team_key, payload=payload, seed=seed)

        def compute() -> dict[str, Any]:
            gm = profile.gm_personality
            metrics = self._common_roster_metrics(context=request.context, profile=profile)
            urgency = self._urgency_from_media(request.context, profile)
            dynasty_adjustment, triggered = self._dynasty_drought_adjustment(context=request.context, profile=profile)

            timeline_fit = _clamp((1.0 - metrics["win_pct"]) * 0.5 + (metrics["youth_ratio"] * 0.5))
            bpa_delta = _clamp(request.board_strength)
            fit_delta = _clamp(request.team_need_fit)
            youth_curve = _clamp((metrics["avg_potential_n"] * 0.6) + (metrics["youth_ratio"] * 0.4))

            player_term = bpa_delta * 0.40
            contract_term = _clamp(1.0 - metrics["cap_pressure"], -1.0, 1.0) * 0.10
            potential_term = youth_curve * gm.youth_development_weight
            window_term = timeline_fit * ((1.0 - gm.youth_development_weight) * 0.45)
            tax_penalty = max(0.0, metrics["cap_pressure"] - 1.0) * gm.cap_sensitivity * 0.45
            star_bonus = _clamp(1.0 - metrics["star_ratio"]) * gm.star_bias_weight * 0.20
            pressure_urgency = urgency * 0.25
            ownership_adjustment = self._ownership_adjustment(profile) * 0.45
            era_adjustment = (profile.era_modifier.spacing_bias_multiplier - 1.0) * 0.08

            total_score = (
                player_term
                + contract_term
                + potential_term
                + window_term
                - tax_penalty
                + star_bonus
                + pressure_urgency
                + ownership_adjustment
                + era_adjustment
                + dynasty_adjustment
            )
            risk_score = _clamp((gm.risk_tolerance * 0.6) + ((1.0 - fit_delta) * 0.25) + (urgency * 0.15))

            if total_score >= 0.95 and risk_score >= 0.55:
                target_profile = "upside"
                decision = "Prioritize high-ceiling prospect even with longer timeline."
            elif fit_delta >= bpa_delta:
                target_profile = "fit"
                decision = "Draft system-fit prospect to stabilize rotation value."
            else:
                target_profile = "BPA"
                decision = "Draft best player available with balanced risk profile."

            next_profile = self._build_next_profile_recommendation(
                profile=profile,
                context=request.context,
                urgency=urgency,
                direction_hint="draft_cycle",
            )
            if target_profile == "upside":
                triggered.append("upside_priority")
            response = AiDraftDecisionResponse(
                team_key=profile.team_key,
                decision=decision,
                risk_score=risk_score,
                target_profile=target_profile,
                justification=f"Draft context favors {target_profile} with urgency={urgency:.2f}.",
                decision_breakdown={
                    "playerTerm": round(player_term, 6),
                    "contractTerm": round(contract_term, 6),
                    "potentialTerm": round(potential_term, 6),
                    "windowTerm": round(window_term, 6),
                    "taxPenalty": round(tax_penalty, 6),
                    "starBonus": round(star_bonus, 6),
                    "pressureUrgency": round(pressure_urgency, 6),
                    "ownershipAdjustment": round(ownership_adjustment, 6),
                    "eraAdjustment": round(era_adjustment, 6),
                    "dynastyAdjustment": round(dynasty_adjustment, 6),
                    "totalScore": round(total_score, 6),
                    "triggeredRuleCount": float(len(set(triggered))),
                },
                next_profile_recommendation=next_profile,
            )
            return response.model_dump()

        result = self._cache.get_or_compute(cache_key, compute)
        return AiDraftDecisionResponse.model_validate(result)

    def free_agency_decision(self, *, request: AiFreeAgencyDecisionRequest) -> AiFreeAgencyDecisionResponse:
        profile = self.resolve_profile(context=request.context)
        payload = self._normalized_request_payload(request)
        payload["context"]["team_id"] = profile.team_key
        seed = request.context.seed or self._default_seed
        cache_key = self._cache_key(
            endpoint="ai_free_agency_decision",
            team_key=profile.team_key,
            payload=payload,
            seed=seed,
        )

        def compute() -> dict[str, Any]:
            gm = profile.gm_personality
            owner = profile.owner_profile
            metrics = self._common_roster_metrics(context=request.context, profile=profile)
            urgency = self._urgency_from_media(request.context, profile)
            dynasty_adjustment, triggered = self._dynasty_drought_adjustment(context=request.context, profile=profile)

            cap_elasticity = _clamp(_safe_ratio(request.cap_room, max(1.0, owner.spending_limit * 0.25)))
            role_fit = _clamp((metrics["avg_overall_n"] * 0.45) + (metrics["star_ratio"] * 0.20) + (metrics["youth_ratio"] * 0.35))
            offer_efficiency = _clamp((1.0 - request.market_offer_pressure) * 0.55 + (1.0 - metrics["cap_pressure"]) * 0.45)
            window_term = _clamp(metrics["win_pct"] * 0.6 + owner.championship_demand * 0.4) * 0.30

            player_term = role_fit * 0.30
            contract_term = offer_efficiency * 0.25
            potential_term = metrics["avg_potential_n"] * gm.youth_development_weight * 0.20
            tax_penalty = max(0.0, metrics["cap_pressure"] - owner.luxury_tax_tolerance) * gm.cap_sensitivity
            star_bonus = gm.star_bias_weight * profile.era_modifier.star_movement_probability * 0.18
            pressure_urgency = urgency * 0.25
            ownership_adjustment = self._ownership_adjustment(profile) * 0.6
            era_adjustment = (profile.era_modifier.salary_cap_volatility - 1.0) * 0.10

            total_score = (
                player_term
                + contract_term
                + potential_term
                + window_term
                - tax_penalty
                + star_bonus
                + pressure_urgency
                + ownership_adjustment
                + era_adjustment
                + dynasty_adjustment
            )

            offer_multiplier = _clamp(0.65 + (gm.risk_tolerance * 0.15) + (owner.championship_demand * 0.20), 0.5, 1.2)
            max_offer_guidance = max(0.0, request.cap_room * offer_multiplier)
            projected_tax_ratio = _safe_ratio(max(0.0, (metrics["cap_pressure"] * owner.spending_limit) + max_offer_guidance - owner.spending_limit), owner.spending_limit)
            tax_impact = round(projected_tax_ratio, 6)

            aggressiveness = _clamp(_logistic((total_score - 0.7) * 1.65))
            if aggressiveness >= 0.72:
                decision = "Pursue premium free agent and absorb short-term cap pressure."
            elif aggressiveness >= 0.50:
                decision = "Target value signing in top two roster needs."
            else:
                decision = "Preserve flexibility and avoid long-term overpay."

            if tax_impact > owner.luxury_tax_tolerance:
                triggered.append("tax_tolerance_guardrail")

            next_profile = self._build_next_profile_recommendation(
                profile=profile,
                context=request.context,
                urgency=urgency,
                direction_hint="free_agency_window",
            )
            response = AiFreeAgencyDecisionResponse(
                team_key=profile.team_key,
                decision=decision,
                max_offer_guidance=max_offer_guidance,
                tax_impact=tax_impact,
                justification=f"FA score={total_score:.3f}, tax_impact={tax_impact:.3f}.",
                decision_breakdown={
                    "playerTerm": round(player_term, 6),
                    "contractTerm": round(contract_term, 6),
                    "potentialTerm": round(potential_term, 6),
                    "windowTerm": round(window_term, 6),
                    "taxPenalty": round(tax_penalty, 6),
                    "starBonus": round(star_bonus, 6),
                    "pressureUrgency": round(pressure_urgency, 6),
                    "ownershipAdjustment": round(ownership_adjustment, 6),
                    "eraAdjustment": round(era_adjustment, 6),
                    "dynastyAdjustment": round(dynasty_adjustment, 6),
                    "totalScore": round(total_score, 6),
                    "capElasticity": round(cap_elasticity, 6),
                    "triggeredRuleCount": float(len(set(triggered))),
                },
                next_profile_recommendation=next_profile,
            )
            return response.model_dump()

        result = self._cache.get_or_compute(cache_key, compute)
        return AiFreeAgencyDecisionResponse.model_validate(result)

    def franchise_direction(self, *, request: AiFranchiseDirectionRequest) -> AiFranchiseDirectionResponse:
        profile = self.resolve_profile(context=request.context)
        payload = self._normalized_request_payload(request)
        payload["context"]["team_id"] = profile.team_key
        seed = request.context.seed or self._default_seed
        cache_key = self._cache_key(
            endpoint="ai_franchise_direction",
            team_key=profile.team_key,
            payload=payload,
            seed=seed,
        )

        def compute() -> dict[str, Any]:
            urgency = self._urgency_from_media(request.context, profile)
            result = self._direction_engine.classify(context=request.context, profile=profile)
            next_profile = self._build_next_profile_recommendation(
                profile=profile,
                context=request.context,
                urgency=urgency,
                direction_hint=result.direction,
            )
            response = AiFranchiseDirectionResponse(
                team_key=profile.team_key,
                direction=result.direction,
                confidence=result.confidence,
                trigger_factors=result.trigger_factors,
                justification=f"Direction={result.direction} confidence={result.confidence:.2f}.",
                decision_breakdown=result.breakdown,
                next_profile_recommendation=next_profile,
            )
            return response.model_dump()

        payload_result = self._cache.get_or_compute(cache_key, compute)
        return AiFranchiseDirectionResponse.model_validate(payload_result)
