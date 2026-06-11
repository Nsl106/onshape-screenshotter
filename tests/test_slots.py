"""Tests for the pure slot logic (no I/O, no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from progressor.slots import (
    Microversion,
    floor_to_hour,
    microversion_at,
    slot_key,
)


def _utc(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


# --- slot_key -------------------------------------------------------------------


def test_slot_key_format() -> None:
    assert slot_key(_utc(2024, 1, 5, 9, 30)) == "2024-01-05_09"


def test_slot_key_normalizes_other_timezone_to_utc() -> None:
    # 09:30 at +02:00 is 07:30 UTC -> hour bucket 07.
    plus2 = timezone(timedelta(hours=2))
    t = datetime(2024, 1, 5, 9, 30, tzinfo=plus2)
    assert slot_key(t) == "2024-01-05_07"


def test_slot_key_treats_naive_as_utc() -> None:
    assert slot_key(datetime(2024, 1, 5, 9, 30)) == "2024-01-05_09"


def test_slot_keys_sort_chronologically() -> None:
    keys = [slot_key(_utc(2024, 1, 5, h)) for h in (23, 0, 9)]
    assert sorted(keys) == [
        "2024-01-05_00",
        "2024-01-05_09",
        "2024-01-05_23",
    ]


# --- floor_to_hour --------------------------------------------------------------


def test_floor_to_hour() -> None:
    assert floor_to_hour(_utc(2024, 1, 5, 14, 23, 45)) == _utc(2024, 1, 5, 14)


# --- microversion_at ------------------------------------------------------------


def _history() -> list[Microversion]:
    # Newest-first, as the API returns it.
    return [
        Microversion("m3", _utc(2024, 1, 3)),
        Microversion("m2", _utc(2024, 1, 2)),
        Microversion("m1", _utc(2024, 1, 1)),
    ]


def test_microversion_at_returns_latest_at_or_before_t() -> None:
    mv = microversion_at(_history(), _utc(2024, 1, 2, 12))
    assert mv is not None and mv.id == "m2"


def test_microversion_at_exact_boundary_is_inclusive() -> None:
    mv = microversion_at(_history(), _utc(2024, 1, 2))
    assert mv is not None and mv.id == "m2"


def test_microversion_at_before_first_returns_none() -> None:
    assert microversion_at(_history(), _utc(2023, 12, 31)) is None


def test_microversion_at_empty_history_returns_none() -> None:
    assert microversion_at([], _utc(2024, 1, 2)) is None


def test_microversion_at_short_circuits_lazy_iterator() -> None:
    consumed: list[str] = []

    def lazy():
        for mv in _history():
            consumed.append(mv.id)
            yield mv

    mv = microversion_at(lazy(), _utc(2024, 1, 3, 12))
    assert mv is not None and mv.id == "m3"
    # Only the first (newest) entry should have been pulled.
    assert consumed == ["m3"]
