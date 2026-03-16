@echo off
setlocal

rem Launch the NBA 2K26 editor from a double-clickable script.
rem Requires the repo-local .venv so startup stays on the validated interpreter path.
rem Funnels through launch_editor.py, which owns the relaunch/bootstrap guardrails.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PY_EXE="
if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" set "PY_EXE=%SCRIPT_DIR%\.venv\Scripts\python.exe"
if not defined PY_EXE if exist "%SCRIPT_DIR%\.venv\Scripts\pythonw.exe" set "PY_EXE=%SCRIPT_DIR%\.venv\Scripts\pythonw.exe"

if not defined PY_EXE (
    echo Launch failed: repo-local .venv was not found.
    echo Create or restore .venv and install dependencies, then try again.
    pause
    exit /b 1
)

echo Starting editor with %PY_EXE% via launch_editor.py ...
"%PY_EXE%" "%SCRIPT_DIR%launch_editor.py"
if errorlevel 1 (
    echo.
    echo Launch failed. Ensure the repo-local .venv dependencies are installed, then try again.
    pause
)
