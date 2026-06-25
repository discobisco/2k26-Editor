# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the NBA2K Editor GUI.

Keep this file explicit and current.  The Player Generator folder is a legacy
runtime package with a space in the directory name, so its modules are collected
by filename instead of relying on PyInstaller package discovery.
"""
from __future__ import annotations

from pathlib import Path


project_root = Path(SPECPATH).resolve()
package_root = project_root / "nba2k_editor"
player_generator_dir = package_root / "Player Generator"
core_offsets_dir = package_root / "core" / "Offsets"
player_data_dir = player_generator_dir / "NBA Player Data"
player_pool_dir = player_data_dir / "player_generation_pool"


def _existing_data(source: Path, target: str) -> tuple[str, str] | None:
    return (str(source), target) if source.exists() else None


def _existing_file(source: Path, target_dir: str) -> tuple[str, str] | None:
    return (str(source), target_dir) if source.is_file() else None


def _player_generator_modules() -> list[str]:
    if not player_generator_dir.exists():
        return []
    stems = sorted(
        path.stem
        for path in player_generator_dir.glob("*.py")
        if path.stem != "__init__"
    )
    # Both forms are needed:
    # - dpg_editor imports nba2k_editor.Player Generator.display dynamically.
    # - display.py then puts the folder on sys.path and imports contracts/etc.
    return [*(f"nba2k_editor.Player Generator.{stem}" for stem in stems), *stems]


datas: list[tuple[str, str]] = []
for item in (
    _existing_data(core_offsets_dir, "nba2k_editor\\core\\Offsets"),
    _existing_data(player_pool_dir, "nba2k_editor\\Player Generator\\NBA Player Data\\player_generation_pool"),
    _existing_file(player_data_dir / "NBA_DATA_Master.sqlite", "nba2k_editor\\Player Generator\\NBA Player Data"),
    _existing_file(player_data_dir / "nba.sqlite", "nba2k_editor\\Player Generator\\NBA Player Data"),
    _existing_file(player_data_dir / "NBA_DATA_MASTER_MAP.md", "nba2k_editor\\Player Generator\\NBA Player Data"),
    _existing_file(player_data_dir / "README.md", "nba2k_editor\\Player Generator\\NBA Player Data"),
    _existing_file(player_data_dir / "Team Logos.txt", "nba2k_editor\\Player Generator\\NBA Player Data"),
    _existing_file(player_data_dir / "Player Portraits.txt", "nba2k_editor\\Player Generator\\NBA Player Data"),
    _existing_file(package_root / "franchise_manager.sqlite", "nba2k_editor"),
):
    if item is not None:
        datas.append(item)


hiddenimports = [
    "dearpygui.dearpygui",
    "nba2k_editor.entrypoints.gui",
    "nba2k_editor.entrypoints.runtime_cleanup",
    "nba2k_editor.models.data_model",
    "nba2k_editor.ui.dpg_editor",
    "nba2k_editor.ui.theme",
    *_player_generator_modules(),
]


excludes = [
    # Old/optional editor integrations not used by the GUI bundle.
    "nba2k_editor.dual_base_mirror",
    "nba2k_editor.offsets2_loader",
    # Optional heavy AI/RL/data stacks; keep the GUI app small and fast to build.
    "accelerate",
    "gymnasium",
    "huggingface_hub",
    "lxml",
    "matplotlib",
    "onnxruntime",
    "PIL",
    "pygame",
    "safetensors",
    "scipy",
    "sklearn",
    "tensorflow",
    "tokenizers",
    "torch",
    "torchvision",
    "transformers",
]


a = Analysis(
    ["launch_editor.py"],
    pathex=[str(project_root), str(player_generator_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DB2kEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
