"""Idle quota probe — detect that you're limited while you're away (plan §4).

@context  No API exposes the reset clock, so when idle we occasionally send a
          tiny `claude -p` call; if it comes back as a limit message we parse
          the reset and arm. Public-CLI only — honors the Golden Rule.
@done     probe(cfg) -> (limited, text) using subproc (no window) + shared
          is_limit_message.
@todo     —
@limits   Costs a little quota per call, so the daemon gates cadence to
          poll_interval_min and only runs while WATCHING (BUGS-noted §9.4).
@affects  Called by daemon.tick when poll_enabled. Reuses reset_parser.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from . import config, subproc
from .reset_parser import is_limit_message

PROBE_PROMPT = "reply with the single word: ok"


def probe(cfg: Optional[dict] = None) -> tuple[bool, Optional[str]]:
    """Send one tiny probe. Returns (limited, raw_text).

    limited=True means the probe output read as a usage-limit message. Any
    error (claude missing, timeout) returns (False, None) — never raises.
    """
    cfg = cfg or config.load()
    cmd = [
        cfg["claude_path"],
        "-p",
        PROBE_PROMPT,
        "--permission-mode",
        cfg["permission_mode"],
    ]
    try:
        proc = subproc.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.get("fire_timeout_sec", 1800),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, None
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if is_limit_message(combined):
        return True, combined
    return False, None
