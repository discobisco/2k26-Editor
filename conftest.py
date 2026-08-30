"""Test-session path setup.

The editor package directory is ``2keditor`` to match the shared remote. That
name starts with a digit, so it cannot appear in an ``import`` statement; it has
to be loaded by string. Importing it runs ``2keditor/__init__.py``, which
registers the module under ``nba2k_editor`` so the package's own absolute
imports resolve.

That registration uses ``sys.modules.setdefault``, so it only wins if nothing
has already claimed the ``nba2k_editor`` name. An editable install pointing at
another checkout installs a ``sys.meta_path`` finder that would otherwise
resolve the name to that other tree, and the whole suite would silently test the
wrong code. Claiming the name here, before any test module is imported, keeps
the suite bound to this repository.

The ``Player Generator`` modules import each other as bare top-level names, so
that directory goes on ``sys.path`` as well.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PACKAGE_DIR = _ROOT / "2keditor"
_GENERATOR_DIR = _PACKAGE_DIR / "Player Generator"


def _prepend_sys_path(path: Path) -> None:
    if not path.is_dir():
        raise RuntimeError(f"expected test import path is missing: {path}")
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


_prepend_sys_path(_ROOT)
importlib.import_module("2keditor")

if sys.modules["nba2k_editor"].__file__ != str(_PACKAGE_DIR / "__init__.py"):
    raise RuntimeError(
        "nba2k_editor resolved to "
        f"{sys.modules['nba2k_editor'].__file__} instead of this repository's "
        f"{_PACKAGE_DIR}. Remove the stale editable install "
        "(pip uninstall nba2k_editor) before running the tests."
    )

_prepend_sys_path(_GENERATOR_DIR)
