# nba2k_editor folder

## Responsibilities
- Package root for runtime composition and module execution.
- Owns direct Python files: `__init__.py`, `__main__.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Package root for runtime composition and module execution.
This folder currently has 2 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Integrated within `nba2k_editor/` runtime graph.
- Consumed by neighboring package layers through imports and method calls.

## Function Tree
Scope: direct Python files in this folder only. Child folder details are documented in their own READMEs.

### `__init__.py`
- No callable definitions.

### `__main__.py`
- Defines `main()`.
- Delegates module execution to `launch_editor.main()`.

## Child Folder Map
- `core/`: `core/README.md`
- `entrypoints/`: `entrypoints/README.md`
- `importing/`: `importing/README.md`
- `logs/`: `logs/README.md`
- `memory/`: `memory/README.md`
- `models/`: `models/README.md`
- `Offsets/`: runtime offsets bundle.
- `tests/`: `tests/README.md`
- `ui/`: `ui/README.md`

## Call Graph Navigation
- Static call graph summary: `artifacts/call_graph/CALL_GRAPH.md`
- Machine-readable call graph: `artifacts/call_graph/call_graph.json`
- Node id format: `module::qualname` (example: `nba2k_editor.entrypoints.gui::main`)
- Edge kinds:
- `call`: direct static call expression resolution.
- `callback_ref`: function references passed as callback-style arguments/keywords.

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Run pytest from the parent repo root (`C:\Users\roaum\.openclaw\workspace\gpt trial run`) so imports like `nba2k_editor.*` resolve correctly, or set `PYTHONPATH` to that parent directory before invoking pytest from inside `nba2k_editor\`.
- Use targeted pytest runs around impacted modules after edits.
