# ADR-0008 — Zero-quota limit auto-detect via a Claude Code hook

**Status:** Accepted — COMPLETE · 2026-06-23 · Supersedes the idle poll (ADR-0002) as
the default auto-detect; builds on ADR-0001.

## Context
ADR-0002's idle poll auto-detects the limit by sending a `claude -p` probe every
`poll_interval_min`. Each probe is a real Claude request, so an idle machine quietly
spends the user's quota — it burns the very resource cloophole exists to protect
(BUGS B9, user-reported "drained my usage while doing nothing"). We need auto-detect
that costs **nothing** and still honors the Golden Rule (no internal/transcript reads).

Claude Code exposes a **`StopFailure`** hook event with matcher **`rate_limit`** that
fires exactly when a turn ends because of a usage limit. A hook is a local command
Claude runs — it makes **no** API call — so it costs zero quota, and it fires only on
a real limit, not on normal turns. This is the public extension mechanism (the user's
own config), not a peek at Claude's internals.

## Decision & key rules
- **Detect by being told, not by asking.** Register a `StopFailure`/`rate_limit` hook
  that runs `cloophole limit-signal`. No probing by default.
- **Signal file, not memory.** `limit-signal` writes `~/.cloophole/limit-signal.json`
  (`ts`, `cwd`, `source`); the daemon watches it (filesystem only, zero quota).
- **Estimate the reset.** `StopFailure` carries no reset text (that's transcript-only,
  off-limits), so on a signal the daemon arms `WAITING` with `now + limit_window_hours`
  (default 5). Exact minute stays manual via `report` / "Enter limit time".
- **Use the hook's `cwd`.** Stored as `state.hook_dir`; `_fire_dirs` falls back to it
  when no live session cwd is readable — also mitigates B6.
- **Own only our entry.** Install/uninstall merge/prune just the `limit-signal` hook in
  the user's `settings.json`; foreign hooks are untouched. `open` installs it (with a
  printed notice), `uninstall` and `hook off` remove it.
- **Poll stays, but opt-in.** The `claude -p` probe remains available via `cloophole
  poll on` for anyone who wants it; it is OFF by default (B9) and gone from the GUI.
- Deterministic offline tests: settings I/O on a temp dir, signal round-trip, daemon
  consume with the detector stubbed. No Claude is ever invoked.

## Plan (batches)
- [x] **8.1 — `claude_hook` module:** settings install/uninstall/installed +
  record/read/clear signal. Result: shipped.
- [x] **8.2 — daemon consume:** `tick` arms WAITING from a signal (+ `hook_dir`);
  `_fire_dirs` hook-dir fallback; `state.hook_dir`, `config.limit_window_hours`.
- [x] **8.3 — CLI + wiring:** `limit-signal` (hook target), `hook on|off`; `open`
  auto-registers + notice; `uninstall` deregisters. GUI shows hook on/off, drops the
  poll checkbox.

## Acceptance
- ✅ `install_hook` is idempotent and leaves foreign hooks intact; `uninstall_hook`
  removes only ours and prunes empties.
- ✅ `limit-signal` parses the hook's stdin JSON, records the `cwd`, and never raises.
- ✅ A signal moves WATCHING/ARMED → WAITING with an estimated reset and is consumed.
- ✅ `_fire_dirs` uses `hook_dir` only when there's no pin and no live cwd.
- ✅ Tests green offline; Golden Rule held (hook = public config; no internal reads).

## Notes for the executor
- The hook loads when Claude Code (re)starts — tell users to restart Claude once.
- `StopFailure` is observational (can't block); that's fine — we only need the signal.
- Update STATUS + progress + DATA_MODEL (`hook_dir`, `limit_window_hours`, signal file,
  new commands) + ROADMAP + BUGS B9 (now resolved) this phase.
