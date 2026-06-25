"""Claude Code hook integration — zero-quota limit auto-detect (ADR-0008).

@context  Instead of spending quota to probe for the limit, we let Claude Code
          tell us: a StopFailure/rate_limit hook runs `cloophole limit-signal`
          the moment a turn ends from a usage limit, dropping a signal file the
          daemon watches. Public hooks API only — honors the Golden Rule (no
          transcript/internal reads; the hook is the user's own config).
@done     install_hook/uninstall_hook/hook_installed (merge our entry into the
          Windows Claude settings.json) + install_hook_wsl/uninstall_hook_wsl (same
          hook in the WSL distro's settings via \\wsl$, command runs our exe through
          interop — so a WSL-only session signals the limit too). record_signal
          (write), read_signal/clear_signal (daemon side).
@todo     surface install state in the GUI; macOS/Linux paths.
@limits   The hook reports THAT a limit hit (+ its cwd); record_signal tries to
          parse a reset time out of the payload too. If absent, the daemon probes
          once (probe_on_limit) for the real reset, else estimates the window.
          settings.json is the user's public config; we only touch our own entry.
@affects  CLI `limit-signal`/`hook`; consumed by daemon.tick. Writes
          ~/.cloophole/limit-signal.json and ~/.claude/settings.json.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .paths import home

HOOK_EVENT = "StopFailure"
HOOK_MATCHER = "rate_limit"
_MARK = "limit-signal"  # how we recognise our own hook entry on uninstall


def signal_file() -> Path:
    return home() / "limit-signal.json"


def settings_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(base) if base else Path.home() / ".claude"
    return root / "settings.json"


def _cloophole_cmd() -> str:
    """The command Claude runs on a rate limit."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" limit-signal'
    return "cloophole limit-signal"


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def hook_installed() -> bool:
    data = _load(settings_path())
    for entry in data.get("hooks", {}).get(HOOK_EVENT, []):
        for h in entry.get("hooks", []):
            if _MARK in h.get("command", ""):
                return True
    return False


def _install_at(p, cmd: str) -> bool:
    """Merge our StopFailure/rate_limit hook (running `cmd`) into the settings at `p`.
    Idempotent; refreshes our command if present; keeps the user's other hooks."""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        data = _load(p)
        hooks = data.setdefault("hooks", {})
        lst = hooks.setdefault(HOOK_EVENT, [])
        for entry in lst:
            for h in entry.get("hooks", []):
                if _MARK in h.get("command", ""):
                    h["command"] = cmd
                    _save(p, data)
                    return True
        lst.append({"matcher": HOOK_MATCHER,
                    "hooks": [{"type": "command", "command": cmd}]})
        _save(p, data)
        return True
    except OSError:
        return False


def _uninstall_at(p) -> bool:
    """Remove only our hook entry from the settings at `p`; prune empties."""
    if not p.exists():
        return False
    try:
        data = _load(p)
    except OSError:
        return False
    hooks = data.get("hooks", {})
    lst = hooks.get(HOOK_EVENT, [])
    removed = False
    new_lst = []
    for entry in lst:
        original = entry.get("hooks", [])
        kept = [h for h in original if _MARK not in h.get("command", "")]
        if len(kept) != len(original):
            removed = True
        if kept:
            entry["hooks"] = kept
            new_lst.append(entry)
    if removed:
        if new_lst:
            hooks[HOOK_EVENT] = new_lst
        else:
            hooks.pop(HOOK_EVENT, None)
        if not hooks:
            data.pop("hooks", None)
        try:
            _save(p, data)
        except OSError:
            return False
    return removed


def install_hook() -> bool:
    """Register the rate-limit hook in the Windows Claude settings."""
    return _install_at(settings_path(), _cloophole_cmd())


def uninstall_hook() -> bool:
    return _uninstall_at(settings_path())


# ---- WSL Claude: its settings live inside the distro and it can't run a Windows exe
# path, so a WSL-only session never signalled the limit. Install the SAME hook into the
# distro's ~/.claude (via the \\wsl$ path), running our exe through WSL interop. ----

def _wsl_cmd() -> Optional[str]:
    if not getattr(sys, "frozen", False):
        return None
    from . import wsl
    u = wsl.exe_unix_path(sys.executable)
    return f"'{u}' limit-signal" if u else None


def install_hook_wsl() -> bool:
    cmd = _wsl_cmd()
    if not cmd:
        return False
    from . import wsl
    sp = wsl.claude_settings_winpath()
    return _install_at(Path(sp), cmd) if sp else False


def uninstall_hook_wsl() -> bool:
    from . import wsl
    sp = wsl.claude_settings_winpath()
    return _uninstall_at(Path(sp)) if sp else False


# --- daemon side: the signal file -------------------------------------------

def record_signal(stdin_text: Optional[str] = None) -> None:
    """Write the limit signal. NEVER raises — it runs inside the user's Claude,
    so any failure must stay silent rather than break their session."""
    try:
        raw = stdin_text
        if raw is None:
            raw = "" if (sys.stdin is None or sys.stdin.isatty()) else sys.stdin.read()
        cwd = None
        try:
            data = json.loads(raw) if raw and raw.strip() else {}
            if isinstance(data, dict):
                cwd = data.get("cwd")
        except (json.JSONDecodeError, ValueError):
            pass
        # If Claude put a reset time anywhere in the payload, grab it (zero quota) so
        # the countdown is the REAL reset, not a worst-case estimate.
        reset_at = None
        try:
            from .reset_parser import parse_reset
            dt = parse_reset(raw or "")
            if dt:
                reset_at = dt.isoformat()
        except Exception:
            pass
        sig = {"ts": datetime.now(timezone.utc).isoformat(),
               "cwd": cwd, "source": HOOK_MATCHER, "reset_at": reset_at}
        signal_file().write_text(json.dumps(sig), encoding="utf-8")
    except Exception:
        pass


def read_signal() -> Optional[dict]:
    p = signal_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def clear_signal() -> None:
    try:
        signal_file().unlink()
    except OSError:
        pass
