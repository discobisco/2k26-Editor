from __future__ import annotations

import unittest

from nba2k_editor.models.player_movement import PlayerMovement
from nba2k_editor.models.schema import FieldEntry, RecordListItem


class PlayerMovementModel:
    def __init__(self) -> None:
        self.team_a = RecordListItem("Teams", 0, 0x2000, "Team A")
        self.team_b = RecordListItem("Teams", 1, 0x3000, "Team B")
        self.player_a = RecordListItem("Players", 10, 0x5000, "Player A")
        self.player_b = RecordListItem("Players", 11, 0x5100, "Player B")
        self.player_c = RecordListItem("Players", 12, 0x5200, "Player C")
        self.player_d = RecordListItem("Players", 13, 0x5300, "Player D")
        self.player_e = RecordListItem("Players", 14, 0x5400, "Player E")
        self.player_f = RecordListItem("Players", 15, 0x5500, "Player F")
        self.free_agent = RecordListItem("Players", 16, 0x5600, "Free Agent")
        self.loaded_items = {
            "Teams": {
                self.team_a.display_label: self.team_a,
                self.team_b.display_label: self.team_b,
            },
            "Players": {
                player.display_label: player
                for player in (
                    self.player_a,
                    self.player_b,
                    self.player_c,
                    self.player_d,
                    self.player_e,
                    self.player_f,
                    self.free_agent,
                )
            },
        }
        self.current_team_entry = FieldEntry(
            "Players",
            "Vitals",
            "Team",
            0,
            {"normalized_name": "CURRENTTEAM", "display_name": "Current Team"},
        )
        self.contract_team_entry = FieldEntry(
            "Players",
            "Contract",
            "Contract Terms",
            1,
            {"normalized_name": "CONTRACTTEAM", "display_name": "Contract Team"},
        )
        self.slot_entries = [
            FieldEntry(
                "Teams",
                "Team Players",
                "Team Players",
                slot,
                {"normalized_name": f"PLAYER{slot}", "display_name": f"Player {slot}"},
            )
            for slot in range(1, 5)
        ]
        self.slot_values = {
            self.team_a.index: [self.player_a.address, self.player_b.address, self.player_c.address, 0],
            self.team_b.index: [self.player_d.address, self.player_e.address, self.player_f.address, 0],
        }
        self.current_teams = {
            self.player_a.index: self.team_a.address,
            self.player_b.index: self.team_a.address,
            self.player_c.index: self.team_a.address,
            self.player_d.index: self.team_b.address,
            self.player_e.index: self.team_b.address,
            self.player_f.index: self.team_b.address,
            self.free_agent.index: 0,
        }
        self.contract_teams = dict(self.current_teams)
        self.writes: list[tuple[str, int, str, int]] = []

    def _team_player_slot_entries(self) -> list[tuple[int, FieldEntry]]:
        return list(enumerate(self.slot_entries, start=1))

    def _field_by_normalized_name(self, domain: str, name: str) -> FieldEntry | None:
        if domain == "Players" and name == "CURRENTTEAM":
            return self.current_team_entry
        if domain == "Players" and name == "CONTRACTTEAM":
            return self.contract_team_entry
        return None

    def read_entry_value_for_item(self, entry: FieldEntry, item: RecordListItem, *, stat_selector=None):
        if entry.domain == "Teams":
            slot_index = int(entry.normalized_name.removeprefix("PLAYER")) - 1
            value = self.slot_values[item.index][slot_index]
        elif entry.normalized_name == "CONTRACTTEAM":
            value = self.contract_teams[item.index]
        else:
            value = self.current_teams[item.index]
        return {"raw_value": value, "display_value": value}

    def write_entry_value_for_item(self, entry: FieldEntry, item: RecordListItem, *, value: int, stat_selector=None) -> None:
        numeric = int(value)
        self.writes.append((entry.domain, item.index, entry.normalized_name, numeric))
        if entry.domain == "Teams":
            slot_index = int(entry.normalized_name.removeprefix("PLAYER")) - 1
            self.slot_values[item.index][slot_index] = numeric
        elif entry.normalized_name == "CONTRACTTEAM":
            self.contract_teams[item.index] = numeric
        else:
            self.current_teams[item.index] = numeric


