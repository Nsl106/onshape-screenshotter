"""Frame file layout and first-writer-wins image writing.

Implemented in Phase 3. Maps a target + slot key to ``frames/<target>/<slot>.png``,
checks whether a slot is already filled (the committed directory is the authoritative
record), and writes PNG bytes without ever overwriting an existing frame.
"""

from __future__ import annotations
