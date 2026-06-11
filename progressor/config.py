"""Load and validate ``config.toml`` into typed, frozen configuration objects.

This module is the boundary between a team-edited TOML file and the rest of the
pipeline. It parses the file, applies defaults, and validates every field with
error messages aimed at a non-programmer ("fix X in config.toml"), failing fast
before any network call or file write happens.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

# Allowed values for a target's ``element_type``. These map directly to the two
# shaded-view endpoint families in the Onshape API (part studios vs. assemblies).
ELEMENT_TYPES = ("assembly", "partstudio")


class ConfigError(Exception):
    """Raised when ``config.toml`` is missing, malformed, or fails validation.

    The message is written for the team member editing the file, not for a
    developer: it names the offending field and what a valid value looks like.
    """


@dataclass(frozen=True)
class Target:
    """One Onshape part studio or assembly to track.

    Attributes:
        name: Directory-safe label; names ``frames/<name>/`` and ``state/<name>.json``.
        document_id: The ``documents/<id>`` segment of the Onshape URL.
        workspace_id: The ``w/<id>`` segment of the Onshape URL.
        element_id: The ``e/<id>`` segment (the specific tab) of the Onshape URL.
        element_type: ``"assembly"`` or ``"partstudio"``.
    """

    name: str
    document_id: str
    workspace_id: str
    element_id: str
    element_type: str


@dataclass(frozen=True)
class Settings:
    """Global rendering and scheduling preferences shared by all targets.

    Attributes:
        image_width: Rendered PNG width in pixels.
        image_height: Rendered PNG height in pixels.
        view: A named Onshape view (e.g. ``"isometric"``) or a 12-number matrix string.
        backfill_interval_hours: Bucket size, in hours, for sampling history.
        timelapse_fps: Frames per second for the stitched timelapse video.
        keepalive: Whether the workflow commits a monthly no-op to defeat the
            60-day scheduled-workflow auto-disable.
    """

    image_width: int
    image_height: int
    view: str
    backfill_interval_hours: int
    timelapse_fps: int
    keepalive: bool


@dataclass(frozen=True)
class Config:
    """The fully parsed and validated configuration."""

    settings: Settings
    targets: tuple[Target, ...]


# Defaults applied when a key is absent from ``[settings]``. Mirrors the shipped
# config.toml so an upgrade that adds a setting doesn't break an older file.
_SETTINGS_DEFAULTS: dict[str, object] = {
    "image_width": 1024,
    "image_height": 1024,
    "view": "isometric",
    "backfill_interval_hours": 24,
    "timelapse_fps": 10,
    "keepalive": True,
}


def _is_safe_name(name: str) -> bool:
    """Return True if ``name`` is safe to use as a single directory component.

    Rejects empty strings, path separators, ``..``, leading dots, and whitespace
    so a target name can never escape ``frames/`` or collide with the filesystem.
    """
    if not name or name != name.strip():
        return False
    if name in (".", ".."):
        return False
    forbidden = set('/\\:*?"<>|')
    if any(c in forbidden for c in name):
        return False
    return not name.startswith(".")


def _require_str(raw: dict, key: str, where: str) -> str:
    """Fetch ``key`` from ``raw`` as a non-empty string or raise ConfigError."""
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"{where}: '{key}' is required and must be a non-empty string."
        )
    return value.strip()


def _coerce_setting(key: str, value: object) -> object:
    """Validate and coerce a single ``[settings]`` value against its default's type."""
    default = _SETTINGS_DEFAULTS[key]
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ConfigError(f"[settings]: '{key}' must be true or false.")
        return value
    if isinstance(default, int):
        # bool is a subclass of int; reject it explicitly so keepalive=1 isn't a size.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"[settings]: '{key}' must be a whole number.")
        if value <= 0:
            raise ConfigError(f"[settings]: '{key}' must be greater than zero.")
        return value
    # The only remaining default type is str (view).
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"[settings]: '{key}' must be a non-empty string.")
    return value.strip()


def _parse_settings(raw: dict) -> Settings:
    """Build a Settings object from the raw ``[settings]`` table, applying defaults."""
    if not isinstance(raw, dict):
        raise ConfigError("[settings] must be a table.")
    merged: dict[str, object] = {}
    for key, default in _SETTINGS_DEFAULTS.items():
        merged[key] = _coerce_setting(key, raw[key]) if key in raw else default
    unknown = set(raw) - set(_SETTINGS_DEFAULTS)
    if unknown:
        raise ConfigError(
            f"[settings]: unknown option(s) {sorted(unknown)}. "
            f"Valid options are {sorted(_SETTINGS_DEFAULTS)}."
        )
    return Settings(**merged)  # type: ignore[arg-type]


def _parse_target(raw: dict, index: int) -> Target:
    """Build one Target from a raw ``[[targets]]`` table."""
    where = f"targets[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: each target must be a table.")
    name = _require_str(raw, "name", where)
    if not _is_safe_name(name):
        raise ConfigError(
            f"{where}: name '{name}' is not a valid folder name. "
            "Use letters, numbers, dashes or underscores; no slashes or spaces."
        )
    element_type = _require_str(raw, "element_type", where)
    if element_type not in ELEMENT_TYPES:
        raise ConfigError(
            f"{where} ('{name}'): element_type must be one of "
            f"{list(ELEMENT_TYPES)}, not '{element_type}'."
        )
    return Target(
        name=name,
        document_id=_require_str(raw, "document_id", f"{where} ('{name}')"),
        workspace_id=_require_str(raw, "workspace_id", f"{where} ('{name}')"),
        element_id=_require_str(raw, "element_id", f"{where} ('{name}')"),
        element_type=element_type,
    )


def parse_config(data: dict) -> Config:
    """Validate an already-parsed TOML mapping and return a Config.

    Separated from file reading so tests can exercise validation without touching
    the filesystem.

    Raises:
        ConfigError: on any missing/invalid field, duplicate target name, or empty
            target list. The message names the field and how to fix it.
    """
    settings = _parse_settings(data.get("settings", {}))

    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ConfigError(
            "At least one [[targets]] entry is required. Add a [[targets]] block "
            "with document_id, workspace_id, element_id and element_type."
        )

    targets = tuple(_parse_target(t, i) for i, t in enumerate(raw_targets))

    seen: set[str] = set()
    for t in targets:
        if t.name in seen:
            raise ConfigError(
                f"Duplicate target name '{t.name}'. Each [[targets]] name must be "
                "unique — it is used as the frame folder name."
            )
        seen.add(t.name)

    return Config(settings=settings, targets=targets)


def load_config(path: str | Path = "config.toml") -> Config:
    """Read and validate ``config.toml`` from disk.

    Args:
        path: Path to the TOML file. Defaults to ``config.toml`` in the working dir.

    Raises:
        ConfigError: if the file is missing, not valid TOML, or fails validation.
    """
    p = Path(path)
    try:
        raw = p.read_bytes()
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Configuration file '{p}' not found. Copy the example config.toml and "
            "fill in your document IDs."
        ) from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"'{p}' is not valid TOML: {exc}") from exc
    return parse_config(data)
