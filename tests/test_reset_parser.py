"""Reset-parser tests — the riskiest unit (free-form limit text -> timestamp)."""

from datetime import datetime, timezone

from cloophole.reset_parser import parse_reset

NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_relative_hours_minutes():
    dt = parse_reset("try again in 4h 30m", now=NOW)
    assert dt == NOW + (datetime(2026, 6, 22, 16, 30, tzinfo=timezone.utc) - NOW)


def test_relative_minutes_words():
    dt = parse_reset("please try again in 90 minutes", now=NOW)
    assert (dt - NOW).total_seconds() == 90 * 60


def test_relative_hours_words():
    dt = parse_reset("in 2 hours", now=NOW)
    assert (dt - NOW).total_seconds() == 2 * 3600


def test_iso_z():
    dt = parse_reset("available at 2026-06-22T17:30:00Z", now=NOW)
    assert dt == datetime(2026, 6, 22, 17, 30, tzinfo=timezone.utc)


def test_iso_space():
    # naive ISO (no zone) is interpreted as local time, returned as aware UTC
    dt = parse_reset("back 2026-06-22 18:00", now=NOW)
    expected = datetime(2026, 6, 22, 18, 0).astimezone().astimezone(timezone.utc)
    assert dt == expected


def test_clock_pm_future_same_day():
    # 5:30 PM local; result must be aware UTC, strictly after NOW within a day
    dt = parse_reset("resets at 5:30 PM", now=NOW)
    assert dt is not None and dt.tzinfo is not None
    assert NOW <= dt <= NOW.replace(hour=23) + (datetime(2026, 6, 23, tzinfo=timezone.utc) - datetime(2026, 6, 22, tzinfo=timezone.utc))


def test_clock_rolls_to_tomorrow_when_past():
    past_now = datetime(2026, 6, 22, 20, 0, tzinfo=timezone.utc)
    dt = parse_reset("resets at 9am", now=past_now)
    assert dt is not None and dt > past_now


def test_garbage_returns_none():
    assert parse_reset("no time here") is None
    assert parse_reset("") is None
