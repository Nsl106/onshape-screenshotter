"""Pure time/slot logic for the capture job. No I/O, no network — unit-testable.

Provides the canonical slot key for an instant, plus the quiet-hours gate that lets
the scheduled job skip runs (and spend zero API calls) during a window when the CAD
won't be changing.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _to_utc(t: datetime) -> datetime:
    """Normalize any datetime to timezone-aware UTC.

    A naive datetime is assumed to already be in UTC; an aware one is converted, so
    every slot key is anchored to UTC regardless of the caller's timezone.
    """
    if t.tzinfo is None:
        return t.replace(tzinfo=UTC)
    return t.astimezone(UTC)


def slot_key(t: datetime) -> str:
    """Return the canonical ``YYYY-MM-DD_HH`` slot key for instant ``t`` (UTC).

    This is the single source of truth for a frame's filename, derived from the
    run's wall-clock hour. Slot keys sort chronologically as plain strings, so the
    timelapse stitcher can order frames lexicographically.
    """
    return _to_utc(t).strftime("%Y-%m-%d_%H")


def resolve_timezone(name: str) -> tzinfo:
    """Resolve an IANA timezone name (e.g. ``"America/New_York"``) to a tzinfo.

    ``"UTC"`` is handled without consulting the system tz database so the default
    always works even on minimal images.

    Raises:
        ValueError: if the name isn't a known timezone.
    """
    if name.strip().upper() == "UTC":
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone '{name}'") from exc


def is_quiet(now: datetime, tz_name: str, start_hour: int, end_hour: int) -> bool:
    """Return True if ``now`` falls in the configured quiet-hours window.

    Hours are interpreted in ``tz_name`` local time, as ``[start_hour, end_hour)``.
    A window that wraps midnight (``start_hour > end_hour``, e.g. 22→6) is handled.
    ``start_hour == end_hour`` means the window is disabled (never quiet).
    """
    if start_hour == end_hour:
        return False
    local_hour = _to_utc(now).astimezone(resolve_timezone(tz_name)).hour
    if start_hour < end_hour:
        return start_hour <= local_hour < end_hour
    return local_hour >= start_hour or local_hour < end_hour
