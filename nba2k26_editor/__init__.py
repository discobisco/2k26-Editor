"""
NBA 2K26 editor package scaffold.

This package will host the modularized code currently in ``2k26Editor.py``.
"""
from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("nba2k26_editor")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"
