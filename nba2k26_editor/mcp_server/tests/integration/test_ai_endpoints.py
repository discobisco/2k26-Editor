from __future__ import annotations

from fastapi.testclient import TestClient

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings


def _client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def _base_context() -> dict[str, object]:
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
            },
            {
                "player_id": 2,
                "name": "Young PF",
                "team": "NYK",
                "age": 22,
                "overall": 79,
                "potential": 89,
                "contract_years": 3,
                "salary": 9_000_000,
            },
        ],
        "media_context": {
            "fan_sentiment": 0.4,
            "media_criticism_index": 0.78,
            "recent_playoff_success": 0.2,
            "market_size_factor": 0.9,
        },
        "rings_last_6_years": 0,
        "title_drought_years": 11,
        "checkpoint": "trade_deadline",
        "seed": 2026,
    }


def test_ai_endpoints_return_expected_shapes():
    client = _client()

    trade = client.post("/v1/ai/trade-decision", json={"context": _base_context()})
    assert trade.status_code == 200
    trade_body = trade.json()
    assert "decision" in trade_body
    assert "aggressivenessScore" in trade_body
    assert "futurePickIncluded" in trade_body
    assert "decisionBreakdown" in trade_body
    assert "nextProfileRecommendation" in trade_body

    draft = client.post(
        "/v1/ai/draft-decision",
        json={
            "context": _base_context(),
            "board_strength": 0.8,
            "team_need_fit": 0.45,
        },
    )
    assert draft.status_code == 200
    draft_body = draft.json()
    assert "riskScore" in draft_body
    assert "targetProfile" in draft_body

    free_agency = client.post(
        "/v1/ai/free-agency-decision",
        json={
            "context": _base_context(),
            "cap_room": 15_000_000,
            "market_offer_pressure": 0.7,
        },
    )
    assert free_agency.status_code == 200
    fa_body = free_agency.json()
    assert "maxOfferGuidance" in fa_body
    assert "taxImpact" in fa_body

    direction = client.post("/v1/ai/franchise-direction", json={"context": _base_context()})
    assert direction.status_code == 200
    direction_body = direction.json()
    assert direction_body["direction"] in {"contender", "pretender", "rebuilder", "tanking", "retooling"}
    assert "triggerFactors" in direction_body


def test_ai_profile_normalizes_dual_team_id_inputs():
    client = _client()
    numeric = client.get("/v1/ai/profile/19", params={"season": "2003-04", "era": "modern"})
    canonical = client.get("/v1/ai/profile/NYK_2003", params={"season": "2003-04", "era": "modern"})
    assert numeric.status_code == 200
    assert canonical.status_code == 200
    assert numeric.json()["team_key"] == "NYK_2003"
    assert canonical.json()["team_key"] == "NYK_2003"


def test_ai_apply_live_changes_obeys_flag(monkeypatch):
    monkeypatch.setenv("MYERAS_MCP_ENABLE_LIVE_WRITES", "true")
    get_settings.cache_clear()
    client = TestClient(create_app())

    no_write_response = client.post(
        "/v1/ai/trade-decision",
        json={
            "context": _base_context(),
            "apply_live_changes": False,
        },
    )
    assert no_write_response.status_code == 200
    assert no_write_response.json()["write_operations"] == []

    with_write_response = client.post(
        "/v1/ai/trade-decision",
        json={
            "context": _base_context(),
            "apply_live_changes": True,
            "live_operations": [
                {
                    "entity_id": "player:1",
                    "field": "overall",
                    "value": 88,
                    "min_value": 40,
                    "max_value": 99,
                    "bounds_source": "integration-test",
                }
            ],
        },
    )
    assert with_write_response.status_code == 200
    assert with_write_response.json()["write_operations"][0]["success"] is True
