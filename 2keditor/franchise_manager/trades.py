from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .assets import player_asset_value
from .models import TeamDirection
from .world import DraftPickAsset, FranchisePlayer, PlayerContract, TeamContext


@dataclass(frozen=True)
class TradeAsset:
    kind: str
    player_id: str = ""
    player_obj: FranchisePlayer | None = None
    contract: PlayerContract | None = None
    pick_obj: DraftPickAsset | None = None
    note: str = ""

    @classmethod
    def existing_player(cls, player_id: str, *, note: str = "") -> TradeAsset:
        return cls(kind="player", player_id=player_id, note=note)

    @classmethod
    def player(cls, player: FranchisePlayer, contract: PlayerContract | None = None, *, note: str = "") -> TradeAsset:
        return cls(kind="player", player_id=player.player_id, player_obj=player, contract=contract, note=note)

    @classmethod
    def pick(cls, pick: DraftPickAsset, *, note: str = "") -> TradeAsset:
        return cls(kind="pick", pick_obj=pick, note=note)


@dataclass(frozen=True)
class TradePackage:
    label: str
    outgoing: tuple[TradeAsset, ...] = ()
    incoming: tuple[TradeAsset, ...] = ()
    target_team_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradeScore:
    package: TradePackage
    outgoing_value: float
    incoming_value: float
    salary_out: int
    salary_in: int
    cap_legal: bool
    acceptance_score: int
    decision: str
    reasons: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)


def trade_recommendations(context: TeamContext, direction: TeamDirection | None = None):
    from .transactions import recommend_team_transactions

    return tuple(item for item in recommend_team_transactions(context, direction) if item.kind == "trade")


def draft_pick_trade_value(pick: DraftPickAsset, *, current_season: int) -> float:
    if pick.round <= 1:
        value = 18.0
    elif pick.round == 2:
        value = 5.0
    else:
        value = 1.0

    years_out = max(0, pick.year - current_season)
    value -= min(8.0, years_out * 1.5)

    protection = pick.protection.lower().replace("-", " ").strip()
    if protection:
        if "top 3" in protection or "top 4" in protection or "top 5" in protection:
            value *= 0.72
        elif "top 10" in protection or "lottery" in protection:
            value *= 0.55
        elif "protected" in protection:
            value *= 0.8

    if pick.incoming_from:
        value += 1.5
    if pick.outgoing_to:
        value = -abs(value)
    return round(value, 2)


def score_trade_package(context: TeamContext, package: TradePackage, direction: TeamDirection | None = None) -> TradeScore:
    direction = direction or _infer_trade_direction(context)
    outgoing_value = sum(_asset_value(context, asset, incoming=False, direction=direction) for asset in package.outgoing)
    incoming_value = sum(_asset_value(context, asset, incoming=True, direction=direction) for asset in package.incoming)
    salary_out = sum(_asset_salary(context, asset) for asset in package.outgoing)
    salary_in = sum(_asset_salary(context, asset) for asset in package.incoming)
    cap_legal, cap_reason = _salary_match_result(context, salary_out=salary_out, salary_in=salary_in)
    direction_bonus, direction_reasons = _direction_bonus(context, package, direction=direction)
    margin = incoming_value - outgoing_value
    score = int(round(50 + margin * 1.7 + direction_bonus))
    reasons = list(direction_reasons)
    if margin >= 8:
        reasons.append("incoming asset value clears outgoing value")
    elif margin <= -8:
        reasons.append("outgoing asset value is too high for return")
    if cap_reason:
        reasons.append(cap_reason)
    if not cap_legal:
        score = min(score, 35)
    score = max(0, min(100, score))
    decision = "accept" if cap_legal and score >= 60 else "consider" if cap_legal and score >= 45 else "reject"
    return TradeScore(
        package=package,
        outgoing_value=round(outgoing_value, 2),
        incoming_value=round(incoming_value, 2),
        salary_out=salary_out,
        salary_in=salary_in,
        cap_legal=cap_legal,
        acceptance_score=score,
        decision=decision,
        reasons=tuple(reasons or ("neutral trade value",)),
        evidence={
            "direction": direction.value,
            "value_margin": round(margin, 2),
            "direction_bonus": round(direction_bonus, 2),
            "salary_out": salary_out,
            "salary_in": salary_in,
            "cap_space": context.cap.cap_space,
            "tax_team": context.cap.is_tax_team,
        },
    )


