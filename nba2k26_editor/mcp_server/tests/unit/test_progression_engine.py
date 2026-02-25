from __future__ import annotations

from nba2k_editor.mcp_server.api.v1.models import RosterPlayer
from nba2k_editor.mcp_server.domain.progression_engine import ProgressionEngine


def test_progression_growth_then_decline_age_curve():
    engine = ProgressionEngine()
    players = [
        RosterPlayer(
            player_id=1,
            name="Young Core",
            team="Chicago Bulls",
            age=22,
            overall=76,
            potential=90,
            contract_years=3,
            salary=8_000_000,
        ),
        RosterPlayer(
            player_id=2,
            name="Veteran Wing",
            team="Chicago Bulls",
            age=33,
            overall=82,
            potential=82,
            contract_years=2,
            salary=22_000_000,
        ),
    ]
    results = engine.simulate(players=players, years=2, seed=7)
    by_id = {item.player_id: item for item in results}
    assert by_id[1].after_overall > by_id[1].before_overall
    assert by_id[2].after_overall < by_id[2].before_overall
