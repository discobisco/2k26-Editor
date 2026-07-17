from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nba2k_editor.models.schema import FieldEntry, RecordListItem


@dataclass(frozen=True)
class PlayerPlacement:
    team: RecordListItem
    slot: int


class PlayerMovement:
    """Orchestrates player CURRENTTEAM and Team PLAYER# slot writes."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def _current_team_entry(self) -> FieldEntry:
        entry = self.model._field_by_normalized_name("Players", "CURRENTTEAM")
        if entry is None:
            raise ValueError("Players CURRENTTEAM field is not available")
        return entry

    def _slot_entries(self) -> tuple[tuple[int, FieldEntry], ...]:
        entries = tuple(self.model._team_player_slot_entries())
        if not entries:
            raise ValueError("Team PLAYER slots are not available")
        return entries

    def _team_for_address(self, address: int) -> RecordListItem:
        for team in self.model.loaded_items.get("Teams", {}).values():
            if int(team.address) == int(address):
                return team
        raise ValueError(f"Current team address 0x{int(address):X} is not loaded")

    def _placement(self, player: RecordListItem) -> PlayerPlacement:
        team_pointer = int(
            self.model.read_entry_value_for_item(self._current_team_entry(), player).get("raw_value") or 0
        )
        if not team_pointer:
            raise ValueError(f"{player.label} is not assigned to a team")
        team = self._team_for_address(team_pointer)
        matching_slots: list[int] = []
        for slot, entry in self._slot_entries():
            value = self.model.read_entry_value_for_item(entry, team).get("raw_value")
            if int(value or 0) == int(player.address):
                matching_slots.append(slot)
        if len(matching_slots) != 1:
            raise ValueError(
                f"{player.label} must occur exactly once in {team.label} PLAYER slots; found {len(matching_slots)}"
            )
        return PlayerPlacement(team=team, slot=matching_slots[0])

    def remove_player(self, player: RecordListItem) -> PlayerPlacement:
        placement = self._placement(player)
        slot_entries = self._slot_entries()
        values = [
            int(self.model.read_entry_value_for_item(entry, placement.team).get("raw_value") or 0)
            for _slot, entry in slot_entries
        ]
        removed_index = placement.slot - 1
        compacted_values = [
            *values[:removed_index],
            *(value for value in values[removed_index + 1 :] if value),
        ]
        compacted_values.extend([0] * (len(values) - len(compacted_values)))
        self.model.write_entry_value_for_item(self._current_team_entry(), player, value=0)
        for index, (old_value, new_value) in enumerate(zip(values, compacted_values, strict=True)):
            if old_value != new_value:
                self.model.write_entry_value_for_item(
                    slot_entries[index][1], placement.team, value=new_value
                )
        return placement

    def add_player(self, player: RecordListItem, team: RecordListItem) -> PlayerPlacement:
        current_team = int(
            self.model.read_entry_value_for_item(self._current_team_entry(), player).get("raw_value") or 0
        )
        if current_team:
            assigned_team = self._team_for_address(current_team)
            raise ValueError(f"{player.label} is already assigned to {assigned_team.label}")
        for slot, entry in self._slot_entries():
            value = self.model.read_entry_value_for_item(entry, team).get("raw_value")
            if int(value or 0) == 0:
                self.model.write_entry_value_for_item(entry, team, value=int(player.address))
                self.model.write_entry_value_for_item(
                    self._current_team_entry(), player, value=int(team.address)
                )
                return PlayerPlacement(team=team, slot=slot)
        raise ValueError(f"{team.label} has no open player slot")

    def trade_players(
        self,
        first_player: RecordListItem,
        second_player: RecordListItem,
    ) -> tuple[PlayerPlacement, PlayerPlacement]:
        if first_player == second_player:
            raise ValueError("Select two different players to trade")
        first_prior = self._placement(first_player)
        second_prior = self._placement(second_player)
        if first_prior.team == second_prior.team:
            raise ValueError("Selected players are already on the same team")
        self.remove_player(first_player)
        self.remove_player(second_player)
        first_new = self.add_player(first_player, second_prior.team)
        second_new = self.add_player(second_player, first_prior.team)
        return first_new, second_new


__all__ = ["PlayerMovement", "PlayerPlacement"]
