from __future__ import annotations

import unittest

from nba2k_editor.franchise_manager import FranchiseTeam, GMProfile, ImportedDataKind, ImportedSnapshot, OwnerProfile
from nba2k_editor.franchise_manager.free_agency import (
    FreeAgentTarget,
    build_contract_offer,
    decide_re_sign_or_renounce,
    free_agency_plan,
    rank_free_agent_targets,
)
from nba2k_editor.franchise_manager.models import TeamDirection
from nba2k_editor.franchise_manager.transactions import recommend_team_transactions
from nba2k_editor.franchise_manager.world import FranchisePlayer, PlayerContract, build_team_context


class FranchiseManagerFreeAgencyTests(unittest.TestCase):
    def test_cap_space_team_ranks_timeline_fit_over_expensive_aging_veteran(self) -> None:
        context = _cap_space_rebuild_context()
        targets = (
            FreeAgentTarget(FranchisePlayer("young", "FA", name="Young Shooter", age=23, overall=76, potential=86, position="SG"), asking_salary=14_000_000, asking_years=3),
            FreeAgentTarget(FranchisePlayer("old", "FA", name="Old Name", age=34, overall=82, potential=82, position="SF"), asking_salary=31_000_000, asking_years=4),
        )

        ranked = rank_free_agent_targets(context, targets, direction=TeamDirection.REBUILD)

        self.assertEqual("young", ranked[0].target.player.player_id)
        self.assertGreater(ranked[0].fit_score, ranked[1].fit_score)
        self.assertIn("timeline", " ".join(ranked[0].reasons).lower())

    def test_tax_contender_offer_uses_short_exception_style_contract(self) -> None:
        context = _tax_contender_context()
        target = FreeAgentTarget(FranchisePlayer("vet", "FA", name="Veteran Center", age=32, overall=78, potential=78, position="C"), asking_salary=18_000_000, asking_years=3)

        offer = build_contract_offer(context, target, direction=TeamDirection.CONTEND)

        self.assertLessEqual(offer.first_year_salary, 12_900_000)
        self.assertLessEqual(offer.years, 2)
        self.assertEqual("exception", offer.offer_type)
        self.assertIn("tax", " ".join(offer.reasons).lower())

    def test_re_sign_decision_keeps_young_core_and_renounces_expensive_declining_veteran(self) -> None:
        context = _cap_space_rebuild_context()
        young = FreeAgentTarget(FranchisePlayer("core", "SEA", name="Young Core", age=22, overall=75, potential=88), asking_salary=12_000_000, asking_years=4, bird_rights=True)
        old = FreeAgentTarget(FranchisePlayer("oldfa", "SEA", name="Declining Vet", age=35, overall=76, potential=76), asking_salary=28_000_000, asking_years=3, bird_rights=True)

        keep = decide_re_sign_or_renounce(context, young, direction=TeamDirection.REBUILD)
        renounce = decide_re_sign_or_renounce(context, old, direction=TeamDirection.REBUILD)

        self.assertEqual("re_sign", keep.decision)
        self.assertEqual("renounce", renounce.decision)
        self.assertIn("young", " ".join(keep.reasons).lower())
        self.assertIn("timeline", " ".join(renounce.reasons).lower())

    def test_free_agency_plan_returns_ranked_targets_offers_and_renounce_actions(self) -> None:
        context = _cap_space_rebuild_context()
        targets = (
            FreeAgentTarget(FranchisePlayer("young", "FA", name="Young Shooter", age=23, overall=76, potential=86), asking_salary=14_000_000, asking_years=3),
            FreeAgentTarget(FranchisePlayer("old", "FA", name="Old Name", age=34, overall=82, potential=82), asking_salary=31_000_000, asking_years=4),
        )
        own_free_agents = (
            FreeAgentTarget(FranchisePlayer("core", "SEA", name="Young Core", age=22, overall=75, potential=88), asking_salary=12_000_000, asking_years=4, bird_rights=True),
            FreeAgentTarget(FranchisePlayer("oldfa", "SEA", name="Declining Vet", age=35, overall=76, potential=76), asking_salary=28_000_000, asking_years=3, bird_rights=True),
        )

        plan = free_agency_plan(context, targets=targets, own_free_agents=own_free_agents, direction=TeamDirection.REBUILD)

        self.assertEqual("young", plan.ranked_targets[0].target.player.player_id)
        self.assertEqual("young", plan.offers[0].target.player.player_id)
        self.assertTrue(any(decision.decision == "renounce" for decision in plan.re_sign_decisions))
        self.assertGreater(plan.cap_space_after_top_offer, 0)

    def test_transaction_recommendation_includes_free_agency_plan_evidence(self) -> None:
        context = _cap_space_rebuild_context()

        fa = next(item for item in recommend_team_transactions(context, TeamDirection.REBUILD) if item.kind == "free_agency")

        self.assertIn("free_agency_strategy", fa.evidence)
        self.assertIn("estimated_cap_space_after_top_offer", fa.evidence)


def _cap_space_rebuild_context():
    team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner", rebuild_tolerance=90), GMProfile("GM", prospect_preference=85, contract_discipline=75))
    return build_team_context(
        season=2026,
        team=team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 24, "losses": 58, "expected_wins": 28}}),
            ImportedSnapshot(2026, None, ImportedDataKind.PLAYER_STATS, {"players": [{"player_id": "kid", "team_id": "SEA", "name": "Young Guard", "age": 21, "overall": 74, "potential": 88, "minutes": 24}]}),
            ImportedSnapshot(2026, None, ImportedDataKind.CONTRACTS, {"salary_cap": 141_000_000, "luxury_tax_line": 171_000_000, "contracts": [{"player_id": "kid", "team_id": "SEA", "salary": 7_000_000, "years_remaining": 3}], "draft_picks": [{"team_id": "SEA", "year": 2027, "round": 1}]}),
        ),
    )


def _tax_contender_context():
    team = FranchiseTeam("SEA", "Seattle", OwnerProfile("Owner", spending_willingness=45), GMProfile("GM", contract_discipline=70))
    return build_team_context(
        season=2026,
        team=team,
        snapshots=(
            ImportedSnapshot(2026, None, ImportedDataKind.STANDINGS, {"SEA": {"wins": 54, "losses": 28, "expected_wins": 57}}),
            ImportedSnapshot(2026, None, ImportedDataKind.PLAYER_STATS, {"players": [{"player_id": "star", "team_id": "SEA", "name": "Star", "age": 29, "overall": 93, "potential": 93}]}),
            ImportedSnapshot(2026, None, ImportedDataKind.CONTRACTS, {"salary_cap": 141_000_000, "luxury_tax_line": 171_000_000, "contracts": [{"player_id": "star", "team_id": "SEA", "salary": 178_000_000, "years_remaining": 3}]}),
        ),
    )


if __name__ == "__main__":
    unittest.main()
