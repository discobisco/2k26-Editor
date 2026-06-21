from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("active_export_runs", ROOT / "tools" / "active_export_runs.py")
assert SPEC is not None and SPEC.loader is not None
active_export_runs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(active_export_runs)
active_export_paths = active_export_runs.active_export_paths
create_next_run_dir = active_export_runs.create_next_run_dir
latest_run_dir = active_export_runs.latest_run_dir


class ActiveExportRunTests(unittest.TestCase):
    def test_create_next_run_dir_numbers_runs_without_reusing_existing_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            first = create_next_run_dir(repo)
            second = create_next_run_dir(repo)

            self.assertEqual(repo / "outputs" / "current_active_stat_extractor_runs" / "run_001", first)
            self.assertEqual(repo / "outputs" / "current_active_stat_extractor_runs" / "run_002", second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertEqual(second, latest_run_dir(repo))

    def test_active_export_paths_keep_all_extract_files_inside_run_folder(self) -> None:
        run_dir = Path("/tmp/example") / "run_007"
        paths = active_export_paths(run_dir)

        self.assertEqual(run_dir / "current_active_player_stats.csv", paths["stats_csv"])
        self.assertEqual(run_dir / "current_active_player_attributes.csv", paths["attributes_csv"])
        self.assertEqual(run_dir / "current_active_player_tendencies.csv", paths["tendencies_csv"])
        self.assertTrue(all(path.parent == run_dir for path in paths.values()))


if __name__ == "__main__":
    unittest.main()
