"""Staff editor built with Dear PyGui."""
from __future__ import annotations

from .base_entity_editor import BaseEntityEditor, EntityEditorConfig

_STAFF_EDITOR_CONFIG = EntityEditorConfig(
    editor_type="staff",
    entity_type="staff",
    index_attr="staff_index",
    name_attr=None,
    super_type="Staff",
    label="Staff Editor",
    width=780,
    height=620,
    save_error_title="Staff Editor",
    save_success_title="Staff Editor",
    save_success_message="Saved {count} field(s).",
    detailed_errors=True,
    require_process_for_save=False,
    empty_categories_message="No staff categories detected in offsets files.",
    notice_text="Live editing will activate once staff base pointers/stride are defined in offsets files.",
)


class FullStaffEditor(BaseEntityEditor):
    """Tabbed staff editor using Dear PyGui."""

    def __init__(self, app, model, staff_index: int | None = None) -> None:
        super().__init__(
            app=app,
            model=model,
            entity_index=staff_index if staff_index is not None else 0,
            entity_name="",
            config=_STAFF_EDITOR_CONFIG,
        )


__all__ = ["FullStaffEditor"]

