# ROADMAP

> Phases and their batches. Status per batch. Detail + acceptance live in the ADRs.
> Phases mirror `claude-resume-product-plan.md` §10.

## Phase 1 — Engine — COMPLETE (ADR-0001)
**Goal:** daemon loop, reset parser, state file, CLI; fire via `--continue`.

| # | Task | Status |
|---|------|--------|
| 1.1 | paths + config + state record | ✅ |
| 1.2 | reset parser (clock / relative / ISO) + tests | ✅ |
| 1.3 | fire path (`claude --continue` headless) | ✅ |
| 1.4 | CLI (status/report/queue/dir/fire-now/arm/clear/config) | ✅ |

## Phase 2 — Gating — COMPLETE (ADR-0001)
**Goal:** process detector + cwd capture; live-session gate; ARMED-waits-for-session.

| # | Task | Status |
|---|------|--------|
| 2.1 | Windows claude.exe detection (ctypes toolhelp) | ✅ |
| 2.2 | working-dir capture via PEB read | ✅ |
| 2.3 | daemon state machine WAITING/ARMED/FIRING + tests | ✅ |

## Phase 4 — UI — COMPLETE (ADR-0001)
**Goal:** local countdown page + live-session indicator.

| # | Task | Status |
|---|------|--------|
| 4.1 | stdlib status page + `/state` JSON | ✅ |

## Phase A — App lifecycle — COMPLETE (ADR-0003)
**Goal:** installed-feeling app; explicit start, background, single-instance.

| # | Task | Status |
|---|------|--------|
| A1 | extract `daemon.loop(cfg, stop)` from `run()` | ✅ |
| A2 | `runner.py` launch/attach/stop (`open`/`close`) | ✅ |
| A3 | ~~tray app~~ → replaced by terminal menu (Phase C) | ↩ |
| A4 | CLI `open`/`close`/`uninstall`; drop run-at-logon | ✅ |

## Phase C — Terminal menu UI — SUPERSEDED by ADR-0007
Built (ADR-0006), then replaced by the desktop window. `menu.py` removed.

## Phase D — Desktop GUI window — COMPLETE (ADR-0007)
**Goal:** a dedicated native window (Tkinter), not web/tray/terminal; stay light.

| # | Task | Status |
|---|------|--------|
| D1 | `runner` GUI support: `gui.pid`, launch/stop, single-instance | ✅ |
| D2 | `gui.py` Tkinter window: live status + all actions | ✅ |
| D3 | `open` → watcher + GUI; internal `_gui`; drop menu; spec +tkinter | ✅ |

## Phase 5 (partial) — Windows autostart — SUPERSEDED by ADR-0003
| # | Task | Status |
|---|------|--------|
| 5.1 | Task Scheduler / Startup-shim run-at-logon | ⛔ removed (no autostart; `open` starts it). Cleanup kept in `install_win.py` for old installs. |

## Phase 3 — Idle poll — COMPLETE (ADR-0002)
**Goal:** auto-detect the limited→available transition while you're away.

| # | Task | Status |
|---|------|--------|
| 3.1 | shared `is_limit_message` + `probe` module (no-window) | ✅ |
| 3.2 | `State.last_poll`; arm from probe in `daemon.tick` | ✅ |
| 3.3 | wire `poll_enabled`/`poll_interval_min` + `poll on\|off` CLI | ✅ |

## Phase 5 (rest) — Cross-platform — PLANNED (ADR-0004+)
| # | Task | Status |
|---|------|--------|
| 5.2 | macOS detection + tray + cwd | ⬜ |
| 5.3 | Linux detection + tray + cwd via `/proc` | ⬜ |
| 5.4 | single-file `.exe` bundle (PyInstaller) | ✅ (ADR-0005) |

## Phase B — Distribution — COMPLETE (ADR-0005)
**Goal:** one-line install, no Python/pip.

| # | Task | Status |
|---|------|--------|
| B1 | PyInstaller onefile `cloophole.exe` | ✅ |
| B2 | `install.ps1`/`uninstall.ps1` (irm \| iex) + PATH + frozen-aware launch | ✅ |
| B3 | release CI builds + attaches the exe on tag | ✅ |

## Phase H — Zero-quota limit hook — COMPLETE (ADR-0008)
**Goal:** auto-detect the limit without spending quota; replace the idle poll as the
default (poll stays opt-in). Supersedes ADR-0002 for everyday use.

| # | Task | Status |
|---|------|--------|
| H1 | `claude_hook` — settings install/uninstall + signal read/write | ✅ |
| H2 | daemon consumes the signal → WAITING (+ `hook_dir` fallback, B6) | ✅ |
| H3 | CLI `limit-signal`/`hook`; `open` registers + notice; uninstall removes; GUI drops poll checkbox | ✅ |

## Phase I — Clean uninstall — COMPLETE (ADR-0009)
**Goal:** no leftover/hanging processes after close/uninstall; remove the hook.

| # | Task | Status |
|---|------|--------|
| I1 | `runner.kill_all()` sweep by image name (excl. self, frozen-only) | ✅ |
| I2 | wire into `close` + `uninstall`; `uninstall` deregisters the hook | ✅ |
| I3 | `uninstall.ps1` kills by name + `hook off` + PATH/exe/data removal | ✅ |

## Phase J — Session tick boxes + GUI redesign — COMPLETE (ADR-0010)
**Goal:** see every detected session in the window, tick which to resume (default all),
and a modern look that never clips the list.

| # | Task | Status |
|---|------|--------|
| J1 | `state.excluded_dirs`; `_fire_dirs` = ticked live dirs; `_do_fire` no-op on empty | ✅ |
| J2 | GUI scrollable per-session checkboxes + all/none; resume fires ticked | ✅ |
| J3 | Visual polish: phase badge, bordered cards, button hover, bottom-pinned actions | ✅ |

## Phase 6 — Polish — PLANNED (ADR-0004)
| # | Task | Status |
|---|------|--------|
| 6.1 | version-tolerant limit-text patterns + corpus | ⬜ |
| 6.2 | structured logging + log rotation | ⬜ |
| 6.3 | config hot-reload | ⬜ |

## Backlog / deferred (open questions, plan §11)
- ~~Multiple live sessions: fire in all / most-recent / pinned dir?~~ **DECIDED:**
  fire in **all** live session dirs; `cloophole dir <path>` pins to one. (`detect_all`
  + `daemon._fire_dirs`.)
- Queue note: auto-capture from last prompt vs. stay manual? (now: manual) — would
  need a Claude Code hook, must respect the Golden Rule (no internal reads).
- Git Bash startup-shim install path as an alternative to Task Scheduler.
