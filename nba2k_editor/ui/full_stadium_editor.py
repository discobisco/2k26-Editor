"""Stadium editor built with Dear PyGui."""
from __future__ import annotations

from .base_entity_editor import BaseEntityEditor, EntityEditorConfig

_STADIUM_EDITOR_CONFIG = EntityEditorConfig(
    editor_type="stadium",
    entity_type="stadium",
    index_attr="stadium_index",
    name_attr=None,
    super_type="Stadiums",
    label="Stadium Editor",
    width=780,
    height=620,
    save_error_title="Stadium Editor",
    save_success_title="Stadium Editor",
    save_success_message="Saved {count} field(s).",
    detailed_errors=True,
    require_process_for_save=False,
    empty_categories_message="No stadium categories detected in offsets files.",
    notice_text="Live editing will activate once stadium base pointers/stride are defined in offsets files.",
    refresh_before_load="refresh_stadiums",
)


class FullStadiumEditor(BaseEntityEditor):
    """Tabbed stadium editor using Dear PyGui."""

    def __init__(self, app, model, stadium_index: int | None = None) -> None:
        super().__init__(
            app=app,
            model=model,
            entity_index=stadium_index if stadium_index is not None else 0,
            entity_name="",
            config=_STADIUM_EDITOR_CONFIG,
        )


__all__ = ["FullStadiumEditor"]

