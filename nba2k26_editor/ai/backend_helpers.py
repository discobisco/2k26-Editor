"""Helper functions for in-process Python backends.

Provides synchronous and async generation helpers and a light cache for model
instances. Designed to be importable from `assistant.py` and used by the UI.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

_PYTHON_BACKEND_INSTANCES: dict[str, Any] = {}


def _get_instance_key(backend: str, model_path: str) -> str:
    return f"{backend}::{model_path}"


def load_python_instance(backend: str, model_path: str, **kwargs: Any) -> Any:
    """Load or return a cached python backend instance.

    Supported backends:
    - "llama_cpp": returns a `Llama` instance from `llama_cpp`.
    - "transformers": returns a `pipeline("text-generation")` instance.

    Raises RuntimeError when dependencies are missing or configuration is invalid.
    """
    backend = str(backend or "").strip().lower()
    key = _get_instance_key(backend, model_path or "")
    inst = _PYTHON_BACKEND_INSTANCES.get(key)
    if inst is not None:
        return inst

    if backend == "llama_cpp":
        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency error path
            raise RuntimeError("Install 'llama-cpp-python' to use the llama_cpp backend.") from exc
        if not model_path:
            raise RuntimeError("Provide 'model_path' for llama_cpp backend.")
        inst = Llama(model_path=model_path)
        _PYTHON_BACKEND_INSTANCES[key] = inst
        return inst

    if backend == "transformers":
        try:
            from transformers import pipeline  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency error path
            raise RuntimeError("Install 'transformers' to use the transformers backend.") from exc
        if not model_path:
            raise RuntimeError("Provide 'model_path' for transformers backend.")
        inst = pipeline("text-generation", model=model_path, device_map="auto")
        _PYTHON_BACKEND_INSTANCES[key] = inst
        return inst

    raise RuntimeError(f"Unsupported python backend: {backend}")


def generate_text_sync(backend: str, instance: Any, prompt: str, max_tokens: int = 256, temperature: float = 0.4) -> str:
    """Run a synchronous generation on a loaded instance and return text.

    This function understands the shapes returned by `llama_cpp` and
    `transformers` pipeline and extracts the generated text.
    """
    if backend == "llama_cpp":
        # llama_cpp returns dict with 'choices' -> [{'text': ...}] or similar
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


def generate_text_async(
    backend: str,
    model_path: str,
    prompt: str,
    max_tokens: int = 256,
    temperature: float = 0.4,
    on_update: Callable[[str, bool, Exception | None], None] | None = None,
) -> threading.Thread:
    """Run generation in a background thread and report via `on_update`.

    The callback signature is (text_so_far: str, done: bool, error: Exception | None).
    For now we call the callback once when complete or on error. Returns the
    Thread object so callers can join or track it.
    """

    def _worker() -> None:
        try:
            inst = load_python_instance(backend, model_path)
        except Exception as exc:  # noqa: BLE001
            if on_update:
                try:
                    on_update("", False, exc)
                except Exception:
                    pass
            return

        # Try to stream token-by-token for llama_cpp if supported
        try:
            if backend == "llama_cpp":
                buffer_parts: list[str] = []

                def _cb(token: str) -> None:
                    try:
                        if token:
                            buffer_parts.append(token)
                            # report the latest token as a partial update
                            if on_update:
                                on_update(token, False, None)
                    except Exception:
                        pass

                try:
                    # prefer streaming API if available
                    inst.create(prompt=prompt, max_tokens=max_tokens, temperature=temperature, stream=True, callback=_cb)  # type: ignore
                except TypeError:
                    # fallback: call non-streaming and send final text
                    full = generate_text_sync(backend, inst, prompt, max_tokens=max_tokens, temperature=temperature)
                    if on_update:
                        on_update(full, True, None)
                    return
                # After stream completes, send final combined text
                final = "".join(buffer_parts)
                if on_update:
                    on_update(final, True, None)
                return

            # For transformers, attempt true streaming via TextIteratorStreamer when available
            if backend == "transformers":
                try:
                    from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer  # type: ignore
                except Exception:
                    # Fall back to chunked emission if streamer isn't available
                    inst = inst  # type: ignore
                    full = generate_text_sync(backend, inst, prompt, max_tokens=max_tokens, temperature=temperature)
                    if not full:
                        if on_update:
                            on_update("", True, None)
                        return
                    chunk_size = 40
                    emitted = ""
                    for i in range(0, len(full), chunk_size):
                        chunk = full[i : i + chunk_size]
                        emitted += chunk
                        if on_update:
                            on_update(chunk, False, None)
                        time.sleep(0.05)
                    if on_update:
                        on_update(full, True, None)
                    return

                # Try to stream tokens using TextIteratorStreamer
                try:
                    tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
                    model = AutoModelForCausalLM.from_pretrained(model_path, device_map="auto")
                    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, decode_kwargs={"skip_special_tokens": True})
                    # Kick off generation in a separate thread so we can iterate streamer here
                    def _gen():
                        inputs = tokenizer(prompt, return_tensors="pt")
                        inputs = {k: v.to(model.device) for k, v in inputs.items()}
                        model.generate(**inputs, max_new_tokens=max_tokens, do_sample=True, temperature=temperature, streamer=streamer)
                    gen_thread = threading.Thread(target=_gen, daemon=True)
                    gen_thread.start()

                    buffer_parts: list[str] = []
                    for token in streamer:
                        try:
                            buffer_parts.append(token)
                            if on_update:
                                on_update(token, False, None)
                        except Exception:
                            pass
                    final = "".join(buffer_parts)
                    if on_update:
                        on_update(final, True, None)
                    return
                except Exception:
                    # On any failure, fall back to chunked emission of the final result
                    inst = inst  # type: ignore
                    full = generate_text_sync(backend, inst, prompt, max_tokens=max_tokens, temperature=temperature)
                    if not full:
                        if on_update:
                            on_update("", True, None)
                        return
                    chunk_size = 40
                    for i in range(0, len(full), chunk_size):
                        chunk = full[i : i + chunk_size]
                        if on_update:
                            on_update(chunk, False, None)
                        time.sleep(0.05)
                    if on_update:
                        on_update(full, True, None)
                    return

            # Other/unknown backends: run synchronously and send final text
            full = generate_text_sync(backend, inst, prompt, max_tokens=max_tokens, temperature=temperature)
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
