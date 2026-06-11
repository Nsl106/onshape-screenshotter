"""Pure slot logic shared by both the forward and backfill jobs.

Holds the ``Microversion`` domain type plus the three pure functions at the heart
of the anchoring + dedup design: the canonical slot key for an instant, the
resolver for "the microversion current at instant T", and the boundary-instant
generator the backfill steps through. No I/O, no network — fully unit-testable.
(The functions land in Phase 3; the ``Microversion`` type lives here so the
networked client and the pure logic share it without ``slots`` depending on
``requests``.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
