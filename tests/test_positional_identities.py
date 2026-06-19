from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT = REPO_ROOT / "nba2k_editor" / "Player Generator"
sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget  # noqa: E402
from player_generator import generate_player_proposal_from_index, season_context_index  # noqa: E402
from positional_identities import load_positional_identity_catalog  # noqa: E402
from source_data import GeneratorSourceInventory  # noqa: E402


class PositionalIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_root = GeneratorSourceInventory.from_default().root

    def test_positional_identity_catalog_parses_all_position_files(self) -> None:
        catalog = load_positional_identity_catalog()
        counts = {position: len(catalog.roles_for_position(position)) for position in ("PG", "SG", "SF", "PF", "C")}

        self.assertGreaterEqual(counts["PG"], 70)
        self.assertGreaterEqual(counts["SG"], 70)
        self.assertGreaterEqual(counts["SF"], 70)
        self.assertGreaterEqual(counts["PF"], 70)
        self.assertGreaterEqual(counts["C"], 70)
        pg_pnr = catalog.find_role("PG", "PnR Maestro")
        self.assertIsNotNone(pg_pnr)
        self.assertEqual("PG/PnR Maestro (Read-First)", pg_pnr.role_key)
        self.assertIn("screen", pg_pnr.details["key_characteristics"].lower())

    def test_generated_player_identity_gets_stat_driven_positional_roles_without_new_fields(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        proposal = generate_player_proposal_from_index(context, player_id="curryst01", team="GSW")

        role_keys = tuple(proposal.identity["positional_identity_role_keys"])
        self.assertIn("PG/PnR Scoring Threat (Pull-Up Three)", role_keys)
        self.assertIn("PG/PnR Maestro (Read-First)", role_keys)
        self.assertTrue(all(identity["role_key"] in role_keys for identity in proposal.identity["positional_identities"]))
        self.assertNotIn("Positional Identity", {candidate.section for candidate in proposal.field_candidates})

    def test_big_profiles_get_different_positional_roles_from_same_catalog(self) -> None:
        contract = GeneratorInputContract(
            season=2025,
            source_root=self.source_root,
            output_target=OutputTarget.PROPOSAL,
        ).validate()
        context = season_context_index(contract)
        jokic = generate_player_proposal_from_index(context, player_id="jokicni01", team="DEN")
        gobert = generate_player_proposal_from_index(context, player_id="goberru01", team="MIN")

        self.assertIn("C/Point Center (Primary Initiator 5)", tuple(jokic.identity["positional_identity_role_keys"]))
        self.assertIn("C/High-Post Hub (Elbow Facilitator)", tuple(jokic.identity["positional_identity_role_keys"]))
        self.assertIn("C/Vertical Spacer (Lob Magnet)", tuple(gobert.identity["positional_identity_role_keys"]))
        self.assertIn("C/Rebounding-First Defensive Anchor", tuple(gobert.identity["positional_identity_role_keys"]))


if __name__ == "__main__":
    unittest.main()
