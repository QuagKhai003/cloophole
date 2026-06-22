# STATUS — what's happening right now

> Single source of truth for the CURRENT moment. Update at the start and end of every
> session. History goes in `docs/progress/`, not here.

**Last updated:** 2026-06-22 (terminal-menu UI — ADR-0006; dropped web dashboard + tray)

## Phase
Phases 1–4 + **A (app lifecycle)** + **B (distribution)** + **C (terminal menu UI,
ADR-0006)** are **COMPLETE** on Windows. UI is now a terminal menu (`cloophole open`)
— web dashboard + tray removed, back to **zero runtime deps**. 25 tests green. Next:
cross-platform (mac/Linux detection), then Phase 6 polish.
Branch: feature work now on per-feature branches (e.g. `feat/terminal-menu`).

## Active task
**Phase C — terminal menu UI (ADR-0006) — DONE (branch `feat/terminal-menu`).**
Replaced the web dashboard + tray with `menu.py` (stdlib terminal menu: status header
+ fire/queue/report/poll/dir/clear/stop actions). Removed `ui.py`, `app.py`, the
`pystray`/`Pillow` deps, `tkinter`, and the `ui_enabled`/`ui_port` config + daemon UI
hookup → back to zero runtime deps. `runner.launch` now starts the background watcher
daemon; CLI is `open` (daemon + menu) / `menu` / `close`. 25 tests green; menu render +
detached-daemon lifecycle verified live. **Pending:** merge `feat/terminal-menu` → main.
**NEXT:** cross-platform detection (mac/Linux), or Phase 6 polish.

## Next action (whoever picks this up)
- **Before the `irm` one-liner works:** repo set to `QuagKhai003/cloophole` in
  scripts/README — now just push to GitHub and cut one `v*` tag (CI builds the exe).
- Cross-platform: mac/Linux process detection + tray + cwd (`/proc`), new ADR.
- Phase 6 polish (version-tolerant limit patterns, log rotation, config hot-reload).

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
