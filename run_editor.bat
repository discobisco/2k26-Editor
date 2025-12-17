@echo off
setlocal

rem Launch the NBA 2K26 editor from a double-clickable script.
rem Tries a local .venv first, then falls back to system Python.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PY_EXE="
if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" set "PY_EXE=%SCRIPT_DIR%\.venv\Scripts\python.exe"
if not defined PY_EXE if exist "%SCRIPT_DIR%\.venv\Scripts\pythonw.exe" set "PY_EXE=%SCRIPT_DIR%\.venv\Scripts\pythonw.exe"
if not defined PY_EXE set "PY_EXE=python"

echo Starting editor with %PY_EXE% ...
"%PY_EXE%" -m nba2k26_editor.entrypoints.gui
if errorlevel 1 (
    echo.
    echo Launch failed. Ensure Python and dependencies are installed, then try again.
    pause
)
