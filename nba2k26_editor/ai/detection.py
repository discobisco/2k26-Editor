"""Local AI tool detection helpers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LocalAIDetectionResult:
    """Represents a discovered local AI executable."""

    name: str
    command: Path
    arguments: str = ""


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
        },
        {
            "name": "Ollama",
            "paths": [
                _maybe_path(program_files, "Ollama", "ollama.exe"),
                _maybe_path(program_files_x86, "Ollama", "ollama.exe"),
                _maybe_path(localapp, "Programs", "Ollama", "ollama.exe"),
            ],
            "arguments": "run llama3",
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
        },
        {
            "name": "text-generation-webui",
            "paths": [
                _maybe_path(documents, "text-generation-webui", "oneclick", "start_windows.bat"),
                _maybe_path(userprofile, "text-generation-webui", "oneclick", "start_windows.bat"),
            ],
            "arguments": "",
        },
    ]


def detect_local_ai_installations() -> list[LocalAIDetectionResult]:
    """
    Find known local AI executables on disk.

    Returns a list of LocalAIDetectionResult objects.
    """
    matches: list[LocalAIDetectionResult] = []
    seen: set[str] = set()
    for definition in _local_ai_candidates():
        name = str(definition.get("name", "") or "Local AI Tool")
        args = str(definition.get("arguments", "") or "")
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
                )
            )
    return matches


__all__ = ["LocalAIDetectionResult", "detect_local_ai_installations"]
