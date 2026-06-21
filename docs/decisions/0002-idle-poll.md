# ADR-0002 — Idle quota poll

**Status:** Accepted — COMPLETE · 2026-06-22 · Builds on ADR-0001.

## Context
ADR-0001 learns the reset time only when you paste the limit text (`report`). When
you are away from the keyboard nothing arms cloophole, so a reset that lands while
you are gone is missed until you return. The product plan (§4 "Poll (idle)", §9.4)
calls for a gentle background probe that detects you are limited and parses the reset
time from that — without an API for the reset clock, and without violating the Golden
Rule (observe via the public CLI only).

## Decision & key rules (apply to every batch)
- **Probe via the public CLI only:** a tiny `claude -p` call. No internal-state reads.
- **Gentle:** probe at most every `poll_interval_min` (default 30), only while
  `WATCHING`, only when `poll_enabled` is true. Probing costs quota (§9.4).
- **Shared limit-detection:** one `is_limit_message()` helper used by both the probe
  and the fire's `still_limited` check, so they can never diverge (addresses BUGS B3
  drift risk; hardening the heuristic itself stays Phase 6).
- **State, not memory:** track `last_poll` in `state.json` so cadence survives restarts.
- Each batch ships a deterministic, offline test (probe stubbed — never hits network).

## Plan (batches)
- [x] **3.1 — shared limit detection + probe module.** `reset_parser.is_limit_message`;
  `probe.probe(cfg)` runs `claude -p` and returns `(limited, text)`. `fire` reuses the
  helper (parity preserved). Result: shipped.
- [x] **3.2 — arm from probe.** `State.last_poll`; `daemon.tick` probes in WATCHING when
  due, parses the reset, moves to WAITING. Result: shipped.
- [x] **3.3 — wire config.** `poll_enabled` / `poll_interval_min` gate cadence; `cloophole
  poll on|off` convenience command. Result: shipped.

## Acceptance
- ✅ With `poll_enabled=false`, `tick` never probes (default; no quota spend).
- ✅ With it on and due, a probe that reads as limited arms WATCHING → WAITING with the
  parsed reset.
- ✅ A probe before the interval elapses does not run.
- ✅ `fire.still_limited` and the probe use the same `is_limit_message`.
- ✅ Tests green offline; Golden Rule held (probe = public CLI only).

## Notes for the executor
- Sequence: 3.1 → 3.2 → 3.3.
- The limit-text heuristic remains text-based (BUGS B3); robustness corpus is Phase 6.
- Update STATUS + progress + DATA_MODEL (`last_poll`, new command) this phase.
