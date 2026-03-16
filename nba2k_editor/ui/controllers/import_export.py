"""Import/export controller helpers."""
from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Callable

import dearpygui.dearpygui as dpg

from ..dialogs import ImportSummaryDialog, TeamSelectionDialog

if TYPE_CHECKING:
    from ..app import PlayerEditorApp


def normalize_entity_key(entity_type: str | None) -> str:
    return (entity_type or "").strip().lower()



def entity_title(entity_key: str) -> str:
    return (entity_key or "").strip().title() or "Entity"



def set_excel_status(app: PlayerEditorApp, message: str) -> None:
    app.excel_status_var.set(message)
    if app.excel_status_text_tag and dpg.does_item_exist(app.excel_status_text_tag):
        dpg.set_value(app.excel_status_text_tag, message)



def reset_excel_progress(app: PlayerEditorApp) -> None:
    app.excel_progress_var.set(0)
    if app.excel_progress_bar_tag and dpg.does_item_exist(app.excel_progress_bar_tag):
        dpg.set_value(app.excel_progress_bar_tag, 0)



def apply_excel_progress(
    app: PlayerEditorApp,
    verb: str,
    entity_label: str,
    current: int,
    total: int,
    sheet_name: str | None,
) -> None:
    app.excel_progress_var.set(current if total else 0)
    status = f"{verb} {entity_label}"
    if sheet_name:
        status = f"{status} ({sheet_name})"
    if total > 0:
        status = f"{status} {current}/{total}"
    set_excel_status(app, status)
    if app.excel_progress_bar_tag and dpg.does_item_exist(app.excel_progress_bar_tag):
        dpg.set_value(app.excel_progress_bar_tag, current / total if total else 0)



def excel_progress_callback(
    app: PlayerEditorApp,
    verb: str,
    entity_label: str,
) -> Callable[[int, int, str | None], None]:
    def _callback(current: int, total: int, sheet_name: str | None) -> None:
        app.run_on_ui_thread(lambda: apply_excel_progress(app, verb, entity_label, current, total, sheet_name))

    return _callback



def queue_excel_export_progress(app: PlayerEditorApp, current: int, total: int, sheet_name: str | None) -> None:
    if app._excel_export_queue is None:
        return
    app._excel_export_queue.put(("progress", current, total, sheet_name))



def poll_excel_export(app: PlayerEditorApp) -> None:
    if app._excel_export_queue is None:
        app._excel_export_polling = False
        return
    done_seen = False
    done_result = None
    done_error = None
    try:
        while True:
            item = app._excel_export_queue.get_nowait()
            if not item:
                continue
            kind = item[0]
            if kind == "progress":
                current = int(item[1]) if len(item) > 1 else 0
                total = int(item[2]) if len(item) > 2 else 0
                sheet_name = item[3] if len(item) > 3 else None
                apply_excel_progress(
                    app,
                    "Exporting",
                    app._excel_export_entity_label,
                    current,
                    total,
                    sheet_name,
                )
            elif kind == "done":
                done_seen = True
                done_result = item[1] if len(item) > 1 else None
                done_error = item[2] if len(item) > 2 else None
    except queue.Empty:
        pass
    if done_seen:
        finish_excel_export(app, done_result, done_error)
        return
    if app._excel_export_thread is not None and app._excel_export_thread.is_alive():
        app._excel_export_polling = True
        app.after(100, lambda: poll_excel_export(app))
    else:
        app._excel_export_polling = False



def finish_excel_export(app: PlayerEditorApp, result: object, error: Exception | None) -> None:
    app._excel_export_thread = None
    app._excel_export_queue = None
    app._excel_export_polling = False
    if error is not None:
        app._reset_excel_progress()
        app._set_excel_status("")
        app.show_error("Excel Export", f"Export failed: {error}")
        return
    if result is None:
        app._reset_excel_progress()
        app._set_excel_status("")
        app.show_error("Excel Export", "Export failed: Unknown error.")
        return
    app.excel_progress_var.set(1.0)
    if app.excel_progress_bar_tag and dpg.does_item_exist(app.excel_progress_bar_tag):
        dpg.set_value(app.excel_progress_bar_tag, 1.0)
    if app._excel_export_entity_label:
        app._set_excel_status(f"{app._excel_export_entity_label} export complete.")
    else:
        app._set_excel_status("Export complete.")
    try:
        summary = result.summary_text()  # type: ignore[union-attr]
    except Exception:
        summary = "Export completed."
    app.show_info("Excel Export", summary)



