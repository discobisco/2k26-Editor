# ai folder

This folder contains the editor's AI integrations: settings storage, local tool
detection, NBA reference data loading, the AI Assistant UI, and the control
bridge for automation.

## Responsibilities
- Persist and load AI settings for local or remote backends.
- Detect common local AI executables (LM Studio, Ollama, etc).
- Load NBA reference data for prompt enrichment.
- Provide the Player AI Assistant panel.
- Expose a lightweight HTTP control bridge for automation.

## Settings and configuration
- Settings file: `ai_settings.json` (path from `core.config.AI_SETTINGS_PATH`).
- Default structure:
  - `mode`: `none`, `local`, or `remote`.
  - `remote`: `base_url`, `api_key`, `model`, `timeout` (seconds).
  - `local`: `command`, `arguments`, `working_dir`.
- Control bridge host/port can be overridden with:
  - `NBA2K26_AI_HOST` (default `127.0.0.1`)
  - `NBA2K26_AI_PORT` (default `18711`)

## Player AI Assistant
- UI panel embeds a request entry, Ask/Copy buttons, and a read-only response.
- Collects the selected player name and current detail fields from the UI.
- Optionally appends a real-world NBA summary from `nba_data` when found.
- Runs backend calls in a background thread to keep the UI responsive.

## AI backends
- Local mode:
  - Builds a command from settings and runs it with stdin/stdout pipes, or uses an in-process Python backend.
  - Python backend (set `local.backend` to `python`) supports `llama-cpp-python` (`llama_cpp`) and Hugging Face `transformers`.
- Helper utilities are available in `ai.backend_helpers` for loading model instances and performing synchronous or asynchronous generation (useful for UI-driven progress updates).
- Transformers streaming: when available, the helpers use `transformers.TextIteratorStreamer` for real streaming token-by-token; otherwise they fall back to chunked emission to simulate streaming.
  - Uses `shlex.split` for CLI arguments and supports a working directory for CLI mode.
  - Enforces a timeout and surfaces stderr on failure.
- Remote mode:
  - Sends OpenAI-compatible `chat/completions` requests to `remote.base_url`.
  - Uses `remote.model` and `remote.api_key` when provided.
  - Parses the first response choice and returns the text to the UI.

## Control bridge API (HTTP)
The bridge runs a `ThreadingHTTPServer` in a daemon thread and provides CORS
headers for browser-based tools.

- `GET /state`: Snapshot of the current UI state (selected player, fields,
  list sizes, active screen, and available actions).
- `GET /players`: Listbox entries with list index and filtered player index.
- `POST /command`: Execute an action.
  - Payload shape: `{"action": "command_name", "payload": {...}}`
  - Response shape: `{"success": true, "result": ...}` or
    `{"success": false, "error": ...}`

### Command surface (high level)
The dispatcher supports:
- Player selection and edits (`select_player`, `set_name_fields`,
  `set_detail_field`, `save_player`, `refresh_players`).
- Team edits (`select_team`, `set_team_field`, `set_team_fields`,
  `get_team_state`, `save_team`).
- Navigation (`show_screen`: `home`, `players`, `teams`, `staff`,
  `stadium`, `excel`).
- Tool invocation (`invoke_feature`, `open_full_editor`, `open_randomizer`,
  `open_team_shuffle`, `open_batch_edit`, etc).
- Full editor field APIs for player/staff/stadium editors.

## NBA data integration
- `nba_data` lazily loads `NBA Player Data\NBA DATA Master.xlsx`.
- Caches player bio and per-game stats in memory for fast reuse.
- Used by `PlayerAIAssistant` to add an NBA summary sentence to prompts.

## Files
- `__init__.py`: package marker.
- `settings.py`: load/save logic for `ai_settings.json`.
- `detection.py`: local AI executable discovery.
- `nba_data.py`: NBA workbook loader and cache.
- `assistant.py`: AI Assistant UI and control bridge.
- `README.md`: this document.

## Generated folder
- `__pycache__\`: Python bytecode cache (generated).
