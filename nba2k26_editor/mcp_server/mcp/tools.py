from __future__ import annotations

from typing import Any

from ..errors import ServiceError
from ..api.v1.models import (
    AiDraftDecisionRequest,
    AiDraftDecisionResponse,
    AiFreeAgencyDecisionRequest,
    AiFreeAgencyDecisionResponse,
    AiFranchiseDirectionRequest,
    AiFranchiseDirectionResponse,
    AiProfileLookupRequest,
    AiProfileResponse,
    AiTradeDecisionRequest,
    AiTradeDecisionResponse,
    ChemistryCalculateRequest,
    ChemistryCalculateResponse,
    ConflictSimulateRequest,
    ConflictSimulateResponse,
    DraftGenerateRequest,
    DraftGenerateResponse,
    DraftLotteryRequest,
    DraftLotteryResponse,
    DynastyTrackRequest,
    DynastyTrackResponse,
    EraTransitionRequest,
    EraTransitionResponse,
    FranchiseOptimizeRequest,
    FranchiseOptimizeResponse,
    LockerRoomStatus,
    LockerRoomStatusResponse,
    MoraleEvaluateRequest,
    MoraleEvaluateResponse,
    PersonalityPlayerState,
    PersonalityUpdateRequest,
    PersonalityUpdateResponse,
    PlayerPersonality,
    ProgressionSimulateRequest,
    ProgressionResult,
    ProgressionSimulateResponse,
    SeasonSimulateRequest,
    SeasonOutcome,
    SeasonSimulateResponse,
    TradeEvaluation,
    TradeEvaluateRequest,
    TradeEvaluateResponse,
)


def _apply_live_writes(container, *, apply_live_changes: bool, live_operations):
    if not apply_live_changes:
        return []
    return container.live_gateway.apply_operations(live_operations)


def _ensure_ai_enabled(container) -> None:
    if not container.settings.enable_cpu_ai_personality_v1:
        raise ServiceError(
            status_code=503,
            code="AI_PERSONALITY_FEATURE_DISABLED",
            message="CPU AI personality module is disabled by server configuration.",
            details={"capability_flag": "cpu_ai_personality_v1"},
        )


def _ensure_locker_enabled(container) -> None:
    if not container.settings.enable_locker_room_v1:
        raise ServiceError(
            status_code=503,
            code="LOCKER_ROOM_FEATURE_DISABLED",
            message="Locker-room personality module is disabled by server configuration.",
            details={"capability_flag": "locker_room_personality_v1"},
        )


def _safe_team_id(value: str | int | None, *, fallback: str) -> str:
    if value is None:
        return str(fallback)
    return str(value)


