from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class CodeSyncValidationResult:
    errors: list[str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(project_root: Path, module: str) -> Path:
    return (project_root / module.replace("/", str(Path("/").anchor or "/")).replace("\\", "/").replace("//", "/")).resolve()


def _resolve_module(project_root: Path, module: str) -> Path:
    module_path = project_root / module
    return module_path


def _fingerprints(project_root: Path, modules: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for module in modules:
        p = _resolve_module(project_root, module)
        if p.exists() and p.is_file():
            out[module] = _sha256(p)
    return out


def generate_code_sync(
    *,
    project_root: Path,
    offsets_league_path: Path,
    runtime_modules: list[str],
    test_modules: list[str],
    doc_modules: list[str],
) -> None:
    payload = json.loads(offsets_league_path.read_text(encoding="utf-8"))
    payload["code_sync"] = {
        "runtime_modules": runtime_modules,
        "test_modules": test_modules,
        "doc_modules": doc_modules,
        "module_fingerprints": _fingerprints(project_root, runtime_modules),
    }
    offsets_league_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def validate_code_sync(
    *,
    project_root: Path,
    offsets_league_path: Path,
    check_runtime_fingerprints: bool = False,
) -> CodeSyncValidationResult:
    errors: list[str] = []
    payload = json.loads(offsets_league_path.read_text(encoding="utf-8"))
    code_sync = payload.get("code_sync") or {}
    runtime_modules = code_sync.get("runtime_modules") or []
    stored = code_sync.get("module_fingerprints") or {}

    if check_runtime_fingerprints:
        current = _fingerprints(project_root, runtime_modules)
        for module in runtime_modules:
            expected = stored.get(module)
            actual = current.get(module)
            if expected is None:
                errors.append(f"Missing fingerprint: {module}")
            elif actual is None:
                errors.append(f"Missing runtime module: {module}")
            elif actual != expected:
                errors.append(f"Fingerprint mismatch: {module}")

    return CodeSyncValidationResult(errors=errors)
