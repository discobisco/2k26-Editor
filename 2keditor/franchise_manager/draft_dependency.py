from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
from typing import Any, Protocol

from .models import DraftClassMode, DraftProspect


class DraftClassDependency(Protocol):
    def generate_draft_class(self, draft_year: int, *, mode: DraftClassMode = DraftClassMode.DRAFT_PICKS) -> tuple[DraftProspect, ...]: ...


class ExistingPlayerGeneratorDraftDependency:
    """Adapter around the existing Player Generator.

    Franchise Manager must not create a second player generation system. For a
    historical draft year, this adapter asks the existing generator for the
    following season's rookie/player proposals and converts the proposal objects
    into draft-prospect records that the franchise database can edit/store.
    """

    def __init__(self, *, source_root: Path | None = None) -> None:
        self.source_root = source_root

    def generate_draft_class(self, draft_year: int, *, mode: DraftClassMode = DraftClassMode.DRAFT_PICKS) -> tuple[DraftProspect, ...]:
        if isinstance(draft_year, bool) or not isinstance(draft_year, int) or draft_year < 1947:
            raise ValueError("draft_year must be >= 1947")
        draft_mode = mode if isinstance(mode, DraftClassMode) else DraftClassMode(str(mode))
        rookie_season = draft_year + 1
        generator_dir = Path(__file__).resolve().parents[1] / "Player Generator"
        generator_dir_text = str(generator_dir)
        if generator_dir_text not in sys.path:
            sys.path.insert(0, generator_dir_text)
        source_data = import_module("source_data")
        player_generator = import_module("player_generator")

        source_root = self.source_root or source_data.GeneratorSourceInventory.from_default().root
        draft_class = player_generator.generate_draft_class_proposals(
            draft_year,
            mode=draft_mode.value,
            source_root=source_root,
        )
        return tuple(_prospect_from_existing_generator_proposal(draft_year, rookie_season, proposal) for proposal in draft_class.proposals)


def _prospect_from_existing_generator_proposal(draft_year: int, rookie_season: int, proposal: Any) -> DraftProspect:
    identity = proposal.identity if isinstance(getattr(proposal, "identity", None), dict) else {}
    by_key = proposal.by_field_key() if hasattr(proposal, "by_field_key") else {}
    ratings: dict[str, Any] = {}
    tendencies: dict[str, Any] = {}
    badges: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    for key, candidate in by_key.items():
        value = getattr(candidate, "display_value", None)
        if key.startswith("Attributes/"):
            ratings[key.removeprefix("Attributes/")] = value
        elif key.startswith("Tendencies/"):
            tendencies[key.removeprefix("Tendencies/")] = value
        elif key.startswith("Badges/"):
            badges[key.removeprefix("Badges/")] = value
        else:
            metadata[key] = value
    first = metadata.get("Vitals/FIRSTNAME") or identity.get("first_name") or ""
    last = metadata.get("Vitals/LASTNAME") or identity.get("last_name") or ""
    for key in (
        "draft_class_mode",
        "draft_year",
        "rookie_season",
        "draft_overall_pick",
        "draft_round",
        "draft_team",
        "draft_college",
    ):
        if key in identity:
            metadata[key] = identity[key]
    name = str(identity.get("player") or f"{first} {last}".strip() or getattr(proposal, "player_id", ""))
    position = str(metadata.get("Vitals/POSITION") or identity.get("position") or "")
    return DraftProspect(
        draft_year=draft_year,
        rookie_season=rookie_season,
        player_id=str(getattr(proposal, "player_id", "")),
        name=name,
        position=position,
        historical_team=str(getattr(proposal, "team", "")),
        ratings=ratings,
        tendencies=tendencies,
        badges=badges,
        metadata=metadata,
    )
