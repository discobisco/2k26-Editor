from __future__ import annotations

import math

from ..api.v1.models import FranchiseState, RosterPlayer, TradeEvaluation, TradeProposal


class TradeEngine:
    def _age_curve(self, age: int) -> float:
        if age <= 23:
            return 1.08
        if age <= 27:
            return 1.0
        if age <= 31:
            return 0.93
        return 0.84

    def _player_value(self, player: RosterPlayer) -> float:
        base = (player.overall * 0.75) + (player.potential * 0.25)
        age_adjusted = base * self._age_curve(player.age)
        contract_efficiency = 0.0 if player.salary <= 0 else min(15.0, (player.overall * 1_000_000.0) / player.salary)
        years_bonus = max(0.0, (4 - player.contract_years) * 0.7)
        return age_adjusted + contract_efficiency + years_bonus

    def evaluate(
        self,
        *,
        franchise_state: FranchiseState,
        proposal: TradeProposal,
        cpu_profile: str,
    ) -> TradeEvaluation:
        roster_by_id = {p.player_id: p for p in franchise_state.roster}

        outgoing = [roster_by_id[pid] for pid in proposal.outgoing_player_ids if pid in roster_by_id]
        incoming = [roster_by_id[pid] for pid in proposal.incoming_player_ids if pid in roster_by_id]

        outgoing_value = sum(self._player_value(p) for p in outgoing) + proposal.outgoing_asset_value
        incoming_value = sum(self._player_value(p) for p in incoming) + proposal.incoming_asset_value

        value_delta = incoming_value - outgoing_value
        outgoing_salary = sum(p.salary for p in outgoing)
        incoming_salary = sum(p.salary for p in incoming)
        projected_cap_delta = outgoing_salary - incoming_salary

        profile_weight = 1.0
        if cpu_profile == "modern-aggressive":
            profile_weight = 1.1
        elif cpu_profile == "modern-conservative":
            profile_weight = 0.9

        fairness_raw = 0.0 if (incoming_value + outgoing_value) == 0 else value_delta / (incoming_value + outgoing_value)
        fairness_score = math.tanh(fairness_raw * 4.0 * profile_weight)

        abs_score = abs(fairness_score)
        if abs_score <= 0.10:
            verdict = "fair"
        elif abs_score <= 0.25:
            verdict = "leans_from_team" if fairness_score > 0 else "leans_to_team"
        else:
            verdict = "unbalanced"

        rationale = [
            f"Outgoing value: {outgoing_value:.2f}",
            f"Incoming value: {incoming_value:.2f}",
            f"CPU profile: {cpu_profile}",
            f"Projected cap delta: {projected_cap_delta:,.0f}",
        ]
        return TradeEvaluation(
            fairness_score=float(fairness_score),
            verdict=verdict,  # type: ignore[arg-type]
            rationale=rationale,
            projected_cap_delta=float(projected_cap_delta),
        )
