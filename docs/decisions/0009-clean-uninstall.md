# ADR-0009 — Clean uninstall: sweep by image name + deregister the hook

**Status:** Accepted — COMPLETE · 2026-06-23 · Builds on ADR-0003 (lifecycle),
ADR-0008 (hook).

## Context
The pid-file stops (`stop`, `stop_gui`) only kill the processes whose pids we recorded.
A stale pid file, a second instance, or a GUI whose pid file was already cleared can
leave a cloophole process **hanging after uninstall** (user-reported: "still feel the
uninstall doesn't fully remove — leftover, hanging, running process"). Uninstall also
needs to remove the rate-limit hook (ADR-0008) from the user's Claude `settings.json`,
or that entry lingers and points at a deleted exe.

## Decision & key rules
- **Sweep by image name, not just pid.** `runner.kill_all()` enumerates every
  `cloophole.exe` via `winproc.find_pids` and `taskkill /T /F`s each — **except the
  current process** (uninstall runs as `cloophole.exe` itself).
- **Frozen + Windows only.** From source the processes are `python.exe`; we do **not**
  sweep those (would risk unrelated python). `getattr(sys, "frozen", False)` gates it.
  Always clears the pid files regardless.
- **Two entry points, both hardened.** `cloophole close` and `cloophole uninstall` call
  `kill_all()` after the pid-file stops. The `uninstall.ps1` also kills `Get-Process
  cloophole` by name (the shell isn't cloophole, so it can kill them all) and calls
  `hook off` before deleting files.
- **Deregister the hook on uninstall** (`claude_hook.uninstall_hook()`), touching only
  our entry.
- **Never touch `claude.exe`.** cloophole only manages its own processes; the user's
  Claude sessions are off-limits (a fired `claude -p` may briefly linger — accepted).

## Acceptance
- ✅ `kill_all` returns 0 and no-ops from source (not frozen); signals every other
  `cloophole.exe` and never the caller's pid when frozen.
- ✅ `close`/`uninstall` leave no cloophole process and no pid files.
- ✅ `uninstall` removes the hook from `settings.json`; `uninstall.ps1` kills by name +
  removes PATH/exe/data.

## Notes for the executor
- Tests stub `winproc.find_pids` + `subprocess.run` and fake `sys.frozen`/`executable`.
- The running exe still can't delete itself; the detached `cmd` rmdir (ADR-0005) stays.
