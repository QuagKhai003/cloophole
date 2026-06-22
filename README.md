# cloophole

Auto-resume your Claude Code work when your usage quota resets — Windows.

You hit the limit and walk away. When the window reopens and a `claude` session is
running, cloophole runs `claude --continue` for you so the work picks itself back up.
It runs as a hidden background watcher you control from a small terminal menu.

## Install

In PowerShell — no admin, no Python:

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/install.ps1 | iex
```

Then:

```powershell
cloophole open
```

`open` starts the watcher in the background and opens the menu. The watcher keeps
running even if you close the terminal — run `cloophole open` again anytime to
reopen the menu.

## Using it

The menu shows live status and lets you act:

```
  [1] Fire now            resume right now
  [2] Set queue note      what it should continue
  [3] Report limit text   paste "resets at 5:30 PM" to arm a reset time
  [4] Toggle idle poll    auto-detect the limit while you're away
  [5] Pin / clear dir     fire in one dir (default: all live sessions)
  [s] Stop daemon         [q] Quit menu (watcher keeps running)
```

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
