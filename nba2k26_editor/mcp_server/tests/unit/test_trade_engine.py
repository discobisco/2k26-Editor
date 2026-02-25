from __future__ import annotations

from nba2k_editor.mcp_server.api.v1.models import FranchiseState, RosterPlayer, TradeProposal
from nba2k_editor.mcp_server.domain.trade_engine import TradeEngine


def _state() -> FranchiseState:
    roster = [
        RosterPlayer(
            player_id=1,
            name="Player A",
            team="Chicago Bulls",
            age=26,
            overall=85,
            potential=88,
            contract_years=3,
            salary=28_000_000,
        ),
        RosterPlayer(
            player_id=2,
            name="Player B",
            team="Chicago Bulls",
            age=25,
            overall=84,
            potential=87,
            contract_years=2,
            salary=27_500_000,
        ),
    ]
    return FranchiseState(era="2025-26", team="Chicago Bulls", cap_space=12_000_000, owner_goal="win-now", roster=roster)


def test_trade_fairness_near_neutral_for_balanced_swap():
    state = _state()
    engine = TradeEngine()
    proposal = TradeProposal(
        from_team="Chicago Bulls",
        to_team="Mock Team 2",
        outgoing_player_ids=[1],
        incoming_player_ids=[2],
    )
    evaluation = engine.evaluate(franchise_state=state, proposal=proposal, cpu_profile="modern-balanced")
    assert abs(evaluation.fairness_score) <= 0.2
