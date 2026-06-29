from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

from nba2k_editor.models.data_model import EditorDataModel, PLAYER_TEAM_FILTER_ALL
from nba2k_editor.models.schema import FieldEntry, RecordListItem
from nba2k_editor.ui.dpg_editor import DpgEditorApp

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "nba2k_editor" / "Player Generator"))
from player_generation_pool import capture_active_roster_pool_rows  # type: ignore[import-not-found]  # noqa: E402


def _entry(normalized_name: str, ordinal: int, **field_extra: Any) -> FieldEntry:
    field = {"normalized_name": normalized_name, "display_name": field_extra.pop("display_name", normalized_name)}
    field.update(field_extra)
    return FieldEntry(
        domain="Players",
        section="Stats",
        group="Season IDs",
        ordinal=ordinal,
        field=field,
    )


class SeasonStatModel(EditorDataModel):
    def __init__(self, stat_ids: dict[str, int]) -> None:
        self.stat_ids = stat_ids
        self.selector_entries = [
            _entry("CURRENTYEARSTATID", 1, display_name="Current Year Stat ID", stat_role="season_id_selector"),
            _entry("STATSID1", 2, display_name="STATS_ID#1", stat_role="season_id_selector"),
            _entry("STATSID2", 3, display_name="STATS_ID#2", stat_role="season_id_selector"),
        ]
        self.detail_entry = _entry(
            "POINTS",
            4,
            display_name="Points",
            stat_role="season_id_detail",
            selected_record_source={
                "base_pointer": "PlayerSeasonStats",
                "stride": "playerSeasonStatsSize",
                "selector_role": "season_id_selector",
                "invalid_ids": [0, 65535],
            },
        )

    def grouped_fields(self, domain: str):  # type: ignore[override]
        if domain != "Players":
            raise AssertionError(domain)
        return {"Stats": {"Season IDs": [*self.selector_entries, self.detail_entry]}}

    def read_value(self, domain: str, *, index: int, field: dict[str, Any]):  # type: ignore[override]
        if domain != "Players":
            raise AssertionError(domain)
        name = str(field.get("normalized_name") or "")
        raw = self.stat_ids[name]
        return {"raw_value": raw, "display_value": str(raw), "address": 0x1000 + index}


class PlayerListDpg:
    mvTable_SizingStretchProp = 0

    def __init__(self, existing: set[str]) -> None:
        self.existing = set(existing)
        self.values: dict[str, object] = {}
        self.configs: dict[str, dict[str, object]] = {}
        self.selectables: list[str] = []

    def does_item_exist(self, tag: str) -> bool:
        return tag in self.existing

    def set_value(self, tag: str, value: object) -> None:
        self.values[tag] = value

    def configure_item(self, tag: str, **kwargs: object) -> None:
        self.configs[tag] = dict(kwargs)

    def delete_item(self, tag: str, *, children_only: bool = False) -> None:
        self.values[f"deleted:{tag}"] = children_only

    def table(self, **_kwargs: object) -> "PlayerListDpg":
        return self

    def table_row(self, **_kwargs: object) -> "PlayerListDpg":
        return self

    def __enter__(self) -> "PlayerListDpg":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def add_table_column(self, **_kwargs: object) -> None:
        return None

    def add_selectable(self, *, label: str, **_kwargs: object) -> None:
        self.selectables.append(label)


class PlayerSeasonStatDisplayTests(unittest.TestCase):
    def test_player_popout_options_keep_no_stat_season_ids_available_to_callers(self) -> None:
        model = SeasonStatModel({"CURRENTYEARSTATID": 65535, "STATSID1": 0, "STATSID2": 42})

        self.assertEqual(["-- Current Year Stat ID (65535)", "-- STATS ID#1 (0)", "[42] STATS ID#2"], model.player_season_stat_id_options(0))

    def test_no_stat_season_filter_does_not_hide_players(self) -> None:
        model = SeasonStatModel({"CURRENTYEARSTATID": 65535, "STATSID1": 0, "STATSID2": 65535})
        player = RecordListItem("Players", 0, 0x1000, "No Stat Player")
        model.loaded_items = {"Players": {player.display_label: player}, "Teams": {}, "Draft Class": {}}

        self.assertEqual(["[0] No Stat Player"], model.player_item_labels_for_team_filter(PLAYER_TEAM_FILTER_ALL))
        self.assertEqual(["-- Current Year Stat ID (65535)", "-- STATS ID#1 (0)", "-- STATS ID#2 (65535)"], model.player_season_stat_id_options(0))

    def test_player_list_sync_does_not_call_season_stat_filter(self) -> None:
        model = SeasonStatModel({"CURRENTYEARSTATID": 65535, "STATSID1": 0, "STATSID2": 65535})
        player = RecordListItem("Players", 0, 0x1000, "No Stat Player")
        model.loaded_items = {"Players": {player.display_label: player}, "Teams": {}, "Draft Class": {}}
        model.selected_items = {"Players": player, "Teams": None, "Draft Class": None}
        model.domain_status = lambda _domain: "loaded 1 players"  # type: ignore[method-assign]

        def fail_if_player_list_uses_season_options(_index: int) -> list[str]:
            raise AssertionError("player list must not use season-stat options")

        model.player_season_stat_id_options = fail_if_player_list_uses_season_options  # type: ignore[method-assign]
        app = DpgEditorApp(model)
        app._update_detail_panel = lambda *_args: None  # type: ignore[method-assign]
        dpg = PlayerListDpg(
            {
                app._player_team_filter_tag(),
                app._player_search_tag(),
                app._count_tag("Players"),
                app._status_tag("Players"),
                app._list_content_tag("Players"),
            }
        )

        app._sync_player_list(dpg)

        self.assertEqual("Players: 1", dpg.values[app._count_tag("Players")])
        self.assertEqual(["[0] No Stat Player"], dpg.selectables)

    def test_selected_stat_detail_rejects_no_stat_season_ids(self) -> None:
        model = SeasonStatModel({"CURRENTYEARSTATID": 65535, "STATSID1": 0, "STATSID2": 42})

        with self.assertRaisesRegex(ValueError, "no stats row"):
            model.read_entry_value(model.detail_entry, index=0, stat_selector="Current Year Stat ID")

    def test_pool_capture_leaves_no_stat_season_fields_blank(self) -> None:
        model = PoolCaptureNoStatsModel()

        stats_rows, attribute_rows, tendency_rows = capture_active_roster_pool_rows(model)

        self.assertEqual(1, len(stats_rows))
        self.assertEqual(65535, stats_rows[0]["current_year_stat_id"])
        self.assertEqual("", stats_rows[0]["Points"])
        self.assertEqual(1, len(attribute_rows))
        self.assertEqual(1, len(tendency_rows))


