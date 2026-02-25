from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SectionAnchor:
    section_id: str
    article: str
    section: str
    paragraph_index: int
    title: str


PULL_FIRST_SECTION_IDS: List[str] = [
    "article_ii_section_6_minimum_salary",
    "article_ii_section_7_maximum_salary",
    "article_ii_section_9_10_day_contracts",
    "article_ii_section_10_rest_of_season_contracts",
    "article_ii_section_11_two_way_contracts",
    "article_ii_section_15_moratorium_period",
    "article_vii_section_2_cap_tax_aprons_draft_penalty",
    "article_vii_section_5_contract_structure",
    "article_vii_section_6_cap_exceptions",
    "article_vii_section_8_trade_rules",
    "article_viii_section_1_3_rookie_scale",
    "article_x_draft_timing_and_rights",
    "article_xi_restricted_free_agency",
    "article_xxix_section_2_4_roster_and_waiver_deadline",
    "cba_tables_higher_max_tax_apron_transaction_exception",
]


DEFERRED_SECTION_IDS: List[str] = [
    "article_vii_section_10_12_audit_and_accounting",
    "benefits_conduct_grievance_labor_media_articles",
    "deep_financial_waiver_setoff_stretched_salary",
    "full_legal_text_reproduction_and_non_gameplay_exhibits",
]


BODY_SECTION_ANCHORS: Dict[str, SectionAnchor] = {
    "article_ii_section_6_minimum_salary": SectionAnchor(
        section_id="article_ii_section_6_minimum_salary",
        article="II",
        section="6",
        paragraph_index=701,
        title="Minimum Player Salary",
    ),
    "article_ii_section_7_maximum_salary": SectionAnchor(
        section_id="article_ii_section_7_maximum_salary",
        article="II",
        section="7",
        paragraph_index=711,
        title="Maximum Annual Salary",
    ),
    "article_ii_section_9_10_day_contracts": SectionAnchor(
        section_id="article_ii_section_9_10_day_contracts",
        article="II",
        section="9",
        paragraph_index=789,
        title="10-Day Contracts",
    ),
    "article_ii_section_10_rest_of_season_contracts": SectionAnchor(
        section_id="article_ii_section_10_rest_of_season_contracts",
        article="II",
        section="10",
        paragraph_index=793,
        title="Rest-of-Season Contracts",
    ),
    "article_ii_section_11_two_way_contracts": SectionAnchor(
        section_id="article_ii_section_11_two_way_contracts",
        article="II",
        section="11",
        paragraph_index=796,
        title="Two-Way Contracts",
    ),
    "article_ii_section_15_moratorium_period": SectionAnchor(
        section_id="article_ii_section_15_moratorium_period",
        article="II",
        section="15",
        paragraph_index=880,
        title="Moratorium Period",
    ),
    "article_vii_section_2_cap_tax_aprons_draft_penalty": SectionAnchor(
        section_id="article_vii_section_2_cap_tax_aprons_draft_penalty",
        article="VII",
        section="2",
        paragraph_index=1392,
        title="Salary Cap, Tax Level, Apron Levels, Draft Pick Penalty",
    ),
    "article_vii_section_5_contract_structure": SectionAnchor(
        section_id="article_vii_section_5_contract_structure",
        article="VII",
        section="5",
        paragraph_index=1703,
        title="Salary Cap Contract Structure Rules",
    ),
    "article_vii_section_6_cap_exceptions": SectionAnchor(
        section_id="article_vii_section_6_cap_exceptions",
        article="VII",
        section="6",
        paragraph_index=1733,
        title="Exceptions to the Salary Cap",
    ),
    "article_vii_section_8_trade_rules": SectionAnchor(
        section_id="article_vii_section_8_trade_rules",
        article="VII",
        section="8",
        paragraph_index=1888,
        title="Trade Rules",
    ),
    "article_viii_section_1_3_rookie_scale": SectionAnchor(
        section_id="article_viii_section_1_3_rookie_scale",
        article="VIII",
        section="1-3",
        paragraph_index=2048,
        title="Rookie Scale Contracts / Draft Rights",
    ),
    "article_x_draft_timing_and_rights": SectionAnchor(
        section_id="article_x_draft_timing_and_rights",
        article="X",
        section="2-4",
        paragraph_index=2104,
        title="Draft Timing / Required Tender / Draft Rights",
    ),
    "article_xi_restricted_free_agency": SectionAnchor(
        section_id="article_xi_restricted_free_agency",
        article="XI",
        section="5",
        paragraph_index=2233,
        title="Restricted Free Agency",
    ),
    "article_xxix_section_2_4_roster_and_waiver_deadline": SectionAnchor(
        section_id="article_xxix_section_2_4_roster_and_waiver_deadline",
        article="XXIX",
        section="2-4",
        paragraph_index=2901,
        title="Roster Size / Two-Way / Postseason Waiver Deadline",
    ),
}


TABLE_ANCHORS: Dict[str, int] = {
    "higher_max_criteria": 0,
    "tax_brackets_non_repeater": 1,
    "tax_brackets_repeater": 2,
    "transaction_restrictions": 3,
    "apron_levels": 4,
    "excluded_international_payment": 5,
    "taxpayer_mle_base": 6,
    "rookie_salary_scale_header": 10,
}

