# claude-resume — Product Plan

A lightweight, cross-platform background daemon that resumes your Claude Code work automatically when your usage quota resets.

---

## 1. What it is

A lightweight, cross-platform background daemon that watches your Claude Code usage state. When your quota window reopens, it automatically tells your *existing* Claude Code session to continue the work that got cut off — without you being at the keyboard. If no session is open at reset, it waits and fires the moment one appears.

## 2. The one-sentence promise

> "You hit the limit at 1 PM and leave at 5; at 5:30 your reset lands and your work picks itself back up — as long as a `claude` terminal is open, or whenever you next open one."

## 3. Core behavior

**Resume mechanism.** When the quota resets, the harness does *not* keystroke-inject into your visible REPL. Instead it runs `claude -p --continue` in the recorded working directory. Because `--continue` resumes the most recent conversation *in that directory*, it picks up the exact thread your open session belongs to — same context, same task — and tells it to keep going. The harness holds a short "memory" note of what the current work was, and passes that into the continue prompt ("resume the job / move to the next phase").

**Live-session gate.** The harness only fires if it detects at least one running `claude` process. No live session → it does nothing and keeps waiting. This rule is enforced by process detection rather than by trying to read Claude Code's internal state.

**No-session-at-reset behavior.** If the window reopens but no `claude` is running, the harness arms itself and fires automatically the next time a `claude` process appears. It polls for that transition.

## 4. How it knows your reset time

There is no API that exposes your subscription reset clock, so two paths are used:

- **Parse (primary).** When you actually hit the wall, Claude Code prints a limit message containing the reset time. You paste it (or a hook captures it), the harness parses `resets at 5:30 PM` / `try again in 4h 30m` into a concrete timestamp and arms.
- **Poll (idle).** When you're not actively working, the harness occasionally sends a tiny probe. If it comes back limited, it parses the reset time from *that*. Polling detects the limited → available transition; it does not read the clock ahead of time.

## 5. The "memory of current work"

Before firing, the harness needs to know *what* to continue. Sources, in priority order:

1. A note you set explicitly (`queue "finish the auth refactor"`).
2. The directory's most recent session (resumed implicitly by `--continue`).
3. A generic fallback ("continue where you left off before the limit").

This is stored in a small state file the UI and CLI both read.

## 6. Components

| Component | Job |
|---|---|
| **Daemon** | Long-lived watcher. Tracks limit state, reset timestamp, live-session presence; fires `--continue` when reset + live session are both true. |
| **CLI** | `status`, `report "<limit text>"`, `queue "<note>"`, `dir <path>`, `fire-now`, `config`. Your manual control surface. |
| **Process detector** | Cross-platform check for a running `claude` process and its working directory (so the harness fires in the right folder). |
| **Reset parser** | Turns limit-message text into a UTC timestamp; handles clock-time, relative-duration, and ISO forms. |
| **UI** | Tiny local page showing: current status, countdown to reset, whether a live session is detected, what work is queued. Lightweight, served by the daemon — no native GUI toolkit. |
| **Installers** | Per-OS register-at-startup + uninstall. macOS launchd, Linux systemd-user, Windows Task Scheduler / Startup. |

## 7. State machine

```
WATCHING ──limit detected (parse/poll)──▶ WAITING
WAITING ──reset reached, live session?──┬─ yes ─▶ FIRING ─▶ FIRED ─▶ WATCHING
                                        └─ no  ─▶ ARMED (wait for session)
ARMED ──claude process appears──▶ FIRING
FIRING ──still limited──▶ WAITING (re-arm)
FIRING ──error──▶ ERROR ─▶ WATCHING
```

## 8. Cross-platform install / uninstall

- **macOS:** `launchd` plist in `~/Library/LaunchAgents`, `RunAtLoad=true`. Uninstall = `launchctl unload` + remove plist.
- **Linux:** systemd *user* service, `WantedBy=default.target`, `systemctl --user enable`. Uninstall = disable + remove unit.
- **Windows:** Task Scheduler task at logon (or Startup-folder shim for Git Bash users). Uninstall = delete task.
- A single `install.py` dispatches by `sys.platform`; `uninstall.py` reverses it. Lightweight: pure Python + one background process, no service framework.

## 9. Hard constraints

1. **No reset-clock API.** Reset time only comes from parsing limit text. The poll path is a fallback, not a precise clock.
2. **`--continue` is per-directory.** The harness must fire in the correct folder, so capturing the live session's working directory matters.
3. **Live-session detection is by OS process inspection,** not by reading Claude Code's internals. Good enough to gate firing; it cannot see *what* the session is mid-task on, which is why the work-memory note exists.
4. **Probing costs a little quota.** Idle poll interval is deliberately gentle (e.g. 30 min).
5. **Permissions.** Headless `--continue` needs a non-interactive permission mode (e.g. `acceptEdits`) or it will block waiting for confirmations no one is there to give.

## 10. Build phases

- **Phase 1 — Engine:** daemon loop, reset parser, state file, CLI `report` / `status`. Fire via `--continue`, manual arm only.
- **Phase 2 — Gating:** process detector + working-directory capture; live-session gate; ARMED-waits-for-session behavior.
- **Phase 3 — Idle poll:** automatic limit detection when you are away.
- **Phase 4 — UI:** local countdown page + live-session indicator.
- **Phase 5 — Installers:** all three OSes, install / uninstall, run-at-startup.
- **Phase 6 — Polish:** version-tolerant limit-text patterns, logging, config hot-reload.

## 11. Open questions before Phase 2

- On Windows, do you want the Git Bash startup-shim path or a proper Scheduled Task? The shim is simpler but only runs when you open Git Bash.
- For "which directory," if you have multiple `claude` sessions open at once, should it fire in *all* their directories, the most recently active, or one you pin?
- Should the work-memory note auto-capture from your last prompt, or stay manual?
