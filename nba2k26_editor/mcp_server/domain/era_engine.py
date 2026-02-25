from __future__ import annotations

import json
from pathlib import Path

from ..api.v1.models import EraConfig
from ..errors import ServiceError


class EraEngine:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def get_era_config(self, *, era: str, season: str) -> EraConfig:
        if era.lower() != "modern":
            raise ServiceError(
                status_code=400,
                code="UNSUPPORTED_ERA",
                message=f"Era '{era}' is not supported in this release.",
                details={"supported_eras": ["modern"]},
            )
        filename = f"modern_{season.replace('-', '_')}.json"
        path = self._data_dir / filename
        if not path.exists():
            raise ServiceError(
                status_code=400,
                code="UNSUPPORTED_SEASON",
                message=f"Season '{season}' does not have a modern era pack.",
                details={"supported_files": sorted(p.name for p in self._data_dir.glob("modern_*.json"))},
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EraConfig(**payload)

    def transition(self, *, era: str, from_season: str, to_season: str) -> tuple[EraConfig, EraConfig, list[str]]:
        previous = self.get_era_config(era=era, season=from_season)
        target = self.get_era_config(era=era, season=to_season)
        changes: list[str] = []
        if previous.salary_cap != target.salary_cap:
            changes.append(f"Salary cap changed from {previous.salary_cap:,.0f} to {target.salary_cap:,.0f}.")
        if previous.luxury_tax_line != target.luxury_tax_line:
            changes.append(
                f"Luxury tax line changed from {previous.luxury_tax_line:,.0f} to {target.luxury_tax_line:,.0f}."
            )
        if previous.pace_factor != target.pace_factor:
            changes.append(f"Pace factor changed from {previous.pace_factor:.3f} to {target.pace_factor:.3f}.")
        if previous.hand_checking != target.hand_checking:
            changes.append("Hand-checking rules changed.")
        if previous.defensive_three_seconds != target.defensive_three_seconds:
            changes.append("Defensive three-seconds enforcement changed.")
        if not changes:
            changes.append("No major rules changed between the selected seasons.")
        return previous, target, changes
