from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from source_data import GeneratorSourceInventory


class OutputTarget(StrEnum):
    PROPOSAL = "proposal"
    PREVIEW = "preview"
    OVERWRITE_CURRENT_ROSTER = "overwrite_current_roster"


@dataclass(frozen=True)
class GeneratorInputContract:
    """Explicit Phase 0 generator input contract.

    The contract intentionally has no default season and no implicit output target
    conversion beyond the declared enum values. Live roster overwrite is only valid
    when the caller supplies a label for the roster/session being overwritten.
    """

    season: int
    source_root: Path
    output_target: OutputTarget | str
    roster_label: str | None = None

    def validate(self) -> "GeneratorInputContract":
        season = self._validate_season(self.season)
        source_root = Path(self.source_root).expanduser().resolve()
        GeneratorSourceInventory.from_root(source_root)

        try:
            output_target = self.output_target if isinstance(self.output_target, OutputTarget) else OutputTarget(str(self.output_target))
        except ValueError as exc:
            valid = ", ".join(target.value for target in OutputTarget)
            raise ValueError(f"output_target must be one of: {valid}") from exc

        roster_label = str(self.roster_label or "").strip() or None
        if output_target is OutputTarget.OVERWRITE_CURRENT_ROSTER and roster_label is None:
            raise ValueError("roster_label is required for overwrite_current_roster output")

        return replace(self, season=season, source_root=source_root, output_target=output_target, roster_label=roster_label)

    @staticmethod
    def _validate_season(value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("season must be an explicit season-ending year")
        if isinstance(value, int):
            season = value
        elif isinstance(value, str) and value.strip().isdigit():
            season = int(value.strip())
        else:
            raise ValueError("season must be an explicit season-ending year")
        if season <= 0:
            raise ValueError("season must be an explicit season-ending year")
        return season


__all__ = ["GeneratorInputContract", "OutputTarget"]
