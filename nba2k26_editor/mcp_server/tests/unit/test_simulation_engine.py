from __future__ import annotations

from nba2k_editor.mcp_server.api.v1.models import TeamStrengthInput
from nba2k_editor.mcp_server.domain.simulation_engine import SimulationEngine


def test_season_simulation_is_deterministic_for_seed():
    engine = SimulationEngine()
    inputs = [
        TeamStrengthInput(team="A", strength=101),
        TeamStrengthInput(team="B", strength=96),
        TeamStrengthInput(team="C", strength=92),
    ]
    first = engine.simulate_season(team_strengths=inputs, iterations=40, seed=3, pace_factor=1.0)
    second = engine.simulate_season(team_strengths=inputs, iterations=40, seed=3, pace_factor=1.0)
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]
