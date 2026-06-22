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

It runs as a small **system-tray app** — no terminal to keep open, no browser
required.

## Install (one line)

In PowerShell — no admin, no Python, no pip:

```powershell
irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
```

That downloads a standalone `cloophole.exe` into `%LOCALAPPDATA%\Programs\cloophole`
and adds it to your PATH. Then:

```powershell
cloophole open
```

A **tray icon appears near the clock** — right-click for the menu (dashboard, fire
now, idle poll, queue note, quit). It keeps running even if you close the terminal.
Run `cloophole open` again anytime to re-attach (never a second copy).

- **Stop it:** tray **Quit**, or `cloophole close`.
- **Uninstall:** `cloophole uninstall` (stops + removes everything), or
  `irm https://raw.githubusercontent.com/OWNER/REPO/main/uninstall.ps1 | iex`.
- **Dashboard:** http://127.0.0.1:8787 (also in the tray menu) — optional.

> Replace `OWNER/REPO` with your GitHub repo. The one-liner pulls the exe from that
> repo's latest release — see **Building / releasing** below.

## Run from source (developers)

```powershell
pip install -e .            # installs the `cloophole` command + deps
cloophole open              # tray app
python -m cloophole daemon  # or headless, no tray
```

Requirements for source: Windows 10/11, Python 3.10+, `claude` CLI on PATH. Runtime
deps `pystray` + `Pillow` install automatically.

## Building / releasing

The standalone exe is built by PyInstaller and shipped via GitHub Releases:

```powershell
pip install pyinstaller
cd packaging; python -m PyInstaller cloophole.spec --noconfirm   # -> dist/cloophole.exe
```

Or just push a tag — `.github/workflows/release.yml` builds `cloophole.exe` and
attaches it to the release, which `install.ps1` downloads:

```powershell
git tag v0.1.0 && git push --tags
```

## Usage

```powershell
cloophole open                         # launch the tray app (or attach if running)
cloophole close                        # stop the background app
cloophole status                       # phase + countdown + live-session
cloophole report "resets at 5:30 PM"   # parse limit text, arm -> WAITING
cloophole queue  "finish auth refactor"# what to continue (else: fallback)
cloophole dir    C:\path\to\project    # pin one dir (else: fire ALL live sessions)
cloophole poll   on                    # idle auto-detection of the limit
cloophole fire-now                     # fire immediately, ignoring the gate
cloophole arm    "in 2h"               # arm manually (clock / relative / ISO)
cloophole clear                        # back to WATCHING
cloophole config [key [value]]         # show / get / set tunables
cloophole ui [port]                    # serve the dashboard in the foreground
cloophole daemon                       # run the watcher headless (no tray)
cloophole uninstall                    # stop everything + remove app data
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
| `ui_enabled` | `true` | daemon serves the status page itself |
| `ui_port` | `8787` | local status page |
| `fire_timeout_sec` | `1800` | cap one `--continue` run |
| `claude_process_name` | `claude.exe` | name matched for the live gate |

State, config, and logs live in `~/.cloophole/` (override with `$CLOOPHOLE_HOME`).

## Status of this build

Done: engine + state machine, reset parser, Windows process/cwd detection,
multi-directory `--continue` fire (hidden), idle quota poll, **system-tray app**
(`open`/`close`, single-instance, native toast on fire, tray menu + dashboard), full
CLI, tests.

Not yet: macOS/Linux tray + detection, a single-file `.exe` bundle (PyInstaller), a
hook to auto-capture the limit message and last prompt, version-tolerant limit-text
patterns.

## Tests

```powershell
pip install pytest
python -m pytest -q
```
