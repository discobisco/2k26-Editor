from __future__ import annotations

from dataclasses import dataclass

from .assets import player_asset_value, team_need_summary
from .finances import assess_team_finances
from .models import TeamDirection
from .world import FranchisePlayer, TeamContext


@dataclass(frozen=True)
class FreeAgentTarget:
    player: FranchisePlayer
    asking_salary: int = 0
    asking_years: int = 1
    bird_rights: bool = False
    restricted: bool = False
    market_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FreeAgentFit:
    target: FreeAgentTarget
    fit_score: int
    projected_role: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ContractOffer:
    target: FreeAgentTarget
    first_year_salary: int
    years: int
    offer_type: str
    total_value: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReSignDecision:
    target: FreeAgentTarget
    decision: str
    reason_score: int
    offer: ContractOffer | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class FreeAgencyPlan:
    strategy: str
    ranked_targets: tuple[FreeAgentFit, ...]
    offers: tuple[ContractOffer, ...]
    re_sign_decisions: tuple[ReSignDecision, ...]
    cap_space_after_top_offer: int
    warnings: tuple[str, ...]


def free_agency_recommendations(context: TeamContext, direction: TeamDirection | None = None):
    from .transactions import recommend_team_transactions

    return tuple(item for item in recommend_team_transactions(context, direction) if item.kind == "free_agency")


def rank_free_agent_targets(context: TeamContext, targets: tuple[FreeAgentTarget, ...], direction: TeamDirection | None = None) -> tuple[FreeAgentFit, ...]:
    direction = direction or _infer_free_agency_direction(context)
    return tuple(sorted((_score_target_fit(context, target, direction) for target in targets), key=lambda fit: fit.fit_score, reverse=True))


def build_contract_offer(context: TeamContext, target: FreeAgentTarget, direction: TeamDirection | None = None) -> ContractOffer:
    direction = direction or _infer_free_agency_direction(context)
    finance = assess_team_finances(context)
    ask_salary = max(0, int(target.asking_salary or _estimated_market_salary(target.player)))
    ask_years = max(1, int(target.asking_years or 1))
    reasons: list[str] = []

    if finance.status == "tax":
        salary = min(ask_salary, 12_900_000)
        years = min(ask_years, 2)
        offer_type = "exception"
        reasons.append("tax team should use exception/minimum style offers")
    elif finance.status == "cap_space" and direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        salary = min(ask_salary, max(0, int(context.cap.cap_space * 0.45))) if context.cap.cap_space else ask_salary
        years = min(ask_years, 3 if _timeline_fit(target.player, direction) else 2)
        offer_type = "cap_space"
        reasons.append("cap space is available but rebuild should preserve flexibility")
    elif finance.status == "cap_space":
        salary = min(ask_salary, max(0, context.cap.cap_space)) if context.cap.cap_space else ask_salary
        years = min(ask_years, 4)
        offer_type = "cap_space"
        reasons.append("cap space can fund a direct offer")
    elif target.bird_rights:
        salary = ask_salary
        years = min(ask_years, 5)
        offer_type = "bird_rights"
        reasons.append("Bird rights allow re-signing above cap")
    else:
        salary = min(ask_salary, 12_900_000)
        years = min(ask_years, 2)
        offer_type = "exception"
        reasons.append("over-cap team should avoid long new salary")

    if direction in {TeamDirection.REBUILD, TeamDirection.TANK} and not _timeline_fit(target.player, direction):
        years = min(years, 1 if target.player.age and target.player.age >= 32 else 2)
        reasons.append("shorten offer because player does not fit rebuild timeline")
    if direction is TeamDirection.CONTEND and (target.player.overall or 0) >= 76:
        reasons.append("rotation-ready player fits contender window")
    return ContractOffer(target, max(0, int(salary)), max(1, int(years)), offer_type, max(0, int(salary)) * max(1, int(years)), tuple(reasons))


def decide_re_sign_or_renounce(context: TeamContext, target: FreeAgentTarget, direction: TeamDirection | None = None) -> ReSignDecision:
    direction = direction or _infer_free_agency_direction(context)
    fit = _score_target_fit(context, target, direction)
    offer = build_contract_offer(context, target, direction)
    reasons = list(fit.reasons)
    score = fit.fit_score
    expensive = target.asking_salary >= 25_000_000
    aging = (target.player.age or 0) >= 32

    if direction in {TeamDirection.REBUILD, TeamDirection.TANK} and expensive and aging:
        score -= 35
        reasons.append("renounce expensive veteran cap hold that does not fit timeline")
    if target.bird_rights and _timeline_fit(target.player, direction) and (target.player.potential or target.player.overall or 0) >= 82:
        score += 18
        reasons.append("young Bird-rights player is core retention candidate")
    if context.cap.is_tax_team and expensive and (target.player.overall or 0) < 84:
        score -= 20
        reasons.append("tax team should avoid premium non-star retention")

    if score >= 62:
        decision = "re_sign"
        final_offer: ContractOffer | None = offer
    elif score <= 42:
        decision = "renounce"
        final_offer = None
    else:
        decision = "hold_rights"
        final_offer = offer if target.bird_rights else None
    return ReSignDecision(target, decision, max(0, min(100, int(round(score)))), final_offer, tuple(reasons or ("neutral retention case",)))


