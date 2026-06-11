"""Onshape API client — the only module in the pipeline that touches the network.

Implemented in Phase 2: HTTP Basic auth against the Onshape REST API, lazy paging
of document history, shaded-view rendering at a specific microversion, and a single
rate-limit-aware request helper. Credentials are read from environment variables and
never appear in logs or exception messages.
"""

from __future__ import annotations
