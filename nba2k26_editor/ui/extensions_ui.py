"""Extension loader helpers extracted from PlayerEditorApp."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Sequence, cast

import tkinter as tk
from tkinter import messagebox

from ..core.extensions import load_autoload_extensions, save_autoload_extensions


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
    try:
        app.destroy()
    except Exception:
        pass
    python = sys.executable or "python"
    argv = sys.argv[1:] if len(sys.argv) > 1 else []
    os.execl(python, python, *argv)


def autoload_extensions_from_file(app: Any) -> None:
    for path in load_autoload_extensions():
        key = str(path)
        var = app.extension_vars.get(key)
        if var is not None:
            var.set(True)
        if is_extension_loaded(app, path):
            chk = app.extension_checkbuttons.get(key)
            if chk is not None:
                chk.configure(state="disabled")
            continue
        if load_extension_module(path):
            app.loaded_extensions.add(key)
            chk = app.extension_checkbuttons.get(key)
            if chk is not None:
                chk.configure(state="disabled")


def discover_extension_files() -> list[Path]:
    base_dir = Path(__file__).resolve().parent.parent
    ext_dir = base_dir / "Extentions"
    search_dirs = [base_dir, ext_dir]
    files: list[Path] = []
    seen: set[str] = set()
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("__"):
                continue
            lower_name = path.name.lower()
            if lower_name.startswith("2k26editor"):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
    return files


def is_extension_loaded(app: Any, path: Path) -> bool:
    abs_path = str(path.resolve())
    if abs_path in app.loaded_extensions:
        return True
    for module in list(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == path.resolve():
            return True
    return False


def load_extension_module(path: Path) -> bool:
    try:
        spec = importlib.util.spec_from_file_location(f"ext_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True
    except Exception as exc:
        messagebox.showerror("Extension Loader", f"Failed to load {path.name}:\n{exc}")
        return False


def toggle_extension_module(app: Any, path: Path, var: tk.BooleanVar) -> None:
    key = str(path.resolve())
    if not var.get():
        if key in app.loaded_extensions:
            app.extension_status_var.set("Unloading extensions is not supported once they are loaded.")
            var.set(True)
        return
    if key in app.loaded_extensions:
        app.extension_status_var.set(f"{path.name} is already loaded.")
        return
    if load_extension_module(path):
        app.loaded_extensions.add(key)
        app.extension_status_var.set(f"Loaded extension: {path.name}")
        chk = app.extension_checkbuttons.get(key)
        if chk is not None:
            chk.configure(state=tk.DISABLED)
        if hasattr(app, "btn_import"):
            try:
                app.btn_import.configure(command=lambda app=app: app._open_import_dialog())
            except Exception:
                pass
    else:
        var.set(False)


__all__ = [
    "reload_with_selected_extensions",
    "autoload_extensions_from_file",
    "discover_extension_files",
    "is_extension_loaded",
    "load_extension_module",
    "toggle_extension_module",
]
