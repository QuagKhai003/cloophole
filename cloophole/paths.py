"""Filesystem locations for cloophole state, config, and logs.

@context  Single place that resolves the home dir and the files inside it, so
          durable state lives on disk and the CLI/daemon/UI agree. On Windows the
          home is %LOCALAPPDATA%\\cloophole (NOT ~/.cloophole) so OneDrive can't sync
          it across machines and two daemons can't write the same file.
@done     home(), state_file(), config_file(), log_file(), pid_file(),
          gui_pid_file(); $CLOOPHOLE_HOME override for test isolation.
@todo     —
@limits   PURE-ish: only path resolution + mkdir of the home dir.
@affects  Imported by config, state, daemon, ui, claude_hook. Honors $CLOOPHOLE_HOME;
          install.ps1/uninstall.ps1/reset.ps1 must use the same %LOCALAPPDATA% path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def home() -> Path:
    """Where state/config/logs live. On Windows this is %LOCALAPPDATA%\\cloophole
    (AppData\\Local) — never roamed or OneDrive-synced, so two machines can't write
    the same file. $CLOOPHOLE_HOME overrides (used by tests). Falls back to
    ~/.cloophole off Windows or when LOCALAPPDATA is unset."""
    override = os.environ.get("CLOOPHOLE_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"]) / "cloophole"
    else:
        base = Path.home() / ".cloophole"
    base.mkdir(parents=True, exist_ok=True)
    return base


def state_file() -> Path:
    return home() / "state.json"


def config_file() -> Path:
    return home() / "config.json"


def log_file() -> Path:
    return home() / "cloophole.log"


def pid_file() -> Path:
    return home() / "daemon.pid"


def gui_pid_file() -> Path:
    return home() / "gui.pid"
