"""Tests for config parsing and validation (no filesystem or network)."""

from __future__ import annotations

import pytest

from progressor.config import ConfigError, parse_config


def _valid_data() -> dict:
    """A minimal valid parsed-TOML mapping; tests mutate copies of this."""
    return {
        "settings": {
            "image_width": 800,
            "image_height": 600,
            "view": "isometric",
            "backfill_interval_hours": 12,
            "timelapse_fps": 15,
            "keepalive": False,
        },
        "targets": [
            {
                "name": "robot",
                "document_id": "doc1",
                "workspace_id": "ws1",
                "element_id": "el1",
                "element_type": "assembly",
            }
        ],
    }


def test_valid_config_parses() -> None:
    cfg = parse_config(_valid_data())
    assert cfg.settings.image_width == 800
    assert cfg.settings.keepalive is False
    assert len(cfg.targets) == 1
    assert cfg.targets[0].name == "robot"
    assert cfg.targets[0].element_type == "assembly"


def test_settings_defaults_applied_when_absent() -> None:
    data = _valid_data()
    del data["settings"]
    cfg = parse_config(data)
    # Defaults mirror the shipped config.toml.
    assert cfg.settings.image_width == 1024
    assert cfg.settings.view == "isometric"
    assert cfg.settings.backfill_interval_hours == 24
    assert cfg.settings.timelapse_fps == 10
    assert cfg.settings.keepalive is True


def test_missing_required_target_field_raises() -> None:
    data = _valid_data()
    del data["targets"][0]["document_id"]
    with pytest.raises(ConfigError, match="document_id"):
        parse_config(data)


def test_empty_target_field_raises() -> None:
    data = _valid_data()
    data["targets"][0]["workspace_id"] = "   "
    with pytest.raises(ConfigError, match="workspace_id"):
        parse_config(data)


def test_bad_element_type_raises() -> None:
    data = _valid_data()
    data["targets"][0]["element_type"] = "drawing"
    with pytest.raises(ConfigError, match="element_type"):
        parse_config(data)


def test_duplicate_names_raise() -> None:
    data = _valid_data()
    data["targets"].append(dict(data["targets"][0]))
    with pytest.raises(ConfigError, match="Duplicate target name"):
        parse_config(data)


@pytest.mark.parametrize("bad_name", ["../escape", "a/b", "..", ".", "  ", ".hidden"])
def test_unsafe_target_name_raises(bad_name: str) -> None:
    data = _valid_data()
    data["targets"][0]["name"] = bad_name
    with pytest.raises(ConfigError):
        parse_config(data)


def test_no_targets_raises() -> None:
    data = _valid_data()
    data["targets"] = []
    with pytest.raises(ConfigError, match="targets"):
        parse_config(data)


def test_missing_targets_key_raises() -> None:
    data = _valid_data()
    del data["targets"]
    with pytest.raises(ConfigError, match="targets"):
        parse_config(data)


def test_negative_image_size_raises() -> None:
    data = _valid_data()
    data["settings"]["image_width"] = -10
    with pytest.raises(ConfigError, match="image_width"):
        parse_config(data)


def test_bool_for_int_setting_raises() -> None:
    data = _valid_data()
    data["settings"]["image_width"] = True
    with pytest.raises(ConfigError, match="image_width"):
        parse_config(data)


def test_unknown_setting_raises() -> None:
    data = _valid_data()
    data["settings"]["bogus"] = 1
    with pytest.raises(ConfigError, match="unknown"):
        parse_config(data)
