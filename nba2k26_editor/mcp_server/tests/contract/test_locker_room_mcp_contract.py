from __future__ import annotations

from fastapi.testclient import TestClient

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MYERAS_MCP_PROFILE_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("MYERAS_MCP_ENABLE_LOCKER_ROOM_V1", "true")
    get_settings.cache_clear()
    app = create_app()
    app.state.container.live_roster_snapshot_adapter.load_team_snapshot = (  # type: ignore[method-assign]
        lambda team_id, season: {
            "team_id": team_id,
            "season": season,
            "roster": [
                {
                    "player_id": 1,
                    "name": "Star One",
                    "team": "LAL",
                    "age": 31,
                    "overall": 92,
                    "potential": 93,
                    "actual_minutes": 36,
                    "actual_usage_rate": 0.33,
                }
            ],
            "live": True,
        }
    )
    return TestClient(app)


def test_locker_room_mcp_tools_listed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    tools = client.get("/v1/mcp/tools")
    assert tools.status_code == 200
    names = {entry["name"] for entry in tools.json()["tools"]}
    assert {
        "locker_room_chemistry_calculate",
        "locker_room_personality_update",
        "locker_room_conflict_simulate",
        "locker_room_morale_evaluate",
        "locker_room_status_lookup",
    }.issubset(names)


def test_locker_room_mcp_invocation_shapes(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {
        "profileId": "profile_mcp",
        "teamId": "LAL_1998",
        "season": "1998-99",
        "era": "1990s",
    }
    chemistry = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "locker_room_chemistry_calculate",
            "arguments": {**payload, "recentRecord": "7-3"},
        },
    )
    assert chemistry.status_code == 200
    assert "chemistryScore" in chemistry.json()["result"]

    update = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "locker_room_personality_update",
            "arguments": {**payload, "mode": "auto"},
        },
    )
    assert update.status_code == 200
    assert "players" in update.json()["result"]

    conflict = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "locker_room_conflict_simulate",
            "arguments": {**payload, "tradeRumorPressure": 0.7, "mediaPressure": 0.8},
        },
    )
    assert conflict.status_code == 200
    assert "queueSize" in conflict.json()["result"]

    morale = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "locker_room_morale_evaluate",
            "arguments": {**payload, "teamWinPct": 0.55},
        },
    )
    assert morale.status_code == 200
    assert "averageMorale" in morale.json()["result"]

    status = client.post(
        "/v1/mcp/invoke",
        json={
            "tool": "locker_room_status_lookup",
            "arguments": {"profile_id": "profile_mcp", "team_id": "LAL_1998", "season": "1998-99", "era": "1990s"},
        },
    )
    assert status.status_code == 200
    assert "status" in status.json()["result"]

