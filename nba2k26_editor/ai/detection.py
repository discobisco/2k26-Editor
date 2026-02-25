"""Local AI tool detection helpers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LocalAIDetectionResult:
    """Represents a discovered local AI tool or model."""

    name: str
    command: Path | None = None
    arguments: str = ""
    kind: str = "launcher"
    backend: str = ""
    model_path: Path | None = None


def _maybe_path(base: str | Path | None, *parts: str) -> Path | None:
    """Compose a Path from base and parts, returning None when base is falsy."""
    if not base:
        return None
    path = Path(base).expanduser()
    for piece in parts:
        if piece:
            path = path / piece
    return path


def _local_ai_candidates() -> list[dict[str, Any]]:
    """Describe common local AI launchers and their installation hints."""
    localapp = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    userprofile = os.environ.get("USERPROFILE")
    documents = Path.home() / "Documents"

    return [
        {
            "name": "LM Studio",
            "paths": [
                _maybe_path(localapp, "Programs", "LM Studio", "lmstudio-cli.exe"),
                _maybe_path(localapp, "Programs", "LM Studio", "lmstudio.exe"),
                _maybe_path(localapp, "Programs", "LM Studio", "LM Studio.exe"),
                _maybe_path(program_files, "LM Studio", "LM Studio.exe"),
                _maybe_path(program_files_x86, "LM Studio", "LM Studio.exe"),
            ],
            "arguments": "",
            "kind": "launcher",
        },
        {
            "name": "Ollama",
            "paths": [
                _maybe_path(program_files, "Ollama", "ollama.exe"),
                _maybe_path(program_files_x86, "Ollama", "ollama.exe"),
                _maybe_path(localapp, "Programs", "Ollama", "ollama.exe"),
            ],
            "arguments": "run llama3",
            "kind": "launcher",
        },
        {
            "name": "koboldcpp",
            "paths": [
                _maybe_path(program_files, "koboldcpp", "koboldcpp.exe"),
                _maybe_path(program_files_x86, "koboldcpp", "koboldcpp.exe"),
                _maybe_path(documents, "koboldcpp", "koboldcpp.exe"),
                _maybe_path(userprofile, "koboldcpp", "koboldcpp.exe"),
            ],
            "arguments": "",
            "kind": "launcher",
        },
        {
            "name": "text-generation-webui",
            "paths": [
                _maybe_path(documents, "text-generation-webui", "oneclick", "start_windows.bat"),
                _maybe_path(userprofile, "text-generation-webui", "oneclick", "start_windows.bat"),
            ],
            "arguments": "",
            "kind": "launcher",
        },
    ]


def _local_model_roots() -> list[Path]:
    """Return likely folders containing local model files."""
    localapp = os.environ.get("LOCALAPPDATA")
    userprofile = os.environ.get("USERPROFILE")
    documents = Path.home() / "Documents"
    roots = [
        _maybe_path(localapp, "LM Studio", "models"),
        _maybe_path(localapp, "LM Studio", "Models"),
        _maybe_path(localapp, "lm-studio", "models"),
        _maybe_path(userprofile, ".cache", "lm-studio", "models"),
        _maybe_path(documents, "LM Studio", "Models"),
        _maybe_path(documents, "lm-studio", "models"),
        _maybe_path(documents, "text-generation-webui", "models"),
        _maybe_path(documents, "koboldcpp", "models"),
        _maybe_path(documents, "llama.cpp", "models"),
        _maybe_path(documents, "models"),
    ]
    return [path for path in roots if path is not None]


def _iter_model_files(root: Path, max_depth: int = 3) -> list[Path]:
    """Collect likely model files under root with a shallow scan."""
    matches: list[Path] = []
    if not root.exists():
        return matches
    for dirpath, dirnames, filenames in os.walk(root):
        try:
            rel_depth = len(Path(dirpath).relative_to(root).parts)
        except Exception:
            rel_depth = 0
        if rel_depth > max_depth:
            dirnames[:] = []
            continue
        for filename in filenames:
            lower = filename.lower()
            if lower.endswith(".gguf") or lower.endswith(".ggml"):
                matches.append(Path(dirpath) / filename)
    return matches


def detect_local_ai_installations() -> list[LocalAIDetectionResult]:
    """
    Find known local AI executables and model files on disk.

    Returns a list of LocalAIDetectionResult objects.
    """
    matches: list[LocalAIDetectionResult] = []
    seen: set[str] = set()
    for definition in _local_ai_candidates():
        name = str(definition.get("name", "") or "Local AI Tool")
        args = str(definition.get("arguments", "") or "")
        kind = str(definition.get("kind", "launcher") or "launcher")
        paths = definition.get("paths")
        if not isinstance(paths, (list, tuple)):
            continue
        for raw_path in paths:
            if raw_path is None:
                continue
            command = Path(raw_path)
            if not command.exists():
                continue
            resolved = command.resolve()
            key = str(resolved).lower()
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                LocalAIDetectionResult(
                    name=name,
                    command=resolved,
                    arguments=args,
                    kind=kind,
                )
            )
    for root in _local_model_roots():
        for model_path in _iter_model_files(root):
            resolved = model_path.resolve()
            key = f"model::{str(resolved).lower()}"
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                LocalAIDetectionResult(
                    name=resolved.name,
                    kind="model",
                    backend="llama_cpp",
                    model_path=resolved,
                )
            )
    return matches


__all__ = ["LocalAIDetectionResult", "detect_local_ai_installations"]