class PoolCaptureNoStatsModel:
    def __init__(self) -> None:
        self.player = RecordListItem("Players", 0, 0x1000, "A Z")
        self.team = RecordListItem("Teams", 0, 0x2000, "Team")
        self.loaded_items = {
            "Players": {self.player.display_label: self.player},
            "Teams": {self.team.display_label: self.team},
        }
        self.team_player = FieldEntry("Teams", "Team Players", "Team Players", 1, {"normalized_name": "PLAYER1", "display_name": "PLAYER1"})
        self.position = FieldEntry("Players", "Vitals", "Vitals", 2, {"normalized_name": "POSITION", "display_name": "Position"})
        self.height = FieldEntry("Players", "Vitals", "Vitals", 3, {"normalized_name": "HEIGHT", "display_name": "HEIGHT"})
        self.current_stat_id = FieldEntry("Players", "Stats", "Season IDs", 4, {"normalized_name": "CURRENTYEARSTATID", "display_name": "Current Year Stat ID", "stat_role": "season_id_selector"})
        self.points = FieldEntry("Players", "Stats", "Season IDs", 5, {"normalized_name": "POINTS", "display_name": "Points", "stat_role": "season_id_detail", "selected_record_source": {"base_pointer": "PlayerSeasonStats", "stride": "playerSeasonStatsSize", "invalid_ids": [0, 65535]}})
        self.attribute = FieldEntry("Players", "Attributes", "Shooting", 6, {"normalized_name": "MIDRANGE", "display_name": "Mid-Range"})
        self.tendency = FieldEntry("Players", "Tendencies", "Shooting", 7, {"normalized_name": "SHOT", "display_name": "Shot"})

    def grouped_fields(self, domain: str):
        if domain == "Teams":
            return {"Team Players": {"Team Players": [self.team_player]}}
        if domain == "Players":
            return {
                "Vitals": {"Vitals": [self.position, self.height]},
                "Stats": {"Season IDs": [self.current_stat_id, self.points]},
                "Attributes": {"Shooting": [self.attribute]},
                "Tendencies": {"Shooting": [self.tendency]},
            }
        raise AssertionError(domain)

    def is_player_season_id_selector_entry(self, entry: FieldEntry) -> bool:
        return entry.field.get("stat_role") == "season_id_selector"

    def is_player_selected_stat_detail_entry(self, entry: FieldEntry) -> bool:
        return entry.field.get("stat_role") == "season_id_detail" and isinstance(entry.field.get("selected_record_source"), dict)

    def read_entry_value(self, entry: FieldEntry, *, index: int, stat_selector: object | None = None):
        if stat_selector is not None:
            raise AssertionError("no-stat player seasons must not read selected stat detail rows")
        name = str(entry.normalized_name).upper()
        if entry.domain == "Teams" and name == "PLAYER1":
            return {"raw_value": self.player.address, "display_value": str(self.player.address), "address": 0x3000}
        if name == "CURRENTYEARSTATID":
            return {"raw_value": 65535, "display_value": "65535", "address": 0x4000}
        if name == "POSITION":
            return {"raw_value": 0, "display_value": "PG", "address": 0x5000}
        if name == "HEIGHT":
            return {"raw_value": 74, "display_value": "74", "address": 0x5001}
        return {"raw_value": 50, "display_value": "50", "address": 0x6000}


if __name__ == "__main__":
    unittest.main()
