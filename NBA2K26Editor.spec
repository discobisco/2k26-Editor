# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launch_editor.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('nba2k26_editor\\Offsets', 'nba2k26_editor\\Offsets'),
        ('nba2k26_editor\\NBA Player Data', 'nba2k26_editor\\NBA Player Data'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='NBA2K26Editor',
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
