"""Extension loader helpers extracted from PlayerEditorApp."""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox

from ..core.extensions import (
    EXTENSION_MODULE_PREFIX,
    load_autoload_extensions,
    save_autoload_extensions,
)


@dataclass(frozen=True)
class ExtensionEntry:
    key: str
    label: str
    path: Path | None = None
    module: str | None = None


BUILTIN_EXTENSIONS: dict[str, str] = {
    "nba2k26_editor.dual_base_mirror": "dual_base_mirror.py (built-in)",
}


def _module_key(module_name: str) -> str:
    return f"{EXTENSION_MODULE_PREFIX}{module_name}"


_BUILTIN_KEYS = {module: _module_key(module) for module in BUILTIN_EXTENSIONS}
_BUILTIN_STEMS = {module.rsplit(".", 1)[-1]: _module_key(module) for module in BUILTIN_EXTENSIONS}


def _key_to_module_name(key: str) -> str | None:
    if key.startswith(EXTENSION_MODULE_PREFIX):
        return key[len(EXTENSION_MODULE_PREFIX) :].strip()
    return None


def _key_to_path(key: str) -> Path | None:
    if key.startswith(EXTENSION_MODULE_PREFIX):
        return None
    try:
        return Path(key).expanduser()
    except Exception:
        return None


def _normalize_autoload_key(key: str) -> str:
    if key.startswith(EXTENSION_MODULE_PREFIX):
        return key
    try:
        stem = Path(key).stem
    except Exception:
        return key
    return _BUILTIN_STEMS.get(stem, key)


def extension_label_for_key(key: str) -> str:
    module_name = _key_to_module_name(key)
    if module_name:
        return BUILTIN_EXTENSIONS.get(module_name, module_name)
    path = _key_to_path(key)
    if path is not None:
        return path.name
    return key


def _build_restart_command() -> list[str]:
    executable = sys.executable or "python"
    if getattr(sys, "frozen", False):
        return [executable, *sys.argv[1:]]
    main_module = sys.modules.get("__main__")
    spec = getattr(main_module, "__spec__", None)
    module_name = getattr(spec, "name", None) if spec else None
    if module_name:
        return [executable, "-m", module_name, *sys.argv[1:]]
    main_file = getattr(main_module, "__file__", None)
    if main_file:
        return [executable, main_file, *sys.argv[1:]]
    if sys.argv:
        return [executable, *sys.argv]
    return [executable]


def reload_with_selected_extensions(app: Any) -> None:
    selected: list[str] = []
    for key, var in app.extension_vars.items():
        try:
            if var.get():
                selected.append(key)
        except Exception:
            continue
    try:
        save_autoload_extensions(list(selected))
    except Exception as exc:
        messagebox.showerror("Extensions", f"Failed to save selected extensions:\n{exc}")
        return
    restart_cmd = _build_restart_command()
    try:
        subprocess.Popen(restart_cmd, close_fds=True)
    except Exception as exc:
        messagebox.showerror("Extensions", f"Failed to restart the editor:\n{exc}")
        return
    try:
        app.destroy()
    except Exception:
        pass
    os._exit(0)


def autoload_extensions_from_file(app: Any) -> None:
    for raw_key in load_autoload_extensions():
        key = _normalize_autoload_key(str(raw_key))
        var = app.extension_vars.get(key)
        if var is not None:
            var.set(True)
        if is_extension_loaded(app, key):
            continue
        if load_extension_module(key):
            app.loaded_extensions.add(key)


def discover_extension_files() -> list[ExtensionEntry]:
    base_dir = Path(__file__).resolve().parent.parent
    ext_dir = base_dir / "Extentions"
    search_dirs = [base_dir, ext_dir]
    if getattr(sys, "frozen", False):
        try:
            search_dirs.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
    files: list[ExtensionEntry] = []
    seen: set[str] = set()
    builtin_stems = set(_BUILTIN_STEMS)
    for module_name, label in BUILTIN_EXTENSIONS.items():
        key = _BUILTIN_KEYS[module_name]
        if key in seen:
            continue
        seen.add(key)
        files.append(ExtensionEntry(key=key, label=label, module=module_name))
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("__"):
                continue
            lower_name = path.name.lower()
            if lower_name.startswith("2k26editor"):
                continue
            if path.stem in builtin_stems:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            files.append(ExtensionEntry(key=key, label=path.name, path=path))
    return files


def is_extension_loaded(app: Any, key: str) -> bool:
    if key in app.loaded_extensions:
        return True
    module_name = _key_to_module_name(key)
    if module_name:
        return module_name in sys.modules
    path = _key_to_path(key)
    if path is None:
        return False
    try:
        abs_path = path.resolve()
    except Exception:
        abs_path = path
    for module in list(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            if Path(module_file).resolve() == abs_path:
                return True
        except Exception:
            continue
    return False


def load_extension_module(key: str) -> bool:
    label = extension_label_for_key(key)
    module_name = _key_to_module_name(key)
    if module_name:
        try:
            importlib.import_module(module_name)
            return True
        except Exception as exc:
            messagebox.showerror("Extension Loader", f"Failed to load {label}:\n{exc}")
            return False
    path = _key_to_path(key)
    if path is None:
        messagebox.showerror("Extension Loader", f"Failed to load {label}:\nInvalid extension key.")
        return False
    if not path.exists():
        messagebox.showerror("Extension Loader", f"Failed to load {label}:\nExtension file not found.")
        return False
    try:
        spec = importlib.util.spec_from_file_location(f"ext_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True
    except Exception as exc:
        messagebox.showerror("Extension Loader", f"Failed to load {label}:\n{exc}")
        return False


def toggle_extension_module(app: Any, key: str, label: str, var: tk.BooleanVar) -> None:
    display_name = label or extension_label_for_key(key)
    if not var.get():
        if key in app.loaded_extensions:
            should_restart = False
            try:
                should_restart = messagebox.askyesno(
                    "Extensions",
                    f"Unload {display_name}? The editor must restart to fully unload it.",
                    parent=app,
                )
            except Exception:
                should_restart = True
            if should_restart:
                app.loaded_extensions.discard(key)
                try:
                    app.extension_status_var.set(f"Restarting without {display_name}...")
                except Exception:
                    pass
                reload_with_selected_extensions(app)
            else:
                var.set(True)
        return
    if key in app.loaded_extensions:
        app.extension_status_var.set(f"{display_name} is already loaded.")
        return
    if load_extension_module(key):
        app.loaded_extensions.add(key)
        app.extension_status_var.set(f"Loaded extension: {display_name}")
    else:
        var.set(False)


__all__ = [
    "ExtensionEntry",
    "reload_with_selected_extensions",
    "autoload_extensions_from_file",
    "discover_extension_files",
    "is_extension_loaded",
    "load_extension_module",
    "toggle_extension_module",
]