class PlayerMovementTests(unittest.TestCase):
    def test_remove_sets_current_team_to_none_and_shifts_lower_slots_up(self) -> None:
        model = PlayerMovementModel()
        movement = PlayerMovement(model)

        prior = movement.remove_player(model.player_b)

        self.assertEqual(model.team_a, prior.team)
        self.assertEqual(2, prior.slot)
        self.assertEqual(
            [model.player_a.address, model.player_c.address, 0, 0],
            model.slot_values[model.team_a.index],
        )
        self.assertEqual(0, model.current_teams[model.player_b.index])
        self.assertEqual(0, model.contract_teams[model.player_b.index])
        self.assertEqual(
            [
                ("Players", model.player_b.index, "CURRENTTEAM", 0),
                ("Players", model.player_b.index, "CONTRACTTEAM", 0),
                ("Teams", model.team_a.index, "PLAYER2", model.player_c.address),
                ("Teams", model.team_a.index, "PLAYER3", 0),
            ],
            model.writes,
        )

    def test_remove_compacts_lower_players_across_an_existing_gap(self) -> None:
        model = PlayerMovementModel()
        model.slot_values[model.team_a.index] = [
            model.player_a.address,
            model.player_b.address,
            0,
            model.player_c.address,
        ]
        movement = PlayerMovement(model)

        movement.remove_player(model.player_b)

        self.assertEqual(
            [model.player_a.address, model.player_c.address, 0, 0],
            model.slot_values[model.team_a.index],
        )

    def test_remove_rejects_duplicate_team_slot_membership_before_writing(self) -> None:
        model = PlayerMovementModel()
        model.slot_values[model.team_a.index][3] = model.player_b.address
        movement = PlayerMovement(model)

        with self.assertRaisesRegex(ValueError, "exactly once"):
            movement.remove_player(model.player_b)

        self.assertEqual([], model.writes)

    def test_add_uses_first_open_slot_and_sets_current_and_contract_team(self) -> None:
        model = PlayerMovementModel()
        movement = PlayerMovement(model)

        placement = movement.add_player(model.free_agent, model.team_a)

        self.assertEqual(model.team_a, placement.team)
        self.assertEqual(4, placement.slot)
        self.assertEqual(model.free_agent.address, model.slot_values[model.team_a.index][3])
        self.assertEqual(model.team_a.address, model.current_teams[model.free_agent.index])
        self.assertEqual(model.team_a.address, model.contract_teams[model.free_agent.index])
        self.assertEqual(
            [
                ("Players", model.free_agent.index, "CURRENTTEAM", model.team_a.address),
                ("Players", model.free_agent.index, "CONTRACTTEAM", model.team_a.address),
                ("Teams", model.team_a.index, "PLAYER4", model.free_agent.address),
            ],
            model.writes,
        )

    def test_add_rejects_a_full_team_without_writing(self) -> None:
        model = PlayerMovementModel()
        model.slot_values[model.team_a.index][3] = 0x9999
        movement = PlayerMovement(model)

        with self.assertRaisesRegex(ValueError, "no open player slot"):
            movement.add_player(model.free_agent, model.team_a)

        self.assertEqual([], model.writes)
        self.assertEqual(0, model.current_teams[model.free_agent.index])

    def test_trade_removes_both_players_then_adds_each_to_the_other_team(self) -> None:
        model = PlayerMovementModel()
        team_a_tail = 0x5A00
        team_b_tail = 0x5B00
        model.slot_values[model.team_a.index][3] = team_a_tail
        model.slot_values[model.team_b.index][3] = team_b_tail
        movement = PlayerMovement(model)

        first_placement, second_placement = movement.trade_players(model.player_a, model.player_d)

        self.assertEqual(model.team_b, first_placement.team)
        self.assertEqual(model.team_a, second_placement.team)
        self.assertEqual(
            [model.player_b.address, model.player_c.address, team_a_tail, model.player_d.address],
            model.slot_values[model.team_a.index],
        )
        self.assertEqual(
            [model.player_e.address, model.player_f.address, team_b_tail, model.player_a.address],
            model.slot_values[model.team_b.index],
        )
        self.assertEqual(model.team_b.address, model.current_teams[model.player_a.index])
        self.assertEqual(model.team_a.address, model.current_teams[model.player_d.index])
        self.assertEqual(model.team_b.address, model.contract_teams[model.player_a.index])
        self.assertEqual(model.team_a.address, model.contract_teams[model.player_d.index])
        first_none_write = model.writes.index(("Players", model.player_a.index, "CURRENTTEAM", 0))
        second_none_write = model.writes.index(("Players", model.player_d.index, "CURRENTTEAM", 0))
        first_add_write = model.writes.index(("Players", model.player_a.index, "CURRENTTEAM", model.team_b.address))
        second_add_write = model.writes.index(("Players", model.player_d.index, "CURRENTTEAM", model.team_a.address))
        self.assertLess(first_none_write, first_add_write)
        self.assertLess(second_none_write, second_add_write)


if __name__ == "__main__":
    unittest.main()
