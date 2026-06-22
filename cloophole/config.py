"""Config load/save — tunables only (runtime status lives in state.py).

@context  JSON config at ~/.cloophole/config.json with sane DEFAULTS; missing
          keys fall back so old files keep working as defaults grow.
@done     DEFAULTS, load/save, get/set_ helpers.
@todo     config hot-reload (Phase 6, ADR-0004).
@limits   PURE: no process/network. Keys documented in docs/DATA_MODEL.md.
@affects  Read by daemon, fire, ui, CLI `config`. Writes config.json via paths.
"""

from __future__ import annotations

import json
from typing import Any

from . import paths

DEFAULTS: dict[str, Any] = {
    "claude_path": "claude",        # executable name or full path
    "permission_mode": "acceptEdits",  # non-interactive; headless can't confirm
    "daemon_tick_sec": 15,          # main loop cadence
    "poll_enabled": False,          # Phase 3 idle probing; off by default
    "poll_interval_min": 30,        # gentle, probing costs quota
    "fire_timeout_sec": 1800,       # cap a single --continue run
    "claude_process_name": "claude.exe",
}


def load() -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    f = paths.config_file()
    if f.exists():
        try:
            cfg.update(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save(cfg: dict[str, Any]) -> None:
    paths.config_file().write_text(
        json.dumps(cfg, indent=2), encoding="utf-8"
    )


def get(key: str) -> Any:
    return load().get(key, DEFAULTS.get(key))


def set_(key: str, value: Any) -> dict[str, Any]:
    cfg = load()
    cfg[key] = value
    save(cfg)
    return cfg
