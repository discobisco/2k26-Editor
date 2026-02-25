"""HTTP AI backend helpers."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def call_chat_completions(
    *,
    base_url: str,
    model: str,
    prompt: str,
    api_key: str = "",
    timeout: int = 30,
    persona: str | None = None,
) -> str:
    base = str(base_url or "").strip()
    if not base:
        raise RuntimeError("Remote API base URL is not configured.")
    url = base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    system_intro = "You are a helpful basketball analyst assisting with NBA 2K roster edits."
    system_content = (str(persona).strip() + "\n\n" if persona else "") + system_intro
    payload = {
        "model": str(model or "lmstudio"),
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    headers = {"Content-Type": "application/json"}
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=int(timeout)) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Remote API error: {exc.reason}") from exc
    parsed = json.loads(raw)
    choices = parsed.get("choices")
    if not choices:
        raise RuntimeError("Remote API returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content")
    if not content:
        raise RuntimeError("Remote API choice did not include content.")
    return str(content).strip()

