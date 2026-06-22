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

The watcher runs as a **hidden background process**; you view and control it from an
**interactive terminal menu** (`cloophole open`). No browser, no tray, no GUI.

## Install (one line)

In PowerShell — no admin, no Python, no pip:

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/install.ps1 | iex
```

That downloads a standalone `cloophole.exe` into `%LOCALAPPDATA%\Programs\cloophole`
and adds it to your PATH. Then:

```powershell
cloophole open
```

This starts the watcher in the background and opens an **interactive terminal menu**
(status + fire now / queue note / report limit / toggle poll). The watcher keeps
running even if you close the terminal — run `cloophole open` again anytime to
re-open the menu (never a second watcher).

- **Stop it:** menu `[s]`, or `cloophole close`.
- **Uninstall:** `cloophole uninstall` (stops + removes everything), or
  `irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/uninstall.ps1 | iex`.

> The one-liner pulls `cloophole.exe` from this repo's latest GitHub Release — push
> the repo and cut one `v*` tag first (see **Building / releasing** below).

## Run from source (developers)

```powershell
pip install -e .            # installs the `cloophole` command (stdlib only)
cloophole open              # daemon + terminal menu
python -m cloophole daemon  # or run the watcher in the foreground
```

Requirements for source: Windows 10/11, Python 3.10+, `claude` CLI on PATH. No
third-party Python dependencies.

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
cloophole open                         # start daemon + open the terminal menu
cloophole menu                         # open the terminal menu
cloophole close                        # stop the background daemon
cloophole status                       # phase + countdown + live-session
cloophole report "resets at 5:30 PM"   # parse limit text, arm -> WAITING
cloophole queue  "finish auth refactor"# what to continue (else: fallback)
cloophole dir    C:\path\to\project    # pin one dir (else: fire ALL live sessions)
cloophole poll   on                    # idle auto-detection of the limit
cloophole fire-now                     # fire immediately, ignoring the gate
cloophole arm    "in 2h"               # arm manually (clock / relative / ISO)
cloophole clear                        # back to WATCHING
cloophole config [key [value]]         # show / get / set tunables
cloophole daemon                       # run the watcher in the foreground
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
| `fire_timeout_sec` | `1800` | cap one `--continue` run |
| `claude_process_name` | `claude.exe` | name matched for the live gate |

State, config, and logs live in `~/.cloophole/` (override with `$CLOOPHOLE_HOME`).

## Status of this build

Done: engine + state machine, reset parser, Windows process/cwd detection,
multi-directory `--continue` fire (hidden), idle quota poll, **interactive terminal
menu** + single-instance background daemon (`open`/`menu`/`close`), standalone exe +
one-line installer, full CLI, tests.

Not yet: macOS/Linux detection, a hook to auto-capture the limit message and last
prompt, version-tolerant limit-text patterns.

## Tests

```powershell
pip install pytest
python -m pytest -q
```
