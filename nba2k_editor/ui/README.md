# ui folder

## Responsibilities
- Owns the Dear PyGui application shell, screen builders, dialogs, and local UI orchestration for the NBA2K editor.
- Presents editor workflows over the model/runtime layers without owning the underlying data model.

## Current shell and navigation surface
- `app.py` defines `PlayerEditorApp`, grouped UI state bags, the screen registry, and screen-specific post-show hooks.
- `app_shell.py` owns the shell frame/sidebar and declares the live nav surface in `_NAV_ITEMS`.
- `ui.controllers.navigation.show_screen_key(app, key)` is the navigation entrypoint used by the shell.
- `PlayerEditorApp._screen_registry` in `app.py` maps lazy-built screen keys to builders and optional post-show hooks.
- `ui.controllers.screen_registry` handles lazy construction and post-show callback dispatch.

Navigation flow:
1. `app_shell.build_sidebar()` wires sidebar buttons from `_NAV_ITEMS`.
2. Button callbacks call `ui.controllers.navigation.show_screen_key(app, key)`.
3. Non-home registered screens are lazy-built through `PlayerEditorApp._screen_registry`.
4. After a screen becomes visible, any registered post-show hook runs (for example roster-load gating, trade refresh, league refresh, or staff/stadium list refresh).

## Load strategy
- `app_shell.build_ui()` builds the shell and Home immediately.
- Home is the only eagerly built screen.
- `players`, `teams`, `nba_history`, `nba_records`, `staff`, `stadium`, `excel`, and `trade` are built on first navigation.
- `players` and `teams` intentionally share roster-load gating so a loaded roster is reused instead of forcing repeated full scans.
- Trade refresh happens when the Trade screen is opened rather than during startup.

## Direct Python modules in this folder
This folder currently has 28 direct Python modules:
- `__init__.py`
- `app.py`
- `app_launchers.py`
- `app_shell.py`
- `base_entity_editor.py`
- `batch_edit.py`
- `bound_vars.py`
- `context_menu.py`
- `dialogs.py`
- `entity_list_screen.py`
- `excel_screen.py`
- `extensions_ui.py`
- `full_editor_launch.py`
- `full_player_editor.py`
- `full_staff_editor.py`
- `full_stadium_editor.py`
- `full_team_editor.py`
- `home_screen.py`
- `league_screen.py`
- `players_screen.py`
- `randomizer.py`
- `shell_utils.py`
- `stadium_screen.py`
- `staff_screen.py`
- `team_shuffle.py`
- `teams_screen.py`
- `theme.py`
- `trade_players.py`

## Child folders
- `controllers/`: shared screen/navigation/controller helpers.
- `state/`: lightweight UI-local state helpers.

## Integration points
- Consumes model and import/export layers.
- Instantiated by the GUI entrypoint as the top-level application shell.

## Validation notes
- Coverage for this folder lives in `nba2k_editor/tests`.
- Useful focused checks after UI edits include startup/load-order, screen-loading, trade-state, and full-editor launch regressions.
