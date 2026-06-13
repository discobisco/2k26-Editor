from __future__ import annotations

import sys
import unittest
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from contracts import GeneratorInputContract, OutputTarget
from source_data import GeneratorSourceInventory


class GeneratorContractTests(unittest.TestCase):
    def test_contract_requires_selected_season(self) -> None:
        source_root = GeneratorSourceInventory.from_default().root

        with self.assertRaisesRegex(ValueError, "season"):
            GeneratorInputContract(season=0, source_root=source_root, output_target=OutputTarget.PROPOSAL).validate()

    def test_contract_rejects_non_integral_season(self) -> None:
        source_root = GeneratorSourceInventory.from_default().root

        with self.assertRaisesRegex(ValueError, "season"):
            GeneratorInputContract(season=2025.9, source_root=source_root, output_target=OutputTarget.PROPOSAL).validate()  # type: ignore[arg-type]

    def test_contract_requires_existing_source_root(self) -> None:
        with self.assertRaises(FileNotFoundError):
            GeneratorInputContract(
                season=2025,
                source_root=Path("/tmp/missing-nba2k-generator-source-root"),
                output_target=OutputTarget.PROPOSAL,
            ).validate()

    def test_contract_rejects_unknown_output_target(self) -> None:
        source_root = GeneratorSourceInventory.from_default().root

        with self.assertRaisesRegex(ValueError, "output_target"):
            GeneratorInputContract(season=2025, source_root=source_root, output_target="random-roster").validate()

    def test_overwrite_current_roster_requires_explicit_roster_label(self) -> None:
        source_root = GeneratorSourceInventory.from_default().root

        with self.assertRaisesRegex(ValueError, "roster_label"):
            GeneratorInputContract(
                season=2025,
                source_root=source_root,
                output_target=OutputTarget.OVERWRITE_CURRENT_ROSTER,
            ).validate()

    def test_valid_contract_normalizes_paths_and_target(self) -> None:
        source_root = GeneratorSourceInventory.from_default().root

        validated = GeneratorInputContract(
            season=2025,
            source_root=source_root,
            output_target="preview",
            roster_label="2024-25 test roster",
        ).validate()

        self.assertEqual(validated.season, 2025)
        self.assertEqual(validated.output_target, OutputTarget.PREVIEW)
        self.assertEqual(validated.source_root, source_root.resolve())
        self.assertEqual(validated.roster_label, "2024-25 test roster")


if __name__ == "__main__":
    unittest.main()
