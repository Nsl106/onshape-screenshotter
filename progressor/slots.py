"""Pure slot logic for the capture job.

Holds the ``Microversion`` domain type plus the pure functions at the heart of the
anchoring + dedup design: the canonical slot key for an instant and the resolver
for "the microversion current at instant T". No I/O, no network — fully
unit-testable. (The ``Microversion`` type lives here so the networked client and
the pure logic share it without ``slots`` depending on ``requests``.)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Microversion:
    """One immutable point in a document's edit history.

    Attributes:
        id: The Onshape microversion id (``microversionId``), addressable via the
            ``m/{id}`` path.
        created_at: When the microversion was created, as a timezone-aware UTC
            datetime (parsed from the API's ``date`` field).
    """

    id: str
    created_at: datetime


def _to_utc(t: datetime) -> datetime:
    """Normalize any datetime to timezone-aware UTC.

    A naive datetime is assumed to already be in UTC; an aware one is converted.
    This keeps every slot key and comparison anchored to UTC regardless of the
    caller's timezone (GitHub runners, local testing, ``--at`` overrides).
    """
    if t.tzinfo is None:
        return t.replace(tzinfo=UTC)
    return t.astimezone(UTC)


def floor_to_hour(t: datetime) -> datetime:
    """Return ``t`` (normalized to UTC) truncated to the top of its hour."""
    u = _to_utc(t)
    return u.replace(minute=0, second=0, microsecond=0)


def slot_key(t: datetime) -> str:
    """Return the canonical ``YYYY-MM-DD_HH`` slot key for instant ``t`` (UTC).

    This is the single source of truth for a frame's filename. The capture job
    derives it from its target instant ``T`` — never from a microversion's own
    timestamp or from wall-clock run time — so frames share one ordered,
    collision-free naming scheme. Slot keys also sort chronologically as strings.
    """
    return _to_utc(t).strftime("%Y-%m-%d_%H")


def microversion_at(
    history: Iterable[Microversion], t: datetime
) -> Microversion | None:
    """Return the microversion that was current at instant ``t``.

    That is the latest microversion whose ``created_at <= t``. ``history`` must be
    ordered newest-first (as the API returns it), so the first qualifying entry is
    the answer and the rest of a lazy iterator is never consumed — letting the
    forward job short-circuit instead of paging full history each hour.

    Returns ``None`` when no microversion existed at or before ``t`` (the document
    didn't exist yet), signaling the caller to skip that slot.
    """
    cutoff = _to_utc(t)
    for mv in history:
        if mv.created_at <= cutoff:
            return mv
    return None
