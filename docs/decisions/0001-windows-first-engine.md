# ADR-0001 — Windows-first engine, gating, UI, installer

**Status:** Accepted — COMPLETE · 2026-06-22 · Foundation ADR.

## Context
cloophole must auto-resume Claude Code work when the usage quota resets, with no API
for the reset clock and no safe way to read Claude Code's internal state. We build
Windows-first (the user's platform) and need: a way to know the reset time, a way to
know a session is live and where it runs, and a way to resume without disturbing the
visible REPL. Plan phases 1, 2, 4, and the Windows slice of 5.

## Decision & key rules (apply to every batch)
- **Golden Rule:** never touch Claude Code internals or its REPL. Observe via OS
  process inspection; act only via the public `claude` CLI.
- **Zero third-party runtime deps.** Stdlib + `ctypes` (no psutil).
- **Durable state on disk** (`~/.cloophole/state.json`) — CLI, daemon, UI all read it.
- **Resume = `claude -p --continue --permission-mode acceptEdits`** in the recorded
  directory; never keystroke injection.
- Every logic change ships a deterministic offline test.

## Plan (batches)
- [x] **1.1 — paths + config + state record.** `~/.cloophole/` locations, JSON config
  with defaults, `State` dataclass + load/save. Result: shipped.
- [x] **1.2 — reset parser.** clock / relative / ISO → aware UTC; 8 tests incl.
  garbage→None. Result: shipped.
- [x] **1.3 — fire path.** headless `--continue`, `still_limited` detection,
  `FireResult`. Result: shipped.
- [x] **1.4 — CLI.** status/report/queue/dir/fire-now/arm/clear/config/daemon/ui/
  install/uninstall. Result: shipped.
- [x] **2.1 — Windows process detection.** ctypes Toolhelp snapshot of `claude.exe`.
  Result: shipped, verified against real process.
- [x] **2.2 — working-dir capture.** PEB → ProcessParameters → CurrentDirectory read
  (64-bit). Result: shipped, returned correct cwd live.
- [x] **2.3 — state machine.** WAITING/ARMED/FIRING transitions in `daemon.tick`;
  4 tests with detect/fire stubbed. Result: shipped.
- [x] **4.1 — UI.** stdlib status page + `/state` JSON, self-refresh. Result: shipped.
- [x] **5.1 — Windows installer.** Task Scheduler run-at-logon via `schtasks`.
  Result: shipped.

## Acceptance
- ✅ `python -m cloophole status/report/queue` flow works; state persists.
- ✅ Process gate finds the real `claude.exe` and reads its cwd.
- ✅ 12 offline tests green (`python -m pytest -q`).
- ✅ UI serves `/` and `/state` on the configured port.
- ✅ Golden Rule held: no internal-state reads anywhere; resume only via the CLI.

## Notes for the executor
- Known limitations logged in `docs/BUGS.md` (B1 64-bit PEB, B2 own-process gate,
  B3 text heuristic).
- Next: ADR-0002 (idle poll), batches 3.1–3.3.
