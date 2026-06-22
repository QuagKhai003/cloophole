"""Filesystem locations for cloophole state, config, and logs.

@context  Single place that resolves the ~/.cloophole/ home and the files inside
          it, so durable state lives on disk and the CLI/daemon/UI agree.
@done     home(), state_file(), config_file(), log_file(), pid_file(),
          gui_pid_file(); $CLOOPHOLE_HOME override for test isolation.
@todo     —
@limits   PURE-ish: only path resolution + mkdir of the home dir.
@affects  Imported by config, state, daemon, ui. Honors $CLOOPHOLE_HOME.
"""

from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    override = os.environ.get("CLOOPHOLE_HOME")
    base = Path(override) if override else Path.home() / ".cloophole"
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
