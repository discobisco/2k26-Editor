"""Home screen for Dear PyGui."""
from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..core.config import (
    APP_VERSION,
    HOOK_TARGETS,
)
from . import extensions_ui


def build_home_screen(app) -> None:
    with dpg.child_window(tag="screen_home", parent=app.content_root, autosize_x=True, autosize_y=True) as tag:
        app.screen_tags["home"] = tag
        dpg.add_text("2K26 Offline Player Editor", bullet=False, color=(224, 225, 221, 255))
        dpg.add_spacer(height=10)
        with dpg.child_window(border=False, autosize_x=True, autosize_y=True, tag="home_content"):
            with dpg.tab_bar():
                with dpg.tab(label="Overview"):
                    _build_home_overview_tab(app)
                with dpg.tab(label="AI Settings"):
                    _build_home_ai_settings_tab(app)
        dpg.add_spacer(height=8)
        dpg.add_text(f"Version {APP_VERSION}", color=(150, 160, 170, 255))


def _build_home_overview_tab(app) -> None:
    dpg.add_text("Hook target", color=(224, 225, 221, 255))
    labels = [label for label, _ in HOOK_TARGETS]
    label_to_exe = {label: exe for label, exe in HOOK_TARGETS}
    current_exe = (app.hook_target_var.get() or label_to_exe.get(labels[0], "")).lower()
    current_label = next((lbl for lbl, exe in HOOK_TARGETS if exe.lower() == current_exe), labels[0])
    dpg.add_radio_button(
        items=labels,
        horizontal=True,
        default_value=current_label,
        callback=lambda _s, value: app._set_hook_target(label_to_exe.get(value, value)),
    )
    dpg.add_spacer(height=6)
    app.status_text_tag = dpg.add_text(app.status_var.get(), wrap=480)

    def refresh_status():
        app._update_status()
        dpg.set_value(app.status_text_tag, app.status_var.get())

    dpg.add_spacer(height=4)
    with dpg.group(horizontal=True):
        dpg.add_button(label="Refresh", callback=lambda: refresh_status(), width=140)
        dpg.add_button(label="Load Offsets File", callback=app._open_offset_file_dialog, width=160)
    dpg.add_spacer(height=6)
    app.offset_status_text_tag = dpg.add_text(app.offset_load_status.get(), wrap=520, color=(155, 164, 181, 255))

    dpg.add_spacer(height=16)
    _build_extension_loader(app)


def _build_home_ai_settings_tab(app) -> None:
    dpg.add_text("AI Settings", color=(224, 225, 221, 255))
    dpg.add_spacer(height=6)
    with dpg.group(horizontal=True):
        dpg.add_text("Mode", color=(200, 208, 214, 255))
        dpg.add_radio_button(
            items=["none", "remote", "local"],
            default_value=app.ai_mode_var.get() or "none",
            callback=lambda _s, v: app.ai_mode_var.set(v),
            horizontal=True,
        )
    dpg.add_spacer(height=4)
    dpg.add_text("Remote (OpenAI-compatible)", color=(200, 208, 214, 255))
    dpg.add_input_text(
        label="Base URL",
        default_value=app.ai_api_base_var.get(),
        width=320,
        callback=lambda s, v: app.ai_api_base_var.set(v),
    )
    dpg.add_input_text(
        label="API Key",
        default_value=app.ai_api_key_var.get(),
        width=320,
        password=True,
        callback=lambda s, v: app.ai_api_key_var.set(v),
    )
    dpg.add_input_text(
        label="Model",
        default_value=app.ai_model_var.get(),
        width=320,
        callback=lambda s, v: app.ai_model_var.set(v),
    )
    dpg.add_input_text(
        label="Timeout (sec)",
        default_value=app.ai_api_timeout_var.get(),
        width=120,
        callback=lambda s, v: app.ai_api_timeout_var.set(v),
    )
    dpg.add_spacer(height=6)
    dpg.add_text("Local", color=(200, 208, 214, 255))
    dpg.add_combo(
        label="Backend",
        items=["cli", "python"],
        default_value=app.ai_local_backend_var.get() or "cli",
        width=160,
        callback=lambda s, v: app.ai_local_backend_var.set(v),
    )
    dpg.add_input_text(
        label="Command",
        default_value=app.ai_local_command_var.get(),
        width=400,
        callback=lambda s, v: app.ai_local_command_var.set(v),
    )
    dpg.add_input_text(
        label="Arguments",
        default_value=app.ai_local_args_var.get(),
        width=400,
        callback=lambda s, v: app.ai_local_args_var.set(v),
    )
    dpg.add_input_text(
        label="Working Dir",
        default_value=app.ai_local_workdir_var.get(),
        width=400,
        callback=lambda s, v: app.ai_local_workdir_var.set(v),
    )
    dpg.add_input_text(
        label="Python Backend",
        default_value=app.ai_python_backend_var.get(),
        width=200,
        callback=lambda s, v: app.ai_python_backend_var.set(v),
    )
    dpg.add_input_text(
        label="Model Path/ID",
        default_value=app.ai_model_path_var.get(),
        width=400,
        callback=lambda s, v: app.ai_model_path_var.set(v),
    )
    dpg.add_input_text(
        label="Max Tokens",
        default_value=app.ai_model_max_tokens_var.get(),
        width=140,
        callback=lambda s, v: app.ai_model_max_tokens_var.set(v),
    )
    dpg.add_input_text(
        label="Temperature",
        default_value=app.ai_model_temperature_var.get(),
        width=140,
        callback=lambda s, v: app.ai_model_temperature_var.set(v),
    )


def _build_extension_loader(app) -> None:
    dpg.add_text("Extensions", color=(224, 225, 221, 255))
    entries = extensions_ui.discover_extension_files()
    if not entries:
        dpg.add_text("No additional Python modules detected in the editor directory.", color=(155, 164, 181, 255))
        return
    with dpg.child_window(height=180, border=True):
        for entry in entries:
            key = entry.key
            label = entry.label
            already_loaded = extensions_ui.is_extension_loaded(app, key)
            app.extension_vars.setdefault(key, False)

            def _toggle(_sender, value, k=key, l=label):
                app.extension_vars[k] = bool(value)
                extensions_ui.toggle_extension_module(app, k, l, bool(value))

            chk = dpg.add_checkbox(label=label, default_value=already_loaded, callback=_toggle)
            app.extension_checkbuttons[key] = chk
            if already_loaded:
                dpg.disable_item(chk)
                app.loaded_extensions.add(key)
    app.extension_status_text = dpg.add_text(app.extension_status_var.get(), wrap=400, color=(155, 164, 181, 255))
    dpg.add_button(
        label="Reload with selected extensions",
        callback=lambda: extensions_ui.reload_with_selected_extensions(app),
        width=260,
    )
    extensions_ui.autoload_extensions_from_file(app)


__all__ = ["build_home_screen"]
