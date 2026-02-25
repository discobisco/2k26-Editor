"""Shared backend types."""
from __future__ import annotations

from typing import Callable

StreamUpdateCallback = Callable[[str, bool, Exception | None], None]

