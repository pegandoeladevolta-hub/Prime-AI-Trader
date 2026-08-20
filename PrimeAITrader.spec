# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets" / "icon.ico"), "assets")],
    hiddenimports=["sklearn.utils._cython_blas", "sklearn.neighbors._typedefs", "sklearn.neighbors._quad_tree"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["matplotlib"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="PrimeAITrader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "icon.ico"),
    version=str(root / "version_info.txt"),
)

