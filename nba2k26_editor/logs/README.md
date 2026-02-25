# logs folder

## Responsibilities
- Runtime logging helpers plus generated log artifacts.
- Owns direct Python files: `logging.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
Runtime logging helpers plus generated log artifacts.
This folder currently has 1 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Integrated within `nba2k_editor/logs` runtime graph.
- Consumed by neighboring package layers through imports and method calls.

## Function Tree
### `logging.py`
- [def] logging.py::_null_logger
- [def] logging.py::_truthy_env
- [def] logging.py::_int_env
- [def] logging.py::_parse_list_env
- [def] logging.py::_infer_scan_context
- [def] logging.py::_parse_tag_overrides
- [def] logging.py::_infer_tag_context
- [def] logging.py::_infer_caller
- [def] logging.py::_infer_stack
- [def] logging.py::_thread_context
  - [def] logging.py::_ScanContextFilter.filter
- [def] logging.py::_attach_scan_filter
- [def] logging.py::_effective_log_dir
- [def] logging.py::_file_logger
- [def] logging.py::format_event
- [def] logging.py::_load_logger_from_path
- [def] logging.py::_load_dev_logger
- [def] logging.py::get_memory_logger
- [def] logging.py::get_ai_logger
- [def] logging.py::log_ai_event
- [def] logging.py::_install_ai_trace
  - [def] logging.py::_install_ai_trace._profile

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
