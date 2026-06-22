# cloophole

Auto-resume your Claude Code work when your usage quota resets — Windows.

You hit the limit and walk away. cloophole **watches for the limit on its own**, and
when the window reopens with a `claude` session running, it runs `claude --continue`
for you so the work picks itself back up. A hidden background watcher does the work;
you see and control it from a small **desktop window**.

## Install

In PowerShell — no admin, no Python:

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/install.ps1 | iex
```

Then:

```powershell
cloophole open
```

`open` starts the watcher in the background and opens the **cloophole window**. The
watcher keeps running even if you close the window or the terminal — run
`cloophole open` again anytime to reopen the window.

## Using it

The window shows live plain-language status and a button for each action:

- **Resume now** — continue your Claude work right now
- **What to resume** — a note telling it what to continue (blank = pick up where you left off)
- **Enter limit time** — if you know when it resets (e.g. "5:30 PM")
- **Auto-detect** — let it find the limit on its own (on by default)
- **Choose folder** — resume in one project (default: every open Claude window)
- **Reset status** / **Stop watching** / **Close window**

**Auto-detect is on by default:** the watcher quietly checks for the limit every ~30
min and sets itself up when it appears — you don't need to enter anything. (Each check
costs a tiny bit of quota; turn it off in the window if you'd rather enter limits
yourself.)

Same actions exist as commands, e.g. `cloophole report "resets at 5:30 PM"`,
`cloophole queue "finish the refactor"`, `cloophole status`.

## Stop / uninstall

```powershell
cloophole close       # stop the background watcher
cloophole uninstall   # stop + remove everything (exe, PATH entry, app data)
```

Or uninstall via the web:

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/uninstall.ps1 | iex
```
