# models/services folder

## Responsibilities
- Service and codec modularization around model operations.
- Owns direct Python files: `__init__.py`, `base_entity_service.py`, `io_codec.py`, `player_service.py`, `stadium_service.py`, `staff_service.py`, `team_service.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Service and codec modularization around model operations.
This folder currently has 7 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Integrated within `nba2k_editor/models/services` runtime graph.
- Consumed by neighboring package layers through imports and method calls.

## Function Tree
### `__init__.py`
- No callable definitions.

### `base_entity_service.py`
  - [def] base_entity_service.py::EntityServiceBase.__init__
  - [def] base_entity_service.py::EntityServiceBase._mark_dirty

### `io_codec.py`
  - [def] io_codec.py::IOCodec.__init__
  - [def] io_codec.py::IOCodec.get_player
  - [def] io_codec.py::IOCodec.set_player
  - [def] io_codec.py::IOCodec.get_team
  - [def] io_codec.py::IOCodec.set_team
  - [def] io_codec.py::IOCodec.get_staff
  - [def] io_codec.py::IOCodec.set_staff
  - [def] io_codec.py::IOCodec.get_stadium
  - [def] io_codec.py::IOCodec.set_stadium

### `player_service.py`
  - [def] player_service.py::PlayerService.__init__
  - [def] player_service.py::PlayerService.refresh
  - [def] player_service.py::PlayerService.get_field
  - [def] player_service.py::PlayerService.set_field

### `stadium_service.py`
  - [def] stadium_service.py::StadiumService.__init__
  - [def] stadium_service.py::StadiumService.refresh
  - [def] stadium_service.py::StadiumService.get_field
  - [def] stadium_service.py::StadiumService.set_field

### `staff_service.py`
  - [def] staff_service.py::StaffService.__init__
  - [def] staff_service.py::StaffService.refresh
  - [def] staff_service.py::StaffService.get_field
  - [def] staff_service.py::StaffService.set_field

### `team_service.py`
  - [def] team_service.py::TeamService.__init__
  - [def] team_service.py::TeamService.refresh
  - [def] team_service.py::TeamService.get_fields
  - [def] team_service.py::TeamService.set_fields
  - [def] team_service.py::TeamService.get_field
  - [def] team_service.py::TeamService.set_field

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
