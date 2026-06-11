"""Onshape Progressor — render an Onshape document on a schedule into timelapse frames.

The package is a small pipeline. Each module owns one stage:

- ``config``    — load and validate ``config.toml`` into typed, frozen objects.
- ``onshape``   — the only module that talks to the network: auth, history paging,
                  shaded-view rendering, rate-limit handling.
- ``slots``     — pure logic: slot keys, boundary instants, and "the microversion
                  current at instant T". Shared by both jobs.
- ``state``     — read/write the per-target ``state/<target>.json`` change marker.
- ``frames``    — frame paths, existence checks, image writing (first-writer-wins).
- ``capture``   — the hourly forward job entrypoint.
- ``backfill``  — the one-time history reconstruction entrypoint.
- ``timelapse`` — stitch committed frames into a video via ffmpeg.
"""

__version__ = "0.1.0"
