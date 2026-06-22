"""Launch / attach / stop the background watcher daemon (ADR-0003/0006).

@context  `cloophole open` is launch-or-attach: start the detached background
          watcher daemon if it isn't running, then open the app window.
          `close` stops it. No run-at-logon — started explicitly via `open`.
@done     is_running()/pid()/launch()/stop() for the daemon; is_gui_running()/
          launch_gui() for the GUI window (both detached + single-instance).
@todo     mac/Linux launch (P5, ADR-0003 follow-up).
@limits   Windows-first; launch uses pythonw + DETACHED_PROCESS|CREATE_NO_WINDOW,
          with stdio -> DEVNULL so the detached GUI child has valid handles.
@affects  Used by CLI open/close/uninstall. Process holds daemon.pid.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from .paths import gui_pid_file, pid_file

DETACHED = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        from . import winproc
        return winproc.pid_alive(pid)
    return True


def _read_pid(path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


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


def _cmd(sub: str) -> list[str]:
    """Subcommand launcher: frozen exe relaunches itself; source uses pythonw."""
    if getattr(sys, "frozen", False):
        return [sys.executable, sub]
    return [_pythonw(), "-m", "cloophole", sub]


def _spawn(sub: str) -> None:
    # Detach std handles too: with DETACHED_PROCESS the child has no console, so
    # inherited stdout/stderr are invalid and the first write (e.g. Tk startup in
    # the `_gui` child) crashes it. DEVNULL gives it valid, silent handles.
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = DETACHED
    subprocess.Popen(_cmd(sub), close_fds=True, **kwargs)


def launch() -> bool:
    """Start the background watcher daemon detached. False if already running."""
    if is_running():
        return False
    _spawn("daemon")
    return True


def is_gui_running() -> bool:
    return _alive(_read_pid(gui_pid_file()))


def launch_gui() -> bool:
    """Open the GUI window (detached) if one isn't already open."""
    if is_gui_running():
        return False
    _spawn("_gui")
    return True


def stop_gui() -> bool:
    """Close a running GUI window. False if none was open."""
    p = _read_pid(gui_pid_file())
    if not _alive(p):
        try:
            gui_pid_file().unlink()
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
        gui_pid_file().unlink()
    except OSError:
        pass
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
