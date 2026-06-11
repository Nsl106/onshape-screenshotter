"""Per-target change-detection state: ``state/<target>.json``.

Implemented in Phase 3. Reads and writes the last-captured microversion id (plus a
human-readable capture timestamp) for each target, tolerating a missing file on the
first run. No network access.
"""

from __future__ import annotations
