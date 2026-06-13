"""Tests for the pure slot/time logic (no I/O, no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from screenshotter.slots import is_quiet, resolve_timezone, slot_key


def _utc(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


# --- slot_key -------------------------------------------------------------------


def test_slot_key_format() -> None:
    assert slot_key(_utc(2024, 1, 5, 9, 30)) == "2024-01-05_09"


def test_slot_key_normalizes_other_timezone_to_utc() -> None:
    plus2 = timezone(timedelta(hours=2))
    t = datetime(2024, 1, 5, 9, 30, tzinfo=plus2)
    assert slot_key(t) == "2024-01-05_07"


def test_slot_key_treats_naive_as_utc() -> None:
    assert slot_key(datetime(2024, 1, 5, 9, 30)) == "2024-01-05_09"


def test_slot_keys_sort_chronologically() -> None:
    keys = [slot_key(_utc(2024, 1, 5, h)) for h in (23, 0, 9)]
    assert sorted(keys) == ["2024-01-05_00", "2024-01-05_09", "2024-01-05_23"]


# --- resolve_timezone -----------------------------------------------------------


def test_resolve_utc() -> None:
    assert resolve_timezone("UTC") is UTC
    assert resolve_timezone("utc") is UTC


def test_resolve_named_zone() -> None:
    # A real zone resolves and applies the expected offset.
    tz = resolve_timezone("America/New_York")
    # 2024-01-05 12:00 UTC is 07:00 EST.
    assert _utc(2024, 1, 5, 12).astimezone(tz).hour == 7


def test_resolve_bad_zone_raises() -> None:
    with pytest.raises(ValueError, match="unknown timezone"):
        resolve_timezone("Mars/Olympus_Mons")


# --- is_quiet -------------------------------------------------------------------


def test_quiet_disabled_when_start_equals_end() -> None:
    assert is_quiet(_utc(2024, 1, 5, 4), "UTC", 0, 0) is False


def test_quiet_simple_window() -> None:
    # Quiet 03:00-09:00 UTC.
    assert is_quiet(_utc(2024, 1, 5, 3), "UTC", 3, 9) is True
    assert is_quiet(_utc(2024, 1, 5, 8), "UTC", 3, 9) is True
    assert is_quiet(_utc(2024, 1, 5, 9), "UTC", 3, 9) is False  # end exclusive
    assert is_quiet(_utc(2024, 1, 5, 2), "UTC", 3, 9) is False


def test_quiet_window_wraps_midnight() -> None:
    # Quiet 22:00-06:00.
    assert is_quiet(_utc(2024, 1, 5, 23), "UTC", 22, 6) is True
    assert is_quiet(_utc(2024, 1, 5, 2), "UTC", 22, 6) is True
    assert is_quiet(_utc(2024, 1, 5, 6), "UTC", 22, 6) is False
    assert is_quiet(_utc(2024, 1, 5, 12), "UTC", 22, 6) is False


def test_quiet_respects_timezone() -> None:
    # 08:00 UTC is 03:00 in New York; a 1-9 Eastern quiet window should be quiet.
    assert is_quiet(_utc(2024, 1, 5, 8), "America/New_York", 1, 9) is True
    # 16:00 UTC is 11:00 Eastern -> not quiet.
    assert is_quiet(_utc(2024, 1, 5, 16), "America/New_York", 1, 9) is False
