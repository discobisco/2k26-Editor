from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class RuleCitation:
    citation_id: str
    article: str
    section: str
    paragraph_index: Optional[int] = None
    table_index: Optional[int] = None
    source_type: str = "docx"
    note: str = ""


@dataclass
class CapRules:
    salary_cap_percent_bri: float
    minimum_team_salary_percent_cap: float
    tax_level_percent_cap: float
    first_apron_by_season: Dict[str, float]
    second_apron_by_season: Dict[str, float]
    tax_brackets_non_repeater: List[Dict[str, Any]]
    tax_brackets_repeater: List[Dict[str, Any]]
    transaction_restrictions: Dict[str, str]
    excluded_international_payment_by_season: Dict[str, float]
    taxpayer_mle_base_2023_24: float
    taxpayer_mle_formula_note: str
    citations: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class ContractRules:
    minimum_salary_required: bool
    minimum_salary_scale_available: bool
    minimum_salary_scale_note: str
    max_salary_percent_by_service: Dict[str, float]
    annual_raise_limits: Dict[str, float]
    moratorium_start: str
    moratorium_end: str
    ten_day_contract_supported: bool
    rest_of_season_contract_supported: bool
    two_way_contract_supported: bool
    citations: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class TradeRules:
    cash_trade_limit_percent_cap: float
    rookie_trade_wait_days: int
    free_agent_trade_wait_months: int
    free_agent_trade_wait_alt_date: str
    prior_team_raise_trade_wait_alt_date: str
    extension_trade_wait_months: int
    designated_veteran_trade_wait_years: int
    post_deadline_trade_blocked: bool
    sign_and_trade_first_year_max_percent_cap: float
    citations: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class DraftRules:
    draft_rounds: int
    first_round_rookie_scale_years: int
    first_round_team_option_years: List[int]
    required_tender_deadlines: Dict[str, str]
    draft_pick_penalty_enabled: bool
    rookie_scale_table_available: bool
    rookie_scale_table_note: str
    citations: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class FreeAgencyRules:
    restricted_offer_sheet_1_2_yos_capped_to_non_taxpayer_mle: bool
    restricted_match_window_default: str
    restricted_match_window_moratorium: str
    rofr_post_match_trade_wait_years: int
    qualifying_offer_accept_deadline: str
    qualifying_offer_withdraw_deadline: str
    citations: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class RosterRules:
    regular_season_min_players: int
    regular_season_max_players: int
    short_roster_min_players: int
    short_roster_max_consecutive_weeks: int
    short_roster_max_days_total: int
    offseason_max_players: int
    postseason_waiver_deadline: str
    two_way_postseason_eligible: bool
    citations: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class CbaRuleSet:
    ruleset_version: str
    season: str
    source_doc: str
    generated_at_utc: str
    pull_first_sections: List[str]
    deferred_sections: List[str]
    cap: CapRules
    contract: ContractRules
    trade: TradeRules
    draft: DraftRules
    free_agency: FreeAgencyRules
    roster: RosterRules
    citations: List[RuleCitation]
    unresolved_fields: List[str] = field(default_factory=list)
    confidence_flags: Dict[str, str] = field(default_factory=dict)
    overrides_applied: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CbaRuleSet":
        citations = [RuleCitation(**c) for c in data.get("citations", [])]
        return cls(
            ruleset_version=str(data.get("ruleset_version", "0.0.0")),
            season=str(data.get("season", "2025-26")),
            source_doc=str(data.get("source_doc", "")),
            generated_at_utc=str(data.get("generated_at_utc", "")),
            pull_first_sections=list(data.get("pull_first_sections", [])),
            deferred_sections=list(data.get("deferred_sections", [])),
            cap=CapRules(**dict(data.get("cap", {}))),
            contract=ContractRules(**dict(data.get("contract", {}))),
            trade=TradeRules(**dict(data.get("trade", {}))),
            draft=DraftRules(**dict(data.get("draft", {}))),
            free_agency=FreeAgencyRules(**dict(data.get("free_agency", {}))),
            roster=RosterRules(**dict(data.get("roster", {}))),
            citations=citations,
            unresolved_fields=list(data.get("unresolved_fields", [])),
            confidence_flags=dict(data.get("confidence_flags", {})),
            overrides_applied=list(data.get("overrides_applied", [])),
        )