def generate_trade_proposals(context: TeamContext, direction: TeamDirection | None = None) -> tuple[TradePackage, ...]:
    direction = direction or _infer_trade_direction(context)
    proposals: list[TradePackage] = []
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        veteran = _best_trade_veteran(context)
        if veteran is not None:
            proposals.append(
                TradePackage(
                    label=f"Shop veteran {veteran.name or veteran.player_id} for draft assets",
                    outgoing=(TradeAsset.existing_player(veteran.player_id),),
                    incoming=(TradeAsset.pick(DraftPickAsset(context.team.team_id, context.season + 1, round=1, protection="top 8")),),
                    metadata={"reason": "rebuild veterans into first-round equity"},
                )
            )
    elif direction is TeamDirection.CONTEND:
        outgoing = _least_cost_pick_or_player(context)
        label = "Add injury insurance veteran" if context.injuries.active_count else "Add playoff upgrade veteran"
        proposals.append(
            TradePackage(
                label=label,
                outgoing=(outgoing,),
                incoming=(TradeAsset.player(FranchisePlayer("target_veteran", "TRADE", name="Veteran Upgrade", age=30, overall=78, potential=78), PlayerContract("target_veteran", "TRADE", salary=max(2_000_000, _asset_salary(context, outgoing)), years_remaining=1, expiring=True)),),
                metadata={"reason": "contender depth upgrade"},
            )
        )
    else:
        proposals.append(
            TradePackage(
                label="Market scan for balanced upgrade",
                outgoing=(_least_cost_pick_or_player(context),),
                incoming=(TradeAsset.player(FranchisePlayer("balanced_target", "TRADE", name="Balanced Target", age=26, overall=76, potential=79), PlayerContract("balanced_target", "TRADE", salary=6_000_000, years_remaining=2)),),
                metadata={"reason": "evaluation phase market scan"},
            )
        )
    return tuple(proposals)


def rank_trade_proposals(context: TeamContext, proposals: tuple[TradePackage, ...] | None = None, direction: TeamDirection | None = None) -> tuple[TradeScore, ...]:
    direction = direction or _infer_trade_direction(context)
    proposals = proposals or generate_trade_proposals(context, direction=direction)
    return tuple(sorted((score_trade_package(context, proposal, direction=direction) for proposal in proposals), key=lambda score: score.acceptance_score, reverse=True))


def _infer_trade_direction(context: TeamContext) -> TeamDirection:
    if context.record.win_pct >= 0.58 or context.record.expected_win_pct >= 0.58 or context.roster.star_quality >= 88:
        return TeamDirection.CONTEND
    if context.record.win_pct <= 0.35 and context.roster.young_core_count >= 1:
        return TeamDirection.REBUILD
    if context.record.win_pct <= 0.30 and context.roster.star_quality < 82:
        return TeamDirection.TANK
    return TeamDirection.EVALUATE


def _asset_value(context: TeamContext, asset: TradeAsset, *, incoming: bool, direction: TeamDirection) -> float:
    if asset.kind == "pick" and asset.pick_obj is not None:
        value = draft_pick_trade_value(asset.pick_obj, current_season=context.season)
        if direction in {TeamDirection.REBUILD, TeamDirection.TANK} and incoming:
            value *= 1.35
        if direction is TeamDirection.CONTEND and not incoming:
            value *= 0.85
        return value

    player = asset.player_obj or _player_by_id(context, asset.player_id)
    if player is None:
        return 0.0
    value = player_asset_value(player) - 68.0
    contract = asset.contract or _contract_by_player_id(context, player.player_id)
    if contract is not None:
        value += _contract_adjustment(player, contract, incoming=incoming, direction=direction)
    if direction is TeamDirection.CONTEND and incoming and (player.overall or 0) >= 77:
        value += 7.0
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK} and incoming and (player.age or 99) <= 24 and (player.potential or 0) >= 80:
        value += 12.0
    return round(value, 2)


