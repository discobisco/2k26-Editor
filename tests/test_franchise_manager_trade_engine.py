from __future__ import annotations

import unittest

from nba2k_editor.franchise_manager import FranchiseTeam, GMProfile, ImportedDataKind, ImportedSnapshot, OwnerProfile
from nba2k_editor.franchise_manager.models import TeamDirection
from nba2k_editor.franchise_manager.trades import TradeAsset, TradePackage, draft_pick_trade_value, generate_trade_proposals, score_trade_package
from nba2k_editor.franchise_manager.transactions import recommend_team_transactions
from nba2k_editor.franchise_manager.world import DraftPickAsset, FranchisePlayer, PlayerContract, build_team_context


class FranchiseManagerTradeEngineTests(unittest.TestCase):
    def test_draft_pick_valuation_accounts_for_round_year_and_protection(self) -> None:
        unprotected_first = DraftPickAsset("SEA", 2027, round=1)
        protected_first = DraftPickAsset("SEA", 2027, round=1, protection="top 10")
        far_first = DraftPickAsset("SEA", 2031, round=1)
        second = DraftPickAsset("SEA", 2027, round=2)
        outgoing_first = DraftPickAsset("SEA", 2027, round=1, outgoing_to="DAL")

        self.assertGreater(draft_pick_trade_value(unprotected_first, current_season=2026), draft_pick_trade_value(protected_first, current_season=2026))
        self.assertGreater(draft_pick_trade_value(protected_first, current_season=2026), draft_pick_trade_value(second, current_season=2026))
        self.assertGreater(draft_pick_trade_value(unprotected_first, current_season=2026), draft_pick_trade_value(far_first, current_season=2026))
        self.assertLess(draft_pick_trade_value(outgoing_first, current_season=2026), 0)

    def test_contender_scores_veteran_injury_insurance_offer_as_acceptable(self) -> None:
        context = _contender_context()
        package = TradePackage(
            label="Add veteran wing",
            outgoing=(TradeAsset.pick(DraftPickAsset("SEA", 2028, round=2)),),
            incoming=(TradeAsset.player(FranchisePlayer("wing", "DAL", name="Veteran Wing", age=30, overall=81, potential=81, position="SF"), PlayerContract("wing", "DAL", salary=9_000_000, years_remaining=1, expiring=True)),),
        )

        score = score_trade_package(context, package, direction=TeamDirection.CONTEND)

        self.assertTrue(score.cap_legal)
        self.assertGreaterEqual(score.acceptance_score, 60)
        self.assertEqual("accept", score.decision)
        self.assertIn("injury", " ".join(score.reasons).lower())
        self.assertGreater(score.incoming_value, score.outgoing_value)

    def test_rebuild_scores_veteran_for_young_player_and_first_as_acceptable(self) -> None:
        context = _rebuild_context()
        package = TradePackage(
            label="Move veteran for future",
            outgoing=(TradeAsset.existing_player("vet"),),
            incoming=(
                TradeAsset.player(FranchisePlayer("kid2", "NYK", name="Young Forward", age=22, overall=73, potential=86, position="PF"), PlayerContract("kid2", "NYK", salary=5_000_000, years_remaining=3)),
                TradeAsset.pick(DraftPickAsset("SEA", 2027, round=1, protection="top 4")),
            ),
        )

        score = score_trade_package(context, package, direction=TeamDirection.REBUILD)

        self.assertTrue(score.cap_legal)
        self.assertGreaterEqual(score.acceptance_score, 65)
        self.assertEqual("accept", score.decision)
        joined_reasons = " ".join(score.reasons).lower()
        self.assertIn("draft", joined_reasons)
        self.assertIn("timeline", joined_reasons)

    def test_over_cap_trade_rejects_illegal_salary_match(self) -> None:
        context = _tax_context()
        package = TradePackage(
            label="Illegal salary jump",
            outgoing=(TradeAsset.existing_player("min"),),
            incoming=(TradeAsset.player(FranchisePlayer("max", "LAL", name="Max Salary", age=29, overall=89), PlayerContract("max", "LAL", salary=43_000_000, years_remaining=3)),),
        )

        score = score_trade_package(context, package, direction=TeamDirection.CONTEND)

        self.assertFalse(score.cap_legal)
        self.assertEqual("reject", score.decision)
        self.assertLess(score.acceptance_score, 40)
        self.assertIn("salary", " ".join(score.reasons).lower())

    def test_generate_trade_proposals_uses_team_direction(self) -> None:
        rebuild = _rebuild_context()
        contender = _contender_context()

        rebuild_proposals = generate_trade_proposals(rebuild, direction=TeamDirection.REBUILD)
        contender_proposals = generate_trade_proposals(contender, direction=TeamDirection.CONTEND)

        self.assertTrue(any("veteran" in proposal.label.lower() for proposal in rebuild_proposals))
        self.assertTrue(any("injury" in proposal.label.lower() or "upgrade" in proposal.label.lower() for proposal in contender_proposals))

    def test_transaction_recommendation_includes_top_trade_score_evidence(self) -> None:
        context = _rebuild_context()

        trade_recommendation = next(item for item in recommend_team_transactions(context, TeamDirection.REBUILD) if item.kind == "trade")

        self.assertIn("top_trade_score", trade_recommendation.evidence)
        self.assertIn("top_trade_decision", trade_recommendation.evidence)
        self.assertIn("veteran", trade_recommendation.evidence["top_trade_label"].lower())

