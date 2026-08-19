# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['tektronix_scope_gui_v7_tabs.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pyvisa', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'tektronix_utils'],
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
    name='TektronixScopeGUI',
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
