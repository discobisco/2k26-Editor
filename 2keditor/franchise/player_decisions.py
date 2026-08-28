from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping


PLAYER_DECISION_FACTORS: tuple[tuple[str, str], ...] = (
    (
        "contract_value_and_security",
        "Compare exact salary, total guarantee, contract length, options, and market risk only when those facts are provided.",
    ),
    (
        "winning_and_championship_outlook",
        "Consider current team quality and championship opportunity without assuming that winning always outweighs contract value.",
    ),
    (
        "role_minutes_and_development",
        "Consider the offered role, playing time, usage, starting opportunity, and development path when supported by the provided facts.",
    ),
    (
        "roster_coach_and_relationship_fit",
        "Consider roster fit and recorded relationships with coaches, teammates, and staff.",
    ),
    (
        "home_family_and_community",
        "Consider hometown, family, and community connections only when explicitly present in the provided data.",
    ),
    (
        "personal_growth_and_cultural_alignment",
        "Consider documented personal goals, organizational values, leadership representation, and cultural fit.",
    ),
    (
        "organization_trust_and_direction",
        "Consider management trust, role commitments, coaching stability, rebuilding direction, and competitive plans.",
    ),
    (
        "tax_and_financial_geography",
        "Consider taxes and other location-specific financial facts only when exact applicable data is provided.",
    ),
    (
        "continuity_and_relocation_cost",
        "Consider established relationships, family stability, familiarity, and the cost of changing teams.",
    ),
)

PLAYER_DECISION_FACTOR_KEYS = frozenset(key for key, _description in PLAYER_DECISION_FACTORS)


@dataclass(frozen=True)
class PlayerFreeAgencyDecisionRequest:
    true_sim_year: int
    free_agency_status: str
    player_index: int
    player_label: str
    player_facts: Mapping[str, object]
    current_team: Mapping[str, object] | None
    offers: tuple[Mapping[str, object], ...]
    era_rules: Mapping[str, object]


@dataclass(frozen=True)
class PlayerFreeAgencyDecision:
    player_index: int
    player_label: str
    decision: str
    selected_team_index: int | None
    selected_team_label: str
    primary_factors: tuple[str, ...]
    reasoning: str
    raw_llm_response: str


def _offer_identity(offer: Mapping[str, object]) -> tuple[int, str]:
    if "team_index" not in offer:
        raise ValueError("free-agency offer is missing team_index")
    if "team_label" not in offer:
        raise ValueError("free-agency offer is missing team_label")
    return int(str(offer["team_index"])), str(offer["team_label"])


def build_player_free_agency_decision_prompt(request: PlayerFreeAgencyDecisionRequest) -> str:
    offer_payloads = tuple(dict(offer) for offer in request.offers)
    for offer in offer_payloads:
        _offer_identity(offer)
    payload = {
        "task": "player_free_agency_decision",
        "rules": [
            "Act only as the named player and the player's representative, not as a team GM.",
            "Evaluate every actual offer together and choose at most one offer.",
            "A signing target, team interest, or negotiation without an offer is not an offer.",
            "Use only the supplied player, team, offer, relationship, location, financial, and era facts.",
            "Do not invent salary, guarantees, contract years, role promises, family preferences, hometown ties, taxes, relationships, personality, or team interest.",
            "Treat career stage and market risk as context from the supplied facts, not as a fixed player class.",
            "Respect free_agency_status and era_rules; do not give the player movement rights unavailable in that era.",
            "The incumbent team must compete as one of the offers if the player is to accept an incumbent-team contract.",
            "Reject all offers when no provided offer is acceptable.",
            "This is a decision only. Do not claim the player was signed, moved, or written to NBA 2K.",
            "Return only valid JSON. No markdown. No prose outside JSON.",
        ],
        "research_based_decision_factors": [
            {"factor": key, "guidance": description}
            for key, description in PLAYER_DECISION_FACTORS
        ],
        "franchise": {
            "true_sim_year": int(request.true_sim_year),
            "free_agency_status": str(request.free_agency_status),
            "era_rules": dict(request.era_rules),
        },
        "player": {
            "player_index": int(request.player_index),
            "player_label": str(request.player_label),
            "facts": dict(request.player_facts),
            "current_team": None if request.current_team is None else dict(request.current_team),
        },
        "offers": list(offer_payloads),
        "required_json_schema": {
            "player_index": int(request.player_index),
            "decision": "accept_offer or reject_all_offers",
            "selected_team_index": "exact team_index from offers when accepting; null when rejecting all offers",
            "selected_team_label": "exact team_label from offers when accepting; empty string when rejecting all offers",
            "primary_factors": "non-empty list using only research_based_decision_factors.factor values",
            "reasoning": "short explanation grounded only in supplied facts",
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _response_json(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain JSON object")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON must be an object")
    return payload


def parse_player_free_agency_decision_response(
    request: PlayerFreeAgencyDecisionRequest,
    response: str,
) -> PlayerFreeAgencyDecision:
    payload = _response_json(response)
    required_keys = (
        "player_index",
        "decision",
        "selected_team_index",
        "selected_team_label",
        "primary_factors",
        "reasoning",
    )
    for key in required_keys:
        if key not in payload:
            raise ValueError(f"LLM response missing {key}")

    player_index = int(str(payload["player_index"]))
    if player_index != int(request.player_index):
        raise ValueError("LLM response player_index does not match requested player")

    decision = str(payload["decision"])
    if decision not in {"accept_offer", "reject_all_offers"}:
        raise ValueError("LLM response decision must be accept_offer or reject_all_offers")

    factors_value = payload["primary_factors"]
    if not isinstance(factors_value, list) or not factors_value:
        raise ValueError("LLM response primary_factors must be a non-empty list")
    primary_factors = tuple(str(factor) for factor in factors_value)
    unknown_factors = tuple(factor for factor in primary_factors if factor not in PLAYER_DECISION_FACTOR_KEYS)
    if unknown_factors:
        raise ValueError(f"LLM response used unknown primary_factors: {', '.join(unknown_factors)}")

    selected_index_value = payload["selected_team_index"]
    selected_team_label = str(payload["selected_team_label"])
    selected_team_index: int | None
    if decision == "accept_offer":
        if selected_index_value is None:
            raise ValueError("accepted offer is missing selected_team_index")
        selected_team_index = int(str(selected_index_value))
        offer_labels = {
            team_index: team_label
            for team_index, team_label in (_offer_identity(offer) for offer in request.offers)
        }
        if selected_team_index not in offer_labels:
            raise ValueError("selected_team_index is not present in offers")
        if selected_team_label != offer_labels[selected_team_index]:
            raise ValueError("selected_team_label does not match the selected offer")
    else:
        if selected_index_value is not None:
            raise ValueError("rejected offers must use null selected_team_index")
        if selected_team_label:
            raise ValueError("rejected offers must use an empty selected_team_label")
        selected_team_index = None

    return PlayerFreeAgencyDecision(
        player_index=player_index,
        player_label=str(request.player_label),
        decision=decision,
        selected_team_index=selected_team_index,
        selected_team_label=selected_team_label,
        primary_factors=primary_factors,
        reasoning=str(payload["reasoning"]),
        raw_llm_response=response,
    )


__all__ = [
    "PLAYER_DECISION_FACTORS",
    "PLAYER_DECISION_FACTOR_KEYS",
    "PlayerFreeAgencyDecision",
    "PlayerFreeAgencyDecisionRequest",
    "build_player_free_agency_decision_prompt",
    "parse_player_free_agency_decision_response",
]
