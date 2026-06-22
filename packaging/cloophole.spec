# PyInstaller spec — standalone onefile cloophole.exe (Windows).
# Build:  pyinstaller packaging/cloophole.spec --noconfirm
# Output: dist/cloophole.exe
#
# Console exe: normal CLI commands print to the terminal; the detached tray
# (`_app`) is launched with CREATE_NO_WINDOW so it shows no console.

# Exclude everything the app doesn't import. App uses only: ctypes, json,
# dataclasses, datetime, pathlib, typing, os, re, subprocess, sys, time,
# threading, shutil, signal, webbrowser(no), http(no).
EXCLUDES = [
    # rejected/replaced features
    "numpy", "pytest", "_pytest", "pystray", "PIL", "tkinter", "turtle",
    # unused stdlib subsystems
    "http", "xml", "xmlrpc", "html", "email", "asyncio", "sqlite3", "curses",
    "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "socketserver",
    "unittest", "doctest", "pydoc", "pdb", "lib2to3", "test", "distutils",
    "setuptools", "pip", "wheel", "multiprocessing", "concurrent",
    "decimal", "fractions", "statistics", "pickletools", "bz2", "lzma",
]

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,  # strip docstrings/asserts from bundled bytecode
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
