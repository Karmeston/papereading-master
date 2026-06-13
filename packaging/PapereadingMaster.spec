from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


ROOT = Path(SPECPATH).parent
ICON = ROOT / "packaging" / "assets" / "papereading-master.ico"
VERSION = ROOT / "packaging" / "version_info.txt"

datas = []
for distribution in (
    "langchain",
    "langchain-core",
    "langchain-openai",
    "openai",
    "pypdf",
    "PyMuPDF",
    "pywebview",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        pass
datas += collect_data_files("webview")

hiddenimports = []
for package in ("finals_agent", "langchain_openai", "webview"):
    hiddenimports += collect_submodules(package)

a = Analysis(
    [str(ROOT / "packaging" / "desktop_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "cefpython3",
        "gi",
        "gtk",
        "sentence_transformers",
        "tensorflow",
        "torch",
        "transformers",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PapereadingMasterBeta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=str(VERSION),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PapereadingMasterBeta",
)