def execute_franchise_optimizer(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = FranchiseOptimizeRequest.model_validate(payload)
    if not request.franchise_state.roster:
        fallback_state = container.gm_rl_adapter.load_franchise_state(team_id=0)
        request.franchise_state = fallback_state.model_copy(
            update={
                "era": request.franchise_state.era,
                "team": request.franchise_state.team or fallback_state.team,
                "owner_goal": request.franchise_state.owner_goal,
                "cap_space": request.franchise_state.cap_space,
            }
        )
    era_config = container.era_engine.get_era_config(era=request.era, season=request.franchise_state.era)
    league_rules = container.cba_rules_adapter.load_league_rules(season=request.franchise_state.era)
    result = container.franchise_engine.optimize(
        franchise_state=request.franchise_state,
        era_config=era_config,
        league_rules=league_rules,
    )
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = FranchiseOptimizeResponse(**result, write_operations=writes)
    return response.model_dump()


def execute_trade_evaluator(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = TradeEvaluateRequest.model_validate(payload)
    if not request.franchise_state.roster:
        fallback_state = container.gm_rl_adapter.load_franchise_state(team_id=0)
        request.franchise_state = fallback_state.model_copy(
            update={
                "era": request.franchise_state.era,
                "team": request.franchise_state.team or fallback_state.team,
                "owner_goal": request.franchise_state.owner_goal,
                "cap_space": request.franchise_state.cap_space,
            }
        )
    evaluation = container.trade_engine.evaluate(
        franchise_state=request.franchise_state,
        proposal=request.proposal,
        cpu_profile=request.cpu_profile,
    )
    if request.profile_id:
        _ensure_locker_enabled(container)
        team_id = _safe_team_id(request.team_id, fallback=request.franchise_state.team)
        season = request.season or request.franchise_state.era
        era = request.era or "modern"
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=team_id,
            season=season,
            era=era,
            seed=None,
            recent_record="0-0",
            team_underperforming=False,
        )
        avg_morale = float(locker_state.get("average_morale", 0.5))
        conflict_risk = float(locker_state.get("conflict_risk", 0.0))
        pressure_multiplier = 1.0 + ((0.5 - avg_morale) * 0.12) + (conflict_risk * 0.08)
        fairness = max(-1.0, min(1.0, float(evaluation.fairness_score) * pressure_multiplier))
        rationale = list(evaluation.rationale)
        rationale.append(f"Locker-room pressure multiplier: {pressure_multiplier:.3f}")
        rationale.append(f"Average morale: {avg_morale:.3f} | Conflict risk: {conflict_risk:.3f}")
        evaluation = TradeEvaluation(
            fairness_score=fairness,
            verdict=evaluation.verdict,
            rationale=rationale,
            projected_cap_delta=evaluation.projected_cap_delta,
        )
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = TradeEvaluateResponse(evaluation=evaluation, write_operations=writes)
    return response.model_dump()


def execute_draft_generator(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = DraftGenerateRequest.model_validate(payload)
    draft_class = container.draft_engine.generate_class(
        era=request.era,
        season=request.season,
        class_size=request.class_size,
        seed=request.seed,
        include_historical_imports=request.include_historical_imports,
    )
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = DraftGenerateResponse(draft_class=draft_class, write_operations=writes)
    return response.model_dump()


def execute_draft_lottery(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = DraftLotteryRequest.model_validate(payload)
    pick_order = container.draft_engine.simulate_lottery(
        teams=request.teams,
        odds=request.odds,
        seed=request.seed,
        draws=request.draws,
    )
    response = DraftLotteryResponse(pick_order=pick_order, draw_count=request.draws)
    return response.model_dump()


def execute_progression_simulator(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = ProgressionSimulateRequest.model_validate(payload)
    results = container.progression_engine.simulate(players=request.players, years=request.years, seed=request.seed)
    if request.profile_id:
        _ensure_locker_enabled(container)
        team_id = _safe_team_id(request.team_id, fallback="team")
        season = request.season or "2025-26"
        era = request.era or "modern"
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=team_id,
            season=season,
            era=era,
            seed=request.seed,
            recent_record="0-0",
            team_underperforming=False,
        )
        morale_map = locker_state.get("morale_map", {})
        stress = float(locker_state.get("stress_factor", 0.0))
        adjusted: list[ProgressionResult] = []
        for item in results:
            morale = float(morale_map.get(str(item.player_id), 0.5))
            dev_mult = max(0.8, min(1.25, 0.85 + (morale * 0.35)))
            injury_mult = max(0.85, min(1.35, 1.12 - (morale * 0.22) + stress))
            adjusted.append(
                ProgressionResult(
                    player_id=item.player_id,
                    before_overall=item.before_overall,
                    after_overall=max(40.0, min(99.0, round(item.before_overall + ((item.after_overall - item.before_overall) * dev_mult), 2))),
                    injury_risk=max(0.0, min(1.0, round(item.injury_risk * injury_mult, 4))),
                )
            )
        results = adjusted
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = ProgressionSimulateResponse(results=results, write_operations=writes)
    return response.model_dump()


def execute_season_simulator(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = SeasonSimulateRequest.model_validate(payload)
    era_config = container.era_engine.get_era_config(era=request.era, season=request.season)
    strengths = request.team_strengths
    if request.profile_id and request.team_id is not None:
        _ensure_locker_enabled(container)
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=_safe_team_id(request.team_id, fallback="team"),
            season=request.season,
            era=request.era if request.era in {"modern"} else "modern",
            seed=request.seed,
            recent_record="0-0",
            team_underperforming=False,
        )
        chemistry = float(locker_state.get("chemistry_score", 0.5))
        stress = float(locker_state.get("stress_factor", 0.0))
        clutch = float(locker_state.get("chemistry_breakdown", {}).get("clutchMultiplier", 1.0))
        multiplier = max(0.85, min(1.12, 1.0 + ((chemistry - 0.5) * 0.10) + ((clutch - 1.0) * 0.5) - (stress * 0.05)))
        strengths = [
            type(entry)(team=entry.team, strength=float(entry.strength * multiplier))
            if str(entry.team).lower() == str(request.team_id).lower()
            else entry
            for entry in request.team_strengths
        ]
    outcomes = container.simulation_engine.simulate_season(
        team_strengths=strengths,
        iterations=request.iterations,
        seed=request.seed,
        pace_factor=era_config.pace_factor,
    )
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = SeasonSimulateResponse(outcomes=outcomes, write_operations=writes)
    return response.model_dump()


def execute_dynasty_tracker(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = DynastyTrackRequest.model_validate(payload)
    snapshot = container.dynasty_engine.track(team=request.team, history=request.history)
    if request.profile_id:
        _ensure_locker_enabled(container)
        team_id = _safe_team_id(request.team_id, fallback=request.team)
        season = request.season or "2025-26"
        era = request.era or "modern"
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=team_id,
            season=season,
            era=era,
            seed=None,
            recent_record="0-0",
            team_underperforming=False,
        )
        finals_boost = 0.07 if request.finals_appearances_last_6 >= 3 else 0.0
        collapse_penalty = 0.1 if request.early_exit_streak >= 2 else 0.0
        chemistry_factor = float(locker_state.get("chemistry_score", 0.5))
        morale_factor = float(locker_state.get("average_morale", 0.5))
        adjusted_score = snapshot.legacy_score * (1.0 + finals_boost - collapse_penalty + ((chemistry_factor - 0.5) * 0.08) + ((morale_factor - 0.5) * 0.05))
        snapshot = snapshot.model_copy(
            update={
                "legacy_score": round(adjusted_score, 2),
                "summary": (
                    f"{snapshot.summary} Culture boost={finals_boost:.2f}, collapse_risk_penalty={collapse_penalty:.2f}, "
                    f"chemistry={chemistry_factor:.2f}, morale={morale_factor:.2f}."
                ),
            }
        )
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = DynastyTrackResponse(snapshot=snapshot, write_operations=writes)
    return response.model_dump()


def execute_era_transition_handler(container, payload: dict[str, Any]) -> dict[str, Any]:
    request = EraTransitionRequest.model_validate(payload)
    previous, target, changes = container.era_engine.transition(
        era=request.era,
        from_season=request.from_season,
        to_season=request.to_season,
    )
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = EraTransitionResponse(previous=previous, target=target, rule_changes=changes, write_operations=writes)
    return response.model_dump()


def execute_ai_trade_decision(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_ai_enabled(container)
    request = AiTradeDecisionRequest.model_validate(payload)
    result = container.cpu_ai_engine.trade_decision(request=request)
    if request.profile_id:
        _ensure_locker_enabled(container)
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=str(request.context.team_id),
            season=request.context.season,
            era=request.context.era if request.context.era in {"1980s", "1990s", "2000s", "modern"} else "modern",
            seed=request.context.seed,
            recent_record=request.context.current_record,
            team_underperforming=False,
        )
        morale = float(locker_state.get("average_morale", 0.5))
        conflict = float(locker_state.get("conflict_risk", 0.0))
        adjusted = max(0.0, min(1.0, (result.aggressiveness_score * (1.0 + ((0.5 - morale) * 0.1) + (conflict * 0.08)))))
        breakdown = dict(result.decision_breakdown)
        breakdown["lockerRoomMorale"] = round(morale, 6)
        breakdown["lockerRoomConflictRisk"] = round(conflict, 6)
        breakdown["lockerRoomAdjustedAggressiveness"] = round(adjusted, 6)
        result = result.model_copy(update={"aggressiveness_score": adjusted, "decision_breakdown": breakdown})
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = result.model_copy(update={"write_operations": writes})
    return AiTradeDecisionResponse.model_validate(response).model_dump(by_alias=True)


def execute_ai_draft_decision(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_ai_enabled(container)
    request = AiDraftDecisionRequest.model_validate(payload)
    result = container.cpu_ai_engine.draft_decision(request=request)
    if request.profile_id:
        _ensure_locker_enabled(container)
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=str(request.context.team_id),
            season=request.context.season,
            era=request.context.era if request.context.era in {"1980s", "1990s", "2000s", "modern"} else "modern",
            seed=request.context.seed,
            recent_record=request.context.current_record,
            team_underperforming=False,
        )
        morale = float(locker_state.get("average_morale", 0.5))
        adjusted = max(0.0, min(1.0, result.risk_score + ((0.5 - morale) * 0.08)))
        breakdown = dict(result.decision_breakdown)
        breakdown["lockerRoomMorale"] = round(morale, 6)
        breakdown["lockerRoomAdjustedRisk"] = round(adjusted, 6)
        result = result.model_copy(update={"risk_score": adjusted, "decision_breakdown": breakdown})
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = result.model_copy(update={"write_operations": writes})
    return AiDraftDecisionResponse.model_validate(response).model_dump(by_alias=True)


def execute_ai_free_agency_decision(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_ai_enabled(container)
    request = AiFreeAgencyDecisionRequest.model_validate(payload)
    result = container.cpu_ai_engine.free_agency_decision(request=request)
    if request.profile_id:
        _ensure_locker_enabled(container)
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=str(request.context.team_id),
            season=request.context.season,
            era=request.context.era if request.context.era in {"1980s", "1990s", "2000s", "modern"} else "modern",
            seed=request.context.seed,
            recent_record=request.context.current_record,
            team_underperforming=False,
        )
        conflict = float(locker_state.get("conflict_risk", 0.0))
        adjusted_offer = max(0.0, result.max_offer_guidance * (1.0 - (conflict * 0.07)))
        breakdown = dict(result.decision_breakdown)
        breakdown["lockerRoomConflictRisk"] = round(conflict, 6)
        breakdown["lockerRoomAdjustedOffer"] = round(adjusted_offer, 6)
        result = result.model_copy(update={"max_offer_guidance": adjusted_offer, "decision_breakdown": breakdown})
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = result.model_copy(update={"write_operations": writes})
    return AiFreeAgencyDecisionResponse.model_validate(response).model_dump(by_alias=True)


def execute_ai_franchise_direction(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_ai_enabled(container)
    request = AiFranchiseDirectionRequest.model_validate(payload)
    result = container.cpu_ai_engine.franchise_direction(request=request)
    if request.profile_id:
        _ensure_locker_enabled(container)
        locker_state = container.locker_room_engine.get_or_refresh_state(
            profile_id=request.profile_id,
            team_id=str(request.context.team_id),
            season=request.context.season,
            era=request.context.era if request.context.era in {"1980s", "1990s", "2000s", "modern"} else "modern",
            seed=request.context.seed,
            recent_record=request.context.current_record,
            team_underperforming=False,
        )
        chemistry = float(locker_state.get("chemistry_score", 0.5))
        adjusted_confidence = max(0.0, min(1.0, result.confidence + ((chemistry - 0.5) * 0.06)))
        breakdown = dict(result.decision_breakdown)
        breakdown["lockerRoomChemistry"] = round(chemistry, 6)
        breakdown["lockerRoomAdjustedConfidence"] = round(adjusted_confidence, 6)
        result = result.model_copy(update={"confidence": adjusted_confidence, "decision_breakdown": breakdown})
    writes = _apply_live_writes(
        container,
        apply_live_changes=request.apply_live_changes,
        live_operations=request.live_operations,
    )
    response = result.model_copy(update={"write_operations": writes})
    return AiFranchiseDirectionResponse.model_validate(response).model_dump(by_alias=True)


def execute_ai_profile_lookup(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_ai_enabled(container)
    request = AiProfileLookupRequest.model_validate(payload)
    result = container.cpu_ai_engine.profile_lookup(
        team_id=request.team_id,
        era=request.era,
        season=request.season,
    )
    return AiProfileResponse.model_validate(result).model_dump(by_alias=True)


def execute_locker_room_personality_update(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_locker_enabled(container)
    request = PersonalityUpdateRequest.model_validate(payload)
    base_state = container.locker_room_engine._live_sync(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        seed=request.seed,
    )
    snapshot = {"roster": [item.model_dump(by_alias=True) for item in request.roster]} if request.roster else {"roster": base_state.get("roster", [])}
    updates = [
        {
            "player_id": item.player_id,
            "archetype": item.archetype,
            "personality": item.personality.model_dump(by_alias=True),
        }
        for item in request.updates
    ]
    state = container.locker_room_engine.generate_or_update_personalities_from_live_snapshot(
        state=base_state,
        snapshot=snapshot,
        era=request.era,
        mode=request.mode,
        seed=request.seed,
        manual_updates=updates,
        events={
            "championships": request.championships,
            "mvp_awards": request.mvp_awards,
            "contract_disputes": request.contract_disputes,
            "public_criticism": request.public_criticism,
        },
    )
    state = container.locker_room_engine._save_state(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        state=state,
    )
    players: list[PersonalityPlayerState] = []
    for payload_item in state.get("personalities", {}).values():
        traits = payload_item.get("personality", {})
        players.append(
            PersonalityPlayerState(
                player_id=int(payload_item.get("player_id", 0)),
                name=str(payload_item.get("name", "")),
                archetype=str(payload_item.get("archetype", "leader")),
                personality=PlayerPersonality.model_validate(traits),
            )
        )
    response = PersonalityUpdateResponse(
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        players=players,
        captain_player_id=state.get("captain_player_id"),
        profile_id=request.profile_id,
    )
    return response.model_dump(by_alias=True)


def execute_locker_room_chemistry_calculate(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_locker_enabled(container)
    request = ChemistryCalculateRequest.model_validate(payload)
    state = container.locker_room_engine.get_or_refresh_state(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        seed=request.seed,
        recent_record=request.recent_record,
        team_underperforming=request.team_underperforming,
    )
    chemistry = container.locker_room_engine.calculate_team_chemistry(
        state=state,
        recent_record=request.recent_record,
        team_underperforming=request.team_underperforming,
    )
    morale = container.locker_room_engine.evaluate_morale(
        state=state,
        team_win_pct=0.5,
        chemistry_score=float(chemistry["chemistry_score"]),
        team_underperforming=request.team_underperforming,
    )
    response = ChemistryCalculateResponse(
        chemistry_score=float(state.get("chemistry_score", chemistry["chemistry_score"])),
        morale_trend=str(state.get("morale_trend", morale["morale_trend"])),
        conflict_risk=float(state.get("conflict_risk", 0.0)),
        mentor_boost_active=bool(state.get("mentor_boost_active", False)),
        breakdown=state.get("chemistry_breakdown", chemistry["breakdown"]),
    )
    container.locker_room_engine._save_state(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        state=state,
    )
    return response.model_dump(by_alias=True)


def execute_locker_room_conflict_simulate(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_locker_enabled(container)
    request = ConflictSimulateRequest.model_validate(payload)
    state = container.locker_room_engine.get_or_refresh_state(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        seed=request.seed,
        recent_record="0-0",
        team_underperforming=False,
    )
    result = container.locker_room_engine.simulate_conflicts(
        state=state,
        trade_rumor_pressure=request.trade_rumor_pressure,
        media_pressure=request.media_pressure,
    )
    container.locker_room_engine._save_state(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        state=state,
    )
    response = ConflictSimulateResponse(
        events=result["events"],
        conflict_risk=result["conflict_risk"],
        morale_penalty=result["morale_penalty"],
        queue_size=len(result["events"]),
    )
    return response.model_dump(by_alias=True)


def execute_locker_room_morale_evaluate(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_locker_enabled(container)
    request = MoraleEvaluateRequest.model_validate(payload)
    state = container.locker_room_engine.get_or_refresh_state(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        seed=request.seed,
        recent_record="0-0",
        team_underperforming=request.team_underperforming,
    )
    morale = container.locker_room_engine.evaluate_morale(
        state=state,
        team_win_pct=request.team_win_pct,
        chemistry_score=request.chemistry_score,
        team_underperforming=request.team_underperforming,
    )
    playoff = container.locker_room_engine.apply_playoff_pressure(state=state, seed=request.seed)
    container.locker_room_engine._save_state(
        profile_id=request.profile_id,
        team_id=request.team_id,
        season=request.season,
        era=request.era,
        state=state,
    )
    response = MoraleEvaluateResponse(
        average_morale=morale["average_morale"],
        morale_trend=morale["morale_trend"],
        players=morale["players"],
        playoff_adjustments=playoff["players"],
    )
    return response.model_dump(by_alias=True)


def execute_locker_room_status_lookup(container, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_locker_enabled(container)
    team_id = str(payload.get("team_id") or "")
    profile_id = str(payload.get("profile_id") or "")
    season = str(payload.get("season") or "")
    era = str(payload.get("era") or "modern")
    if not team_id or not profile_id or not season:
        raise ServiceError(
            status_code=422,
            code="LOCKER_ROOM_STATUS_VALIDATION_FAILED",
            message="team_id, profile_id, and season are required.",
            details={},
        )
    status_payload = container.locker_room_engine.status(
        profile_id=profile_id,
        team_id=team_id,
        season=season,
        era=era,
        seed=payload.get("seed"),
    )
    breakdown = status_payload["status"].get("chemistry_breakdown", {})
    morale_items = []
    for pid, morale in status_payload["status"].get("morale_map", {}).items():
        morale_items.append(
            {
                "player_id": int(pid),
                "morale": float(morale),
                "roleSatisfaction": 0.5,
                "conflictPenalty": 0.0,
                "contractSecurity": 0.5,
                "shotConsistencyMultiplier": 1.0,
                "injuryProbabilityMultiplier": 1.0,
                "developmentRateMultiplier": 1.0,
                "tradeDemandProbability": 0.0,
            }
        )
    response = LockerRoomStatusResponse(
        chemistry_score=status_payload["chemistry_score"],
        morale_trend=status_payload["morale_trend"],
        conflict_risk=status_payload["conflict_risk"],
        mentor_boost_active=status_payload["mentor_boost_active"],
        status=LockerRoomStatus(
            profile_id=status_payload["profile_id"],
            team_id=status_payload["team_id"],
            season=status_payload["season"],
            era=status_payload["era"],
            chemistry_score=status_payload["chemistry_score"],
            morale_trend=status_payload["morale_trend"],
            conflict_risk=status_payload["conflict_risk"],
            mentor_boost_active=status_payload["mentor_boost_active"],
            average_morale=status_payload["average_morale"],
            stress_factor=float(status_payload["status"].get("stress_factor", 0.0)),
            stale_live_data=bool(status_payload.get("stale_live_data", False)),
            captain_player_id=status_payload["status"].get("captain_player_id"),
            conflicts=status_payload["status"].get("conflicts", []),
            morale=morale_items,
            breakdown=breakdown,
        ),
    )
    return response.model_dump(by_alias=True)


TOOL_EXECUTORS = {
    "franchise_optimizer": execute_franchise_optimizer,
    "trade_evaluator": execute_trade_evaluator,
    "draft_generator": execute_draft_generator,
    "progression_simulator": execute_progression_simulator,
    "season_simulator": execute_season_simulator,
    "dynasty_tracker": execute_dynasty_tracker,
    "era_transition_handler": execute_era_transition_handler,
    "ai_trade_decision": execute_ai_trade_decision,
    "ai_draft_decision": execute_ai_draft_decision,
    "ai_free_agency_decision": execute_ai_free_agency_decision,
    "ai_franchise_direction": execute_ai_franchise_direction,
    "ai_profile_lookup": execute_ai_profile_lookup,
    "locker_room_chemistry_calculate": execute_locker_room_chemistry_calculate,
    "locker_room_personality_update": execute_locker_room_personality_update,
    "locker_room_conflict_simulate": execute_locker_room_conflict_simulate,
    "locker_room_morale_evaluate": execute_locker_room_morale_evaluate,
    "locker_room_status_lookup": execute_locker_room_status_lookup,
}
