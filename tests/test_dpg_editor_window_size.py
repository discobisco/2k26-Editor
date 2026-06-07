from __future__ import annotations

import ast
import inspect
import textwrap

from nba2k_editor.ui import dpg_editor
from nba2k_editor.ui.dpg_editor import DpgEditorApp


def _keyword_int(call: ast.Call, name: str) -> int | None:
    for keyword in call.keywords:
        if keyword.arg != name:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, int):
            return keyword.value.value
        if isinstance(keyword.value, ast.Name):
            value = getattr(dpg_editor, keyword.value.id, None)
            if isinstance(value, int):
                return value
    return None


def test_main_app_opens_with_large_viewport_and_matching_canvas() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(DpgEditorApp.run)))
    viewport_size: tuple[int, int] | None = None
    main_window_size: tuple[int, int] | None = None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "create_viewport":
            width = _keyword_int(node, "width")
            height = _keyword_int(node, "height")
            if width is not None and height is not None:
                viewport_size = (width, height)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "window":
            tag = None
            for keyword in node.keywords:
                if keyword.arg == "tag" and isinstance(keyword.value, ast.Constant):
                    tag = keyword.value.value
            if tag == "main_window":
                width = _keyword_int(node, "width")
                height = _keyword_int(node, "height")
                if width is not None and height is not None:
                    main_window_size = (width, height)

    assert viewport_size == (1600, 900)
    assert main_window_size == (1600, 900)
