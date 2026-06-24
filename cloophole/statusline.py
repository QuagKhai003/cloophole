"""Read Claude Code's statusLine JSON to learn the REAL 5-hour reset time + usage,
zero quota, BEFORE any limit is hit (ADR-0014).

@context  Claude pipes a JSON blob to a configured statusLine command every turn; for
          Pro/Max it includes rate_limits.five_hour.{resets_at, used_percentage}. We
          register `cloophole statusline` as that command: it stores the reset/usage to
          status.json (the window reads it for a live countdown + % long before a limit)
          and prints a small status line. Public statusLine API — Claude hands us the
          data, we read no transcript/internal files (Golden Rule, like the hook).
@done     parse/write/read/render; install/uninstall (settings.json, no clobber).
@todo     —
@limits   Pro/Max only; populated after the first API response while Claude runs. Off
          Windows the settings path still works. We never overwrite a user's own
          statusLine command.
@affects  CLI `statusline` (fast path) writes status.json; gui reads it; daemon prefers
          its window_reset_at for an accurate limit reset. Shares settings_path() with
          claude_hook.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .paths import home


def status_file():
    return home() / "status.json"


def parse(blob: Optional[str]) -> Optional[dict]:
    """Pull the 5h/7d reset + usage out of the statusLine JSON. None if absent."""
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    rl = (data or {}).get("rate_limits") or {}
    out: dict = {}

    def _iso(epoch):
        try:
            return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()
        except (ValueError, OSError, TypeError):
            return None

    five = rl.get("five_hour") or {}
    seven = rl.get("seven_day") or {}
    if _iso(five.get("resets_at")):
        out["window_reset_at"] = _iso(five.get("resets_at"))
    if isinstance(five.get("used_percentage"), (int, float)):
        out["used_pct"] = round(float(five["used_percentage"]), 1)
    if _iso(seven.get("resets_at")):
        out["week_reset_at"] = _iso(seven.get("resets_at"))
    if isinstance(seven.get("used_percentage"), (int, float)):
        out["used_pct_7d"] = round(float(seven["used_percentage"]), 1)
    return out or None


def write_status(info: dict) -> None:
    info = dict(info)
    info["ts"] = datetime.now(timezone.utc).isoformat()
    p = status_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(info), encoding="utf-8")


def read_status() -> Optional[dict]:
    p = status_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def render(info: Optional[dict]) -> str:
    """The one-line status string Claude shows (doubles as a usage readout)."""
    if not info:
        return "cloophole"
    parts = []
    if "used_pct" in info:
        parts.append(f"5h {info['used_pct']:.0f}%")
    rt = info.get("window_reset_at")
    if rt:
        try:
            dt = datetime.fromisoformat(rt).astimezone()
            parts.append("resets " + dt.strftime("%I:%M %p").lstrip("0"))
        except ValueError:
            pass
    return "cloophole · " + " · ".join(parts) if parts else "cloophole"


# ---- settings.json registration (shares claude_hook.settings_path) ----------

def _command() -> str:
    import sys
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" statusline'
    return "cloophole statusline"


def statusline_installed() -> bool:
    from . import claude_hook
    data = claude_hook._load(claude_hook.settings_path())
    sl = data.get("statusLine") or {}
    return "statusline" in (sl.get("command") or "")


def install_statusline() -> bool:
    """Register our statusLine command. Returns False (and leaves it alone) if the
    user already has their OWN statusLine — we never clobber it."""
    from . import claude_hook
    p = claude_hook.settings_path()
    data = claude_hook._load(p)
    existing = data.get("statusLine")
    if existing and "statusline" not in ((existing or {}).get("command") or ""):
        return False
    data["statusLine"] = {"type": "command", "command": _command(), "padding": 0}
    claude_hook._save(p, data)
    return True


def uninstall_statusline() -> bool:
    from . import claude_hook
    p = claude_hook.settings_path()
    if not p.exists():
        return False
    data = claude_hook._load(p)
    sl = data.get("statusLine") or {}
    if "statusline" in (sl.get("command") or ""):
        data.pop("statusLine", None)
        claude_hook._save(p, data)
        return True
    return False
