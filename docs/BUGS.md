# BUGS — known limitations & issues

> Log on sight. Each entry: what, impact, status, where.

## Open

### B1 — PEB cwd read is 64-bit only
`winproc.process_cwd` uses hard-coded 64-bit PEB/RTL_USER_PROCESS_PARAMETERS
offsets. A 32-bit `claude.exe` (or 32-bit Python reading a 64-bit target) yields no
cwd, so firing falls back to the configured `work_dir`.
**Impact:** low — Claude Code on Windows is 64-bit. **Status:** accepted.
**Where:** `cloophole/winproc.py`.

### B2 — Live gate can see cloophole's own fired process
The fire path spawns `claude -p --continue`, itself a `claude.exe`. While it runs,
`winproc.detect` would report a live session. Doesn't cause a wrong fire today (the
gate is checked before firing), but a future re-arm/poll loop could misread it.
**Impact:** low. **Status:** watch. **Where:** `cloophole/fire.py`, `daemon.py`.
**Idea:** exclude our own child PID from the gate.

### B3 — limit heuristic is text-based
`reset_parser.is_limit_message` flags a limit when text parses as a reset time AND
contains "limit"/"try again" (shared by `fire.still_limited` and `probe`). Wording
changes in Claude Code could miss it.
**Impact:** medium for robustness. **Status:** to harden in Phase 6 (ADR-0004).
**Where:** `cloophole/reset_parser.py`.

### B6 — fire may resume in an empty conversation (no cwd captured)
If NO live session cwd is readable, `--continue` runs in the daemon's inherited cwd
(e.g. the Startup dir), where there's no recent conversation — the resume does nothing
useful. (The "wrong folder among several sessions" half is fixed: cloophole now fires
in *all* live session dirs, and `cloophole dir` pins one — see ROADMAP backlog.)
**Impact:** low-medium (UX, only when PEB read fails — see B1). **Status:** open.
**Where:** `cloophole/daemon.py` (`_fire_dirs` None branch). **Idea:** require a pin
when no cwd is readable rather than firing blindly.

## Resolved
- **B4 — blank "claude" console window on fire** (user-reported 2026-06-22).
  Console-less `pythonw` spawning `claude.exe` made Windows allocate a blank console
  titled "claude". **Fix:** `subproc.run` applies `CREATE_NO_WINDOW` to all claude.exe
  calls (fire + probe); output is captured so no window is needed.
  RESOLVED 2026-06-22 (`cloophole/subproc.py`).
- **B5 — `cloophole install` "access is denied" (needed admin)** (user-reported
  2026-06-22). `schtasks /Create` required elevation. **Fix:** default install is now a
  user Startup-folder `.vbs` shim (no admin); Task Scheduler is opt-in (`install
  --task`). `install` also starts the daemon immediately (no reboot).
  RESOLVED 2026-06-22 (`cloophole/install_win.py`).
