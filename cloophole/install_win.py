"""Windows run-at-logon install/uninstall (product plan §8, §11).

@context  Make the daemon start at logon and run hidden, with NO admin rights
          by default. Task Scheduler (the old default) needed elevation on some
          machines ("access is denied"), so the shim path is now the default.
@done     install() is idempotent + no-admin: stops old daemon, drops a leftover
          task best-effort, writes a Startup .vbs shim, starts detached. method=
          "task" uses schtasks. start_now/stop are pid-aware (liveness-checked).
@todo     mac launchd / Linux systemd-user + install.py dispatch (P5, ADR-0003).
@limits   Windows-only. Shim runs only for the current user at logon.
@affects  Invoked by CLI install/uninstall/start/stop. Runs
          `pythonw -m cloophole daemon` hidden.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TASK_NAME = "cloophole"
SHIM_NAME = "cloophole.vbs"


def _pythonw() -> str:
    # Prefer pythonw.exe (no console) sitting next to the active interpreter.
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.exists() else exe)


def _startup_dir() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def _shim_path() -> Path:
    return _startup_dir() / SHIM_NAME


def start_now() -> int:
    """Launch the daemon detached + hidden right now (no reboot needed)."""
    from .paths import pid_file
    from . import winproc
    f = pid_file()
    if f.exists():
        try:
            if winproc.pid_alive(int(f.read_text().strip())):
                print("daemon already running; skipping start")
                return 0
        except (ValueError, OSError):
            pass  # stale pid file — fall through and start
    flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    subprocess.Popen(
        [_pythonw(), "-m", "cloophole", "daemon"],
        creationflags=flags,
        close_fds=True,
    )
    print("daemon started in background")
    return 0


def stop() -> int:
    """Stop a running daemon via its pid file."""
    from .paths import pid_file
    f = pid_file()
    if not f.exists():
        print("no daemon pid file; nothing to stop")
        return 0
    try:
        pid = int(f.read_text().strip())
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True)
        print(f"stopped daemon pid {pid}")
    except (ValueError, OSError) as e:
        print(f"could not stop: {e}")
        return 1
    try:
        f.unlink()
    except OSError:
        pass
    return 0


# --- Startup-folder shim (default; no admin) --------------------------------

def _install_shim() -> int:
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.Run "{_pythonw()} -m cloophole daemon", 0, False\r\n'
    )
    path = _shim_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(vbs, encoding="utf-8")
    print(f"installed startup shim -> {path}")
    print("  runs hidden at every logon (no admin needed)")
    return 0


def _uninstall_shim() -> int:
    path = _shim_path()
    if path.exists():
        path.unlink()
        print(f"removed startup shim {path}")
    else:
        print("no startup shim found")
    return 0


# --- Task Scheduler (opt-in: method='task') ---------------------------------

def _install_task() -> int:
    run_cmd = f'"{_pythonw()}" -m cloophole daemon'
    proc = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", run_cmd,
         "/SC", "ONLOGON", "/RL", "LIMITED", "/F"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        print(f"installed Task Scheduler task '{TASK_NAME}' (runs at logon)")
    else:
        print((proc.stdout + proc.stderr).strip())
        print("  (Task Scheduler may need an elevated terminal; try the default "
              "shim instead: `cloophole install`)")
    return proc.returncode


def _task_exists() -> bool:
    return subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True, text=True,
    ).returncode == 0


def _uninstall_task(quiet: bool = False) -> int:
    if not _task_exists():
        return 0
    proc = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        print(f"removed old Task Scheduler task '{TASK_NAME}'")
    elif not quiet:
        # Deletion of an admin-created task may be denied — harmless now, the
        # single-instance guard stops a second daemon from double-firing.
        print(f"note: couldn't remove old task '{TASK_NAME}' (made with admin?). "
              "Safe to leave — the daemon is single-instance. To remove it once: "
              "run in an elevated terminal:  schtasks /Delete /TN cloophole /F")
    return proc.returncode


def install(method: str = "shim") -> int:
    """Idempotent, no-admin by default: stop any old daemon, clear the other
    mechanism, install, and start. Safe to re-run."""
    stop()  # restart cleanly with the latest code
    if method == "task":
        _uninstall_shim()
        rc = _install_task()
    else:
        _uninstall_task(quiet=True)  # best-effort drop a leftover task
        rc = _install_shim()
    if rc == 0:
        start_now()
    return rc


def uninstall(method: str = "shim") -> int:
    # Best-effort remove both, so a switch of methods leaves nothing behind.
    stop()
    _uninstall_shim()
    _uninstall_task()
    return 0
