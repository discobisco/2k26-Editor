from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from .docx_reader import (
    DocxContent,
    extract_date_token,
    find_paragraph,
    load_docx,
    parse_currency_amount,
    parse_percent,
)
from .schema import RuleCitation
from .section_registry import BODY_SECTION_ANCHORS, TABLE_ANCHORS


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


def _load_yaml_json(path: Path) -> Dict[str, Any]:
    # Files are intentionally authored as JSON-compatible YAML for zero extra deps.
    return dict(json.loads(path.read_text(encoding="utf-8")))


def load_manifest(path: Path | None = None) -> Dict[str, Any]:
    manifest_path = path or (Path(__file__).resolve().parent / "extraction_manifest.yaml")
    return _load_yaml_json(manifest_path)


def load_manual_overrides(path: Path | None = None) -> Dict[str, Any]:
    overrides_path = path or (Path(__file__).resolve().parent / "manual_overrides_2025_26.yaml")
    return _load_yaml_json(overrides_path)


def _add_citation(
    citations: Dict[str, RuleCitation],
    *,
    citation_id: str,
    article: str,
    section: str,
    paragraph_index: int | None = None,
    table_index: int | None = None,
    source_type: str = "docx",
    note: str = "",
) -> str:
    if citation_id not in citations:
        citations[citation_id] = RuleCitation(
            citation_id=citation_id,
            article=article,
            section=section,
            paragraph_index=paragraph_index,
            table_index=table_index,
            source_type=source_type,
            note=note,
        )
    return citation_id


def _parse_money_rate(text: str) -> float:
    m = re.search(r"\$(-?\d+(?:\.\d+)?)\s*-for-\s*\$1", text.replace(" ", ""), flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"unable to parse tax rate from '{text}'")
    return float(m.group(1))


