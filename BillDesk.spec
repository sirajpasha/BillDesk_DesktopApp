# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for BillDesk. Build with:  pyinstaller --noconfirm --clean BillDesk.spec   (or .\build_windows.ps1)
#
# Result: dist\BillDesk\BillDesk.exe  (one-folder build; the Inno Setup installer packages that folder)
# Shipped inside: the app code and libraries, app\assets, data\seed_data.json, the bundled MongoDB (mongod.exe + licences).
# Tesseract (148 MB, needed only for the planned OCR feature) is left out unless you set INCLUDE_TESSERACT=1.
import os
from PyInstaller.utils.hooks import collect_all

datas = [
    ("app/assets", "app/assets"),
    ("data/seed_data.json", "data"),
    ("resources/mongo/win32-x64/mongod.exe", "resources/mongo/win32-x64"),
    ("resources/mongo/win32-x64/LICENSE-Community.txt", "resources/mongo/win32-x64"),
    ("resources/mongo/win32-x64/THIRD-PARTY-NOTICES.txt", "resources/mongo/win32-x64"),
    ("resources/mongo/win32-x64/VERSION", "resources/mongo/win32-x64"),
]
if os.environ.get("INCLUDE_TESSERACT") == "1":
    datas.append(("resources/tesseract", "resources/tesseract"))

binaries, hiddenimports = [], ["pymupdf", "fitz", "PIL._tkinter_finder"]
for pkg in ("pymupdf", "reportlab", "certifi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "unittest", "pydoc", "test", "tkinter.test", "pytesseract"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BillDesk",
    console=False,                 # a windowed app; errors go to %APPDATA%\BillDesk\logs\billdesk.log
    icon="app/assets/icon.ico",
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="BillDesk")
