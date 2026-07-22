from __future__ import annotations

import unittest

from nba2k_editor.models.data_model import (
    EDITOR_DOMAINS,
    EditorDataModel,
    PLAYER_TEAM_FILTER_ALL,
    PLAYER_TEAM_FILTER_BASE_TEAMS,
    PLAYER_TEAM_FILTER_DRAFT_CLASS,
    PLAYER_TEAM_FILTER_FREE_AGENTS,
)
from nba2k_editor.models.schema import FieldEntry, RecordListItem


class PlayerIndexModel(EditorDataModel):
    def __init__(self) -> None:
        self.loaded_items = {domain: {} for domain in EDITOR_DOMAINS}
        self.selected_items = {domain: None for domain in EDITOR_DOMAINS}
        self.domain_statuses = {domain: "" for domain in EDITOR_DOMAINS}
        self._data_version = 0
        self._player_team_pointer_cache: dict[int, int] = {}
        self._player_filter_items_by_key: dict[str | int, tuple[RecordListItem, ...]] = {}
        self._player_search_keys: dict[int, str] = {}
        self._player_filter_index_ready = False
        self._player_free_agent_filter_ready = False
        self.team_pointer_reads = 0
        self.active_reads = 0
        self.roster_slot_reads = 0
        self.players = (
            RecordListItem("Players", 10, 0x2000, "Available None"),
            RecordListItem("Players", 11, 0x2100, "Inactive None"),
            RecordListItem("Players", 12, 0x2200, "Active Team"),
        )
        self.team = RecordListItem("Teams", 4, 0x3000, "Test Team")
        self.draft_player = RecordListItem("Players", 10, 0x5000, "Draft Prospect")
        self.loaded_items["Players"] = {item.index: item for item in self.players}
        self.loaded_items["Teams"] = {self.team.index: self.team}
        self._slot_entries = (
            FieldEntry("Teams", "Team Players", "Team Players", 0, {"normalized_name": "PLAYER1"}),
            FieldEntry("Teams", "Team Players", "Team Players", 1, {"normalized_name": "PLAYER2"}),
        )

    def runtime_status_text(self) -> str:  # type: ignore[override]
        return "attached"

    def scan_records(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:  # type: ignore[override]
        if domain != "Players":
            raise AssertionError(domain)
        return list(self.players)

    def _team_player_slot_entries(self):  # type: ignore[override]
        return list(enumerate(self._slot_entries, start=1))

    def read_entry_value(self, entry, *, index: int, stat_selector=None):  # type: ignore[override]
        self.roster_slot_reads += 1
        pointer = self.players[2].address if entry is self._slot_entries[0] else 0
        return {"raw_value": pointer}

    def _read_player_current_team_pointer(self, item: RecordListItem) -> int:  # type: ignore[override]
        self.team_pointer_reads += 1
        return 0 if item.index in {10, 11} else self.team.address

    def _read_player_is_active(self, item: RecordListItem) -> bool:  # type: ignore[override]
        self.active_reads += 1
        return item.index != 11

    def _player_filter_source_values(self, players):  # type: ignore[override]
        values = {}
        for player in players:
            values[int(player.index)] = (
                self._read_player_current_team_pointer(player),
                self._read_player_is_active(player),
            )
        return values

    def _scan_records_from_base_key(self, domain: str, base_key: str, *, limit=None):  # type: ignore[override]
        return [self.draft_player]

    def _write_field_at_record_address(self, domain, record_addr, field, value):  # type: ignore[override]
        return value


class PlayerLoadPerformanceTests(unittest.TestCase):
    def test_refresh_players_only_scans_names_and_leaves_index_unprepared(self) -> None:
        model = PlayerIndexModel()
        model.loaded_items["Players"] = {}

        model.refresh_domain_items("Players")

        self.assertEqual(0, model.team_pointer_reads)
        self.assertEqual(0, model.active_reads)
        self.assertEqual({}, model._player_team_pointer_cache)
        self.assertFalse(model._player_filter_index_ready)
        self.assertEqual(
            [item.display_label for item in model.players],
            model.player_item_labels_for_team_filter(PLAYER_TEAM_FILTER_ALL),
        )

    def test_prepared_index_reads_each_source_once_then_filters_without_io(self) -> None:
        model = PlayerIndexModel()

        all_view = model.build_player_filter_index()

        self.assertEqual(3, model.team_pointer_reads)
        self.assertEqual(3, model.active_reads)
        self.assertEqual(2, model.roster_slot_reads)
        self.assertEqual(model.players, all_view.items)
        self.assertEqual((model.players[0],), model.player_list_view(PLAYER_TEAM_FILTER_FREE_AGENTS).items)
        self.assertEqual((model.players[2],), model.player_list_view(4).items)
        self.assertEqual((model.players[2],), model.player_list_view(PLAYER_TEAM_FILTER_BASE_TEAMS).items)
        self.assertEqual((model.draft_player,), model.player_list_view(PLAYER_TEAM_FILTER_DRAFT_CLASS).items)
        self.assertEqual((model.players[2],), model.player_list_view(PLAYER_TEAM_FILTER_ALL, "active team").items)
        self.assertEqual((model.players[0],), model.player_list_view(PLAYER_TEAM_FILTER_ALL, "available none").items)
        self.assertEqual((model.draft_player,), model.player_list_view(PLAYER_TEAM_FILTER_DRAFT_CLASS, "draft").items)

        model._read_player_current_team_pointer = lambda _item: (_ for _ in ()).throw(AssertionError("live read"))  # type: ignore[method-assign]
        model._read_player_is_active = lambda _item: (_ for _ in ()).throw(AssertionError("live read"))  # type: ignore[method-assign]
        version = model._data_version
        for _ in range(5):
            self.assertEqual((model.players[0],), model.player_list_view(PLAYER_TEAM_FILTER_FREE_AGENTS).items)
            self.assertEqual((model.players[2],), model.player_list_view(4, "team").items)
        self.assertEqual(version, model._data_version)

    def test_refresh_index_skips_expensive_free_agent_reads_until_free_agents_are_requested(self) -> None:
        model = PlayerIndexModel()

        model.build_player_filter_index(include_free_agents=False)

        self.assertEqual(0, model.team_pointer_reads)
        self.assertEqual(0, model.active_reads)
        self.assertEqual((model.players[2],), model.player_list_view(4).items)
        self.assertEqual((), model.player_list_view(PLAYER_TEAM_FILTER_FREE_AGENTS).items)

        free_agents = model.prepare_player_list_view(PLAYER_TEAM_FILTER_FREE_AGENTS)

        self.assertEqual((model.players[0],), free_agents.items)
        self.assertEqual(3, model.team_pointer_reads)
        self.assertEqual(3, model.active_reads)

        model.prepare_player_list_view(PLAYER_TEAM_FILTER_FREE_AGENTS)
        self.assertEqual(3, model.team_pointer_reads)
        self.assertEqual(3, model.active_reads)

    def test_player_filter_source_write_invalidates_prepared_index(self) -> None:
        model = PlayerIndexModel()
        model.build_player_filter_index()
        active_entry = FieldEntry("Players", "Vitals", "Vitals", 0, {"normalized_name": "ISACTIVE"})
        version = model._data_version

        model.write_entry_value_for_item(active_entry, model.players[0], value=0)

        self.assertFalse(model._player_filter_index_ready)
        self.assertGreater(model._data_version, version)

        rebuilt = model.prepare_player_list_view(PLAYER_TEAM_FILTER_FREE_AGENTS)

        self.assertTrue(model._player_filter_index_ready)
        self.assertEqual((model.players[0],), rebuilt.items)
        self.assertEqual(6, model.team_pointer_reads)


if __name__ == "__main__":
    unittest.main()
