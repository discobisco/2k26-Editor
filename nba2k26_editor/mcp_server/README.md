# MyEras MCP Server

FastAPI-based REST + MCP-compatible service for NBA 2K MyEras simulation.

## Run

```bash
python -m nba2k_editor.entrypoints.mcp_server
```

Environment variables:

- `MYERAS_MCP_HOST` (default: `127.0.0.1`)
- `MYERAS_MCP_PORT` (default: `8787`)
- `MYERAS_MCP_LOG_LEVEL` (default: `INFO`)
- `MYERAS_MCP_RATE_LIMIT_PER_MINUTE` (default: `120`)
- `MYERAS_MCP_ENABLE_LIVE_WRITES` (default: `false`)
- `MYERAS_MCP_MODULE_NAME` (default: `nba2k26.exe`)
- `MYERAS_MCP_OFFSETS_PATH` (default: `nba2k_editor/Offsets`)
- `MYERAS_MCP_DEFAULT_SEED` (default: `42`)
- `MYERAS_MCP_ENABLE_CPU_AI_PERSONALITY_V1` (default: `true`)
- `MYERAS_MCP_AI_CACHE_TTL_SECONDS` (default: `45`)
- `MYERAS_MCP_AI_CACHE_MAX_ENTRIES` (default: `4096`)

## REST Endpoints

- `GET /v1/health`
- `GET /v1/capabilities`
- `POST /v1/franchise/optimize`
- `POST /v1/trade/evaluate`
- `POST /v1/draft/generate`
- `POST /v1/draft/simulate-lottery`
- `POST /v1/progression/simulate`
- `POST /v1/season/simulate`
- `POST /v1/dynasty/track`
- `POST /v1/era/transition`
- `POST /v1/chemistry/calculate`
- `POST /v1/personality/update`
- `POST /v1/conflict/simulate`
- `POST /v1/morale/evaluate`
- `GET /v1/locker-room/status/{team_id}`
- `POST /v1/ai/trade-decision`
- `POST /v1/ai/draft-decision`
- `POST /v1/ai/free-agency-decision`
- `POST /v1/ai/franchise-direction`
- `GET /v1/ai/profile/{team_id}`

MCP helper endpoints:

- `GET /v1/mcp/tools`
- `POST /v1/mcp/invoke`

AI MCP tools:

- `ai_trade_decision`
- `ai_draft_decision`
- `ai_free_agency_decision`
- `ai_franchise_direction`
- `ai_profile_lookup`
- `locker_room_chemistry_calculate`
- `locker_room_personality_update`
- `locker_room_conflict_simulate`
- `locker_room_morale_evaluate`
- `locker_room_status_lookup`

## Live Write Safety

- Live writes are opt-in per request via `apply_live_changes: true`.
- Operations are validated with hard bounds and allowed-value locks.
- Out-of-range writes fail with `422`.
- No silent clamping is performed.

## CPU AI Personality Notes

- AI requests are stateless; no server-owned franchise timeline is persisted.
- Long-term behavior drift is request-driven: responses include `nextProfileRecommendation`, and callers must pass updated profile state back on future calls.
- Deterministic seeding is supported via per-request `seed`.
- Concurrency and performance: pure-compute LRU+TTL caching is used for deterministic artifacts only.

## Platform Notes

- Container mode (`Dockerfile.mcp`) is intended for simulation and analytics.
- Direct live memory writes require a Windows host with the NBA 2K process available.
