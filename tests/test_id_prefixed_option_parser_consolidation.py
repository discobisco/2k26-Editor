from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERSIONS_PATH = REPO_ROOT / "nba2k_editor" / "core" / "conversions.py"
DATA_MODEL_PATH = REPO_ROOT / "nba2k_editor" / "models" / "data_model.py"
DPG_EDITOR_PATH = REPO_ROOT / "nba2k_editor" / "ui" / "dpg_editor.py"
NEUTRAL_HELPER_MODULE = "nba2k_editor.core.conversions"
NEUTRAL_HELPER_NAME = "parse_id_prefixed_option"
PRIVATE_HELPER_NAME = "_parse_id_prefixed_option"


def _module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function_defs_named(tree: ast.Module, name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]


def _imports_name_from_module(tree: ast.Module, *, module: str, name: str) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != module:
            continue
        if any(alias.name == name for alias in node.names):
            return True
    return False


def _loads_name(tree: ast.Module, name: str) -> bool:
    return any(
        isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == name
        for node in ast.walk(tree)
    )


def test_id_prefixed_option_parser_is_public_neutral_conversion_helper() -> None:
    from nba2k_editor.core.conversions import parse_id_prefixed_option

    assert parse_id_prefixed_option("[123] Season Row") == 123
    assert parse_id_prefixed_option("  [7] Shoe") == 7
    assert parse_id_prefixed_option("No ID Prefix") is None
    assert parse_id_prefixed_option(None) is None


def test_id_prefixed_option_parser_has_no_ui_to_model_private_helper_dependency() -> None:
    conversions_tree = _module_tree(CONVERSIONS_PATH)
    data_model_tree = _module_tree(DATA_MODEL_PATH)
    dpg_editor_tree = _module_tree(DPG_EDITOR_PATH)

    assert len(_function_defs_named(conversions_tree, NEUTRAL_HELPER_NAME)) == 1
    assert _function_defs_named(data_model_tree, PRIVATE_HELPER_NAME) == []
    assert _function_defs_named(dpg_editor_tree, PRIVATE_HELPER_NAME) == []

    assert not _imports_name_from_module(
        dpg_editor_tree,
        module="nba2k_editor.models.data_model",
        name=PRIVATE_HELPER_NAME,
    )

    for path, tree in ((DATA_MODEL_PATH, data_model_tree), (DPG_EDITOR_PATH, dpg_editor_tree)):
        assert _imports_name_from_module(
            tree,
            module=NEUTRAL_HELPER_MODULE,
            name=NEUTRAL_HELPER_NAME,
        ), f"{path.relative_to(REPO_ROOT)} must import {NEUTRAL_HELPER_NAME} from {NEUTRAL_HELPER_MODULE}"
        assert _loads_name(
            tree,
            NEUTRAL_HELPER_NAME,
        ), f"{path.relative_to(REPO_ROOT)} must use {NEUTRAL_HELPER_NAME}"
