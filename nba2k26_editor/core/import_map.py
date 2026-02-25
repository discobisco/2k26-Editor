"""Static import/reference report utilities."""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(frozen=True)
class ModuleReport:
    file: str
    imports: list[str]
    functions: list[str]
    classes: list[str]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _module_name_for(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def build_import_map(root: Path) -> dict[str, ModuleReport]:
    reports: dict[str, ModuleReport] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(_read_text(path), filename=str(path))
        except SyntaxError:
            continue
        imports: list[str] = []
        functions: list[str] = []
        classes: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    base = "." * node.level + base
                imports.append(base)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.AsyncFunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
        key = _module_name_for(root, path)
        reports[key] = ModuleReport(
            file=str(path),
            imports=sorted(set(imports)),
            functions=sorted(set(functions)),
            classes=sorted(set(classes)),
        )
    return reports


def write_import_report(root: Path, output_path: Path) -> Path:
    data = build_import_map(root)
    serializable = {name: asdict(report) for name, report in data.items()}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    return output_path

