"""Typed trade state models used by the UI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TradeTransaction:
    player: Any
    from_team: str
    to_team: str


@dataclass
class TradeTeamPackage:
    outgoing: list[Any] = field(default_factory=list)
    incoming: list[Any] = field(default_factory=list)


@dataclass
class TradeSlot:
    transactions: list[TradeTransaction] = field(default_factory=list)

    def clear(self) -> None:
        self.transactions.clear()

    def packages(self, participants: list[str]) -> dict[str, TradeTeamPackage]:
        data: dict[str, TradeTeamPackage] = {team: TradeTeamPackage() for team in participants}
        for tx in self.transactions:
            if tx.from_team not in data:
                data[tx.from_team] = TradeTeamPackage()
            if tx.to_team not in data:
                data[tx.to_team] = TradeTeamPackage()
            from_pkg = data[tx.from_team]
            to_pkg = data[tx.to_team]
            if tx.player not in from_pkg.outgoing:
                from_pkg.outgoing.append(tx.player)
            if tx.player not in to_pkg.incoming:
                to_pkg.incoming.append(tx.player)
        return data


@dataclass
class TradeState:
    slot_count: int = 36
    selected_slot: int = 0
    slots: list[TradeSlot] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.slots:
            self.slots = [TradeSlot() for _ in range(self.slot_count)]

    def current_slot(self) -> TradeSlot:
        idx = max(0, min(self.slot_count - 1, int(self.selected_slot)))
        self.selected_slot = idx
        return self.slots[idx]

    def select_slot(self, index: int) -> None:
        self.selected_slot = max(0, min(self.slot_count - 1, int(index)))

    def clear_slot(self, index: int | None = None) -> None:
        if index is None:
            self.current_slot().clear()
            return
        idx = max(0, min(self.slot_count - 1, int(index)))
        self.slots[idx].clear()

    def add_transaction(self, player: Any, from_team: str, to_team: str) -> bool:
        if not from_team or not to_team or from_team == to_team:
            return False
        slot = self.current_slot()
        tx = TradeTransaction(player=player, from_team=from_team, to_team=to_team)
        for existing in slot.transactions:
            if (
                existing.player is player
                and existing.from_team == tx.from_team
                and existing.to_team == tx.to_team
            ):
                return False
        slot.transactions.append(tx)
        return True

    def remove_transaction(self, index: int) -> bool:
        slot = self.current_slot()
        if index < 0 or index >= len(slot.transactions):
            return False
        slot.transactions.pop(index)
        return True

