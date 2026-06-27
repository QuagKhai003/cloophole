"""Read Claude Code's statusLine JSON to learn the REAL 5-hour reset time + usage,
zero quota, BEFORE any limit is hit (ADR-0014).

@context  Claude pipes a JSON blob to a configured statusLine command every turn; for
          Pro/Max it includes rate_limits.five_hour.{resets_at, used_percentage}. We
          register `cloophole statusline` as that command: it stores the reset/usage to
          status.json (the window reads it for a live countdown + % long before a limit)
          and prints a small status line. Public statusLine API — Claude hands us the
          data, we read no transcript/internal files (Golden Rule, like the hook).
@done     parse + update_status (MERGE across terminals: keep the freshest account usage
          so an idle/older terminal can't pull the numbers backward) / read / render
          (UNBRANDED — shows in every project's status bar);
          install/uninstall for BOTH the Windows ~/.claude AND the default WSL distro's
          ~/.claude (via the \\wsl$ path, command runs our exe through WSL interop), so a
          WSL-only setup still gets the reset time. Never clobbers a user's statusLine.
@todo     non-default WSL distros.
@limits   Pro/Max only; populated after the first API response while Claude runs. The
          WSL command runs our exe per turn via interop (heavier) — `hook off` removes it.
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
    import os
    info = dict(info)
    info["ts"] = datetime.now(timezone.utc).isoformat()
    p = status_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")  # atomic + concurrency-safe
    tmp.write_text(json.dumps(info), encoding="utf-8")
    try:
        os.replace(tmp, p)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _dt(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def update_status(info: dict) -> None:
    """Merge a statusLine sample into status.json, keeping the FRESHEST account usage
    across all open terminals. Many terminals write the same file; an idle/older one
    must not pull the numbers backward:
      - drop a sample whose 5h window already passed (stale) when we hold a live one;
      - an OLDER window than the one we hold is ignored; a NEWER window is adopted;
      - within the SAME window, keep the HIGHER used% (usage only rises until reset)."""
    now = datetime.now(timezone.utc)
    cur = read_status() or {}
    nr, cr = _dt(info.get("window_reset_at")), _dt(cur.get("window_reset_at"))
    cur_live = cr is not None and cr > now

    if nr is None:                       # sample carries no reset of its own
        if cur_live and info.get("used_pct", -1) > cur.get("used_pct", -1):
            cur["used_pct"] = info["used_pct"]
            if "used_pct_7d" in info:
                cur["used_pct_7d"] = info["used_pct_7d"]
            write_status(cur)
        elif not cur:
            write_status(info)
        return

    if nr <= now and cur_live:           # this sample's window already reset -> stale
        return
    if cur_live:
        if nr < cr:                      # older window than ours -> ignore
            return
        if nr == cr and info.get("used_pct", -1) <= cur.get("used_pct", -1):
            return                       # same window, not fresher -> keep ours
    write_status(info)                   # newer window, or no live record -> take it


def read_status() -> Optional[dict]:
    p = status_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cwd_of(blob: Optional[str]) -> Optional[str]:
    """This session's cwd from the statusLine JSON (workspace.current_dir or cwd)."""
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    ws = (data or {}).get("workspace") or {}
    return ws.get("current_dir") or data.get("cwd")


def folder_of(blob: Optional[str]) -> Optional[str]:
    """The session's folder NAME — so each terminal's status bar shows its own project."""
    cwd = cwd_of(blob)
    if not cwd:
        return None
    import os
    return os.path.basename(str(cwd).rstrip("/\\")) or str(cwd)


def _win_path(cwd: Optional[str]) -> Optional[str]:
    """A Windows path git can read: pass through 'C:\\…', convert '/mnt/c/…' -> 'C:\\…',
    None for a pure-Linux path (Windows git can't reach it)."""
    if not cwd:
        return None
    import re
    if re.match(r"^[a-zA-Z]:[\\/]", cwd):
        return cwd
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", cwd)
    if m:
        return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\")
    return None


