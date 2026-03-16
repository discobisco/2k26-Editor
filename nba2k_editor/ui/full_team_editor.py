"""Full team editor window built with Dear PyGui."""
from __future__ import annotations

from ..models.data_model import PlayerDataModel
from .base_entity_editor import BaseEntityEditor, EntityEditorConfig

_TEAM_EDITOR_CONFIG = EntityEditorConfig(
    editor_type="team",
    entity_type="team",
    index_attr="team_index",
    name_attr="team_name",
    super_type="Teams",
    label="Edit Team: {name}",
    width=820,
    height=640,
    save_error_title="Save Error",
    save_success_title="Save Successful",
    save_success_message="Saved {count} field(s) for {name}.",
    detailed_errors=False,
    require_process_for_save=True,
)


class FullTeamEditor(BaseEntityEditor):
    """Tabbed team editor using Dear PyGui."""

    def __init__(self, app, team_index: int, team_name: str, model: PlayerDataModel) -> None:
        super().__init__(
            app=app,
            model=model,
            entity_index=team_index,
            entity_name=team_name,
            config=_TEAM_EDITOR_CONFIG,
        )


__all__ = ["FullTeamEditor"]

