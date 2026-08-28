from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_evidence import shotquality_contest_rows  # type: ignore[import-not-found]  # noqa: E402


def test_dcontest_loader_uses_mapped_nba_id_and_data_master_only(tmp_path: Path) -> None:
    database = tmp_path / "NBA_DATA_Master.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE crafted_source_shotquality (
                nba_id REAL,
                player_name TEXT,
                team_abbreviation TEXT,
                year REAL,
                dcontest REAL,
                source_row_id INTEGER NOT NULL
            );
            CREATE TABLE crafted_player_id_map (
                nba_id TEXT PRIMARY KEY,
                player_id TEXT,
                match_method TEXT,
                status TEXT NOT NULL
            );
            CREATE TABLE player_per_game (
                season INTEGER,
                lg TEXT,
                player_id TEXT,
                team TEXT,
                g REAL
            );

            INSERT INTO crafted_source_shotquality VALUES
                (10.0, 'Display Name Does Not Match', 'AAA', 2026.0, 2.5, 1),
                (20.0, 'Alpha', 'AAA', 2026.0, 3.5, 2),
                (30.0, 'No Games', 'AAA', 2026.0, 1.5, 3);
            INSERT INTO crafted_player_id_map VALUES
                ('10', 'alpha01', 'exact_fixture_id', 'mapped'),
                ('20', NULL, NULL, 'unmapped'),
                ('30', 'nogames01', 'exact_fixture_id', 'mapped');
            INSERT INTO player_per_game VALUES
                (2026, 'NBA', 'alpha01', 'AAA', 82.0),
                (2026, 'NBA', 'nogames01', 'AAA', 0.0);
            """
        )

    rows = shotquality_contest_rows(str(database), 2026, "NBA")

    assert set(rows) == {"ALPHA01"}
    assert rows["ALPHA01"]["dcontest"] == 2.5
    assert rows["ALPHA01"]["nba_id"] == "10"
    assert rows["ALPHA01"]["identity_contract"] == (
        "crafted_player_id_map.status=mapped;nba_id_only;no_name_fallback"
    )
    assert rows["ALPHA01"]["source_database"] == "NBA_DATA_Master.sqlite"
    assert shotquality_contest_rows(str(database), 2026, "NBL") == {}