def free_agency_plan(
    context: TeamContext,
    *,
    targets: tuple[FreeAgentTarget, ...] = (),
    own_free_agents: tuple[FreeAgentTarget, ...] = (),
    direction: TeamDirection | None = None,
) -> FreeAgencyPlan:
    direction = direction or _infer_free_agency_direction(context)
    generated_targets = targets or _default_targets_for_context(context, direction)
    ranked = rank_free_agent_targets(context, generated_targets, direction)
    offers = tuple(build_contract_offer(context, fit.target, direction) for fit in ranked[:3] if fit.fit_score >= 45)
    decisions = tuple(decide_re_sign_or_renounce(context, target, direction) for target in own_free_agents)
    cap_after = context.cap.cap_space - (offers[0].first_year_salary if offers else 0)
    warnings: list[str] = []
    if context.cap.is_tax_team:
        warnings.append("tax team: prioritize exceptions/minimums and avoid long non-star salary")
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        warnings.append("rebuild/tank: avoid veteran contracts that block young-player minutes")
    return FreeAgencyPlan(_strategy_label(context, direction), ranked, offers, decisions, cap_after, tuple(warnings))


def _score_target_fit(context: TeamContext, target: FreeAgentTarget, direction: TeamDirection) -> FreeAgentFit:
    player = target.player
    reasons: list[str] = []
    score = player_asset_value(player) - 10
    salary_m = target.asking_salary / 1_000_000
    if target.asking_salary:
        score -= max(0.0, salary_m - max(6.0, (player.overall or 70) - 68)) * 1.2
    if _timeline_fit(player, direction):
        score += 18
        reasons.append("timeline fit")
    elif direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        score -= 18
        reasons.append("poor rebuild timeline fit")
    if direction is TeamDirection.CONTEND and (player.overall or 0) >= 76:
        score += 14
        reasons.append("rotation-ready contender fit")
    if context.cap.is_tax_team and target.asking_salary >= 15_000_000:
        score -= 18
        reasons.append("tax team cannot chase expensive targets")
    if context.cap.cap_space > 20_000_000 and target.asking_salary <= context.cap.cap_space:
        score += 6
        reasons.append("fits available cap room")
    needs = team_need_summary(context)
    if player.position and any(_position_matches_need(player.position, need) for need in needs):
        score += 5
        reasons.append("positional need fit")
    role = _projected_role(player)
    return FreeAgentFit(target, max(0, min(100, int(round(score)))), role, tuple(reasons or ("general talent/depth fit",)))


def _default_targets_for_context(context: TeamContext, direction: TeamDirection) -> tuple[FreeAgentTarget, ...]:
    if direction is TeamDirection.CONTEND:
        return (FreeAgentTarget(FranchisePlayer("fa_vet_depth", "FA", name="Veteran Depth Target", age=31, overall=77, potential=77), asking_salary=10_000_000, asking_years=1),)
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        return (FreeAgentTarget(FranchisePlayer("fa_young_upside", "FA", name="Young Upside Target", age=23, overall=73, potential=84), asking_salary=8_000_000, asking_years=2),)
    return (FreeAgentTarget(FranchisePlayer("fa_balanced_depth", "FA", name="Balanced Depth Target", age=27, overall=75, potential=77), asking_salary=8_000_000, asking_years=2),)


def _estimated_market_salary(player: FranchisePlayer) -> int:
    overall = player.overall or 72
    if overall >= 90:
        return 42_000_000
    if overall >= 84:
        return 28_000_000
    if overall >= 78:
        return 14_000_000
    if overall >= 74:
        return 8_000_000
    return 3_000_000


def _timeline_fit(player: FranchisePlayer, direction: TeamDirection) -> bool:
    age = player.age or 27
    potential = player.potential or player.overall or 0
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        return age <= 25 and potential >= 80
    if direction is TeamDirection.CONTEND:
        return (player.overall or 0) >= 76 and age <= 34
    return age <= 30 or potential >= 80


def _projected_role(player: FranchisePlayer) -> str:
    overall = player.overall or 0
    if overall >= 86:
        return "starter"
    if overall >= 76:
        return "rotation"
    if (player.potential or 0) >= 82 and (player.age or 99) <= 24:
        return "development"
    return "depth"


def _position_matches_need(position: str, need: str) -> bool:
    pos = position.upper()
    if "creator" in need:
        return pos in {"PG", "SG", "SF"}
    if "star" in need:
        return True
    if "depth" in need:
        return True
    return False


def _strategy_label(context: TeamContext, direction: TeamDirection) -> str:
    finance = assess_team_finances(context)
    if finance.status == "tax":
        return "tax-limited exception market"
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        return "timeline fit and flexibility"
    if direction is TeamDirection.CONTEND:
        return "win-now depth and injury insurance"
    return "balanced value market"


def _infer_free_agency_direction(context: TeamContext) -> TeamDirection:
    if context.record.win_pct >= 0.58 or context.record.expected_win_pct >= 0.58 or context.roster.star_quality >= 88:
        return TeamDirection.CONTEND
    if context.record.win_pct <= 0.35 and context.roster.young_core_count >= 1:
        return TeamDirection.REBUILD
    if context.record.win_pct <= 0.30 and context.roster.star_quality < 82:
        return TeamDirection.TANK
    return TeamDirection.EVALUATE
