"""History backfill — the one-time reconstruction entrypoint.

Run as ``python -m progressor.backfill``.

Implemented in Phase 5. Enumerates a document's full history once, steps through
boundary instants at ``backfill_interval_hours``, and renders the microversion
current at each boundary into its slot (skipping filled or unchanged slots), then
hands off to the forward job by writing the latest microversion to state.
"""

from __future__ import annotations
