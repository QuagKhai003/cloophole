# cloophole

**Your Claude Code kept working. Even while you sleep.**

You know the wall: you're deep in the work, Claude says *"you've hit your usage
limit, try again in 5 hours"* — and everything stops. You have to remember to come
back later, reopen everything, and re-explain what you wanted.

cloophole does that for you. You leave a note like *"keep building the checkout
page"*, close your laptop, and walk away. The moment your limit resets, cloophole
types your note into Claude and hits **Enter** — so the work picks itself right back
up. You come back to progress, not a blinking cursor.

> Set it and forget it. Best friend of the $20 plan.

---

## Why you'll like it

- 🌙 **Walk away, come back to progress.** It waits for the reset and restarts your
  work automatically — no alarms, no babysitting.
- ⏱️ **See your limit before you hit it.** A live *"3h 12m until reset · 38% used"*
  readout, so no surprises mid-flow. Costs you nothing.
- 🎯 **You're in control.** It lists every Claude you have open with a checkbox and a
  message box. Tick the ones to continue, leave a note for each, done.
- 🐧 **Works with your setup.** Plain terminals, WSL, tmux splits, even the Claude
  desktop app.
- 🪟 **Just one small window.** No account, no background service, nothing hidden.
  Close it and it's gone.

---

## Get it (Windows, 30 seconds)

Open PowerShell and paste one line:

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/install.ps1 | iex
```

That's the **only** command you ever need — it installs, updates, *and* opens the
app. (First time: restart Claude once so it can tell cloophole when you're limited.)

## Use it (three steps)

1. **Leave a note** — what Claude should do next (or leave it blank for "carry on").
2. **Tick the sessions** you want continued.
3. **Walk away.** When your limit resets, cloophole types the note in and presses
   Enter for you.

Want it now instead of at reset? Hit **Resume now**. Keep the window open (minimized
is fine) so it can watch.

## Remove it

One line, takes everything with it:

```powershell
irm https://raw.githubusercontent.com/QuagKhai003/cloophole/main/uninstall.ps1 | iex
```

---

**On trust:** cloophole never reads your chats or Claude's files. It only watches
whether Claude is running and types the note *you* wrote. Nothing more.
