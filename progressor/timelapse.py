"""Timelapse stitcher — combine committed frames into a video.

Run as ``python -m progressor.timelapse``.

Implemented in Phase 6. Collects ``frames/<target>/*.png`` in chronological (slot
key) order and drives ffmpeg via subprocess to produce ``timelapse/<target>.mp4``
(and optionally ``.gif``), tolerating gaps in the slot sequence and the trivial
zero/one-frame cases.
"""

from __future__ import annotations
