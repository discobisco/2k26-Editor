from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "nba2k_editor" / "Player Generator"
if str(GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATOR_DIR))

from player_generation_pool import capture_active_roster_pool_rows, live_player_team_features, live_team_features  # type: ignore[import-not-found]


@dataclass(frozen=True)
class Item:
    index: int
    address: int
    label: str


@dataclass(frozen=True)
class Entry:
    section: str
    group: str
    normalized_name: str
    display_name: str
    kind: str = ""


class PoolModel:
    def __init__(self) -> None:
        self.player = Item(index=7, address=5000, label="Test Player")
        self.team = Item(index=2, address=9000, label="Test Team")
        self.loaded_items = {"Players": {7: self.player}, "Teams": {2: self.team}}
        self.team_stats = [
            Entry("Team Stats Edit", "Teams", "POINTS", "POINTS"),
            Entry("Team Stats Edit", "Teams", "POSS", "POSS"),
            Entry("Team Stats Edit", "Teams", "MADE", "MADE"),
            Entry("Team Stats Edit", "Teams", "ATTEMPTED", "ATTEMPTED"),
            Entry("Team Stats Edit", "Teams", "3POINTMADE", "3PT_MADE"),
            Entry("Team Stats Edit", "Teams", "3POINTATTEMPTED", "3PT_ATTEMPTED"),
        ]
        self.stat_entries = [
            Entry("Stats", "Season IDs", "CURRENTYEARSTATID", "Current Year Stat ID", "stat_id"),
            *(Entry("Stats", "Season IDs", name.upper().replace(" ", ""), name, "stat_detail") for name in [
                "Assists", "Blocks", "Defensive Rebounds", "Field Goals Attempted", "Field Goals Made", "Fouls",
                "Free Throws Attempted", "Free Throws Made", "Minutes", "Offensive Rebounds", "Points", "Steals",
                "Three Pointers Attempted", "Three Pointers Made", "Turnovers",
            ]),
        ]
        self.player_entries = {
            "Stats": {"Season IDs": self.stat_entries},
            "Vitals": {"Vitals": [
                Entry("Vitals", "Vitals", "POSITION", "Position"),
                Entry("Vitals", "Vitals", "HEIGHT", "Height"),
                *(Entry("Vitals", "Vitals", f"PLAYTYPE{number}", f"Play Type {number}") for number in range(1, 5)),
            ]},
            "Attributes": {"Attributes": [Entry("Attributes", "Attributes", "FREETHROW", "Free Throw")]},
            "Tendencies": {"Tendencies": [Entry("Tendencies", "Tendencies", "SHOT", "Shot")]},
        }
        self.team_entries = {
            "Team Players": {"Team Players": [Entry("Team Players", "Team Players", "PLAYER1", "PLAYER1")]},
            "Team Stats Edit": {"Teams": self.team_stats},
        }

    def grouped_fields(self, domain: str) -> dict[str, dict[str, list[Entry]]]:
        return self.player_entries if domain == "Players" else self.team_entries

    def is_player_season_id_selector_entry(self, entry: Entry) -> bool:
        return entry.kind == "stat_id"

    def is_player_selected_stat_detail_entry(self, entry: Entry) -> bool:
        return entry.kind == "stat_detail"

    def read_entry_value(self, entry: Entry, *, index: int, stat_selector: object | None = None) -> dict[str, Any]:
        if entry.normalized_name == "PLAYER1":
            return {"raw_value": self.player.address, "display_value": str(self.player.address)}
        if entry.section == "Team Stats Edit":
            values = {"POINTS": 1000, "POSS": 900, "MADE": 400, "ATTEMPTED": 800, "3POINTMADE": 100, "3POINTATTEMPTED": 300}
            return {"raw_value": values[entry.normalized_name], "display_value": str(values[entry.normalized_name])}
        if entry.kind == "stat_id":
            return {"raw_value": 1, "display_value": "1"}
        return {"raw_value": 1, "display_value": "1"}


def test_capture_active_roster_pool_rows_reads_team_stats_and_play_types() -> None:
    stats, _attributes, _tendencies, team_stats = capture_active_roster_pool_rows(PoolModel())

    assert [stats[0][f"play_type_{number}"] for number in range(1, 5)] == ["1", "1", "1", "1"]

    assert team_stats == [{
        "team_slot": 0,
        "team_index": 2,
        "team_label": "Test Team",
        "POINTS": "1000",
        "POSS": "900",
        "MADE": "400",
        "ATTEMPTED": "800",
        "3POINTMADE": "100",
        "3POINTATTEMPTED": "300",
    }]


def test_live_team_features_accepts_normalized_team_stat_keys() -> None:
    features = live_team_features({
        "POINTS": "1000",
        "PA": "950",
        "POSS": "900",
        "MADE": "400",
        "ATTEMPTED": "800",
        "3POINTMADE": "100",
        "3POINTATTEMPTED": "300",
        "FREETHROWATTEMPTED": "200",
        "OFGM": "380",
        "OFGA": "790",
        "O3PM": "90",
        "W": "10",
        "L": "5",
    })

    assert features["team_points"] == 1000
    assert features["team_games"] == 15
    assert round(features["team_o_rtg"] or 0, 4) == round(1000 * 100 / 900, 4)
    assert round(features["team_x3p_ar"] or 0, 4) == round(300 / 800, 4)
    assert round(features["team_opp_e_fg_percent"] or 0, 4) == round((380 + 0.5 * 90) / 790, 4)


def test_live_player_team_features_builds_team_dependent_player_rates() -> None:
    team = live_team_features({
        "POINTS": "1000",
        "POSS": "900",
        "MADE": "400",
        "ATTEMPTED": "800",
        "FREETHROWATTEMPTED": "200",
        "TURNOVER": "100",
        "OFGA": "790",
        "O3PA": "250",
        "W": "10",
        "L": "5",
    })
    player = {
        "Minutes": "300",
        "Points": "120",
        "Field Goals Made": "45",
        "Field Goals Attempted": "100",
        "Free Throws Attempted": "30",
        "Assists": "40",
        "Steals": "10",
        "Blocks": "5",
        "Turnovers": "20",
        "Fouls": "25",
        "Three Pointers Attempted": "50",
    }

    features = live_player_team_features(player, team)

    assert features["pts_per100"] is not None
    assert features["ast_percent"] is not None
    assert features["stl_percent"] is not None
    assert features["blk_percent"] is not None
    assert features["usg_percent"] is not None
