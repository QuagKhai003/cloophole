# ADR-0010 — Per-session tick boxes choose where to resume

**Status:** Accepted — COMPLETE · 2026-06-23 · Refines ADR-0007 (window) + the
multi-dir fire (ROADMAP backlog).

## Context
cloophole fires `--continue` in **every** live session dir, or a single pinned
`work_dir`. The user wants finer control from the window: see each detected Claude
session and **tick which ones** should be resumed, with **all ticked by default**. The
old GUI also hid the session list behind the buttons and looked unpolished.

## Decision & key rules
- **Tick boxes drive fire targets.** Each detected session (a live `claude.exe` cwd,
  named by folder) gets a checkbox; ticked = resume there. Default all ticked.
- **Store the exception, not the selection.** `state.excluded_dirs` holds the dirs the
  user **un-ticked**. New/unknown sessions are therefore ticked by default with no
  migration. `_fire_dirs` (no pin) returns `live_dirs − excluded_dirs`.
  - Un-tick everything → fire **nowhere** (`_do_fire` no-ops and logs).
  - A `work_dir` **pin** still overrides the tick boxes (advanced/explicit).
- **OS inspection only.** Sessions are named by **folder** (`Path(cwd).name`) — session
  ids are Claude-internal and off-limits (Golden Rule). The list comes from the
  daemon's `state.live_dirs`; the GUI never inspects processes itself.
- **List can't hide.** The session list is a scrollable canvas (bounded height); the
  action buttons are bottom-pinned; the window fits its content.
- **Polish** (no behavioural impact): phase badge colour, cards with borders, hover on
  buttons, section headers, a primary "Resume ticked sessions" button, `all`/`none`
  quick toggles. Stdlib `tkinter` only (no new deps; web design skills N/A).

## Acceptance
- ✅ `_fire_dirs` excludes un-ticked dirs; `[]` when all un-ticked; pin still wins.
- ✅ `_do_fire` no-ops on empty targets (no spurious FIRING).
- ✅ Default (no `excluded_dirs`) keeps the old "fire in all live dirs" behaviour.
- ✅ GUI imports clean; list scrolls; buttons never clipped. (Window visuals verified
  by the user on the frozen exe — no display in CI.)

## Notes for the executor
- `excluded_dirs` is a list of absolute cwds; compared by exact string (same form as
  `live_dirs`). Update DATA_MODEL + ROADMAP + STATUS this phase.
- GUI run() builds widgets then `mainloop()`; it can't be unit-tested headless, so keep
  logic (`_fire_dirs`, excluded handling) in daemon/state where tests can reach it.
