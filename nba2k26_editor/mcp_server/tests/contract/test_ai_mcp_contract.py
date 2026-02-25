from __future__ import annotations

from fastapi.testclient import TestClient

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings


def _client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def _context() -> dict[str, object]:
    return {
        "team_id": "NYK_2003",
        "era": "modern",
        "season": "2025-26",
        "current_record": "28-30",
        "roster_assets": [
            {
                "player_id": 1,
                "name": "Veteran SG",
                "team": "NYK",
                "age": 31,
                "overall": 86,
                "potential": 86,
                "contract_years": 1,
                "salary": 26_000_000,
            }
        ],
        "media_context": {
            "fan_sentiment": 0.4,
            "media_criticism_index": 0.75,
            "recent_playoff_success": 0.2,
            "market_size_factor": 0.9,
        },
        "rings_last_6_years": 0,
        "title_drought_years": 11,
        "checkpoint": "trade_deadline",
        "seed": 2026,
    }


def test_ai_tools_listed_in_mcp_tools():
    client = _client()
    response = client.get("/v1/mcp/tools")
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["tools"]}
    assert {"ai_trade_decision", "ai_draft_decision", "ai_free_agency_decision", "ai_franchise_direction", "ai_profile_lookup"}.issubset(names)


def test_ai_mcp_tool_invocation_contract_shapes():
    client = _client()

    trade = client.post(
        "/v1/mcp/invoke",
        json={"tool": "ai_trade_decision", "arguments": {"context": _context()}},
    )
    assert trade.status_code == 200
    trade_result = trade.json()["result"]
    assert "aggressivenessScore" in trade_result
    assert "nextProfileRecommendation" in trade_result

    draft = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "ai_draft_decision",
            "arguments": {"context": _context(), "board_strength": 0.82, "team_need_fit": 0.45},
        },
    )
    assert draft.status_code == 200
    draft_result = draft.json()["result"]
    assert "riskScore" in draft_result
    assert "targetProfile" in draft_result

    free_agency = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "ai_free_agency_decision",
            "arguments": {"context": _context(), "cap_room": 14_000_000, "market_offer_pressure": 0.65},
        },
    )
    assert free_agency.status_code == 200
    free_agency_result = free_agency.json()["result"]
    assert "maxOfferGuidance" in free_agency_result
    assert "taxImpact" in free_agency_result

    direction = client.post(
        "/v1/mcp/invoke",
        json={"tool": "ai_franchise_direction", "arguments": {"context": _context()}},
    )
    assert direction.status_code == 200
    direction_result = direction.json()["result"]
    assert "direction" in direction_result
    assert "triggerFactors" in direction_result

    profile = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "ai_profile_lookup",
            "arguments": {"team_id": "NYK_2003", "era": "modern", "season": "2025-26"},
        },
    )
    assert profile.status_code == 200
    profile_result = profile.json()["result"]
    assert profile_result["team_key"] == "NYK_2003"
    assert "capability_flag" in profile_result
