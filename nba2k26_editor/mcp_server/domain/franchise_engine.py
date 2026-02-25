from __future__ import annotations

from ..api.v1.models import EraConfig, FranchiseState, LeagueRuleSet


class FranchiseEngine:
    def optimize(
        self,
        *,
        franchise_state: FranchiseState,
        era_config: EraConfig,
        league_rules: LeagueRuleSet,
    ) -> dict[str, object]:
        payroll = sum(player.salary for player in franchise_state.roster)
        avg_overall = sum(player.overall for player in franchise_state.roster) / max(1, len(franchise_state.roster))
        avg_potential = sum(player.potential for player in franchise_state.roster) / max(1, len(franchise_state.roster))
        expiring_salary = sum(player.salary for player in franchise_state.roster if player.contract_years <= 1)

        recommendations: list[str] = []
        if franchise_state.owner_goal == "win-now":
            recommendations.append("Prioritize two-way veteran depth for the playoff rotation.")
            recommendations.append("Package sub-rotation contracts for one higher-impact starter.")
        elif franchise_state.owner_goal == "rebuild":
            recommendations.append("Flip expiring veterans for future first-round capital.")
            recommendations.append("Shift minutes to players with high potential growth curves.")
        else:
            recommendations.append("Balance cap flexibility with incremental roster upgrades.")
            recommendations.append("Protect positive-value contracts and avoid negative-value extensions.")

        tax_line = league_rules.luxury_tax_line if league_rules.luxury_tax_line > 0 else era_config.luxury_tax_line
        if payroll > tax_line:
            recommendations.append("Trim payroll below tax threshold to avoid repeater pressure.")

        next_season_space = max(0.0, era_config.salary_cap - payroll + (expiring_salary * 0.7))
        competitiveness = (avg_overall * 0.65) + (avg_potential * 0.35)
        flexibility = min(1.0, next_season_space / max(1.0, era_config.salary_cap))
        championship_odds = max(0.01, min(0.80, ((competitiveness / 100.0) * 0.7) + (flexibility * 0.3)))

        return {
            "recommended_moves": recommendations,
            "cap_projection": {
                "current_payroll": float(payroll),
                "next_season_space": float(next_season_space),
            },
            "championship_odds": float(championship_odds),
            "diagnostics": {
                "avg_overall": float(avg_overall),
                "avg_potential": float(avg_potential),
                "expiring_salary": float(expiring_salary),
            },
        }
