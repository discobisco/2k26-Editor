from __future__ import annotations

from dataclasses import dataclass

from .world import FranchisePlayer, TeamContext


@dataclass(frozen=True)
class AssetBreakdown:
    player_value: float
    contract_value: float
    draft_value: float
    cap_flexibility: float
    total: float


def player_asset_value(player: FranchisePlayer) -> float:
    rating = player.overall if player.overall is not None else 65.0
    potential = player.potential if player.potential is not None else rating
    age = player.age if player.age is not None else 27.0
    age_curve = 8.0 if age <= 23 else 4.0 if age <= 26 else 0.0 if age <= 30 else -4.0 if age <= 33 else -8.0
    development = player.development or 0.0
    morale = ((player.morale if player.morale is not None else 50.0) - 50.0) / 10.0
    return round(rating + (potential - rating) * 0.35 + age_curve + development + morale, 2)


def team_asset_breakdown(context: TeamContext) -> AssetBreakdown:
    player_values = sorted((player_asset_value(player) for player in context.roster.players), reverse=True)
    player_value = sum(player_values[:8]) / max(1, min(8, len(player_values))) if player_values else 0.0
    contract_drag = 0.0
    for contract in context.contracts:
        if contract.salary >= 30_000_000 and contract.years_remaining >= 2:
            contract_drag += 4.0
        elif contract.expiring and contract.salary >= 10_000_000:
            contract_drag -= 2.0
    cap_flexibility = max(-20.0, min(20.0, context.cap.cap_space / 5_000_000 if context.cap.salary_cap else 0.0))
    if context.cap.is_tax_team:
        cap_flexibility -= min(20.0, context.cap.luxury_tax_overage / 5_000_000)
    draft_value = context.draft_assets.pick_value
    total = player_value - contract_drag + cap_flexibility + draft_value
    return AssetBreakdown(round(player_value, 2), round(-contract_drag, 2), round(draft_value, 2), round(cap_flexibility, 2), round(total, 2))


def team_need_summary(context: TeamContext) -> tuple[str, ...]:
    needs: list[str] = []
    if context.roster.star_quality < 82:
        needs.append("primary star")
    if context.roster.top_two_quality < 80:
        needs.append("second creator")
    if context.injuries.active_count:
        needs.append("injury insurance")
    if context.cap.is_tax_team:
        needs.append("salary relief")
    if context.roster.young_core_count < 2 and context.record.win_pct < 0.45:
        needs.append("young core")
    return tuple(needs or ("balanced depth",))
