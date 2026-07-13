"""Detect & drive Claude running inside WSL + tmux (ADR-0013).

@context  An agent team often runs in WSL under tmux (split panes), one `claude`
          per pane. Those are LINUX processes — invisible to Windows process scans —
          so we detect/inject via tmux: `wsl tmux list-panes` to find claude panes,
          `wsl tmux send-keys -t <pane>` to type into a specific pane (exact, no focus
          games). Still public-CLI only (Golden Rule, ADR-0012 action side).
@done     claude_sessions() -> [(pane_id, cwd)] (tmux) + send_keys(pane, text);
          plain_sessions() -> [(windows_wsl_host_pid, cwd)] (non-tmux), injected via
          the host console (fire.resume -> inject.send_text on that pid).
@todo     non-default WSL distro / custom tmux socket selection.
@limits   Windows-only host; needs WSL + a running tmux. Best-effort: any failure
          returns [] / False. A pane's command shows as `claude` or its version
          string (e.g. 2.1.186) — both are matched. Plain (non-tmux) pairing of a
          claude cwd to its Windows wsl.exe host is heuristic (newest root first);
          reliable with ONE plain terminal, ambiguous with several (use tmux then).
@affects  Used by sessions.list_all (detect) and fire.resume (inject when key is
          'wsl:<pane>'). Runs wsl.exe via subproc (no console window).
"""

from __future__ import annotations

import base64
import re
import sys
from typing import List, Optional, Tuple

from . import subproc

# A claude pane's current command is "claude" or the Claude Code version (2.1.186).
_IS_CLAUDE = re.compile(r"^(claude|\d+\.\d+\.\d+)")
_SEP = "\t"


def _wsl(args: list[str], timeout: int = 10):
    """Run `wsl.exe <args>` capturing output, no window. None on failure."""
    if sys.platform != "win32":
        return None
    try:
        return subproc.run(["wsl.exe", *args], capture_output=True,
                           text=True, timeout=timeout)
    except Exception:
        return None


def available() -> bool:
    p = _wsl(["tmux", "list-panes", "-a", "-F", "#{pane_id}"], timeout=6)
    return bool(p and p.returncode == 0)


def bash(script: str, timeout: int = 15) -> Optional[str]:
    """Run a bash `script` in the default distro and return stdout (None on failure).
    base64-wraps it so $()/$VAR survive the Windows -> wsl.exe -> bash arg mangling."""
    import base64 as _b64
    b64 = _b64.b64encode(script.encode()).decode()
    p = _wsl(["bash", "-c", f"echo {b64} | base64 -d | bash"], timeout=timeout)
    return p.stdout if (p and p.returncode == 0) else None


# Each wsl.exe round-trip is slow (it starts the distro if cold). These paths don't
# change while we run, so resolve them once per process.
_path_cache: dict = {}


def claude_settings_winpath() -> Optional[str]:
    """Windows path to the default WSL distro's ~/.claude/settings.json (or None).
    Reachable from Windows over \\\\wsl$, so we can read/write it directly. Cached."""
    if "settings" in _path_cache:
        return _path_cache["settings"]
    out = bash('wslpath -w "$HOME/.claude/settings.json" 2>/dev/null')
    val = out.strip() if out and out.strip() else None
    _path_cache["settings"] = val
    return val


def exe_unix_path(win_exe: str) -> Optional[str]:
    """The /mnt/... path WSL uses to run our Windows exe (via interop), or None. Cached."""
    key = f"exe:{win_exe}"
    if key in _path_cache:
        return _path_cache[key]
    out = bash(f'wslpath -u "{win_exe}" 2>/dev/null')
    val = out.strip() if out and out.strip() else None
    _path_cache[key] = val
    return val


def claude_sessions() -> List[Tuple[str, str, str]]:
    """[(pane_id, cwd, where)] for every tmux pane running claude. `where` is a
    human marker like 'w0.p2' (window.pane index) you can match with `prefix + q`."""
    fmt = (f"#{{pane_id}}{_SEP}#{{pane_current_command}}{_SEP}#{{pane_current_path}}"
           f"{_SEP}#{{window_index}}{_SEP}#{{pane_index}}")
    p = _wsl(["tmux", "list-panes", "-a", "-F", fmt])
    if not p or p.returncode != 0 or not p.stdout:
        return []
    out: List[Tuple[str, str, str]] = []
    for line in p.stdout.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 5:
            continue
        pane, cmd, path, win, idx = (x.strip() for x in parts)
        if pane and _IS_CLAUDE.match(cmd):
            out.append((pane, path, f"w{win}.p{idx}"))
    return out


def highlight(pane_id: str) -> bool:
    """Make `pane_id` the active tmux pane and flash the pane numbers, so the user
    can SEE which split is which. Best-effort."""
    if not pane_id:
        return False
    _wsl(["tmux", "select-pane", "-t", pane_id])
    _wsl(["tmux", "display-panes", "-d", "1500"])
    return True


def _plain_claude_cwds() -> List[str]:
    """Distinct cwds of claude processes NOT under tmux. tmux sets the TMUX env var in
    its panes, so its absence in /proc/<pid>/environ means a plain shell."""
    script = ("for p in $(pgrep -f claude 2>/dev/null); do "
              "grep -qz 'TMUX=' /proc/$p/environ 2>/dev/null || "
              "readlink /proc/$p/cwd 2>/dev/null; done")
    # The script's $(...) / $p get mangled crossing Windows -> wsl.exe -> bash (the
    # outer layer expands them). base64 the script so the OUTER command has no shell
    # metachars; decode + run it inside WSL where bash evaluates it cleanly.
    b64 = base64.b64encode(script.encode()).decode()
    p = _wsl(["bash", "-c", f"echo {b64} | base64 -d | bash"], timeout=15)
    if not p or p.returncode != 0 or not p.stdout:
        return []
    seen: List[str] = []
    for c in p.stdout.splitlines():
        c = c.strip()
        if c and c not in seen:
            seen.append(c)
    return seen


def plain_sessions() -> List[Tuple[int, str]]:
    """Plain (non-tmux) WSL claude sessions -> [(windows_wsl_host_pid, cwd)].

    Each interactive `wsl` is a root wsl.exe (parent isn't wsl.exe) hosting a Windows
    console; injecting into that console (via inject.send_text) reaches the WSL claude.
    'Plain' = claude with no TMUX env var, so tmux panes never appear here."""
    plain = _plain_claude_cwds()
    if not plain:
        return []
    from . import winproc
    named = winproc.all_procs_named()
    roots = [pid for pid, (ppid, name) in named.items()
             if (name or "").lower() == "wsl.exe"
             and (named.get(ppid, (0, ""))[1] or "").lower() != "wsl.exe"]
    roots.sort(reverse=True)  # newest terminal first (a just-opened plain claude)
    out: List[Tuple[int, str]] = []
    for i, cwd in enumerate(plain):
        pid = roots[i] if i < len(roots) else (roots[-1] if roots else None)
        if pid:
            out.append((pid, cwd))
    return out


def send_keys(pane_id: str, text: str) -> bool:
    """Type `text` then Enter into tmux pane `pane_id`. True on success.

    Uses send-keys -l (literal) so the text isn't interpreted as key names, then a
    separate Enter — args are passed as a list, so no shell escaping is needed.
    """
    if not pane_id:
        return False
    lit = _wsl(["tmux", "send-keys", "-t", pane_id, "-l", text])
    if not lit or lit.returncode != 0:
        return False
    ent = _wsl(["tmux", "send-keys", "-t", pane_id, "Enter"])
    return bool(ent and ent.returncode == 0)