def _extract_cap_rules(content: DocxContent, citations: Dict[str, RuleCitation]) -> Dict[str, Any]:
    p_cap = content.paragraph(BODY_SECTION_ANCHORS["article_vii_section_2_cap_tax_aprons_draft_penalty"].paragraph_index + 2)
    p_min = content.paragraph(1398)
    p_tax = content.paragraph(1399)

    cap_citations = {
        "salary_cap_percent_bri": [
            _add_citation(citations, citation_id="cap_salary_cap_percent", article="VII", section="2(a)", paragraph_index=1394)
        ],
        "minimum_team_salary_percent_cap": [
            _add_citation(citations, citation_id="cap_min_team_salary_percent", article="VII", section="2(a)", paragraph_index=1398)
        ],
        "tax_level_percent_cap": [
            _add_citation(citations, citation_id="cap_tax_level_percent", article="VII", section="2(a)", paragraph_index=1399)
        ],
        "apron_levels": [
            _add_citation(
                citations,
                citation_id="cap_apron_levels_table",
                article="VII",
                section="2(e)(4)",
                table_index=TABLE_ANCHORS["apron_levels"],
            )
        ],
        "tax_brackets_non_repeater": [
            _add_citation(
                citations,
                citation_id="cap_tax_brackets_non_repeater",
                article="VII",
                section="2",
                table_index=TABLE_ANCHORS["tax_brackets_non_repeater"],
            )
        ],
        "tax_brackets_repeater": [
            _add_citation(
                citations,
                citation_id="cap_tax_brackets_repeater",
                article="VII",
                section="2",
                table_index=TABLE_ANCHORS["tax_brackets_repeater"],
            )
        ],
        "transaction_restrictions": [
            _add_citation(
                citations,
                citation_id="cap_transaction_restrictions",
                article="VII",
                section="2(e)(4)",
                table_index=TABLE_ANCHORS["transaction_restrictions"],
            ),
            _add_citation(
                citations,
                citation_id="cap_transaction_restrictions_text",
                article="VII",
                section="2(e)(2)",
                paragraph_index=1508,
            ),
        ],
        "excluded_international_payment_by_season": [
            _add_citation(
                citations,
                citation_id="cap_excluded_international_payment",
                article="VII",
                section="3(e)",
                table_index=TABLE_ANCHORS["excluded_international_payment"],
            )
        ],
        "taxpayer_mle_base_2023_24": [
            _add_citation(
                citations,
                citation_id="cap_taxpayer_mle_base",
                article="VII",
                section="6(f)",
                table_index=TABLE_ANCHORS["taxpayer_mle_base"],
            )
        ],
    }

    apron_table = content.table(TABLE_ANCHORS["apron_levels"])
    first_apron_by_season: Dict[str, float] = {}
    second_apron_by_season: Dict[str, float] = {}
    for row in apron_table.rows[1:]:
        if len(row) < 3:
            continue
        season = row[0].strip()
        if not season:
            continue
        first_apron_by_season[season] = parse_currency_amount(row[1])
        second_apron_by_season[season] = parse_currency_amount(row[2])

    def _parse_tax_table(table_index: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        table = content.table(table_index)
        for row in table.rows[2:]:
            if len(row) < 3:
                continue
            label = row[0].strip()
            if not label:
                continue
            rec: Dict[str, Any] = {"range": label}
            try:
                rec["rate_2023_24_2024_25"] = _parse_money_rate(row[1])
            except Exception:
                rec["rate_2023_24_2024_25"] = row[1]
            try:
                rec["rate_2025_26_plus"] = _parse_money_rate(row[2])
            except Exception:
                rec["rate_2025_26_plus"] = row[2]
            out.append(rec)
        return out

    txn_table = content.table(TABLE_ANCHORS["transaction_restrictions"])
    transaction_restrictions: Dict[str, str] = {}
    for row in txn_table.rows[1:]:
        if len(row) < 2:
            continue
        m = re.match(r"^([A-K])\.", row[0], flags=re.IGNORECASE)
        if not m:
            continue
        row_id = m.group(1).upper()
        level = "second_apron" if "second apron" in row[1].lower() else "first_apron"
        transaction_restrictions[row_id] = level

    excluded_table = content.table(TABLE_ANCHORS["excluded_international_payment"])
    excluded_by_season: Dict[str, float] = {}
    for row in excluded_table.rows[1:]:
        if len(row) < 2:
            continue
        season = row[0].strip()
        if not season:
            continue
        excluded_by_season[season] = parse_currency_amount(row[1])

    mle_table = content.table(TABLE_ANCHORS["taxpayer_mle_base"])
    taxpayer_mle_base = parse_currency_amount(mle_table.rows[1][1])
    mle_formula_note = mle_table.rows[2][1]

    return {
        "salary_cap_percent_bri": parse_percent(p_cap),
        "minimum_team_salary_percent_cap": parse_percent(p_min),
        "tax_level_percent_cap": parse_percent(p_tax),
        "first_apron_by_season": first_apron_by_season,
        "second_apron_by_season": second_apron_by_season,
        "tax_brackets_non_repeater": _parse_tax_table(TABLE_ANCHORS["tax_brackets_non_repeater"]),
        "tax_brackets_repeater": _parse_tax_table(TABLE_ANCHORS["tax_brackets_repeater"]),
        "transaction_restrictions": transaction_restrictions,
        "excluded_international_payment_by_season": excluded_by_season,
        "taxpayer_mle_base_2023_24": taxpayer_mle_base,
        "taxpayer_mle_formula_note": mle_formula_note,
        "citations": cap_citations,
    }


def _extract_contract_rules(content: DocxContent, citations: Dict[str, RuleCitation]) -> Dict[str, Any]:
    moratorium_def = find_paragraph(content, r"Moratorium Period means")
    contract_citations = {
        "minimum_salary_required": [
            _add_citation(citations, citation_id="contract_minimum_salary_required", article="II", section="6", paragraph_index=702)
        ],
        "max_salary_percent_by_service": [
            _add_citation(citations, citation_id="contract_max_salary_bands", article="II", section="7", paragraph_index=713)
        ],
        "annual_raise_limits": [
            _add_citation(citations, citation_id="contract_raise_limit_5", article="VII", section="5(a)(1)", paragraph_index=1706),
            _add_citation(citations, citation_id="contract_raise_limit_8", article="VII", section="5(a)(2)", paragraph_index=1711),
        ],
        "moratorium": [
            _add_citation(
                citations,
                citation_id="contract_moratorium_definition",
                article="I",
                section="Definitions",
                paragraph_index=(moratorium_def.index if moratorium_def else None),
            ),
            _add_citation(citations, citation_id="contract_moratorium_operational", article="II", section="15", paragraph_index=880),
        ],
        "contract_types": [
            _add_citation(citations, citation_id="contract_10_day", article="II", section="9", paragraph_index=789),
            _add_citation(citations, citation_id="contract_rest_of_season", article="II", section="10", paragraph_index=793),
            _add_citation(citations, citation_id="contract_two_way", article="II", section="11", paragraph_index=796),
        ],
    }
    return {
        "minimum_salary_required": True,
        "minimum_salary_scale_available": False,
        "minimum_salary_scale_note": "Full minimum annual salary exhibit table deferred in phase 1.",
        "max_salary_percent_by_service": {"lt_7": 25.0, "7_to_9": 30.0, "10_plus": 35.0},
        "annual_raise_limits": {"standard": 5.0, "qualifying_or_prior_team": 8.0},
        "moratorium_start": "July 1 12:01 AM ET",
        "moratorium_end": "July 6 12:00 PM ET",
        "ten_day_contract_supported": True,
        "rest_of_season_contract_supported": True,
        "two_way_contract_supported": True,
        "citations": contract_citations,
    }


def _extract_trade_rules(content: DocxContent, citations: Dict[str, RuleCitation]) -> Dict[str, Any]:
    p_cash = content.paragraph(1889)
    p_free_agent = content.paragraph(1894)
    p_prior_team = content.paragraph(1897)
    trade_citations = {
        "cash_trade_limit_percent_cap": [
            _add_citation(citations, citation_id="trade_cash_limit", article="VII", section="8(a)", paragraph_index=1889)
        ],
        "trade_wait_windows": [
            _add_citation(citations, citation_id="trade_wait_rookie", article="VII", section="8(d)(i)", paragraph_index=1893),
            _add_citation(citations, citation_id="trade_wait_free_agent", article="VII", section="8(d)(ii)", paragraph_index=1894),
            _add_citation(citations, citation_id="trade_wait_prior_team_raise", article="VII", section="8(d)(iii)", paragraph_index=1897),
            _add_citation(citations, citation_id="trade_wait_extension", article="VII", section="8(f)(i)", paragraph_index=1906),
            _add_citation(citations, citation_id="trade_wait_designated", article="VII", section="8(f)(ii)", paragraph_index=1907),
        ],
        "post_deadline_trade_blocked": [
            _add_citation(citations, citation_id="trade_deadline_block", article="VII", section="8(c)", paragraph_index=1892)
        ],
        "sign_and_trade_first_year_max_percent_cap": [
            _add_citation(citations, citation_id="trade_sign_and_trade_percent", article="VII", section="8(e)(1)", paragraph_index=1901)
        ],
    }
    return {
        "cash_trade_limit_percent_cap": parse_percent(p_cash),
        "rookie_trade_wait_days": 30,
        "free_agent_trade_wait_months": 3,
        "free_agent_trade_wait_alt_date": extract_date_token(p_free_agent) or "December 15",
        "prior_team_raise_trade_wait_alt_date": extract_date_token(p_prior_team) or "January 15",
        "extension_trade_wait_months": 6,
        "designated_veteran_trade_wait_years": 1,
        "post_deadline_trade_blocked": True,
        "sign_and_trade_first_year_max_percent_cap": 25.0,
        "citations": trade_citations,
    }


def _extract_draft_rules(content: DocxContent, citations: Dict[str, RuleCitation]) -> Dict[str, Any]:
    p_rounds = content.paragraph(2107)
    rookie_table = content.table(TABLE_ANCHORS["rookie_salary_scale_header"])
    rookie_has_values = len(rookie_table.rows) > 1
    draft_citations = {
        "draft_rounds": [
            _add_citation(citations, citation_id="draft_round_count", article="X", section="3", paragraph_index=2107)
        ],
        "rookie_scale_contract_structure": [
            _add_citation(citations, citation_id="draft_rookie_scale_structure", article="VIII", section="1", paragraph_index=2049)
        ],
        "required_tender_deadlines": [
            _add_citation(citations, citation_id="draft_required_tender_deadlines", article="X", section="4", paragraph_index=2110)
        ],
        "draft_pick_penalty_enabled": [
            _add_citation(citations, citation_id="draft_pick_penalty_enabled", article="VII", section="2(f)", paragraph_index=1536)
        ],
        "rookie_scale_table": [
            _add_citation(
                citations,
                citation_id="draft_rookie_scale_table_header",
                article="VIII",
                section="1",
                table_index=TABLE_ANCHORS["rookie_salary_scale_header"],
            )
        ],
    }
    return {
        "draft_rounds": 2 if "(2) rounds" in p_rounds else 2,
        "first_round_rookie_scale_years": 2,
        "first_round_team_option_years": [3, 4],
        "required_tender_deadlines": {
            "first_round": "July 15",
            "second_round_pre_2024": "September 5",
            "second_round_2024_plus": "August 5",
        },
        "draft_pick_penalty_enabled": True,
        "rookie_scale_table_available": rookie_has_values,
        "rookie_scale_table_note": "Rookie salary scale values require exhibit extraction/manual curation in phase 1.",
        "citations": draft_citations,
    }


def _extract_free_agency_rules(content: DocxContent, citations: Dict[str, RuleCitation]) -> Dict[str, Any]:
    p_qo = content.paragraph(2228)
    free_citations = {
        "restricted_offer_sheet_1_2_yos_capped_to_non_taxpayer_mle": [
            _add_citation(citations, citation_id="fa_rfa_offer_cap", article="XI", section="5(d)", paragraph_index=2238)
        ],
        "restricted_match_windows": [
            _add_citation(citations, citation_id="fa_match_window_default", article="XI", section="5(g)", paragraph_index=2251),
            _add_citation(citations, citation_id="fa_match_window_moratorium", article="XI", section="5(g)", paragraph_index=2253),
        ],
        "rofr_post_match_trade_wait": [
            _add_citation(citations, citation_id="fa_rofr_trade_wait", article="XI", section="5(j)", paragraph_index=2254)
        ],
        "qualifying_offer_deadlines": [
            _add_citation(citations, citation_id="fa_qualifying_offer_deadlines", article="XI", section="4(c)(i)", paragraph_index=2228)
        ],
    }
    return {
        "restricted_offer_sheet_1_2_yos_capped_to_non_taxpayer_mle": True,
        "restricted_match_window_default": "11:59 PM ET on day after offer receipt",
        "restricted_match_window_moratorium": "July 7 11:59 PM ET",
        "rofr_post_match_trade_wait_years": 1,
        "qualifying_offer_accept_deadline": extract_date_token(p_qo) or "October 1",
        "qualifying_offer_withdraw_deadline": "July 13",
        "citations": free_citations,
    }


def _extract_roster_rules(content: DocxContent, citations: Dict[str, RuleCitation]) -> Dict[str, Any]:
    roster_citations = {
        "regular_season_roster_bounds": [
            _add_citation(citations, citation_id="roster_regular_bounds", article="XXIX", section="2(a)", paragraph_index=2902)
        ],
        "short_roster_limits": [
            _add_citation(citations, citation_id="roster_short_limits", article="XXIX", section="2(b)", paragraph_index=2904)
        ],
        "offseason_max_players": [
            _add_citation(citations, citation_id="roster_offseason_max", article="XXIX", section="2(d)", paragraph_index=2910)
        ],
        "postseason_waiver_deadline": [
            _add_citation(citations, citation_id="roster_postseason_waiver_deadline", article="XXIX", section="4", paragraph_index=2916)
        ],
        "two_way_postseason_eligibility": [
            _add_citation(citations, citation_id="roster_two_way_postseason", article="XXIX", section="3", paragraph_index=2914)
        ],
    }
    return {
        "regular_season_min_players": 14,
        "regular_season_max_players": 15,
        "short_roster_min_players": 12,
        "short_roster_max_consecutive_weeks": 2,
        "short_roster_max_days_total": 28,
        "offseason_max_players": 21,
        "postseason_waiver_deadline": "March 1 11:59 PM ET",
        "two_way_postseason_eligible": False,
        "citations": roster_citations,
    }


def extract_raw_rules(
    source_path: Path | str,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, RuleCitation]]:
    resolved_manifest = dict(manifest or load_manifest())
    content = load_docx(source_path)
    citations: Dict[str, RuleCitation] = {}

    raw = {
        "ruleset_version": str(resolved_manifest.get("ruleset_version", "1.0.0")),
        "generated_at_utc": _now_utc(),
        "source_doc": str(source_path),
        "pull_first_sections": list(resolved_manifest.get("pull_first_sections", [])),
        "deferred_sections": list(resolved_manifest.get("deferred_sections", [])),
        "cap": _extract_cap_rules(content, citations),
        "contract": _extract_contract_rules(content, citations),
        "trade": _extract_trade_rules(content, citations),
        "draft": _extract_draft_rules(content, citations),
        "free_agency": _extract_free_agency_rules(content, citations),
        "roster": _extract_roster_rules(content, citations),
    }
    return raw, citations
