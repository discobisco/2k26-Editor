"""Extension loader helpers extracted from PlayerEditorApp."""
from __future__ import annotations

from dataclasses import dataclass
import json
import importlib
import importlib.util
import os
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

from ..core.config import AUTOLOAD_EXTENSIONS
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
    "nba2k_editor.dual_base_mirror": "dual_base_mirror.py (built-in)",
    # Legacy import key retained for backward compatibility.
    "nba2k26_editor.dual_base_mirror": "dual_base_mirror.py (legacy built-in)",
}


def _module_key(module_name: str) -> str:
    return f"{EXTENSION_MODULE_PREFIX}{module_name}"


_BUILTIN_KEYS = {module: _module_key(module) for module in BUILTIN_EXTENSIONS}
_BUILTIN_STEMS = {module.rsplit(".", 1)[-1]: _module_key(module) for module in BUILTIN_EXTENSIONS}


def _key_to_module_name(key: str) -> str | None:
    if key.startswith(EXTENSION_MODULE_PREFIX):
        module_name = key[len(EXTENSION_MODULE_PREFIX) :].strip()
        if module_name.startswith("nba2k26_editor."):
            return module_name.replace("nba2k26_editor.", "nba2k_editor.", 1)
        return module_name
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
        if key.startswith(f"{EXTENSION_MODULE_PREFIX}nba2k26_editor."):
            warnings.warn(
                "Legacy extension key 'nba2k26_editor.*' is deprecated; use 'nba2k_editor.*'.",
                DeprecationWarning,
                stacklevel=2,
            )
            return key.replace("nba2k26_editor.", "nba2k_editor.", 1)
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
        if isinstance(var, bool):
            if var:
                selected.append(key)
        else:
            try:
                if var.get():  # type: ignore[attr-defined]
                    selected.append(key)
            except Exception:
                continue
    restart_cmd = _build_restart_command()
    env = None
    if AUTOLOAD_EXTENSIONS:
        try:
            save_autoload_extensions(list(selected))
        except Exception as exc:
            try:
                app.show_error("Extensions", f"Failed to save selected extensions:\n{exc}")
            except Exception:
                pass
            return
    elif selected:
        env = os.environ.copy()
        env["NBA2K_EXTENSIONS_ONCE"] = json.dumps(selected)
    try:
        subprocess.Popen(restart_cmd, close_fds=True, env=env)
    except Exception as exc:
        try:
            app.show_error("Extensions", f"Failed to restart the editor:\n{exc}")
        except Exception:
            print(f"[extensions] Failed to restart editor: {exc}")
        return
    try:
        app.destroy()
    except Exception:
        pass
    os._exit(0)


def _load_extensions_from_keys(app: Any, keys: list[str]) -> None:
    for raw_key in keys:
        key = _normalize_autoload_key(str(raw_key))
        app.extension_vars[key] = True
        if is_extension_loaded(app, key):
            continue
        if load_extension_module(key):
            app.loaded_extensions.add(key)


def autoload_extensions_from_file(app: Any) -> None:
    raw_once = os.environ.pop("NBA2K_EXTENSIONS_ONCE", "").strip()
    if raw_once:
        try:
            parsed = json.loads(raw_once)
        except Exception:
            parsed = []
        if isinstance(parsed, list):
            _load_extensions_from_keys(app, [str(item) for item in parsed if str(item).strip()])
        elif isinstance(parsed, str) and parsed.strip():
            _load_extensions_from_keys(app, [parsed.strip()])
        return
    if not AUTOLOAD_EXTENSIONS:
        return
    _load_extensions_from_keys(app, load_autoload_extensions())


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
            print(f"[extensions] Failed to load {label}: {exc}")
            return False
    path = _key_to_path(key)
    if path is None:
        print(f"[extensions] Failed to load {label}: Invalid extension key.")
        return False
    if not path.exists():
        print(f"[extensions] Failed to load {label}: file not found.")
        return False
    try:
        spec = importlib.util.spec_from_file_location(f"ext_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True
    except Exception as exc:
        print(f"[extensions] Failed to load {label}: {exc}")
        return False


def toggle_extension_module(app: Any, key: str, label: str, var: bool) -> None:
    display_name = label or extension_label_for_key(key)
    enabled = bool(var)
    if not enabled:
        if key in app.loaded_extensions:
            app.loaded_extensions.discard(key)
            try:
                app.extension_status_var.set(f"Restarting without {display_name}...")
            except Exception:
                pass
            reload_with_selected_extensions(app)
        return
    if key in app.loaded_extensions:
        app.extension_status_var.set(f"{display_name} is already loaded.")
        return
    if load_extension_module(key):
        app.loaded_extensions.add(key)
        app.extension_status_var.set(f"Loaded extension: {display_name}")


__all__ = [
    "ExtensionEntry",
    "reload_with_selected_extensions",
    "autoload_extensions_from_file",
    "discover_extension_files",
    "is_extension_loaded",
    "load_extension_module",
    "toggle_extension_module",
]