def _contender_context():
    team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner", spending_willingness=70), GMProfile("GM", aggression=70))
    return build_team_context(
        season=2026,
        team=team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 51, "losses": 31, "expected_wins": 55}}),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.PLAYER_STATS,
                {"players": [
                    {"player_id": "star", "team_id": "SEA", "name": "Star", "age": 28, "overall": 92, "potential": 93, "minutes": 35},
                    {"player_id": "min", "team_id": "SEA", "name": "Minimum Wing", "age": 25, "overall": 70, "potential": 72, "minutes": 8},
                ]},
            ),
            ImportedSnapshot(2026, None, ImportedDataKind.INJURIES, {"injuries": [{"player_id": "star", "team_id": "SEA", "severity": 35, "games_remaining": 5, "description": "ankle"}]}),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.CONTRACTS,
                {
                    "salary_cap": 141_000_000,
                    "luxury_tax_line": 171_000_000,
                    "contracts": [
                        {"player_id": "star", "team_id": "SEA", "salary": 48_000_000, "years_remaining": 3},
                        {"player_id": "min", "team_id": "SEA", "salary": 9_000_000, "years_remaining": 1, "expiring": True},
                    ],
                    "draft_picks": [{"team_id": "SEA", "year": 2028, "round": 2}],
                },
            ),
        ),
    )


def _rebuild_context():
    team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner", rebuild_tolerance=90), GMProfile("GM", prospect_preference=90))
    return build_team_context(
        season=2026,
        team=team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 19, "losses": 45, "expected_wins": 24}}),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.PLAYER_STATS,
                {"players": [
                    {"player_id": "vet", "team_id": "SEA", "name": "Expensive Veteran", "age": 34, "overall": 80, "potential": 80, "minutes": 31},
                    {"player_id": "kid", "team_id": "SEA", "name": "Young Guard", "age": 21, "overall": 74, "potential": 87, "minutes": 17},
                ]},
            ),
            ImportedSnapshot(
                2026,
                None,
                ImportedDataKind.CONTRACTS,
                {
                    "salary_cap": 141_000_000,
                    "luxury_tax_line": 171_000_000,
                    "contracts": [
                        {"player_id": "vet", "team_id": "SEA", "salary": 32_000_000, "years_remaining": 2},
                        {"player_id": "kid", "team_id": "SEA", "salary": 6_000_000, "years_remaining": 3},
                    ],
                    "draft_picks": [{"team_id": "SEA", "year": 2028, "round": 1}],
                },
            ),
        ),
    )


def _tax_context():
    context = _contender_context()
    return build_team_context(
        season=2026,
        team=context.team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 51, "losses": 31, "expected_wins": 55}}),
            ImportedSnapshot(2026, None, ImportedDataKind.PLAYER_STATS, {"players": [{"player_id": "min", "team_id": "SEA", "name": "Minimum Wing", "age": 25, "overall": 70, "minutes": 8}]}),
            ImportedSnapshot(2026, None, ImportedDataKind.CONTRACTS, {"salary_cap": 141_000_000, "luxury_tax_line": 171_000_000, "contracts": [{"player_id": "star", "team_id": "SEA", "salary": 174_000_000, "years_remaining": 3}, {"player_id": "min", "team_id": "SEA", "salary": 2_000_000, "years_remaining": 1}], "payroll": 176_000_000}),
        ),
    )


if __name__ == "__main__":
    unittest.main()
