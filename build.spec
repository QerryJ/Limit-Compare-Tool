# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec -- single-file offline exe.

The design tokens must be bundled: ``src/ui/theme.py`` reads them at runtime and
they are the single source of truth for colours and density.

Build:  pyinstaller build.spec --noconfirm
Output: dist/LimitCompare.exe
"""

import os

from PyInstaller.utils.hooks import collect_submodules

HERE = SPECPATH  # directory of this spec file; cwd-independent build
hiddenimports = collect_submodules("src")

a = Analysis(
    [os.path.join(HERE, "main.py")],
    pathex=[HERE],
    binaries=[],
    datas=[(os.path.join(HERE, "docs/design-system/tokens.css"), "docs/design-system")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "pytest", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LimitCompare",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(HERE, "assets", "app.ico"),   # 字母 C（src/ui/icon.py 生成）
)
