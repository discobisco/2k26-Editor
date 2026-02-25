"""Compatibility wrappers for in-process Python backends."""
from __future__ import annotations

from typing import Any

from .backends.base import StreamUpdateCallback
from .backends.python_backend import (
    generate_async,
    generate_sync,
    load_instance,
)


def load_python_instance(backend: str, model_path: str, **kwargs: Any) -> Any:
    del kwargs
    return load_instance(backend, model_path)


def generate_text_sync(
    backend: str,
    instance: Any,
    prompt: str,
    max_tokens: int = 256,
    temperature: float = 0.4,
) -> str:
    return generate_sync(
        backend,
        instance,
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def generate_text_async(
    backend: str,
    model_path: str,
    prompt: str,
    max_tokens: int = 256,
    temperature: float = 0.4,
    on_update: StreamUpdateCallback | None = None,
):
    return generate_async(
        backend,
        model_path,
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        on_update=on_update,
    )
