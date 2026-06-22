# ADR-0006 — Terminal menu UI (drop web dashboard + tray)

**Status:** Accepted — COMPLETE · 2026-06-22 · Supersedes the web dashboard
(`ui.py`) and the system-tray app (`app.py`) from ADR-0003. Keeps ADR-0003's
`open`/`close`, single-instance, no-run-at-logon model.

## Context
The web dashboard (a local `http.server` page) and the pystray tray icon were both
rejected: the user wants the interface to be an interactive **terminal menu**, not a
web app or a GUI. The background watcher should still run detached; the menu just
views and controls it.

## Decision & key rules
- **UI = `menu.py`**, a stdlib terminal menu (clear-screen status header + numbered
  actions: fire now, set queue note, report limit, toggle poll, pin/clear dir, clear,
  refresh, stop daemon, quit). Blocking `input()`; quitting leaves the daemon running.
- **Remove** `ui.py` (http server), the `ui_enabled`/`ui_port` config, the daemon's
  UI thread, and `app.py` (tray) + the `pystray`/`Pillow`/`tkinter` deps. **Back to
  zero runtime deps.**
- **`open`** = start the detached background daemon if not running, then open the menu;
  **`menu`** = open the menu; **`close`** = stop the daemon. `runner.launch` now spawns
  the watcher daemon (`pythonw -m cloophole daemon`, or the frozen exe) hidden.
- The exe (ADR-0005) still bundles everything; spec drops the GUI hidden-imports.

## Plan (batches)
- [x] **M1 — menu module.** `menu.run()` status header + actions, stdlib only. Shipped.
- [x] **M2 — remove web + tray.** delete `ui.py`/`app.py`, drop deps + `ui_*` config +
  daemon UI hookup. Shipped.
- [x] **M3 — rewire CLI/runner.** `open`/`menu`/`close`; `runner.launch` → daemon;
  drop `ui`/`_app`. Shipped.

## Acceptance
- `cloophole open` starts the hidden daemon and shows the menu; closing the terminal
  leaves the daemon running; `cloophole open` again re-opens the menu (one daemon).
- No `http`/`pystray`/`Pillow` imports remain; `pip install` pulls no third-party deps.
- Menu actions drive the same `state.json` the daemon reads. Tests green.

## Notes for the executor
- Live-verified: menu renders, daemon launches detached, status shows running, close
  stops it. 25 tests. macOS/Linux menu works too (stdlib); detection is the gap.
