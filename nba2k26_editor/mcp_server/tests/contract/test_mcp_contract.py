from __future__ import annotations

from fastapi.testclient import TestClient

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings


def _client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_mcp_tools_contract_contains_required_tools():
    client = _client()
    response = client.get("/v1/mcp/tools")
    assert response.status_code == 200
    tools = response.json()["tools"]
    names = {tool["name"] for tool in tools}
    assert {
        "franchise_optimizer",
        "trade_evaluator",
        "draft_generator",
        "progression_simulator",
        "season_simulator",
        "dynasty_tracker",
        "era_transition_handler",
        "ai_trade_decision",
        "ai_draft_decision",
        "ai_free_agency_decision",
        "ai_franchise_direction",
        "ai_profile_lookup",
        "locker_room_chemistry_calculate",
        "locker_room_personality_update",
        "locker_room_conflict_simulate",
        "locker_room_morale_evaluate",
        "locker_room_status_lookup",
    }.issubset(names)
    for tool in tools:
        assert "input_schema" in tool
        assert "output_schema" in tool


def test_mcp_invoke_validates_schema_and_returns_structured_result():
    client = _client()
    payload = {
        "tool": "era_transition_handler",
        "arguments": {
            "from_season": "2025-26",
            "to_season": "2026-27",
            "era": "modern",
        },
    }
    response = client.post("/v1/mcp/invoke", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["tool"] == "era_transition_handler"
    assert "rule_changes" in body["result"]
