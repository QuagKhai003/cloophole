# STATUS — what's happening right now

> Single source of truth for the CURRENT moment. Update at the start and end of every
> session. History goes in `docs/progress/`, not here.

**Last updated:** 2026-06-23 (limit re-check probes + fix Resume-ticked firing)

## Active task
**Limit re-check + Resume fix — DONE on `main`, pending CI + user verify.**
(1) B17: "Resume ticked sessions" fired nothing — it read raw `live_dirs` not the sticky
ticked list; now fires the displayed-ticked folders. (2) Re-check: WAITING schedules two
probes (`recheck_at`, ~detection+10min and reset−10min) to confirm the estimated limit
is real — a clear probe resumes early (catches a plan upgrade that reset early), a
still-limited probe refines the estimate. Config `recheck_after_min`/`recheck_before_min`.
47 tests. (Flicker B13/B14/B16 + open self-kill B15 all resolved.)

## (prior) Active task
**B16 fix — residual session-list flicker — DONE on `main`, pending CI + user verify.**
A single session's PEB folder read flaking for a tick dropped it from `live_dirs` until
the next 15s tick. GUI now keeps each folder sticky ~22 refreshes after last seen (>
the tick), and `winproc.detect_all` retries the read once. 44 tests. With B15 (open no
longer self-kills) + B13/B14, the list should now be stable.

## (prior) Active task
**B15 fix — `cloophole open` showed no window again — DONE on `main`, pending CI +
user verify.** B14's `kill_all` in `open` tree-killed the PyInstaller bootloader parent
(`/T`), cascading to the open process itself before it launched the GUI. Fix:
`winproc.list_procs` exposes `(pid, ppid)`; `kill_all` skips self AND its bootloader
parent. Clean-restart on `open` + flicker fixes (B13/B14) now actually take effect.
44 tests. Foreground `_gui` confirmed the GUI is fine.

## (prior) Active task
**B14 fix — flicker from duplicate/orphan daemons — DONE on `main`, pending CI +
user verify.** B13's smoothing only covered one daemon; an orphan from an older build
kept writing empty `live_dirs`. Fix: `cloophole open` clean-restarts (stop+kill_all
then launch → one current daemon), and the GUI holds the last good list ~8 refreshes
before showing empty. 44 tests. Existing orphans clear with a one-time
`Get-Process cloophole | Stop-Process -Force`.

## (prior) Active task
**B13 fix — GUI flicker + empty card — DONE on `main`, pending CI + user verify.**
Daemon keeps last good `live_dirs` on a transient empty PEB read (clears only when no
session is live); GUI rebuilds rows only when the sorted set of folders changes; the
big countdown label is packed only when there's a reset (kills the empty gap). 43 tests.
Tick-box selection (ADR-0010) confirmed working in the user's screenshot.

## (prior) Active task
**Session tick boxes + GUI redesign (ADR-0010) — DONE on `main`, pending CI + user
verify.** Detection confirmed working (folders read: cloophole, bull-buddy). GUI now
lists each detected session with a checkbox (default all ticked; `state.excluded_dirs`
stores un-ticks), in a scrollable card so it never hides behind the buttons; "Resume"
fires only the ticked sessions; `_fire_dirs` honours the ticks (pin still overrides).
Refreshed visuals (phase badge, bordered cards, hover, all/none toggles). 42 tests.
NEXT: CI build; user verifies the list + tick→resume + look. Then Phase 6.

## (prior) Active task
**Clean uninstall (ADR-0009) — DONE on `main`, pending CI build + user verify.**
`runner.kill_all()` sweeps every `cloophole.exe` by name (excl. self, frozen-only),
wired into `close` + `uninstall`; uninstall also deregisters the rate-limit hook;
`uninstall.ps1` kills by name + `hook off` + removes PATH/exe/data. 39 tests.
NEXT: one CI build covers the GUI/hook polish AND this; user verifies window fit +
session list + hook, then a clean uninstall leaves nothing behind. Then Phase 6.

## (prior) Active task
**GUI polish + hook (ADR-0008) — DONE on `main`, pending CI build + user verify.**
Hook auto-detect shipped (poll checkbox gone). GUI now lists detected Claude sessions
by folder name (`state.live_dirs`, written by the daemon), pins the action buttons to
the window bottom, and fits the window to its content so nothing clips (the user had to
resize before). 37 tests. NEXT: trigger one CI build; user reinstalls + verifies
window fit + session list + `hook on` status. Then: clean-uninstall hardening (their
other ask), then Phase 6 polish.

