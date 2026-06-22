# STATUS — what's happening right now

> Single source of truth for the CURRENT moment. Update at the start and end of every
> session. History goes in `docs/progress/`, not here.

**Last updated:** 2026-06-22 (B8 fix — blank console window + clipped GUI buttons)

## Active task
**B8 fix — blank console behind GUI + clipped buttons — DONE (branch
`fix/gui-window-console-and-size`).** `_spawn` combined `DETACHED_PROCESS |
CREATE_NO_WINDOW`; Win32 ignores no-window when detached, so the console exe showed a
blank terminal (surfaced once B7 let the GUI live). Fix: CREATE_NO_WINDOW alone +
SW_HIDE. Also the 440x430 window clipped its 6 buttons → now clamps to
`winfo_reqheight`. 29 tests; window verified live from source.
(Prior: B7 — no window at all — fixed via stdio→DEVNULL. Phase D GUI already on main.)

## Phase
Done on Windows: 1–4 (engine/gating/poll), A (app lifecycle), B (distribution: exe +
`irm` installer, build-on-push CI), C (terminal menu — superseded), **D (desktop GUI
window, ADR-0007)**. UI is a Tkinter window; install is one PowerShell line; auto-watch
on by default. 27 tests green, all on per-feature branches.

## Next action (whoever picks this up)
- Cross-platform: mac/Linux process detection + cwd (`/proc`) + GUI check, new ADR.
- Phase 6 polish (version-tolerant limit patterns, log rotation, config hot-reload).
- Optional: onedir build (faster startup, no `_MEI` temp) if size allows.

## Verify before trusting (live, this machine)
- After a fresh install, **rebuild needed**: the released exe predates B7 — CI rebuilds
  on push to main; reinstall via `irm .../install.ps1 | iex` to get the windowed fix.
- `cloophole open` → window must appear. Start a real `claude` session → window's
  "Claude open now" should flip to **yes** and show its folder (proves `winproc` PEB).
- 27→28 offline tests cover logic only; the live fire path still needs a manual smoke
  (`fire-now`) — see B2/B6.

## Watch / before launch
- `winproc.py` PEB offsets are **64-bit only** (BUGS B1).
- The fire path spawns its own `claude.exe`; live gate can momentarily see it (BUGS B2).
- A resume can land in the wrong/empty conversation if no session cwd was captured
  (BUGS B6) — tied to plan §11 "which directory".
- Headless fire/probe require `permission_mode=acceptEdits` or they block.
