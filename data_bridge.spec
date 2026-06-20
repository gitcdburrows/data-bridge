# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Bloomberg Data Bridge app.

Build a single self-contained executable so end users never need a Python
environment. Run this on the *target* OS (a Bloomberg workstation, i.e.
Windows) so that ``blpapi`` is installed and gets bundled:

    pyinstaller --clean --noconfirm data_bridge.spec

Output: dist/BloombergBridge(.exe)

Several dependencies are imported lazily (blpapi, pystray's platform backend,
uvicorn's protocol/loop plugins), so PyInstaller's static analysis can miss
them — they're listed explicitly below.
"""

import os
import sys

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Embed the branded icon into the .exe (Windows wants a .ico). Guarded so a
# missing asset or a non-Windows smoke build doesn't fail.
_ico = os.path.join("assets", "icon.ico")
icon_file = _ico if (os.path.exists(_ico) and sys.platform == "win32") else None

# Bundle blpapi's native library when it's installed on the build machine.
# blpapi is imported lazily, so PyInstaller won't discover its binaries alone.
binaries = []
datas = []
try:
    binaries += collect_dynamic_libs("blpapi")
    datas += collect_data_files("blpapi")
except Exception:
    pass  # blpapi not installed here — build the app without it

hiddenimports = []
for _pkg in ("uvicorn", "pystray", "pydantic", "pydantic_settings", "app"):
    hiddenimports += collect_submodules(_pkg)
hiddenimports += [
    "blpapi",
    "websockets",
    "websockets.legacy",
    "httptools",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "anyio",
    "anyio._backends._asyncio",
]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
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
    a.binaries,
    a.datas,
    [],
    name="BloombergBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # off: avoids AV false positives on locked-down workstations
    runtime_tmpdir=None,
    console=False,  # tray app — no console window
    disable_windowed_traceback=False,
    icon=icon_file,
)
