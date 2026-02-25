from __future__ import annotations

from fastapi.testclient import TestClient

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings
from nba2k_editor.mcp_server.errors import ServiceError


def _snapshot(team_id: str, season: str) -> dict[str, object]:
    return {
        "team_id": team_id,
        "season": season,
        "roster": [
            {
                "player_id": 1,
                "name": "Star One",
                "team": "LAL",
                "age": 30,
                "overall": 92,
                "potential": 93,
                "actual_minutes": 36,
                "actual_usage_rate": 0.34,
            },
            {
                "player_id": 2,
                "name": "Wing Two",
                "team": "LAL",
                "age": 24,
                "overall": 83,
                "potential": 88,
                "actual_minutes": 31,
                "actual_usage_rate": 0.23,
            },
            {
                "player_id": 3,
                "name": "Rookie Three",
                "team": "LAL",
                "age": 21,
                "overall": 76,
                "potential": 87,
                "actual_minutes": 18,
                "actual_usage_rate": 0.17,
            },
        ],
        "live": True,
    }


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MYERAS_MCP_PROFILE_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("MYERAS_MCP_ENABLE_LOCKER_ROOM_V1", "true")
    get_settings.cache_clear()
    app = create_app()
    app.state.container.live_roster_snapshot_adapter.load_team_snapshot = _snapshot  # type: ignore[method-assign]
    return TestClient(app)


def test_locker_room_endpoint_happy_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    personality = client.post(
        "/v1/personality/update",
        json={
            "profileId": "save_a",
            "teamId": "LAL_1998",
            "season": "1998-99",
            "era": "1990s",
            "mode": "auto",
            "seed": 77,
        },
    )
    assert personality.status_code == 200
    assert len(personality.json()["players"]) >= 2

    chemistry = client.post(
        "/v1/chemistry/calculate",
        json={
            "profileId": "save_a",
            "teamId": "LAL_1998",
            "season": "1998-99",
            "era": "1990s",
            "recentRecord": "6-4",
        },
    )
    assert chemistry.status_code == 200
    assert 0.0 <= chemistry.json()["chemistryScore"] <= 1.0

    conflict = client.post(
        "/v1/conflict/simulate",
        json={
            "profileId": "save_a",
            "teamId": "LAL_1998",
            "season": "1998-99",
            "era": "1990s",
            "tradeRumorPressure": 0.8,
            "mediaPressure": 0.75,
        },
    )
    assert conflict.status_code == 200
    assert conflict.json()["queueSize"] >= 1

    morale = client.post(
        "/v1/morale/evaluate",
        json={
            "profileId": "save_a",
            "teamId": "LAL_1998",
            "season": "1998-99",
            "era": "1990s",
            "teamWinPct": 0.65,
        },
    )
    assert morale.status_code == 200
    assert 0.0 <= morale.json()["averageMorale"] <= 1.0

    status = client.get(
        "/v1/locker-room/status/LAL_1998",
        params={"profile_id": "save_a", "season": "1998-99", "era": "1990s"},
    )
    assert status.status_code == 200
    assert "status" in status.json()
    assert status.json()["status"]["teamId"] == "LAL_1998"


def test_locker_room_status_requires_query_fields(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/v1/locker-room/status/LAL_1998")
    assert response.status_code == 422


def test_locker_room_profile_persists_across_app_restart(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    seed_update = client.post(
        "/v1/personality/update",
        json={
            "profileId": "save_b",
            "teamId": "LAL_1998",
            "season": "1998-99",
            "era": "1990s",
            "mode": "auto",
            "seed": 11,
        },
    )
    assert seed_update.status_code == 200

    get_settings.cache_clear()
    monkeypatch.setenv("MYERAS_MCP_PROFILE_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("MYERAS_MCP_ENABLE_LOCKER_ROOM_V1", "true")
    app2 = create_app()

    def _offline(*args, **kwargs):
        raise ServiceError(
            status_code=503,
            code="LIVE_CONNECTION_UNAVAILABLE",
            message="offline",
            details={},
        )

    app2.state.container.live_roster_snapshot_adapter.load_team_snapshot = _offline  # type: ignore[method-assign]
    client2 = TestClient(app2)
    status = client2.get(
        "/v1/locker-room/status/LAL_1998",
        params={"profile_id": "save_b", "season": "1998-99", "era": "1990s"},
    )
    assert status.status_code == 200
    assert status.json()["status"]["staleLiveData"] is True


def test_locker_room_live_unavailable_without_snapshot_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("MYERAS_MCP_PROFILE_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("MYERAS_MCP_ENABLE_LOCKER_ROOM_V1", "true")
    get_settings.cache_clear()
    app = create_app()

    def _offline(*args, **kwargs):
        raise ServiceError(
            status_code=503,
            code="LIVE_CONNECTION_UNAVAILABLE",
            message="offline",
            details={},
        )

    app.state.container.live_roster_snapshot_adapter.load_team_snapshot = _offline  # type: ignore[method-assign]
    client = TestClient(app)
    status = client.get(
        "/v1/locker-room/status/LAL_1998",
        params={"profile_id": "no_seed", "season": "1998-99", "era": "1990s"},
    )
    assert status.status_code == 503
    assert status.json()["error"]["code"] == "LIVE_PROFILE_BOOTSTRAP_REQUIRED"

