# cloophole

Auto-resume your Claude Code work when your usage quota resets — **Windows-first**.

You hit the limit at 1 PM and walk away. At 5:30 your window reopens, and as long
as a `claude` terminal is open (or whenever you next open one), cloophole tells that
session to pick the work back up. No keystroke injection: it runs
`claude --continue` headless in the recorded directory, which resumes the most
recent conversation there.

## How it works

- **Fire mechanism** — runs `claude -p --continue --permission-mode acceptEdits`
  in the captured working directory. `--continue` resumes the latest thread in that
  folder; the queued note tells it what to do next.
- **Live-session gate** — only fires if a `claude.exe` process is running. Detection
  is pure OS process inspection (ctypes, no third-party deps). The process's working
  directory is read from its PEB so we fire in the right folder.
- **No session at reset** — arms itself (`ARMED`) and fires the moment a `claude`
  process appears.
- **Knowing the reset time** — there is no API for it. Paste the limit message
  (`report`) and cloophole parses `resets at 5:30 PM` / `try again in 4h 30m` / ISO
  into a concrete timestamp.

State machine: `WATCHING → WAITING → (ARMED) → FIRING → WATCHING`.

## Requirements

- Windows 10/11, Python 3.10+ (tested on 3.14)
- `claude` CLI on PATH
- Zero third-party Python dependencies

## Install

Two commands. **No administrator rights needed.**

```powershell
pip install -e .
cloophole install
```

That's it — `install` registers a hidden run-at-logon shim (user Startup folder)
**and** starts the daemon right now. It's idempotent: re-run it any time to restart
with the latest code. Remove everything with `cloophole uninstall`.

Prefer a Task Scheduler task instead of the Startup shim? `cloophole install --task`
(that one may prompt for an elevated terminal).

Run the watcher in the foreground without installing:

```powershell
python -m cloophole daemon
```

## Usage

```powershell
cloophole status                       # phase + countdown + live-session
cloophole report "resets at 5:30 PM"   # parse limit text, arm -> WAITING
cloophole queue  "finish auth refactor"# what to continue (else: fallback)
cloophole dir    C:\path\to\project    # pin one dir (else: fire ALL live sessions)
cloophole poll   on                    # idle auto-detection of the limit
cloophole fire-now                     # fire immediately, ignoring the gate
cloophole arm    "in 2h"               # arm manually (clock / relative / ISO)
cloophole clear                        # back to WATCHING
cloophole config [key [value]]         # show / get / set tunables
cloophole ui [port]                    # local status page (default :8787)
cloophole start | stop                 # start/stop the background daemon
cloophole uninstall                    # remove shim/task + stop the daemon
```

By default a fire runs `--continue` in **every** live `claude` session's directory.
Pin a single one with `cloophole dir <path>`.

## Config

`~/.cloophole/config.json` (set via `cloophole config <key> <value>`):

| key | default | meaning |
|---|---|---|
| `claude_path` | `claude` | executable name or full path |
| `permission_mode` | `acceptEdits` | headless can't answer prompts |
| `daemon_tick_sec` | `15` | watcher loop cadence |
| `poll_enabled` | `false` | idle auto-detection (`cloophole poll on`) |
| `poll_interval_min` | `30` | gentle — probing costs quota |
| `ui_port` | `8787` | local status page |
| `fire_timeout_sec` | `1800` | cap one `--continue` run |
| `claude_process_name` | `claude.exe` | name matched for the live gate |

State, config, and logs live in `~/.cloophole/` (override with `$CLOOPHOLE_HOME`).

## Status of this build

Done: engine + state machine, reset parser, Windows process/cwd detection,
multi-directory `--continue` fire (hidden window), idle quota poll, full CLI, local
UI, no-admin Startup-shim installer (+ `start`/`stop`, single-instance daemon), tests.

Not yet: macOS/Linux detection + installers, a hook to auto-capture the limit message
and last prompt, version-tolerant limit-text patterns.

## Tests

```powershell
pip install pytest
python -m pytest -q
```
