# cloophole

**Auto-resume your Claude Code work when your usage limit resets.** Windows.

You hit the limit and walk away. cloophole watches for the reset on its own, and
the moment it clears it types your message straight into your open `claude`
session so the work picks itself back up. No babysitting, no lost momentum.

Especially useful when you only just got 20$ subscription from Anthropic

- 🪟 **Just a window.** One small desktop app — it *is* the watcher. No background
  daemon, no tray, no service.
- 🎯 **Per-session control.** Lists every live Claude session with a tick box and
  its own message. Resume all, or pick which ones.
- 🧠 **Zero-quota detection.** Notices the limit via a Claude hook — costs no quota.
- 🐧 **WSL + tmux aware.** Drives Claude in plain WSL *and* individual tmux panes
  (per-pane `send-keys`), not just native Windows terminals.
- 🖱️ **Click to find.** Click any session to bring its terminal to the front
  (tmux panes flash so you see which split is which).

---

## Install

PowerShell — no admin, no Python:

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/install.ps1 | iex
```

That's the **only command you ever run** — the same line **installs, updates, and
launches**. It stops any old copy, fetches the latest build, and opens the window.

> First time only: restart Claude Code once so it loads the zero-quota limit hook.

## Using it

The window shows live status and your detected Claude sessions:

1. **Type a message** — what Claude should do when it resumes (blank = "pick up
   where you left off"). Toggle **one message for all** ↔ **per-session messages**.
2. **Tick the sessions** to resume (all ticked by default; untick to skip).
3. Walk away. When your limit resets, cloophole types the message into each ticked
   session automatically.

Buttons: **Resume now** (do it immediately) · **Reset the detected time limit**
(if it wrongly thinks you're limited) · **Close**.

Keep the window open (minimized is fine) for it to keep watching.

**Sessions list:** each row shows the folder + a unique tag — `pid 1234` for
Windows / plain WSL, `w0.p2` for tmux panes. Click a row to surface its terminal.

CLI equivalents exist too: `cloophole sessions`, `cloophole status`,
`cloophole open`, `cloophole close`.

## Uninstall

One line — removes everything (the exe, PATH entry, the Claude hook, app data, and
any leftover processes):

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/uninstall.ps1 | iex
```

---

cloophole only acts through the public `claude` CLI and OS process inspection — it
never reads Claude Code's internal files. What to resume comes from *your* message,
not from Claude's memory.
