# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path(".").resolve()


def _add_data_dir(files: list[tuple[str, str]], source: Path, target: str) -> None:
    """Append a data directory only when it exists in the workspace."""
    if source.exists():
        files.append((str(source), target))


data_files: list[tuple[str, str]] = []
_add_data_dir(data_files, project_root / "nba2k_editor" / "Offsets", "nba2k_editor\\Offsets")
_add_data_dir(data_files, project_root / "nba2k_editor" / "mcp_server" / "data", "nba2k_editor\\mcp_server\\data")

a = Analysis(
    ['launch_editor.py'],
    pathex=[str(project_root), str(project_root / ".venv" / "Lib" / "site-packages")],
    binaries=[],
    datas=data_files,
    hiddenimports=[
        "dearpygui.dearpygui",
        "nba2k_editor.entrypoints.gui",
        "nba2k_editor.entrypoints.full_editor",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "nba2k_editor.dual_base_mirror",
        "nba2k_editor.offsets2_loader",
        # Optional heavy AI/RL stacks are runtime-optional in the app; exclude
        # from the default GUI bundle to keep build time and size reasonable.
        "torch",
        "transformers",
        "gymnasium",
        "accelerate",
        "huggingface_hub",
        "tokenizers",
        "safetensors",
        "torchvision",
        "tensorflow",
        "onnxruntime",
        "matplotlib",
        "scipy",
        "sklearn",
        "PIL",
        "pygame",
        "lxml",
    ],
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
    name='DB2kEditor',
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
