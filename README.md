# cloophole

Auto-resume your Claude Code work when your usage quota resets — Windows.

You hit the limit and walk away. cloophole **watches for the limit on its own**, and
when the window reopens with a `claude` session running, it runs `claude --continue`
for you so the work picks itself back up. It runs as a hidden background watcher you
control from a small terminal menu.

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
  [3] Report limit text   paste "resets at 5:30 PM" (only if you want to set it manually)
  [4] Toggle auto-watch   auto-detect the limit (ON by default)
  [5] Pin / clear dir     fire in one dir (default: all live sessions)
  [s] Stop daemon         [q] Quit menu (watcher keeps running)
```

**Auto-watch is on by default:** the watcher quietly probes for the limit every ~30
min and arms itself when it appears — you don't need to paste anything. (Each probe
costs a tiny bit of quota; turn it off with `[4]` or `cloophole poll off` if you'd
rather report limits manually.)

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
