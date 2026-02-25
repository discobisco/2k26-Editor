from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .schema import (
    CbaRuleSet,
    CapRules,
    ContractRules,
    DraftRules,
    FreeAgencyRules,
    RosterRules,
    RuleCitation,
    TradeRules,
)


def _get_nested(data: Mapping[str, Any], dotted_path: str) -> Any:
    cur: Any = data
    for part in dotted_path.split("."):
        if isinstance(cur, Mapping):
            if part not in cur:
                return None
            cur = cur[part]
            continue
        return None
    return cur


def _set_nested(data: Dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    cur: Dict[str, Any] = data
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _apply_overrides(
    raw: Dict[str, Any],
    citations: Dict[str, RuleCitation],
    overrides: Mapping[str, Any] | None,
) -> List[str]:
    applied: List[str] = []
    if not overrides:
        return applied
    for override in overrides.get("overrides", []):
        field = str(override.get("field", "")).strip()
        if not field:
            continue
        _set_nested(raw, field, override.get("value"))
        applied.append(field)
        citation_id = str(override.get("citation_id", "")).strip()
        if citation_id:
            citations[citation_id] = RuleCitation(
                citation_id=citation_id,
                article=str(override.get("article", "")),
                section=str(override.get("section", "")),
                source_type=str(override.get("source_type", "manual_override")),
                note=str(override.get("note", "")),
            )
    return applied


def _validate_required_fields(raw: Mapping[str, Any], required_fields: Iterable[str]) -> None:
    missing: List[str] = []
    for field in required_fields:
        value = _get_nested(raw, field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)
    if missing:
        raise ValueError(f"missing required extracted fields: {', '.join(missing)}")


def _find_unresolved_fields(raw: Mapping[str, Any]) -> List[str]:
    unresolved: List[str] = []

    def walk(prefix: str, obj: Any) -> None:
        if isinstance(obj, Mapping):
            for key, val in obj.items():
                walk(f"{prefix}.{key}" if prefix else str(key), val)
            return
        if obj is None:
            unresolved.append(prefix)

    walk("", raw)
    return unresolved


def normalize_rules(
    raw_rules: Mapping[str, Any],
    citations: Mapping[str, RuleCitation],
    *,
    season: str,
    manifest: Mapping[str, Any],
    overrides: Mapping[str, Any] | None = None,
) -> Tuple[CbaRuleSet, Dict[str, Any]]:
    raw = deepcopy(dict(raw_rules))
    citation_map = {k: v for k, v in citations.items()}
    overrides_applied = _apply_overrides(raw, citation_map, overrides)
    _validate_required_fields(raw, manifest.get("required_fields", []))
    unresolved_fields = _find_unresolved_fields(raw)

    confidence_flags = {
        "cap": "high",
        "contract": "medium",
        "trade": "high",
        "draft": "medium",
        "free_agency": "medium",
        "roster": "high",
    }
    if overrides_applied:
        confidence_flags["manual_overrides"] = "applied"

    ruleset = CbaRuleSet(
        ruleset_version=str(raw.get("ruleset_version", manifest.get("ruleset_version", "1.0.0"))),
        season=season,
        source_doc=str(raw.get("source_doc", manifest.get("source_doc", ""))),
        generated_at_utc=str(raw.get("generated_at_utc", "")),
        pull_first_sections=list(raw.get("pull_first_sections", manifest.get("pull_first_sections", []))),
        deferred_sections=list(raw.get("deferred_sections", manifest.get("deferred_sections", []))),
        cap=CapRules(**dict(raw["cap"])),
        contract=ContractRules(**dict(raw["contract"])),
        trade=TradeRules(**dict(raw["trade"])),
        draft=DraftRules(**dict(raw["draft"])),
        free_agency=FreeAgencyRules(**dict(raw["free_agency"])),
        roster=RosterRules(**dict(raw["roster"])),
        citations=list(citation_map.values()),
        unresolved_fields=unresolved_fields,
        confidence_flags=confidence_flags,
        overrides_applied=overrides_applied,
    )

    report = {
        "season": season,
        "source_doc": ruleset.source_doc,
        "ruleset_version": ruleset.ruleset_version,
        "overrides_applied": overrides_applied,
        "unresolved_fields": unresolved_fields,
        "confidence_flags": confidence_flags,
        "citation_count": len(citation_map),
        "required_fields_checked": list(manifest.get("required_fields", [])),
        "summary": {
            "first_apron_2025_26": ruleset.cap.first_apron_by_season.get("2025-26"),
            "second_apron_2025_26": ruleset.cap.second_apron_by_season.get("2025-26"),
            "cash_trade_limit_percent_cap": ruleset.trade.cash_trade_limit_percent_cap,
        },
    }
    return ruleset, report


def ruleset_to_all_years_payload(ruleset: CbaRuleSet) -> Dict[str, Any]:
    payload = {
        "ruleset_version": ruleset.ruleset_version,
        "generated_at_utc": ruleset.generated_at_utc,
        "source_doc": ruleset.source_doc,
        "rulesets": {ruleset.season: asdict(ruleset)},
    }
    return payload

