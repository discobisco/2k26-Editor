from __future__ import annotations

import json

import pytest

from nba2k_editor.franchise.player_decisions import (
    PLAYER_DECISION_FACTOR_KEYS,
    PlayerFreeAgencyDecisionRequest,
    build_player_free_agency_decision_prompt,
    parse_player_free_agency_decision_response,
)


def _request() -> PlayerFreeAgencyDecisionRequest:
    return PlayerFreeAgencyDecisionRequest(
        true_sim_year=2026,
        free_agency_status="unrestricted",
        player_index=41,
        player_label="Test Player",
        player_facts={
            "age": 28,
            "position": "SF",
            "current_role": "starter",
            "recorded_home_connection": "Chicago",
        },
        current_team={"team_index": 7, "team_label": "Current Team", "wins": 34},
        offers=(
            {
                "team_index": 2,
                "team_label": "Contender",
                "contract": {"years": 2, "guaranteed_value": 20_000_000},
                "role": "bench",
                "wins": 58,
            },
            {
                "team_index": 7,
                "team_label": "Current Team",
                "contract": {"years": 4, "guaranteed_value": 48_000_000},
                "role": "starter",
                "wins": 34,
            },
        ),
        era_rules={"player_may_choose_offer": True, "original_team_matching_right": False},
    )


def test_player_decision_prompt_preserves_exact_facts_and_all_research_factors() -> None:
    request = _request()

    payload = json.loads(build_player_free_agency_decision_prompt(request))

    assert payload["task"] == "player_free_agency_decision"
    assert payload["franchise"] == {
        "era_rules": {"original_team_matching_right": False, "player_may_choose_offer": True},
        "free_agency_status": "unrestricted",
        "true_sim_year": 2026,
    }
    assert payload["player"]["facts"] == dict(request.player_facts)
    assert payload["player"]["current_team"] == dict(request.current_team or {})
    assert payload["offers"] == [dict(offer) for offer in request.offers]
    assert {
        item["factor"] for item in payload["research_based_decision_factors"]
    } == PLAYER_DECISION_FACTOR_KEYS
    assert any("Do not invent salary" in rule for rule in payload["rules"])
    assert any("not an offer" in rule for rule in payload["rules"])


def test_parse_player_decision_accepts_exact_provided_offer() -> None:
    request = _request()
    response = """```json
    {
      "player_index": 41,
      "decision": "accept_offer",
      "selected_team_index": 7,
      "selected_team_label": "Current Team",
      "primary_factors": ["contract_value_and_security", "role_minutes_and_development"],
      "reasoning": "The longer guarantee and recorded starting role are the strongest supplied facts."
    }
    ```"""

    decision = parse_player_free_agency_decision_response(request, response)

    assert decision.player_index == 41
    assert decision.player_label == "Test Player"
    assert decision.decision == "accept_offer"
    assert decision.selected_team_index == 7
    assert decision.selected_team_label == "Current Team"
    assert decision.primary_factors == (
        "contract_value_and_security",
        "role_minutes_and_development",
    )
    assert decision.raw_llm_response == response


def test_parse_player_decision_allows_rejecting_every_offer() -> None:
    request = _request()
    response = json.dumps(
        {
            "player_index": 41,
            "decision": "reject_all_offers",
            "selected_team_index": None,
            "selected_team_label": "",
            "primary_factors": ["contract_value_and_security"],
            "reasoning": "Neither supplied offer meets the player's recorded contract requirements.",
        }
    )

    decision = parse_player_free_agency_decision_response(request, response)

    assert decision.decision == "reject_all_offers"
    assert decision.selected_team_index is None
    assert decision.selected_team_label == ""


def test_parse_player_decision_rejects_team_not_present_in_offers() -> None:
    request = _request()
    response = json.dumps(
        {
            "player_index": 41,
            "decision": "accept_offer",
            "selected_team_index": 18,
            "selected_team_label": "Unlisted Team",
            "primary_factors": ["winning_and_championship_outlook"],
            "reasoning": "An unsupported destination must not be accepted.",
        }
    )

    with pytest.raises(ValueError, match="selected_team_index is not present in offers"):
        parse_player_free_agency_decision_response(request, response)


def test_parse_player_decision_rejects_invented_factor() -> None:
    request = _request()
    response = json.dumps(
        {
            "player_index": 41,
            "decision": "accept_offer",
            "selected_team_index": 2,
            "selected_team_label": "Contender",
            "primary_factors": ["secret_player_personality"],
            "reasoning": "This factor was not supplied by the decision contract.",
        }
    )

    with pytest.raises(ValueError, match="unknown primary_factors"):
        parse_player_free_agency_decision_response(request, response)


def test_parse_player_decision_rejects_mismatched_player() -> None:
    request = _request()
    response = json.dumps(
        {
            "player_index": 99,
            "decision": "reject_all_offers",
            "selected_team_index": None,
            "selected_team_label": "",
            "primary_factors": ["continuity_and_relocation_cost"],
            "reasoning": "Wrong player response.",
        }
    )

    with pytest.raises(ValueError, match="player_index does not match"):
        parse_player_free_agency_decision_response(request, response)
