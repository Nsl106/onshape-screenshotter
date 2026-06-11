"""Pure slot logic shared by both the forward and backfill jobs.

Implemented in Phase 3. Holds the three pure functions at the heart of the
anchoring + dedup design: the canonical slot key for an instant, the resolver for
"the microversion current at instant T", and the boundary-instant generator the
backfill steps through. No I/O, no network — fully unit-testable.
"""

from __future__ import annotations
