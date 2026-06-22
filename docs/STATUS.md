# STATUS — what's happening right now

> Single source of truth for the CURRENT moment. Update at the start and end of every
> session. History goes in `docs/progress/`, not here.

**Last updated:** 2026-06-22 (desktop tray app — ADR-0003; `open`/`close`; no run-at-logon)

## Phase
Phases 1–4 + **Phase A (desktop tray app, ADR-0003)** are **COMPLETE** on Windows.
Run-at-logon was removed (superseded by `cloophole open`). 26 tests green. Next:
cross-platform (mac/Linux tray + detection) or a `.exe` bundle, then Phase 6 polish.

## Active task
**Phase A — desktop tray app (ADR-0003) — DONE.**
New `app.py` (pystray tray: menu, dynamic icon/title, toast on fire, tkinter queue
dialog) + `runner.py` (`open`=launch-or-attach, `close`=stop). `daemon` refactored to
`claim_pid`/`loop`/`start_ui` so the tray runs the watcher in a thread. CLI reworked to
`open`/`close`/`uninstall` (+ internal `_app`); logon `install`/`start`/`stop` removed;
`install_win.py` demoted to legacy cleanup. Deps added: pystray, Pillow. 26 tests green;
full open→attach→close lifecycle verified live.
**NEXT:** cross-platform tray/detection, or PyInstaller `.exe`, or Phase 6 polish.

## Next action (whoever picks this up)
- Cross-platform: mac/Linux process detection + tray + cwd (`/proc`), new ADR.
- Or package a single-file `.exe` (PyInstaller) so users don't need Python.
- Or Phase 6 polish (version-tolerant limit patterns, log rotation, config hot-reload).

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
