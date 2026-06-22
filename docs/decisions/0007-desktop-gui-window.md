# ADR-0007 — Dedicated desktop window (Tkinter)

**Status:** Accepted — COMPLETE · 2026-06-22 · Supersedes ADR-0006 (terminal menu).
Keeps the background-watcher + `open`/`close` model from ADR-0003/0006.

## Context
The user wants a dedicated app **window** (a GUI), not a web page and not a terminal
menu. It must stay lightweight (the exe was just slimmed to ~4 MB), so a heavy toolkit
(Qt/PySide, +40-60 MB) is out.

## Decision & key rules
- **UI = a Tkinter window** (`gui.py`). Stdlib only → no third-party deps; exe stays
  small (~11 MB before UPX). Plain-language status, 1 s auto-refresh, buttons for every
  action (Resume now / Enter limit time / Choose folder / Reset status / Stop / Close;
  a note field + an Auto-detect checkbox).
- **`open`** = ensure the background watcher daemon is running, then spawn the GUI
  **detached** (`pythonw -m cloophole _gui`, or the frozen exe) so it survives the
  launching terminal. **Single-instance** via `gui.pid` (`runner.is_gui_running`).
- **Remove the terminal menu** (`menu.py`). `close` stops the watcher and the window;
  closing the window leaves the watcher running.
- The GUI is a thin view/controller over `state.json`; the watcher stays a separate
  process. Golden Rule unchanged (CLI + OS inspection only).
- PyInstaller spec re-includes `tkinter` (was excluded during the slim pass).

## Plan (batches)
- [x] **G1 — runner GUI support.** `gui.pid`, `is_gui_running`/`launch_gui`/`stop_gui`,
  detached spawn. Shipped.
- [x] **G2 — gui.py window.** Tk window, auto-refresh, all actions. Shipped.
- [x] **G3 — CLI + build.** `open` → daemon + GUI; internal `_gui`; drop `menu`/menu.py;
  spec re-includes tkinter. Shipped.

## Acceptance
- `cloophole open` opens a native window; closing the terminal leaves it up; a second
  `open` doesn't open a second window. `close`/Stop stops the watcher.
- Window shows live status and every action works; no web, no tray.
- Exe bundles tkinter and runs the window (verified). Tests green.

## Notes for the executor
- Verified from source and from the onefile exe (window opens, `gui.pid` tracked).
- Headless/SSH: no window — use `cloophole daemon` + `status`.
