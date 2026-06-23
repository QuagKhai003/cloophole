# ADR-0012 — Type the resume into the user's existing Claude session

**Status:** Accepted — COMPLETE · 2026-06-23 · Revises the Golden Rule (CLAUDE.md);
supersedes ADR-0011's window default.

## Context
Headless resume (ADR-0001) and visible-window resume (ADR-0011) both run a *separate*
`claude --continue`. The user doesn't want that: they keep one interactive session open
per project (e.g. `claude --dangerously-skip-permissions` in bull_buddy) and want
cloophole to **type the resume note into that existing session** — not open a new window
or a second process. Their reason: a separate resume hid what Claude was doing (mystery
untracked files).

This is keystroke injection into the live REPL, which the **original Golden Rule
forbade**. The project owner explicitly decided to lift that ban.

## Decision & key rules
- **Golden Rule revised.** The *read* ban stands (no transcripts/internal state; observe
  only via OS process inspection; "what to resume" = the user's note). The *action* side
  now permits typing the note into the user's own session.
- **`inject` is the default `resume_mode`.** `fire.fire_inject(dir, note)` finds the
  `claude.exe` whose cwd matches `dir` (`winproc.session_pids`), `AttachConsole`s to it,
  and `WriteConsoleInput`s the note + Enter (`inject.send_text`). No new window, no focus
  steal.
- **Three modes** (`config.resume_mode`): `inject` (default), `window`
  (`claude --continue` in a visible console, ADR-0011), `headless` (the original,
  capture + `still_limited` re-arm). GUI button and daemon auto-resume both dispatch via
  `fire.resume()`.
- **Note, not transcript.** We send the user's queued note (or the fallback) — we never
  read what Claude was doing; the user supplies the intent.
- **Windows-first.** `inject` uses Win32 console APIs; mac/Linux (`tmux send-keys`,
  AppleScript) is future work. Best-effort: any failure returns an error string and the
  caller reports it.
- `cloophole send "<text>"` types into every live session — for quick testing.

## Acceptance
- ✅ `fire_inject` targets the pid whose folder matches and sends via `inject.send_text`;
  returns a clear error when no session matches that folder.
- ✅ `resume()` dispatches on `resume_mode`; daemon `_do_fire` uses it for inject/window,
  keeps the headless engine (re-arm) for `headless`.
- ✅ Tests: inject dir→pid matching (send stubbed); default mode dispatches per dir;
  headless engine tests pinned to `resume_mode="headless"`. The raw `WriteConsoleInput`
  path is verified by the user (no console in CI).

## Notes for the executor
- `inject.send_text` tries two paths: (1) classic console — `AttachConsole(pid)` +
  `WriteConsoleInput` (works for conhost); (2) **clipboard paste** — find the hosting
  terminal's window by walking `pid`'s ancestors (`winproc.all_procs` + `EnumWindows`),
  set the clipboard, `SetForegroundWindow`, `SendInput` Ctrl+V + Enter. Windows Terminal
  / VS Code / ConPTY need path 2 (the user confirmed WriteConsoleInput fails on WT).
- **Limits:** paste hits the terminal's ACTIVE tab — a session in a background tab of a
  multi-tab window can't be singled out. Background callers (daemon) may be denied
  `SetForegroundWindow` by the OS focus lock; the GUI button (already foreground) is fine.
