# ADR-0011 — Resume in a visible window (watch Claude work)

**Status:** Accepted — COMPLETE · 2026-06-23 · Refines the fire path (ADR-0001).

## Context
`fire()` ran `claude --continue -p <note>` **headless** (`CREATE_NO_WINDOW`, captured
output). It worked, but the user couldn't see what the resume did — it left mystery
untracked files in the repo with no idea what task Claude continued (user-reported). The
user asked to "drive my visible terminal." True keystroke-injection into the *existing*
REPL is forbidden by the Golden Rule, and is fragile on Windows (varies by terminal app,
steals focus). But the real need is **visibility**, not that exact window.

## Decision & key rules
- **Resume in its own visible window.** `fire.fire_visible(dir, note)` launches
  `claude --continue [prompt]` with `CREATE_NEW_CONSOLE` in the work dir, non-blocking.
  The user watches the resumed conversation live — every edit, the task it's continuing.
- **Still Golden-Rule-clean.** This acts only through the public `claude` CLI; it does
  NOT inject keystrokes into the user's existing REPL and does NOT read Claude internals.
  Visible ≠ scraping. (We rejected real REPL injection — fragile + crosses the line.)
- **Default on, both paths.** `config.resume_visible` (default `True`) governs the GUI
  "Resume" button **and** the daemon's auto-resume, so away-from-keyboard resumes are
  trackable too. `False` keeps the old headless behaviour (the only mode that can detect
  `still_limited` to re-arm).
- **Non-blocking.** `Popen` returns immediately — no 10s wait on the call; the GUI pops
  "Opened N Claude window(s)" at once.
- **Re-arm trade-off.** Visible mode can't read output, so it can't detect a
  still-limited fire to re-arm. The re-check probes (ADR-0008) confirm the reset *before*
  firing, so firing-while-limited is unlikely; if it happens, the visible window shows
  the user.

## Acceptance
- ✅ `fire_visible` launches `claude --continue` (+ note) in a new console in the dir,
  non-blocking; returns an error string only on launch failure.
- ✅ GUI "Resume" opens one window per ticked session and reports the count instantly.
- ✅ With `resume_visible=True` (default) the daemon opens visible resumes; with `False`
  it uses the headless engine (still_limited re-arm) — both covered by tests.

## Notes for the executor
- Opens a *new* window — the user's old, idle (limited) REPL is separate; both resume
  the same most-recent conversation via `--continue`. Fine in practice.
- The note is passed as a positional prompt to guide the resume; if the CLI ignores it,
  the conversation still resumes interactively.