def import_excel(app: PlayerEditorApp, entity_type: str) -> None:
    try:
        from ...importing.excel_import import import_excel_workbook, template_path_for
    except Exception as exc:
        app.show_error("Excel Import", f"Import helpers not available: {exc}")
        return
    if not app.model.mem.open_process():
        app.show_error("Excel Import", "NBA 2K26 is not running.")
        return
    entity_key = normalize_entity_key(entity_type)
    if not entity_key:
        app.show_error("Excel Import", "Unknown entity type.")
        return
    try:
        template = template_path_for(entity_key)
    except ValueError as exc:
        app.show_error("Excel Import", str(exc))
        return

    def _after_choose(path: str) -> None:
        if not path:
            return
        try:
            if entity_key in ("players", "teams"):
                app.model.refresh_players()
            elif entity_key == "staff":
                app.model.refresh_staff()
            elif entity_key in ("stadiums", "stadium"):
                app.model.refresh_stadiums()
        except Exception:
            pass
        app._reset_excel_progress()
        app._set_excel_status(f"Importing {entity_key}...")
        progress_cb = app._excel_progress_callback("Importing", entity_title(entity_key))
        try:
            result = import_excel_workbook(app.model, path, entity_key, progress_cb=progress_cb)
        except Exception as exc:
            app._set_excel_status("")
            app._reset_excel_progress()
            app.show_error("Excel Import", f"Import failed: {exc}")
            return
        app._set_excel_status("")
        app._reset_excel_progress()
        if result.missing_names:
            if entity_key == "players":
                roster_names = [p.full_name for p in app.model.players]
                missing_label = "Players not found - type to search the current roster"
            elif entity_key == "teams":
                roster_names = app.model.get_teams()
                missing_label = "Teams not found - type to search the current list"
            elif entity_key == "staff":
                roster_names = app.model.get_staff()
                missing_label = "Staff not found - type to search the current list"
            else:
                roster_names = app.model.get_stadiums()
                missing_label = "Stadiums not found - type to search the current list"

            def _apply_mapping(mapping: dict[str, str]) -> None:
                if not mapping:
                    return
                app._reset_excel_progress()
                app._set_excel_status(f"Importing {entity_key}...")
                try:
                    follow = import_excel_workbook(
                        app.model,
                        path,
                        entity_key,
                        name_overrides=mapping,
                        only_names=set(mapping.keys()),
                        progress_cb=progress_cb,
                    )
                except Exception as exc:
                    app._reset_excel_progress()
                    app._set_excel_status("")
                    app.show_error("Excel Import", f"Import failed: {exc}")
                    return
                app._reset_excel_progress()
                app._set_excel_status("")
                app.show_info("Excel Import", follow.summary_text())

            ImportSummaryDialog(
                app,
                f"{entity_key.title()} Import Summary",
                result.summary_text(),
                result.missing_names,
                roster_names,
                apply_callback=_apply_mapping,
                missing_label=missing_label,
            )
            return
        app.show_info("Excel Import", result.summary_text())

    app._open_file_dialog(
        "Select Excel workbook to import",
        default_path=str(template.parent),
        default_filename=str(template.name),
        file_types=[("Excel files", ".xlsx")],
        callback=_after_choose,
        save=False,
    )



