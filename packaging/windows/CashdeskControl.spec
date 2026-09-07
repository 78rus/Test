# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for Windows."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]

hiddenimports = [
    "asyncssh",
    "qasync",
    "pyte",
    # the database client imports these inside methods, so the static
    # analysis does not always see them
    "sqlalchemy",
    "psycopg",
    # cryptography moved TripleDES; vnc.py falls back between the two paths
    "cryptography.hazmat.decrepit.ciphers.algorithms",
    "cryptography.hazmat.primitives.ciphers.algorithms",
    *collect_submodules("keyring.backends"),
    *collect_submodules("psycopg"),
]

a = Analysis(
    [str(ROOT / "packaging" / "windows" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CashdeskControl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CashdeskControl",
)
