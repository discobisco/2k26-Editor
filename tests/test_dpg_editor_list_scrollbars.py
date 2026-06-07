from __future__ import annotations

import ast
import inspect
import textwrap

from nba2k_editor.ui.dpg_editor import DpgEditorApp


def _constant_keyword(call: ast.Call, name: str) -> object:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return None


def _list_pane_child_windows(method_name: str) -> list[ast.Call]:
    method = getattr(DpgEditorApp, method_name)
    tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "child_window":
            continue
        width = _constant_keyword(node, "width")
        border = _constant_keyword(node, "border")
        if border is True and width in {340, 420}:
            calls.append(node)
    return calls


def test_left_record_list_panes_do_not_add_outer_scrollbars() -> None:
    calls = [
        *_list_pane_child_windows("_build_players_screen"),
        *_list_pane_child_windows("_build_teams_screen"),
        *_list_pane_child_windows("_build_domain_screen"),
    ]

    assert calls
    assert all(_constant_keyword(call, "no_scrollbar") is True for call in calls)