def _contract_adjustment(player: FranchisePlayer, contract: PlayerContract, *, incoming: bool, direction: TeamDirection) -> float:
    salary_m = contract.salary / 1_000_000
    value = 0.0
    if contract.expiring and salary_m >= 8:
        value += 3.0
    if contract.years_remaining >= 3 and salary_m >= 30 and (player.overall or 0) < 86:
        value -= 10.0
    elif contract.years_remaining >= 2 and salary_m >= 25 and (player.overall or 0) < 82:
        value -= 6.0
    if direction in {TeamDirection.REBUILD, TeamDirection.TANK} and incoming and contract.years_remaining <= 1:
        value += 2.0
    return value


def _direction_bonus(context: TeamContext, package: TradePackage, *, direction: TeamDirection) -> tuple[float, tuple[str, ...]]:
    reasons: list[str] = []
    bonus = 0.0
    incoming_players = [asset.player_obj for asset in package.incoming if asset.player_obj is not None]
    incoming_picks = [asset.pick_obj for asset in package.incoming if asset.pick_obj is not None]
    outgoing_players = [_player_by_id(context, asset.player_id) for asset in package.outgoing if asset.kind == "player"]

    if direction is TeamDirection.CONTEND:
        if any((player.overall or 0) >= 77 for player in incoming_players):
            bonus += 7.0
            reasons.append("contender gains rotation-ready veteran")
        if context.injuries.active_count and incoming_players:
            bonus += 5.0
            reasons.append("injury insurance fits current roster risk")
    elif direction in {TeamDirection.REBUILD, TeamDirection.TANK}:
        if incoming_picks:
            bonus += 10.0
            reasons.append("draft equity fits rebuild plan")
        if any((player.age or 99) <= 24 and (player.potential or 0) >= 80 for player in incoming_players):
            bonus += 10.0
            reasons.append("young incoming player fits team timeline")
        if any(player and (player.age or 0) >= 31 for player in outgoing_players):
            bonus += 4.0
            reasons.append("veteran outgoing asset clears minutes for youth")
    return bonus, tuple(reasons)


def _salary_match_result(context: TeamContext, *, salary_out: int, salary_in: int) -> tuple[bool, str]:
    if salary_in <= salary_out:
        return True, "incoming salary does not exceed outgoing salary"
    if context.cap.salary_cap and context.cap.cap_space >= salary_in - salary_out:
        return True, "cap space covers incoming salary increase"
    if context.cap.salary_cap and context.cap.payroll <= context.cap.salary_cap:
        return False, "salary increase exceeds available cap space"
    allowed_incoming = max(int(salary_out * 1.25) + 250_000, salary_out + 7_500_000)
    if salary_in <= allowed_incoming:
        return True, "over-cap salary match is legal"
    return False, "incoming salary fails over-cap salary matching"


def _asset_salary(context: TeamContext, asset: TradeAsset) -> int:
    if asset.contract is not None:
        return asset.contract.salary
    if asset.kind != "player":
        return 0
    contract = _contract_by_player_id(context, asset.player_id)
    return 0 if contract is None else contract.salary


def _player_by_id(context: TeamContext, player_id: str) -> FranchisePlayer | None:
    return next((player for player in context.roster.players if player.player_id == player_id), None)


def _contract_by_player_id(context: TeamContext, player_id: str) -> PlayerContract | None:
    return next((contract for contract in context.contracts if contract.player_id == player_id), None)


def _best_trade_veteran(context: TeamContext) -> FranchisePlayer | None:
    candidates = [player for player in context.roster.players if (player.age or 0) >= 31 or (_contract_by_player_id(context, player.player_id) or PlayerContract(player.player_id, player.team_id)).salary >= 25_000_000]
    candidates.sort(key=lambda player: ((player.age or 0), (player.overall or 0)), reverse=True)
    return candidates[0] if candidates else None


def _least_cost_pick_or_player(context: TeamContext) -> TradeAsset:
    seconds = [pick for pick in context.draft_picks if pick.round == 2 and not pick.outgoing_to]
    if seconds:
        return TradeAsset.pick(seconds[0])
    low_minutes = sorted(context.roster.players, key=lambda player: ((player.minutes or 0), (player.overall or 0)))
    if low_minutes:
        return TradeAsset.existing_player(low_minutes[0].player_id)
    return TradeAsset.pick(DraftPickAsset(context.team.team_id, context.season + 2, round=2))
