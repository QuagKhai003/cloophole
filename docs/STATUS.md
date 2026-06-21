# STATUS — what's happening right now

> Single source of truth for the CURRENT moment. Update at the start and end of every
> session. History goes in `docs/progress/`, not here.

**Last updated:** 2026-06-22 (one-command no-admin install; single-instance daemon; git; multi-dir fire; Phase 3)

## Phase
Phases 1, 2, 3, 4, and 5.1 (Windows) are **COMPLETE**. Engine, gating, idle poll, UI,
and the Windows installer all work; verified against the real `claude.exe`. 17 tests
green. Next planned work is **Phase 5 (rest) — cross-platform** (ADR-0003) or Phase 6.

## Active task
**Phase 3 idle poll (ADR-0002) — DONE + user-feedback fixes — DONE.**
Added `probe.py` (no-window `claude -p` probe), shared `reset_parser.is_limit_message`
(reused by `fire`), `State.last_poll`, the WATCHING poll branch in `daemon.tick`, and
`cloophole poll on|off`. Reworked `install_win.py`: **Startup-shim default (no admin)**,
Task Scheduler opt-in (`install --task`), `start`/`stop`, and `subproc.run`
(`CREATE_NO_WINDOW`) so firing no longer pops a blank "claude" window. 17 tests green.
**NEXT:** ADR-0003 cross-platform (mac/Linux) OR Phase 6 polish.

## Next action (whoever picks this up)
- **User must re-cut their install** (see "Watch" below) to drop the old admin task.
- Next feature work: ADR-0003 (mac launchd / Linux systemd-user + `/proc` cwd) per
  ROADMAP 5.2–5.4; or Phase 6 polish (version-tolerant patterns, log rotation).

## Watch / before launch
- **Migrating the user's existing install:** just re-run `cloophole install` (no admin).
  It stops the old daemon, best-effort drops the leftover admin task, writes the shim,
  and restarts. If the admin task can't be deleted it's harmless — the daemon is now
  single-instance (`daemon._already_running`), so no double-fire. (Optional one-time
  cleanup, elevated: `schtasks /Delete /TN cloophole /F`.)
- `winproc.py` PEB offsets are **64-bit only** (BUGS B1).
- The fire path spawns its own `claude.exe`; live gate can momentarily see it (BUGS B2).
- A resume can land in the wrong/empty conversation if no session cwd was captured
  (BUGS B6) — tied to plan §11 "which directory".
- Headless fire/probe require `permission_mode=acceptEdits` or they block.
