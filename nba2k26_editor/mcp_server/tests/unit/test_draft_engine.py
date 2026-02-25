from __future__ import annotations

from nba2k_editor.mcp_server.domain.draft_engine import DraftEngine


def test_lottery_odds_convergence_smoke():
    engine = DraftEngine()
    teams = ["A", "B", "C"]
    odds = [0.7, 0.2, 0.1]

    first_pick_counts = {team: 0 for team in teams}
    for seed in range(250):
        order = engine.simulate_lottery(teams=teams, odds=odds, seed=seed, draws=1)
        first_pick_counts[order[0]] += 1

    assert first_pick_counts["A"] > first_pick_counts["B"] > first_pick_counts["C"]
