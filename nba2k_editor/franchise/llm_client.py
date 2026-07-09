from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


_HERMES_DEFAULT_BASE_URL = "http://127.0.0.1:8642/v1"
_HERMES_DEFAULT_MODEL = "hermes-agent"
_OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class LLMClientConfig:
    base_url: str
    api_key: str
    model: str
    backend: str = "auto"


def _env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip().strip('"').strip("'")
    return ""


def _dotenv_value(path: Path, *names: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    wanted = set(names)
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, value = text.split("=", 1)
        if name.strip() in wanted:
            return value.strip().strip('"').strip("'")
    return ""


def _hermes_env_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    explicit = _env_value("FRANCHISE_HERMES_ENV_PATH", "HERMES_ENV_PATH")
    if explicit:
        paths.append(Path(explicit))
    paths.append(Path.home() / ".hermes" / ".env")
    for user in {_env_value("HERMES_WSL_USER"), _env_value("USERNAME"), _env_value("USER"), _env_value("LOGNAME"), "roaumc"}:
        if not user:
            continue
        for distro in ("Ubuntu", "docker-desktop"):
            paths.append(Path(f"\\\\wsl.localhost\\{distro}\\home\\{user}\\.hermes\\.env"))
            paths.append(Path(f"\\\\wsl$\\{distro}\\home\\{user}\\.hermes\\.env"))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return tuple(unique)


def _hermes_api_key() -> str:
    direct = _env_value("FRANCHISE_HERMES_API_KEY", "HERMES_API_KEY", "API_SERVER_KEY")
    if direct:
        return direct
    for path in _hermes_env_paths():
        value = _dotenv_value(path, "API_SERVER_KEY")
        if value:
            return value
    return ""


class LLMClient:
    def __init__(self, config: LLMClientConfig | None = None) -> None:
        self.config = config or LLMClientConfig(
            base_url=_env_value("FRANCHISE_HERMES_BASE_URL", "HERMES_API_BASE_URL") or _HERMES_DEFAULT_BASE_URL,
            api_key=_hermes_api_key(),
            model=_env_value("FRANCHISE_HERMES_MODEL", "HERMES_API_MODEL") or _HERMES_DEFAULT_MODEL,
            backend=_env_value("FRANCHISE_LLM_BACKEND") or "auto",
        )

    def _openai_config(self) -> LLMClientConfig:
        return LLMClientConfig(
            base_url=_env_value("FRANCHISE_LLM_BASE_URL", "OPENAI_BASE_URL") or _OPENAI_DEFAULT_BASE_URL,
            api_key=_env_value("FRANCHISE_LLM_API_KEY", "OPENAI_API_KEY"),
            model=_env_value("FRANCHISE_LLM_MODEL", "OPENAI_MODEL") or "gpt-4o-mini",
            backend="openai",
        )

    def _hermes_api_available(self) -> bool:
        if not self.config.api_key.strip():
            return False
        try:
            request = urllib.request.Request(self.config.base_url.rstrip("/").removesuffix("/v1") + "/health", method="GET")
            with urllib.request.urlopen(request, timeout=2) as response:
                return 200 <= int(response.status) < 300
        except Exception:
            return False

    def _openai_available(self) -> bool:
        return bool(self._openai_config().api_key.strip())

    def _hermes_command(self) -> list[str] | None:
        forced = os.environ.get("FRANCHISE_HERMES_COMMAND")
        if forced:
            return forced.split()
        if shutil.which("hermes"):
            return ["hermes"]
        if os.name == "nt" and shutil.which("wsl.exe"):
            check = subprocess.run(
                ["wsl.exe", "-e", "bash", "-lc", "command -v hermes"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if check.returncode == 0 and check.stdout.strip():
                return ["wsl.exe", "-e", "bash", "-lc"]
        return None

    def _hermes_cli_available(self) -> bool:
        return self._hermes_command() is not None

    def available(self) -> bool:
        backend = self.config.backend.strip().casefold()
        if backend in {"hermes_api", "api", "hermes-server", "hermes_server"}:
            return self._hermes_api_available()
        if backend == "openai":
            return self._openai_available()
        if backend == "hermes":
            return self._hermes_cli_available()
        return self._hermes_api_available() or self._openai_available() or self._hermes_cli_available()

    def generate(self, prompt: str) -> str:
        backend = self.config.backend.strip().casefold()
        if backend in {"hermes_api", "api", "hermes-server", "hermes_server"}:
            return self._generate_with_hermes_api(prompt)
        if backend == "openai":
            return self._generate_with_openai(prompt)
        if backend == "hermes":
            return self._generate_with_hermes_cli(prompt)
        if self._hermes_api_available():
            return self._generate_with_hermes_api(prompt)
        if self._openai_available():
            return self._generate_with_openai(prompt)
        return self._generate_with_hermes_cli(prompt)

    def _messages(self, prompt: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": "Return only valid JSON for the requested NBA2K fantasy draft decision."},
            {"role": "user", "content": prompt},
        ]

    def _generate_with_hermes_api(self, prompt: str) -> str:
        if not self.config.api_key.strip():
            raise RuntimeError("Hermes API Server key unavailable. Set API_SERVER_KEY, FRANCHISE_HERMES_API_KEY, or FRANCHISE_HERMES_ENV_PATH.")
        return self._post_chat_completions(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            model=self.config.model,
            messages=self._messages(prompt),
            timeout=180,
            label="Hermes API Server",
        )

    def _generate_with_hermes_cli(self, prompt: str) -> str:
        command = self._hermes_command()
        if command is None:
            raise RuntimeError("Hermes is unavailable. Start Hermes API Server on 127.0.0.1:8642 or set FRANCHISE_HERMES_API_KEY/API_SERVER_KEY.")
        full_prompt = (
            "Return only valid JSON for the requested NBA2K fantasy draft decision. "
            "Do not use tools. Do not include markdown.\n\n"
            + prompt
        )
        if command[:4] == ["wsl.exe", "-e", "bash", "-lc"]:
            env = dict(os.environ)
            env["FRANCHISE_PROMPT"] = full_prompt
            run = subprocess.run(
                [*command, "hermes chat -Q -t safe -q \"$FRANCHISE_PROMPT\""],
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
            )
        else:
            run = subprocess.run(
                [*command, "chat", "-Q", "-t", "safe", "-q", full_prompt],
                capture_output=True,
                text=True,
                timeout=180,
            )
        if run.returncode != 0:
            raise RuntimeError((run.stderr or run.stdout or "Hermes CLI failed").strip())
        return run.stdout.strip()

    def _generate_with_openai(self, prompt: str) -> str:
        config = self._openai_config()
        if not config.api_key.strip():
            raise RuntimeError("LLM unavailable: Hermes API Server is unavailable and no FRANCHISE_LLM_API_KEY or OPENAI_API_KEY is set")
        return self._post_chat_completions(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            messages=self._messages(prompt),
            timeout=90,
            label="OpenAI-compatible provider",
        )

    def _post_chat_completions(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        timeout: int,
        label: str,
    ) -> str:
        url = base_url.rstrip("/") + "/chat/completions"
        body = json.dumps({"model": model, "messages": messages, "temperature": 0.2}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")[:500]
            raise RuntimeError(f"{label} request failed with HTTP {exc.code}: {details}") from exc
        return str(payload["choices"][0]["message"]["content"])
