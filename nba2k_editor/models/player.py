"""Lightweight player container."""
from dataclasses import dataclass


@dataclass
class Player:
    index: int
    first_name: str = ""
    last_name: str = ""
    team: str = ""
    team_id: int | None = None
    record_ptr: int | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:
        return f"<Player index={self.index} name='{self.full_name}' team='{self.team}' team_id={self.team_id}>"


__all__ = ["Player"]