def git_info(cwd: Optional[str]) -> Optional[str]:
    """'<branch>' or '<branch>*' (dirty working tree) for the repo at cwd, or None if
    not a git repo / git missing. Short timeouts — runs on every status render."""
    wp = _win_path(cwd)
    if not wp:
        return None
    from . import subproc
    try:
        b = subproc.run(["git", "-C", wp, "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True, timeout=3)
        if b.returncode != 0 or not (b.stdout or "").strip():
            return None
        branch = b.stdout.strip()
        s = subproc.run(["git", "-C", wp, "status", "--porcelain"],
                        capture_output=True, text=True, timeout=3)
        dirty = bool((s.stdout or "").strip()) if s.returncode == 0 else False
        return branch + ("*" if dirty else "")
    except Exception:
        return None


def render(info: Optional[dict], folder: Optional[str] = None,
           git: Optional[str] = None) -> str:
    """The one-line status Claude shows: '<folder> (<branch>*) · 5h N% · resets H:MM'.
    UNBRANDED. Any part is omitted when absent."""
    head = folder or ""
    if git:
        head = f"{head} ({git})" if head else f"({git})"
    parts = []
    if info:
        if "used_pct" in info:
            parts.append(f"5h {info['used_pct']:.0f}%")
        rt = info.get("window_reset_at")
        if rt:
            try:
                dt = datetime.fromisoformat(rt).astimezone()
                parts.append("resets " + dt.strftime("%I:%M %p").lstrip("0"))
            except ValueError:
                pass
    usage = " · ".join(parts)
    if head and usage:
        return f"{head} · {usage}"
    return head or usage


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


# ---- WSL Claude: its settings live INSIDE the distro, and it can't run a Windows
# exe path directly. We write the distro's ~/.claude/settings.json (reachable from
# Windows via the \\wsl$ path) with a command that runs OUR exe through WSL interop
# (/mnt/c/...), feeding the SAME shared status.json. So a WSL-only setup still gets
# the real reset time. ---------------------------------------------------------

from pathlib import Path
import sys


def _wsl_settings_path() -> Optional[Path]:
    """Windows path to the default WSL distro's ~/.claude/settings.json, or None."""
    from . import wsl
    out = wsl.bash('wslpath -w "$HOME/.claude" 2>/dev/null')
    if not out or not out.strip():
        return None
    return Path(out.strip()) / "settings.json"


def _wsl_command() -> Optional[str]:
    """The statusLine command for WSL: our Windows exe via its /mnt path + statusline.
    Only meaningful in the frozen exe (dev installs have no shippable command)."""
    if not getattr(sys, "frozen", False):
        return None
    from . import wsl
    out = wsl.bash(f'wslpath -u "{sys.executable}" 2>/dev/null')
    if not out or not out.strip():
        return None
    return f"'{out.strip()}' statusline"


def install_statusline_wsl() -> bool:
    """Register our statusLine in the default WSL distro's Claude settings. Best-effort;
    never clobbers a user's own WSL statusLine. Returns True if we wrote it."""
    cmd = _wsl_command()
    if not cmd:
        return False
    p = _wsl_settings_path()
    if not p:
        return False
    from . import claude_hook
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        data = claude_hook._load(p)
        existing = data.get("statusLine")
        if existing and "statusline" not in ((existing or {}).get("command") or ""):
            return False
        data["statusLine"] = {"type": "command", "command": cmd, "padding": 0}
        claude_hook._save(p, data)
        return True
    except OSError:
        return False


def uninstall_statusline_wsl() -> bool:
    p = _wsl_settings_path()
    if not p or not p.exists():
        return False
    from . import claude_hook
    try:
        data = claude_hook._load(p)
        sl = data.get("statusLine") or {}
        if "statusline" in (sl.get("command") or ""):
            data.pop("statusLine", None)
            claude_hook._save(p, data)
            return True
    except OSError:
        pass
    return False
