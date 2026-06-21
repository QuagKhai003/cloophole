"""Turn Claude Code limit-message text into a concrete UTC reset timestamp.

@context  No API exposes the reset clock; the only signal is the limit text
          Claude prints. This is the riskiest unit (free-form input).
@done     parse_reset() handling ISO / relative / clock forms -> aware UTC,
          parse order most-explicit-first; naive ISO + clock = local time.
@todo     version-tolerant pattern corpus (Phase 6, ADR-0004).
@limits   PURE: no I/O. Clock-times roll to tomorrow if already past today.
@affects  Used by CLI report/arm, fire (still_limited), daemon re-arm.
          Patterns documented in docs/DATA_MODEL.md; tested in tests/.

  clock-time    "resets at 5:30 PM"  "try again at 17:00"  "resets 5pm"
  relative      "try again in 4h 30m"  "in 90 minutes"  "in 2 hours"
  iso           "2026-06-22T17:30:00Z"  "available at 2026-06-22 17:30"
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.astimezone()  # attach local tz
    return dt.astimezone(timezone.utc)


def _parse_iso(text: str) -> Optional[datetime]:
    m = re.search(
        r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)",
        text,
    )
    if not m:
        return None
    raw = m.group(1).replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return _to_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _parse_relative(text: str, now: datetime) -> Optional[datetime]:
    # "in 4h 30m", "in 2 hours", "in 90 minutes", "in 45s"
    if not re.search(r"\bin\b|try again", text, re.I):
        return None
    total = timedelta()
    found = False
    for value, unit in re.findall(
        r"(\d+)\s*(h(?:ours?|rs?)?|m(?:in(?:utes?)?)?|s(?:ec(?:onds?)?)?)\b",
        text,
        re.I,
    ):
        found = True
        n = int(value)
        u = unit[0].lower()
        if u == "h":
            total += timedelta(hours=n)
        elif u == "m":
            total += timedelta(minutes=n)
        else:
            total += timedelta(seconds=n)
    if not found or total == timedelta():
        return None
    return now + total


def _parse_clock(text: str, now: datetime) -> Optional[datetime]:
    # "resets at 5:30 PM", "try again at 17:00", "resets 5pm"
    m = re.search(
        r"\b(?:reset(?:s)?|again|available|back)\b[^0-9]*?"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        text,
        re.I,
    )
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    local_now = now.astimezone()
    cand = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cand <= local_now:
        cand += timedelta(days=1)
    return _to_utc(cand)


def is_limit_message(text: str) -> bool:
    """True if text reads as a Claude Code usage-limit message.

    Shared by the idle probe and the fire's still-limited check so the two can
    never diverge. Heuristic (BUGS B3): a parseable reset time AND limit wording.
    """
    if not text:
        return False
    return parse_reset(text) is not None and (
        "limit" in text.lower() or "try again" in text.lower()
    )


def parse_reset(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Best-effort parse. Returns aware UTC datetime or None.

    Order: ISO (most explicit) -> relative -> clock-time.
    """
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    for fn in (_parse_iso, lambda t: _parse_relative(t, now), lambda t: _parse_clock(t, now)):
        dt = fn(text)
        if dt:
            return dt
    return None
