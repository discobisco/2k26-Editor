from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..api.v1.models import EraBehaviorModifier, GmPersonality, OwnerProfile, TeamAiProfile
from ..errors import ServiceError


class AiProfileRepository:
    def __init__(self, *, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._archetypes = self._read_json("gm_archetypes_modern.json")
        self._owners = self._read_json("owner_defaults_modern.json")
        self._era_modifiers = self._read_json("era_modifiers_modern.json")

    def _read_json(self, filename: str) -> dict[str, Any]:
        path = self._data_dir / filename
        if not path.exists():
            raise ServiceError(
                status_code=500,
                code="AI_PROFILE_DATA_MISSING",
                message=f"Required AI data file '{filename}' is missing.",
                details={"path": str(path)},
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def _default_archetype_for_team(self, team_key: str) -> str:
        team_prefix = team_key.split("_", 1)[0]
        overrides = self._owners.get("team_overrides", {})
        team_override = overrides.get(team_prefix, {})
        archetype = str(team_override.get("archetype", "")).strip()
        if archetype:
            return archetype
        return str(self._owners.get("defaults", {}).get("archetype", "conservative"))

    def get_personality(self, archetype: str | None = None) -> GmPersonality:
        key = archetype or self._owners.get("defaults", {}).get("archetype", "conservative")
        item = self._archetypes.get("archetypes", {}).get(str(key))
        if not isinstance(item, dict):
            raise ServiceError(
                status_code=400,
                code="UNKNOWN_AI_ARCHETYPE",
                message=f"Unknown AI archetype '{key}'.",
                details={"available": sorted(self._archetypes.get("archetypes", {}).keys())},
            )
        return GmPersonality(id=str(key), **item)

    def get_owner_profile(self, *, team_key: str) -> OwnerProfile:
        team_prefix = team_key.split("_", 1)[0]
        overrides = self._owners.get("team_overrides", {})
        if team_prefix in overrides and isinstance(overrides[team_prefix], dict):
            payload = overrides[team_prefix]
            return OwnerProfile(
                spending_limit=float(payload.get("spending_limit", self._owners["defaults"]["spending_limit"])),
                luxury_tax_tolerance=float(
                    payload.get("luxury_tax_tolerance", self._owners["defaults"]["luxury_tax_tolerance"])
                ),
                patience_level=float(payload.get("patience_level", self._owners["defaults"]["patience_level"])),
                championship_demand=float(
                    payload.get("championship_demand", self._owners["defaults"]["championship_demand"])
                ),
            )
        defaults = self._owners.get("defaults", {})
        return OwnerProfile(
            spending_limit=float(defaults.get("spending_limit", 150_000_000)),
            luxury_tax_tolerance=float(defaults.get("luxury_tax_tolerance", 0.5)),
            patience_level=float(defaults.get("patience_level", 0.5)),
            championship_demand=float(defaults.get("championship_demand", 0.5)),
        )

    def get_era_modifier(self, *, era: str, season: str) -> EraBehaviorModifier:
        if str(era).lower() != "modern":
            raise ServiceError(
                status_code=400,
                code="UNSUPPORTED_AI_ERA",
                message=f"AI personality behavior currently supports only modern era. Got '{era}'.",
                details={"supported_eras": ["modern"]},
            )
        by_season = self._era_modifiers.get("by_season", {})
        payload = by_season.get(season) or self._era_modifiers.get("default")
        if not isinstance(payload, dict):
            raise ServiceError(
                status_code=500,
                code="AI_ERA_MODIFIER_MISSING",
                message=f"No AI era behavior modifier found for season '{season}'.",
                details={},
            )
        return EraBehaviorModifier(era="modern", **payload)

    def resolve_profile(
        self,
        *,
        team_key: str,
        season: str,
        explicit_personality: GmPersonality | None,
        explicit_owner: OwnerProfile | None,
        era: str,
    ) -> TeamAiProfile:
        personality = explicit_personality
        if personality is None:
            personality = self.get_personality(self._default_archetype_for_team(team_key))
        owner = explicit_owner or self.get_owner_profile(team_key=team_key)
        era_modifier = self.get_era_modifier(era=era, season=season)
        return TeamAiProfile(
            team_key=team_key,
            season=season,
            gm_personality=personality,
            owner_profile=owner,
            era_modifier=era_modifier,
        )
