from __future__ import annotations

import unittest

from nba2k_editor.models.data_model import EDITOR_DOMAINS, EditorDataModel, PLAYER_TEAM_FILTER_ALL, PLAYER_TEAM_FILTER_FREE_AGENTS
from nba2k_editor.models.schema import RecordListItem


class PlayerLoadModel(EditorDataModel):
    def __init__(self) -> None:
        self.loaded_items = {domain: {} for domain in EDITOR_DOMAINS}
        self.selected_items = {domain: None for domain in EDITOR_DOMAINS}
        self.domain_statuses = {domain: "" for domain in EDITOR_DOMAINS}
        self._player_team_pointer_cache: dict[int, int | None] = {}
        self.team_pointer_reads = 0
        self.items = [
            RecordListItem(domain="Players", index=0, address=0x1000, label="Alpha"),
            RecordListItem(domain="Players", index=1, address=0x1100, label="Beta"),
        ]

    def scan_records(self, domain: str, *, limit: int | None = None) -> list[RecordListItem]:  # type: ignore[override]
        if domain != "Players":
            raise AssertionError(domain)
        return self.items

    def runtime_status_text(self) -> str:  # type: ignore[override]
        return "attached"

    def _read_player_current_team_pointer(self, item: RecordListItem) -> int | None:  # type: ignore[override]
        self.team_pointer_reads += 1
        return 0x2000 + item.index


class PlayerLoadPerformanceTests(unittest.TestCase):
    def test_refresh_players_does_not_eagerly_read_current_team_for_every_player(self) -> None:
        model = PlayerLoadModel()

        model.refresh_domain_items("Players")

        self.assertEqual(0, model.team_pointer_reads)
        self.assertEqual({}, model._player_team_pointer_cache)
        self.assertEqual([item.display_label for item in model.items], model.player_item_labels_for_team_filter(PLAYER_TEAM_FILTER_ALL))
        self.assertEqual(0, model.team_pointer_reads)

    def test_free_agents_filter_requires_active_player_with_no_current_team(self) -> None:
        model = PlayerLoadModel()
        free_agent = RecordListItem(domain="Players", index=10, address=0x2000, label="Active None")
        inactive_none = RecordListItem(domain="Players", index=11, address=0x2100, label="Inactive None")
        active_team = RecordListItem(domain="Players", index=12, address=0x2200, label="Active Team")
        model.loaded_items["Players"] = {
            free_agent.index: free_agent,
            inactive_none.index: inactive_none,
            active_team.index: active_team,
        }
        active_by_index = {10: True, 11: False, 12: True}
        team_pointer_by_index = {10: 0, 11: 0, 12: 0x3000}
        model._read_player_is_active = lambda item: active_by_index[item.index]  # type: ignore[method-assign]
        model._read_player_current_team_pointer = lambda item: team_pointer_by_index[item.index]  # type: ignore[method-assign]

        labels = model.player_item_labels_for_team_filter(PLAYER_TEAM_FILTER_FREE_AGENTS)
        items = model.player_items_for_team_filter(PLAYER_TEAM_FILTER_FREE_AGENTS)

        self.assertIn((PLAYER_TEAM_FILTER_FREE_AGENTS, PLAYER_TEAM_FILTER_FREE_AGENTS), model.player_team_filter_options())
        self.assertEqual([free_agent.display_label], labels)
        self.assertEqual({free_agent.index: free_agent}, items)


if __name__ == "__main__":
    unittest.main()
