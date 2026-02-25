from __future__ import annotations

from fastapi.testclient import TestClient

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings


def test_live_write_bounds_reject_out_of_range(monkeypatch):
    monkeypatch.setenv("MYERAS_MCP_ENABLE_LIVE_WRITES", "true")
    get_settings.cache_clear()
    client = TestClient(create_app())

    payload = {
        "players": [
            {
                "player_id": 1,
                "name": "Player A",
                "team": "Chicago Bulls",
                "age": 22,
                "overall": 78,
                "potential": 90,
                "contract_years": 3,
                "salary": 8000000,
            }
        ],
        "years": 1,
        "seed": 5,
        "apply_live_changes": True,
        "live_operations": [
            {
                "entity_id": "player:1",
                "field": "overall",
                "value": 120,
                "min_value": 40,
                "max_value": 99,
                "bounds_source": "test",
            }
        ],
    }
    response = client.post("/v1/progression/simulate", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "BOUND_VALIDATION_FAILED"


def test_live_write_accepts_in_range(monkeypatch):
    monkeypatch.setenv("MYERAS_MCP_ENABLE_LIVE_WRITES", "true")
    get_settings.cache_clear()
    client = TestClient(create_app())

    payload = {
        "players": [
            {
                "player_id": 1,
                "name": "Player A",
                "team": "Chicago Bulls",
                "age": 22,
                "overall": 78,
                "potential": 90,
                "contract_years": 3,
                "salary": 8000000,
            }
        ],
        "years": 1,
        "seed": 5,
        "apply_live_changes": True,
        "live_operations": [
            {
                "entity_id": "player:1",
                "field": "overall",
                "value": 88,
                "min_value": 40,
                "max_value": 99,
                "bounds_source": "test",
            }
        ],
    }
    response = client.post("/v1/progression/simulate", json=payload)
    assert response.status_code == 200
    assert response.json()["write_operations"][0]["success"] is True
