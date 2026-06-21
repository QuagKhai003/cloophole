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

## Phase 5 (partial) — Windows installer — COMPLETE (ADR-0001, hardened post-feedback)
| # | Task | Status |
|---|------|--------|
| 5.1 | Task Scheduler run-at-logon install/uninstall | ✅ |
| 5.1a | Startup-shim install (no admin) as default + start/stop + no-window fire | ✅ |

## Phase 3 — Idle poll — COMPLETE (ADR-0002)
**Goal:** auto-detect the limited→available transition while you're away.

| # | Task | Status |
|---|------|--------|
| 3.1 | shared `is_limit_message` + `probe` module (no-window) | ✅ |
| 3.2 | `State.last_poll`; arm from probe in `daemon.tick` | ✅ |
| 3.3 | wire `poll_enabled`/`poll_interval_min` + `poll on\|off` CLI | ✅ |

## Phase 5 (rest) — Cross-platform — PLANNED (ADR-0003)
| # | Task | Status |
|---|------|--------|
| 5.2 | macOS detection (`launchd`) + cwd | ⬜ |
| 5.3 | Linux detection (`systemd --user`) + cwd via `/proc` | ⬜ |
| 5.4 | `install.py` / `uninstall.py` platform dispatch | ⬜ |

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
