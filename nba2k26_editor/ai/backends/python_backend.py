"""In-process Python model backends."""
from __future__ import annotations

import importlib
import threading
import time
from typing import Any

from .base import StreamUpdateCallback

_PYTHON_BACKEND_INSTANCES: dict[str, Any] = {}
_TRANSFORMERS_MODEL_CACHE: dict[str, tuple[Any, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _instance_key(backend: str, model_path: str) -> str:
    return f"{backend}::{model_path}"


def load_instance(backend: str, model_path: str) -> Any:
    backend = str(backend or "").strip().lower()
    key = _instance_key(backend, model_path or "")
    inst = _PYTHON_BACKEND_INSTANCES.get(key)
    if inst is not None:
        return inst
    if backend == "llama_cpp":
        try:
            llama_mod = importlib.import_module(backend)
            llama_cls = getattr(llama_mod, "Llama")
        except Exception as exc:
            raise RuntimeError("Install 'llama-cpp-python' to use the llama_cpp backend.") from exc
        if not model_path:
            raise RuntimeError("Provide 'model_path' for llama_cpp backend.")
        inst = llama_cls(model_path=model_path)
        _PYTHON_BACKEND_INSTANCES[key] = inst
        return inst
    if backend == "transformers":
        try:
            transformers_mod = importlib.import_module(backend)
            pipeline = getattr(transformers_mod, "pipeline")
        except Exception as exc:
            raise RuntimeError("Install 'transformers' to use the transformers backend.") from exc
        if not model_path:
            raise RuntimeError("Provide 'model_path' for transformers backend.")
        inst = pipeline("text-generation", model=model_path, device_map="auto")
        _PYTHON_BACKEND_INSTANCES[key] = inst
        return inst
    raise RuntimeError(f"Unsupported python backend: {backend}")


def generate_sync(
    backend: str,
    instance: Any,
    prompt: str,
    *,
    max_tokens: int = 256,
    temperature: float = 0.4,
) -> str:
    backend = str(backend or "").strip().lower()
    if backend == "llama_cpp":
        resp = instance.create(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        choices = resp.get("choices") if isinstance(resp, dict) else None
        if choices and choices[0] and "text" in choices[0]:
            return str(choices[0]["text"]).strip()
        return str(resp)
    if backend == "transformers":
        out = instance(prompt, max_length=max_tokens, do_sample=True, temperature=temperature)
        if isinstance(out, list) and out:
            return str(out[0].get("generated_text", "")).strip()
        return str(out)
    raise RuntimeError(f"Unsupported backend for synchronous generation: {backend}")


def generate_async(
    backend: str,
    model_path: str,
    prompt: str,
    *,
    max_tokens: int = 256,
    temperature: float = 0.4,
    on_update: StreamUpdateCallback | None = None,
) -> threading.Thread:
    backend = str(backend or "").strip().lower()

    def _worker() -> None:
        try:
            inst = load_instance(backend, model_path)
        except Exception as exc:  # noqa: BLE001
            if on_update:
                try:
                    on_update("", False, exc)
                except Exception:
                    pass
            return
        try:
            if backend == "llama_cpp":
                chunks: list[str] = []

                def _cb(token: str) -> None:
                    if token:
                        chunks.append(token)
                        if on_update:
                            on_update(token, False, None)

                try:
                    inst.create(prompt=prompt, max_tokens=max_tokens, temperature=temperature, stream=True, callback=_cb)  # type: ignore
                except TypeError:
                    full = generate_sync(
                        backend,
                        inst,
                        prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    if on_update:
                        on_update(full, True, None)
                    return
                if on_update:
                    on_update("".join(chunks), True, None)
                return

            if backend == "transformers":
                try:
                    transformers_mod = importlib.import_module(backend)
                    auto_tokenizer = getattr(transformers_mod, "AutoTokenizer")
                    auto_model = getattr(transformers_mod, "AutoModelForCausalLM")
                    streamer_cls = getattr(transformers_mod, "TextIteratorStreamer")
                except Exception:
                    full = generate_sync(
                        backend,
                        inst,
                        prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    _emit_chunked(full, on_update)
                    return
                cached_tokenizer = None
                cached_model = None
                with _CACHE_LOCK:
                    cached = _TRANSFORMERS_MODEL_CACHE.get(model_path)
                    if cached:
                        cached_tokenizer, cached_model = cached
                if cached_tokenizer is None or cached_model is None:
                    try:
                        pipeline = load_instance("transformers", model_path)
                        cached_tokenizer = getattr(pipeline, "tokenizer", None)
                        cached_model = getattr(pipeline, "model", None)
                    except Exception:
                        pass
                try:
                    tokenizer = cached_tokenizer or auto_tokenizer.from_pretrained(model_path, use_fast=True)
                    model = cached_model or auto_model.from_pretrained(model_path, device_map="auto")
                    with _CACHE_LOCK:
                        _TRANSFORMERS_MODEL_CACHE[model_path] = (tokenizer, model)
                    streamer = streamer_cls(tokenizer, skip_prompt=True, decode_kwargs={"skip_special_tokens": True})

                    def _gen() -> None:
                        inputs = tokenizer(prompt, return_tensors="pt")
                        inputs = {k: v.to(model.device) for k, v in inputs.items()}
                        model.generate(
                            **inputs,
                            max_new_tokens=max_tokens,
                            do_sample=True,
                            temperature=temperature,
                            streamer=streamer,
                        )

                    thread = threading.Thread(target=_gen, daemon=True)
                    thread.start()
                    chunks: list[str] = []
                    for token in streamer:
                        chunks.append(token)
                        if on_update:
                            on_update(token, False, None)
                    if on_update:
                        on_update("".join(chunks), True, None)
                    return
                except Exception:
                    full = generate_sync(
                        backend,
                        inst,
                        prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    _emit_chunked(full, on_update)
                    return

            full = generate_sync(
                backend,
                inst,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if on_update:
                on_update(full, True, None)
        except Exception as exc:  # noqa: BLE001
            if on_update:
                try:
                    on_update("", False, exc)
                except Exception:
                    pass

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def _emit_chunked(text: str, on_update: StreamUpdateCallback | None, chunk_size: int = 40) -> None:
    if on_update is None:
        return
    if not text:
        on_update("", True, None)
        return
    for idx in range(0, len(text), chunk_size):
        token = text[idx : idx + chunk_size]
        on_update(token, False, None)
        time.sleep(0.05)
    on_update(text, True, None)

