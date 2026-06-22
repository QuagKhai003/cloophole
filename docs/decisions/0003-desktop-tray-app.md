# ADR-0003 — Desktop tray app (no terminal, no browser, no logon)

**Status:** Accepted — COMPLETE · 2026-06-22 · Builds on ADR-0001/0002. Supersedes
the run-at-logon installer from ADR-0001 §5.1 (removed).

## Context
cloophole should feel like an installed app, not a CLI + browser page. User flow:
clone → run the README install command → `cloophole open` (from any directory) shows
a **system-tray app**; it keeps running in the background even if the terminal closes;
running `open` again re-attaches to the same instance; it stops only via the tray Quit
item or `cloophole close`; `cloophole uninstall` stops everything then removes. No
run-at-logon (explicitly dropped).

## Decision & key rules (apply to every batch)
- **One background process** = tray icon (main thread) + watcher loop + UI server
  (daemon threads). Single-instance via `daemon.pid` (`winproc.pid_alive`).
- **`open` is launch-or-attach:** if already running, don't spawn a second; surface the
  existing one. Detached + hidden (`pythonw`), survives the launching terminal.
- **Stop is explicit only:** tray Quit or `cloophole close`. Nothing auto-stops it.
- **Durable state unchanged:** the app is a face over `state.json`; `open` after a crash
  resumes from disk. Golden Rule still holds (CLI + OS inspection only).
- **GUI deps isolated:** `pystray`+`Pillow` imported only by the tray app; the CLI,
  daemon, parser, fire, probe stay importable without them. Text input via stdlib
  `tkinter`.

## Plan (batches)
- [x] **A1 — loop refactor.** `daemon.loop(cfg, stop)` + `claim_pid`/`release_pid`/
  `start_ui`; `run()` keeps foreground behaviour. Shipped.
- [x] **A2 — process runner.** `runner.py`: `is_running()`/`launch()`/`stop()`, pid-aware.
  Shipped; logon install code demoted to legacy cleanup.
- [x] **A3 — tray app.** `app.py`: dynamic title/icon, Open dashboard, Fire now, Idle
  poll toggle, Queue note (tkinter), Quit; toast on fire + start hint. Shipped.
- [x] **A4 — CLI rewrite.** `open`/`close`/`uninstall` + internal `_app`; logon commands
  dropped; `daemon` kept for headless. README updated. Shipped.

## Acceptance
- `cloophole open` from any cwd launches the tray; closing the terminal leaves it up.
- A second `open` does not create a second instance.
- Tray Quit and `cloophole close` both stop it; `uninstall` stops + cleans.
- CLI/daemon still import and run with pystray/Pillow absent (headless fallback).
- Tests green offline (runner pid logic + icon image), Golden Rule held.

## Notes for the executor
- A single-file `.exe` bundle (PyInstaller) is a later option; pip install is the
  current install path. Sequence A1 → A2 → A3 → A4.
