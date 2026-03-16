"""Home screen for Dear PyGui."""
from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..core.config import APP_VERSION, HOOK_TARGETS
from .theme import TEXT_HEADING, TEXT_SECONDARY, to_rgba
from . import extensions_ui


def build_home_screen(app) -> None:
    with dpg.child_window(tag="screen_home", parent=app.content_root, autosize_x=True, autosize_y=True) as tag:
        app.screen_tags["home"] = tag
        dpg.add_text("Offline Player Editor", bullet=False, color=to_rgba(TEXT_HEADING))
        dpg.add_spacer(height=10)
        with dpg.child_window(border=False, autosize_x=True, autosize_y=True, tag="home_content"):
            _build_home_overview_tab(app)
        dpg.add_spacer(height=8)
        dpg.add_text(f"Version {APP_VERSION}", color=to_rgba(TEXT_SECONDARY))


def _build_home_overview_tab(app) -> None:
    from . import app_shell as shell
    dpg.add_text("Hook target", color=to_rgba(TEXT_HEADING))
    labels = [label for label, _ in HOOK_TARGETS]
    label_to_exe = {label: exe for label, exe in HOOK_TARGETS}
    current_exe = (app.hook_target_var.get() or label_to_exe.get(labels[0], "")).lower()
    current_label = next((lbl for lbl, exe in HOOK_TARGETS if exe.lower() == current_exe), labels[0])
    dpg.add_radio_button(
        items=labels,
        horizontal=True,
        default_value=current_label,
        callback=lambda _s, value: shell.set_hook_target(app, label_to_exe.get(value, value)),
    )
    dpg.add_spacer(height=6)
    app.status_text_tag = dpg.add_text(app.status_var.get(), wrap=480)

    def refresh_status():
        shell.update_status(app)
        dpg.set_value(app.status_text_tag, app.status_var.get())

    def open_offsets() -> None:
        from . import app_launchers

        app_launchers.open_offset_file_dialog(app)

    dpg.add_spacer(height=4)
    with dpg.group(horizontal=True):
        dpg.add_button(label="Refresh", callback=lambda: refresh_status(), width=140)
        dpg.add_button(label="Load Offsets File", callback=open_offsets, width=160)
    dpg.add_spacer(height=6)
    app.offset_status_text_tag = dpg.add_text(app.offset_load_status.get(), wrap=520, color=to_rgba(TEXT_SECONDARY))

    dpg.add_spacer(height=16)
    _build_extension_loader(app)

def _build_extension_loader(app) -> None:
    dpg.add_text("Extensions", color=to_rgba(TEXT_HEADING))
    entries = extensions_ui.discover_extension_files()
    if not entries:
        dpg.add_text("No additional Python modules detected in the editor directory.", color=to_rgba(TEXT_SECONDARY))
        return
    extensions_ui.autoload_extensions_from_file(app)
    with dpg.child_window(height=180, border=True):
        for entry in entries:
            key = entry.key
            label = entry.label
            already_loaded = extensions_ui.is_extension_loaded(app, key)
            selected = already_loaded or bool(app.extension_vars.get(key, False))
            app.extension_vars[key] = selected

            def _toggle(_sender, value, k=key, l=label):
                app.extension_vars[k] = bool(value)
                extensions_ui.toggle_extension_module(app, k, l, bool(value))

            chk = dpg.add_checkbox(label=label, default_value=selected, callback=_toggle)
            if already_loaded:
                dpg.disable_item(chk)
                app.loaded_extensions.add(key)
    dpg.add_text(app.extension_status_var.get(), wrap=400, color=to_rgba(TEXT_SECONDARY))
    dpg.add_button(
        label="Reload with selected extensions",
        callback=lambda: extensions_ui.reload_with_selected_extensions(app),
        width=260,
    )


__all__ = ["build_home_screen"]
