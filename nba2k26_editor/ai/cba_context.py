from __future__ import annotations

from typing import List

from ..gm_rl.cba.repository import load_ruleset_for_season


def _format_with_citations(text: str, citations: List[str]) -> str:
    if not citations:
        return text
    return f"{text} [cites: {', '.join(citations)}]"


def build_cba_guidance(*, season: str = "2025-26", rules_path: str | None = None) -> str:
    try:
        rules = load_ruleset_for_season(season, rules_path)
    except Exception:
        return ""

    lines: List[str] = []
    lines.append(
        _format_with_citations(
            f"Salary cap ruleset baseline: {season}; first apron ${rules.cap.first_apron_by_season.get(season, 0.0):,.0f}; second apron ${rules.cap.second_apron_by_season.get(season, 0.0):,.0f}.",
            rules.cap.citations.get("apron_levels", []),
        )
    )
    lines.append(
        _format_with_citations(
            f"Max first-year salary bands by service years: <7={rules.contract.max_salary_percent_by_service.get('lt_7', 25):.0f}%, 7-9={rules.contract.max_salary_percent_by_service.get('7_to_9', 30):.0f}%, 10+={rules.contract.max_salary_percent_by_service.get('10_plus', 35):.0f}%.",
            rules.contract.citations.get("max_salary_percent_by_service", []),
        )
    )
    lines.append(
        _format_with_citations(
            f"Annual raise/decrease limits: standard {rules.contract.annual_raise_limits.get('standard', 5):.0f}%, qualifying/prior-team {rules.contract.annual_raise_limits.get('qualifying_or_prior_team', 8):.0f}%.",
            rules.contract.citations.get("annual_raise_limits", []),
        )
    )
    lines.append(
        _format_with_citations(
            f"Trade cash in a salary-cap year is capped at {rules.trade.cash_trade_limit_percent_cap:.2f}% of salary cap; post-deadline player trades are blocked.",
            rules.trade.citations.get("cash_trade_limit_percent_cap", []) + rules.trade.citations.get("post_deadline_trade_blocked", []),
        )
    )
    lines.append(
        _format_with_citations(
            f"Roster bounds in season: {rules.roster.regular_season_min_players}-{rules.roster.regular_season_max_players}; postseason waiver deadline {rules.roster.postseason_waiver_deadline}.",
            rules.roster.citations.get("regular_season_roster_bounds", []) + rules.roster.citations.get("postseason_waiver_deadline", []),
        )
    )
    lines.append(
        _format_with_citations(
            "Restricted FA offer sheets for 1-2 YOS are capped to non-taxpayer MLE.",
            rules.free_agency.citations.get("restricted_offer_sheet_1_2_yos_capped_to_non_taxpayer_mle", []),
        )
    )
    return "\n".join(f"- {line}" for line in lines)