def export_excel(app: PlayerEditorApp, entity_type: str) -> None:
    try:
        from ...importing.excel_import import export_excel_workbook, template_path_for
    except Exception as exc:
        app.show_error("Excel Export", f"Export helpers not available: {exc}")
        return
    if app._excel_export_thread is not None and app._excel_export_thread.is_alive():
        app.show_info("Excel Export", "An export is already running.")
        return
    if not app.model.mem.open_process():
        app.show_error("Excel Export", "NBA 2K26 is not running.")
        return
    entity_key = normalize_entity_key(entity_type)
    if not entity_key:
        app.show_error("Excel Export", "Unknown entity type.")
        return
    try:
        template = template_path_for(entity_key)
    except ValueError as exc:
        app.show_error("Excel Export", str(exc))
        return

    def _start_export(team_filter: set[str] | None = None) -> None:
        default_name = template.name.replace(".xlsx", "_export.xlsx")

        def _after_choose(path: str) -> None:
            if not path:
                return
            app._reset_excel_progress()
            use_cached = False
            if entity_key == "players":
                use_cached = bool(app.model.players)
            elif entity_key == "teams":
                use_cached = bool(app.model.team_list)
            elif entity_key == "staff":
                use_cached = bool(app.model.staff_list)
            elif entity_key in ("stadiums", "stadium"):
                use_cached = bool(app.model.stadium_list)
            status_label = f"Exporting {entity_key}..."
            if use_cached:
                status_label = f"Exporting {entity_key} (cached scan)..."
            app._set_excel_status(status_label)
            app._excel_export_entity_label = entity_title(entity_key)
            app._excel_export_queue = queue.Queue()
            progress_cb = lambda current, total, sheet_name: queue_excel_export_progress(
                app,
                current,
                total,
                sheet_name,
            )

            def _run_export() -> None:
                try:
                    if entity_key == "players":
                        if not app.model.players:
                            app.model.refresh_players()
                    elif entity_key == "teams":
                        if not app.model.team_list:
                            app.model.refresh_players()
                    elif entity_key == "staff":
                        if not app.model.staff_list:
                            app.model.refresh_staff()
                    elif entity_key in ("stadiums", "stadium"):
                        if not app.model.stadium_list:
                            app.model.refresh_stadiums()
                    result = export_excel_workbook(
                        app.model,
                        path,
                        entity_key,
                        template_path=template,
                        progress_cb=progress_cb,
                        team_filter=team_filter,
                    )
                    if app._excel_export_queue is not None:
                        app._excel_export_queue.put(("done", result, None))
                except Exception as exc:
                    if app._excel_export_queue is not None:
                        app._excel_export_queue.put(("done", None, exc))

            app._excel_export_thread = threading.Thread(target=_run_export, daemon=True)
            app._excel_export_thread.start()
            if not app._excel_export_polling:
                app._poll_excel_export()

        app._open_file_dialog(
            "Save export workbook",
            default_path=str(template.parent),
            default_filename=default_name,
            file_types=[("Excel files", ".xlsx")],
            callback=_after_choose,
            save=True,
        )

    if entity_key == "players":
        if not app.model.players or not app.model.team_list:
            try:
                app.model.refresh_players()
            except Exception:
                pass
        teams_ordered = app.model.get_teams()
        if not teams_ordered:
            app.show_error("Excel Export", "No teams available to export.")
            return
        team_id_map = {name: idx for idx, name in app.model.team_list}
        teams = [(team_id_map.get(name), name) for name in teams_ordered]

        def _after_team_choice(selected: list[str] | None, all_teams: bool) -> None:
            if selected is None:
                return
            team_filter = None
            if not all_teams:
                team_filter = {str(name).lower() for name in selected}
            _start_export(team_filter)

        TeamSelectionDialog(
            app,
            teams,
            title="Export Players",
            message="Select teams to include in the export:",
            select_all=True,
            callback=_after_team_choice,
        )
        return

    _start_export()


__all__ = [
    "apply_excel_progress",
    "entity_title",
    "excel_progress_callback",
    "export_excel",
    "finish_excel_export",
    "import_excel",
    "normalize_entity_key",
    "poll_excel_export",
    "queue_excel_export_progress",
    "reset_excel_progress",
    "set_excel_status",
]
