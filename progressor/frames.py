"""Frame file layout and first-writer-wins image writing.

The committed ``frames/<element_id>/`` directory is the authoritative record of
which slots are filled. Overlap between the capture job and re-runs is prevented at
the slot level: before rendering, a caller checks ``exists`` for the slot, and
``write_frame`` refuses to overwrite — so whoever writes a slot first wins and no
API quota is spent re-rendering it. No network access.
"""

from __future__ import annotations

from pathlib import Path


def frames_dir(element_id: str, root: Path | str = ".") -> Path:
    """Return a target's frame directory: ``<root>/frames/<element_id>``."""
    return Path(root) / "frames" / element_id


def frame_path(element_id: str, slot: str, root: Path | str = ".") -> Path:
    """Return the PNG path for a target's slot: ``frames/<element_id>/<slot>.png``."""
    return frames_dir(element_id, root) / f"{slot}.png"


def exists(element_id: str, slot: str, root: Path | str = ".") -> bool:
    """Return True if the slot is already filled (so it must not be re-rendered)."""
    return frame_path(element_id, slot, root).exists()


def write_frame(
    element_id: str, slot: str, data: bytes, root: Path | str = "."
) -> bool:
    """Write PNG ``data`` to a slot, first-writer-wins.

    Creates the target's frame directory if needed. If the slot file already
    exists, leaves it untouched and returns False — frames are an immutable record.

    Returns:
        True if the file was written, False if a frame already occupied the slot.
    """
    path = frame_path(element_id, slot, root)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def list_frames(element_id: str, root: Path | str = ".") -> list[Path]:
    """Return a target's frame PNGs sorted chronologically (slot keys sort by time).

    Returns an empty list if the target has no frame directory yet.
    """
    directory = frames_dir(element_id, root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.png"))
