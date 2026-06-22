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

The menu shows plain-language status and lets you act:

```
  [1] Resume now          continue your Claude work right now
  [2] Set what to resume  a note telling it what to continue
  [3] Enter limit time    if you know when it resets (e.g. 5:30 PM)
  [4] Auto-detect (on)    let it find the limit on its own
  [5] Choose folder       resume in one project (default: all)
  [6] Reset status        clear the limit and start watching again
  [s] Stop & quit         [q] Close menu (keeps watching)
```

**Auto-detect is on by default:** the watcher quietly checks for the limit every ~30
min and sets itself up when it appears — you don't need to enter anything. (Each check
costs a tiny bit of quota; turn it off with `[4]` if you'd rather enter limits
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
