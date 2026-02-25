# gm_rl/adapters folder

## Responsibilities
- Adapter contracts and implementations for live/editor/mock data.
- Owns direct Python files: `__init__.py`, `base.py`, `editor_live.py`, `editor_state.py`, `local_mock.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Adapter contracts and implementations for live/editor/mock data.
This folder currently has 5 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- `nba2k_editor/gm_rl/env.py` uses these adapter contracts.
- Live adapter paths consume `nba2k_editor/models/data_model.py`.

## Function Tree
### `__init__.py`
- No callable definitions.

### `base.py`
  - [def] base.py::TeamState.roster_size
  - [def] base.py::RosterState.get_team
  - [def] base.py::RosterState.get_player
  - [def] base.py::EditorAdapter.load_roster_state
  - [def] base.py::EditorAdapter.load_league_context
  - [def] base.py::EditorAdapter.apply_gm_action
  - [def] base.py::EditorAdapter.get_salary_cap
  - [def] base.py::EditorAdapter.get_payroll
- [def] base.py::safe_ratio

### `editor_live.py`
- [def] editor_live.py::_resolve_editor_base_dir
  - [def] editor_live.py::EditorLiveAdapter.__init__
  - [def] editor_live.py::EditorLiveAdapter.load_roster_state
  - [def] editor_live.py::EditorLiveAdapter.load_league_context
  - [def] editor_live.py::EditorLiveAdapter.apply_gm_action
  - [def] editor_live.py::EditorLiveAdapter.get_salary_cap
  - [def] editor_live.py::EditorLiveAdapter.get_payroll
  - [def] editor_live.py::EditorLiveAdapter._make_prospect
  - [def] editor_live.py::EditorLiveAdapter._swap_players
  - [def] editor_live.py::EditorLiveAdapter._refresh_payrolls

### `editor_state.py`
- [def] editor_state.py::_default_context
- [def] editor_state.py::_synthetic_stats
- [def] editor_state.py::_synthetic_phys
- [def] editor_state.py::_clone_stats
- [def] editor_state.py::_clone_phys
- [def] editor_state.py::_norm_name
  - [def] editor_state.py::LiveRosterBuilder.__init__
  - [def] editor_state.py::LiveRosterBuilder.build
  - [def] editor_state.py::LiveRosterBuilder._fallback_state

### `local_mock.py`
- [def] local_mock.py::_resolve_editor_base_dir
  - [def] local_mock.py::LocalMockAdapter.__init__
  - [def] local_mock.py::LocalMockAdapter.load_roster_state
  - [def] local_mock.py::LocalMockAdapter.load_league_context
  - [def] local_mock.py::LocalMockAdapter.apply_gm_action
  - [def] local_mock.py::LocalMockAdapter.get_salary_cap
  - [def] local_mock.py::LocalMockAdapter.get_payroll
  - [def] local_mock.py::LocalMockAdapter._load_players
  - [def] local_mock.py::LocalMockAdapter._load_players_from_workbook
  - [def] local_mock.py::LocalMockAdapter._synthetic_players
  - [def] local_mock.py::LocalMockAdapter._build_teams
  - [def] local_mock.py::LocalMockAdapter._swap_players
  - [def] local_mock.py::LocalMockAdapter._prospect_stats
  - [def] local_mock.py::LocalMockAdapter._prospect_phys

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