## (prior) Active task
**ADR-0008 — zero-quota limit auto-detect via Claude hook — DONE (branch
`feat/limit-hook`), pending GUI-polish branch + CI build.** `claude_hook.py` registers
a `StopFailure`/`rate_limit` hook that runs `cloophole limit-signal`; the daemon
watches the signal file and arms WAITING (est. `limit_window_hours`, default 5) with
the hook's `cwd` as a fire fallback (B6). `open` auto-registers + prints a notice;
`uninstall`/`hook off` remove it. GUI's poll checkbox replaced by a hook on/off line.
Poll stays opt-in via `cloophole poll on`. 36 tests. NEXT: GUI session list + window
fit (branch `feat/gui-sessions-and-fit`), then one CI build for the user to verify.

## (prior) Active task
**B11 fix — `cloophole open` shows no window — DONE (branch
`fix/onefile-self-spawn-env`), awaiting user verify.** The frozen exe spawning itself
let the child inherit `_MEIPASS2`/`_PYI_*`, so it bound to the parent's `_MEI` temp
(deleted on exit) and couldn't load tcl/tk → no Tk window. Proven by: a python-parent
spawn with identical flags DID show the window. Fix: strip `_MEI*`/`_PYI*` from the
child env in `runner._spawn`. Also kills the `_MEI` cleanup warning. 30 tests.
The window itself (B7/B8/B10) is already confirmed working via the foreground `_gui`.

## (prior) Active task
**B10 fix — GUI opened hidden (no window) — DONE (branch
`fix/gui-window-hidden-swhide`), awaiting user verify.** B8's anti-console
`STARTUPINFO SW_HIDE` also hid the Tk window (nCmdShow=SW_HIDE). Fix: `CREATE_NO_WINDOW`
alone — no console, window shows. Can only be confirmed on the frozen exe (source uses
windowless pythonw), so the USER builds/installs and reports. 29 tests.

## (prior) Active task
**B9 mitigation — idle probe spent quota in the background — DONE (branch
`fix/poll-off-by-default`).** `poll_enabled` now defaults **False**; the `claude -p`
probe is opt-in only. GUI checkbox warns it costs usage. Tests updated. **Next, real
fix:** replace polling with a Claude Code **`StopFailure`/`rate_limit` hook** (zero
quota, Golden-Rule clean; hook `cwd` also fixes B6) — needs a new ADR. See BUGS B9.

## (prior) Active task
**B8 fix — blank console behind GUI + clipped buttons — DONE (branch
`fix/gui-window-console-and-size`).** `_spawn` combined `DETACHED_PROCESS |
CREATE_NO_WINDOW`; Win32 ignores no-window when detached, so the console exe showed a
blank terminal (surfaced once B7 let the GUI live). Fix: CREATE_NO_WINDOW alone +
SW_HIDE. Also the 440x430 window clipped its 6 buttons → now clamps to
`winfo_reqheight`. 29 tests; window verified live from source.
(Prior: B7 — no window at all — fixed via stdio→DEVNULL. Phase D GUI already on main.)

## Phase
Done on Windows: 1–4 (engine/gating/poll), A (app lifecycle), B (distribution: exe +
`irm` installer, build-on-push CI), C (terminal menu — superseded), **D (desktop GUI
window, ADR-0007)**. UI is a Tkinter window; install is one PowerShell line; auto-watch
on by default. 27 tests green, all on per-feature branches.

## Next action (whoever picks this up)
- Cross-platform: mac/Linux process detection + cwd (`/proc`) + GUI check, new ADR.
- Phase 6 polish (version-tolerant limit patterns, log rotation, config hot-reload).
- Optional: onedir build (faster startup, no `_MEI` temp) if size allows.

## Verify before trusting (live, this machine)
- After a fresh install, **rebuild needed**: the released exe predates B7 — CI rebuilds
  on push to main; reinstall via `irm .../install.ps1 | iex` to get the windowed fix.
- `cloophole open` → window must appear. Start a real `claude` session → window's
  "Claude open now" should flip to **yes** and show its folder (proves `winproc` PEB).
- 27→28 offline tests cover logic only; the live fire path still needs a manual smoke
  (`fire-now`) — see B2/B6.

## Watch / before launch
- `winproc.py` PEB offsets are **64-bit only** (BUGS B1).
- The fire path spawns its own `claude.exe`; live gate can momentarily see it (BUGS B2).
- A resume can land in the wrong/empty conversation if no session cwd was captured
  (BUGS B6) — tied to plan §11 "which directory".
- Headless fire/probe require `permission_mode=acceptEdits` or they block.
