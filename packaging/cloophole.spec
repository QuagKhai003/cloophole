# PyInstaller spec — standalone onefile cloophole.exe (Windows).
# Build:  pyinstaller packaging/cloophole.spec --noconfirm
# Output: dist/cloophole.exe
#
# Console exe: normal CLI commands print to the terminal; the detached tray
# (`_app`) is launched with CREATE_NO_WINDOW so it shows no console.

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("pystray")
    + collect_submodules("PIL")
    + ["tkinter", "tkinter.simpledialog"]
)

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cloophole",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # CLI needs stdout; tray child uses CREATE_NO_WINDOW
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
