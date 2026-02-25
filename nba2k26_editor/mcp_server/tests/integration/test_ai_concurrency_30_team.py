from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings
from nba2k_editor.mcp_server.mcp.tools import execute_ai_trade_decision


def _payload(team_id: int, seed: int) -> dict[str, object]:
    return {
        "context": {
            "team_id": team_id,
            "era": "modern",
            "season": "2025-26",
            "current_record": "25-33",
            "roster_assets": [
                {
                    "player_id": (team_id * 10) + 1,
                    "name": "Starter A",
                    "team": "TEAM",
                    "age": 27,
                    "overall": 82,
                    "potential": 84,
                    "contract_years": 2,
                    "salary": 18_000_000,
                },
                {
                    "player_id": (team_id * 10) + 2,
                    "name": "Prospect B",
                    "team": "TEAM",
                    "age": 22,
                    "overall": 76,
                    "potential": 88,
                    "contract_years": 3,
                    "salary": 5_000_000,
                },
            ],
            "media_context": {
                "fan_sentiment": 0.45,
                "media_criticism_index": 0.6,
                "recent_playoff_success": 0.2,
                "market_size_factor": 0.5,
            },
            "rings_last_6_years": 0,
            "title_drought_years": 7,
            "checkpoint": "trade_deadline",
            "seed": seed,
        }
    }


def test_ai_30_team_parallel_smoke():
    get_settings.cache_clear()
    app = create_app()
    container = app.state.container

    def run(team_id: int) -> str:
        result = execute_ai_trade_decision(container, _payload(team_id, 1000 + team_id))
        return str(result["team_key"])

    with ThreadPoolExecutor(max_workers=30) as pool:
        team_keys = list(pool.map(run, list(range(30))))

    assert len(team_keys) == 30
    assert len(set(team_keys)) == 30
