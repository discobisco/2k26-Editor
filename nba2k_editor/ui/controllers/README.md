# ui/controllers folder

## Current runtime surface
Shared controller helpers used by the Dear PyGui shell.

Direct Python modules currently present:
- `__init__.py`
- `entity_edit.py`
- `import_export.py`
- `league.py`
- `navigation.py`
- `players.py`
- `screen_registry.py`
- `teams.py`
- `trade.py`

## What these modules cover
- `entity_edit.py`: small shared coercion helpers for editor field writes.
- `import_export.py`: shared import/export label and entity-key normalization helpers.
- `league.py`: league-history / records page state, category filtering, widget registration, and refresh helpers.
- `navigation.py`: screen-switch helpers.
- `players.py`: player scan, selection, filtering, and player-editor launch helpers.
- `screen_registry.py`: lazy screen registration / post-show helpers.
- `staff.py`: staff list refresh/filter/selection and staff-editor launch helpers.
- `stadium.py`: stadium list refresh/filter/selection and stadium-editor launch helpers.
- `teams.py`: team list, selection, filtering, and team-editor launch helpers.
- `trade.py`: trade summary formatting and related lightweight helpers.

## Notes
- This README is intentionally inventory-first. The prior exhaustive function tree had drifted and no longer matched the surviving controller set.
- Coverage for these helpers lives in `nba2k_editor/tests`, especially the startup/load-order, screen-loading, trade-state, and full-editor launch regression suites.
