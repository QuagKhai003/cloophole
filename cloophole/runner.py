"""Launch / attach / stop the background watcher daemon (ADR-0003/0006).

@context  `cloophole open` is launch-or-attach: start the detached background
          watcher daemon if it isn't running, then show the terminal menu.
          `close` stops it. No run-at-logon — started explicitly via `open`.
@done     is_running(), pid(), launch() (detached + hidden daemon), stop().
@todo     mac/Linux launch (P5, ADR-0003 follow-up).
@limits   Windows-first; launch uses pythonw + DETACHED_PROCESS|CREATE_NO_WINDOW.
@affects  Used by CLI open/close/uninstall. Process holds daemon.pid.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from .paths import pid_file

DETACHED = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW


def pid() -> Optional[int]:
    f = pid_file()
    if not f.exists():
        return None
    try:
        return int(f.read_text().strip())
    except (ValueError, OSError):
        return None


def is_running() -> bool:
    p = pid()
    if p is None:
        return False
    if sys.platform == "win32":
        from . import winproc
        return winproc.pid_alive(p)
    return True  # best-effort off Windows


def _pythonw() -> str:
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.exists() else exe)


def _daemon_command() -> list[str]:
    """Command that launches the background watcher. As a frozen exe, relaunch
    ourselves; from source, use pythonw -m cloophole (no console window)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "daemon"]
    return [_pythonw(), "-m", "cloophole", "daemon"]


def launch() -> bool:
    """Start the background daemon detached + hidden. False if already running."""
    if is_running():
        return False
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = DETACHED
    subprocess.Popen(_daemon_command(), close_fds=True, **kwargs)
    return True


def stop() -> bool:
    """Stop the running app. Returns False if nothing was running."""
    p = pid()
    if p is None or not is_running():
        # clean a stale pid file if present
        try:
            pid_file().unlink()
        except OSError:
            pass
        return False
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(p), "/T", "/F"],
                       capture_output=True, text=True)
    else:
        import os
        import signal
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    try:
        pid_file().unlink()
    except OSError:
        pass
    return True
