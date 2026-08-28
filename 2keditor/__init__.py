"""
NBA 2K26 editor package scaffold.

This package will host the modularized code currently in ``2k26Editor.py``.
"""
import sys as _sys
from importlib import metadata

# The package directory is ``2keditor`` to match the shared remote, but that name
# is not a valid Python identifier (it starts with a digit), so it cannot appear
# in ``import`` statements. The package's own modules import each other as
# ``nba2k_editor.*``; register this module under that name so those absolute
# imports resolve no matter how the package was first loaded.
_sys.modules.setdefault("nba2k_editor", _sys.modules[__name__])

__all__ = ["__version__"]

try:
    __version__ = metadata.version("nba2k_editor")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"
