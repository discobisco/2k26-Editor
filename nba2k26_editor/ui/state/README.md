# ui/state folder

## Responsibilities
- Typed UI state containers for complex flows.
- Owns direct Python files: `__init__.py`, `trade_state.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Typed UI state containers for complex flows.
This folder currently has 2 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Integrated within `nba2k_editor/ui/state` runtime graph.
- Consumed by neighboring package layers through imports and method calls.

## Function Tree
### `__init__.py`
- No callable definitions.

### `trade_state.py`
  - [def] trade_state.py::TradeSlot.clear
  - [def] trade_state.py::TradeSlot.packages
  - [def] trade_state.py::TradeState.__post_init__
  - [def] trade_state.py::TradeState.current_slot
  - [def] trade_state.py::TradeState.select_slot
  - [def] trade_state.py::TradeState.clear_slot
  - [def] trade_state.py::TradeState.add_transaction
  - [def] trade_state.py::TradeState.remove_transaction

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
