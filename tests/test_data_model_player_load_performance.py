from __future__ import annotations

import unittest

from nba2k_editor.models.data_model import EDITOR_DOMAINS, EditorDataModel, PLAYER_TEAM_FILTER_ALL
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


if __name__ == "__main__":
    unittest.main()
