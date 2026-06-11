"""Forward capture job — the hourly entrypoint (``python -m progressor.capture``).

Implemented in Phase 4. For each configured target it anchors on the top of the
scheduled hour T, resolves the microversion current at T, and renders + files a
frame only if the document changed and the slot is empty. Git commit/push is left
to the workflow so the script stays side-effect-scoped and locally testable.
"""

from __future__ import annotations
