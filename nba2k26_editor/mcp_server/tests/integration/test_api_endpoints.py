from __future__ import annotations

from fastapi.testclient import TestClient

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings


def _client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_and_capabilities():
    client = _client()
    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    caps = client.get("/v1/capabilities")
    assert caps.status_code == 200
    assert "franchise_optimizer" in caps.json()["tools"]


def test_trade_evaluate_success():
    client = _client()
    payload = {
        "franchise_state": {
            "era": "2025-26",
            "team": "Chicago Bulls",
            "cap_space": 12000000,
            "owner_goal": "win-now",
            "roster": [
                {
                    "player_id": 1,
                    "name": "Player A",
                    "team": "Chicago Bulls",
                    "age": 26,
                    "overall": 85,
                    "potential": 87,
                    "contract_years": 3,
                    "salary": 28000000,
                },
                {
                    "player_id": 2,
                    "name": "Player B",
                    "team": "Chicago Bulls",
                    "age": 25,
                    "overall": 84,
                    "potential": 86,
                    "contract_years": 2,
                    "salary": 27000000,
                },
            ],
        },
        "proposal": {
            "from_team": "Chicago Bulls",
            "to_team": "Mock Team 2",
            "outgoing_player_ids": [1],
            "incoming_player_ids": [2],
        },
    }
    response = client.post("/v1/trade/evaluate", json=payload)
    assert response.status_code == 200
    assert "evaluation" in response.json()


def test_era_transition_rejects_unsupported_era():
    client = _client()
    payload = {
        "from_season": "2025-26",
        "to_season": "2026-27",
        "era": "1990s",
    }
    response = client.post("/v1/era/transition", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_ERA"
