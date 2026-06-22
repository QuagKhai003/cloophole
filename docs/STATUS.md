# STATUS — what's happening right now

> Single source of truth for the CURRENT moment. Update at the start and end of every
> session. History goes in `docs/progress/`, not here.

**Last updated:** 2026-06-22 (dedicated desktop window — Tkinter, ADR-0007; replaced terminal menu)

## Active task
**Phase D — desktop GUI window (ADR-0007) — DONE (branch `feat/gui-window`).**
Replaced the terminal menu with `gui.py` (Tkinter window: live status, note field,
auto-detect checkbox, buttons for resume/limit/folder/reset/stop). `runner` gained
`gui.pid` + `is_gui_running`/`launch_gui`/`stop_gui`; `open` now starts the watcher +
spawns the GUI detached (single-instance); removed `menu.py`/`menu` cmd; spec
re-includes tkinter. Exe ~11 MB pre-UPX. 27 tests; verified window from source + exe.
**Pending:** merge `feat/gui-window` → main.

## Phase
Done on Windows: 1–4 (engine/gating/poll), A (app lifecycle), B (distribution: exe +
`irm` installer, build-on-push CI), C (terminal menu — superseded), **D (desktop GUI
window, ADR-0007)**. UI is a Tkinter window; install is one PowerShell line; auto-watch
on by default. 27 tests green, all on per-feature branches.

## Next action (whoever picks this up)
- Cross-platform: mac/Linux process detection + cwd (`/proc`) + GUI check, new ADR.
- Phase 6 polish (version-tolerant limit patterns, log rotation, config hot-reload).
- Optional: onedir build (faster startup, no `_MEI` temp) if size allows.

## Watch / before launch
- `winproc.py` PEB offsets are **64-bit only** (BUGS B1).
- The fire path spawns its own `claude.exe`; live gate can momentarily see it (BUGS B2).
- A resume can land in the wrong/empty conversation if no session cwd was captured
  (BUGS B6) — tied to plan §11 "which directory".
- Headless fire/probe require `permission_mode=acceptEdits` or they block.
