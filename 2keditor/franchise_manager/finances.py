from __future__ import annotations

from dataclasses import dataclass

from .world import CapSheet, TeamContext


@dataclass(frozen=True)
class FinanceAssessment:
    payroll: int
    salary_cap: int
    luxury_tax_line: int
    cap_space: int
    luxury_tax_overage: int
    status: str
    recommended_budget_action: str


def assess_team_finances(context: TeamContext) -> FinanceAssessment:
    cap = context.cap
    if cap.is_tax_team:
        status = "tax"
        action = "reduce luxury tax exposure or require owner approval for win-now spending"
    elif cap.salary_cap and cap.cap_space > 20_000_000:
        status = "cap_space"
        action = "preserve cap room for free agency or absorb assets"
    elif cap.salary_cap and cap.cap_space < 0:
        status = "over_cap"
        action = "use exceptions and trades instead of cap-space offers"
    else:
        status = "neutral"
        action = "maintain current payroll plan"
    return FinanceAssessment(cap.payroll, cap.salary_cap, cap.luxury_tax_line, cap.cap_space, cap.luxury_tax_overage, status, action)


def cap_sheet_from_context(context: TeamContext) -> CapSheet:
    return context.cap
