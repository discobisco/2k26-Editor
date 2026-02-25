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
                    "name": "Starter A",
                    "team": "NYK",
                    "age": 29,
                    "overall": 88,
                    "potential": 89,
                    "actual_minutes": 35,
                    "actual_usage_rate": 0.29,
                },
                {
                    "player_id": 2,
                    "name": "Starter B",
                    "team": "NYK",
                    "age": 24,
                    "overall": 82,
                    "potential": 87,
                    "actual_minutes": 31,
                    "actual_usage_rate": 0.22,
                },
            ],
            "live": True,
        }
    )
    return TestClient(app)


def test_existing_endpoints_accept_profile_hooks(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    profile = "hook_profile"
    team_id = "NYK_2003"
    season = "2025-26"

    trade = client.post(
        "/v1/trade/evaluate",
        json={
            "profileId": profile,
            "teamId": team_id,
            "season": season,
            "era": "modern",
            "franchise_state": {
                "era": season,
                "team": "NYK",
                "cap_space": 11_000_000,
                "owner_goal": "win-now",
                "roster": [
                    {
                        "player_id": 1,
                        "name": "Starter A",
                        "team": "NYK",
                        "age": 29,
                        "overall": 88,
                        "potential": 89,
                        "contract_years": 2,
                        "salary": 40_000_000,
                    },
                    {
                        "player_id": 2,
                        "name": "Starter B",
                        "team": "NYK",
                        "age": 24,
                        "overall": 82,
                        "potential": 87,
                        "contract_years": 3,
                        "salary": 19_000_000,
                    },
                ],
            },
            "proposal": {"from_team": "NYK", "to_team": "LAL", "outgoing_player_ids": [1], "incoming_player_ids": [2]},
        },
    )
    assert trade.status_code == 200
    assert any("Locker-room pressure multiplier" in item for item in trade.json()["evaluation"]["rationale"])

    progression = client.post(
        "/v1/progression/simulate",
        json={
            "profileId": profile,
            "teamId": team_id,
            "season": season,
            "era": "modern",
            "seed": 55,
            "years": 2,
            "players": [
                {
                    "player_id": 1,
                    "name": "Starter A",
                    "team": "NYK",
                    "age": 29,
                    "overall": 88,
                    "potential": 89,
                    "contract_years": 2,
                    "salary": 40_000_000,
                }
            ],
        },
    )
    assert progression.status_code == 200
    assert progression.json()["results"]

    season_sim = client.post(
        "/v1/season/simulate",
        json={
            "profileId": profile,
            "teamId": team_id,
            "era": "modern",
            "season": season,
            "iterations": 10,
            "seed": 99,
            "team_strengths": [
                {"team": team_id, "strength": 120},
                {"team": "LAL_2003", "strength": 115},
            ],
        },
    )
    assert season_sim.status_code == 200
    assert season_sim.json()["outcomes"]

    dynasty = client.post(
        "/v1/dynasty/track",
        json={
            "profileId": profile,
            "teamId": team_id,
            "season": season,
            "era": "modern",
            "finalsAppearancesLast6": 3,
            "earlyExitStreak": 2,
            "team": "NYK",
            "history": [{"rings": 1, "mvps": 0, "all_nba": 3, "wins": 57}],
        },
    )
    assert dynasty.status_code == 200
    assert "Culture boost" in dynasty.json()["snapshot"]["summary"]

    ai_trade = client.post(
        "/v1/ai/trade-decision",
        json={
            "profileId": profile,
            "context": {
                "team_id": team_id,
                "era": "modern",
                "season": season,
                "current_record": "30-20",
                "checkpoint": "trade_deadline",
                "seed": 321,
                "roster_assets": [
                    {
                        "player_id": 1,
                        "name": "Starter A",
                        "team": "NYK",
                        "age": 29,
                        "overall": 88,
                        "potential": 89,
                        "contract_years": 2,
                        "salary": 40_000_000,
                    }
                ],
            },
        },
    )
    assert ai_trade.status_code == 200
    assert "lockerRoomMorale" in ai_trade.json()["decisionBreakdown"]

