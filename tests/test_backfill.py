"""Backfill scenario tests with a fake client (no network, no real sleeps)."""

from __future__ import annotations

from datetime import UTC, datetime

from progressor import frames
from progressor.backfill import run
from progressor.config import Config, Settings, Target
from progressor.onshape import ElementMetadata, OnshapeAPIError
from progressor.slots import Microversion
from progressor.state import read_state, state_path


def _utc(y, mo, d, h=0):
    return datetime(y, mo, d, h, tzinfo=UTC)


def _target(eid="E1", did="D1", wid="W1") -> Target:
    return Target(
        url=f"https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}",
        document_id=did,
        workspace_id=wid,
        element_id=eid,
    )


def _config(interval=24, *targets: Target) -> Config:
    settings = Settings(
        image_width=64,
        image_height=64,
        view="isometric",
        backfill_interval_hours=interval,
        timelapse_fps=10,
        keepalive=True,
    )
    return Config(settings=settings, targets=targets or (_target(),))


class FakeClient:
    def __init__(self, history, *, fail_render_for=()):
        self._history = history  # newest-first list
        self._fail = set(fail_render_for)
        self.rendered: list[str] = []

    def get_element_metadata(self, target):
        return ElementMetadata(name="Drivetrain", element_type="assembly")

    def get_document_name(self, did):
        return "Robot 2026"

    def iter_document_history(self, did, wid):
        yield from self._history

    def render_shaded_view(self, target, element_type, mid, *, view, width, height):
        if mid in self._fail:
            raise OnshapeAPIError(500, "render boom")
        self.rendered.append(mid)
        return f"PNG-{mid}".encode()


def _history_daily(ids_and_days):
    # ids_and_days newest-first: [("m3", day3), ("m2", day2), ...]
    return [Microversion(i, _utc(2024, 1, d)) for i, d in ids_and_days]


def test_renders_one_frame_per_changed_day(tmp_path) -> None:
    # m1 on day1, m2 on day2, m3 on day3. Daily sampling, now=day3.
    hist = _history_daily([("m3", 3), ("m2", 2), ("m1", 1)])
    client = FakeClient(hist)
    [res] = run(
        _config(24),
        client,
        now=_utc(2024, 1, 3),
        root=tmp_path,
        sleep=lambda s: None,
    )
    assert res.rendered == 3
    assert frames.exists("E1", "2024-01-01_00", tmp_path)
    assert frames.exists("E1", "2024-01-02_00", tmp_path)
    assert frames.exists("E1", "2024-01-03_00", tmp_path)


def test_unchanged_period_skipped(tmp_path) -> None:
    # Only one microversion ever; every boundary resolves to it -> 1 render, rest skip.
    hist = _history_daily([("m1", 1)])
    client = FakeClient(hist)
    [res] = run(
        _config(24), client, now=_utc(2024, 1, 4), root=tmp_path, sleep=lambda s: None
    )
    assert res.rendered == 1
    assert res.skipped_unchanged == 3  # days 2,3,4 unchanged since day 1
    assert client.rendered == ["m1"]


def test_existing_slot_skipped_resumable(tmp_path) -> None:
    hist = _history_daily([("m3", 3), ("m2", 2), ("m1", 1)])
    # Pretend day 2 was already produced by a prior (interrupted) run.
    frames.write_frame("E1", "2024-01-02_00", b"prior", tmp_path)
    client = FakeClient(hist)
    [res] = run(
        _config(24), client, now=_utc(2024, 1, 3), root=tmp_path, sleep=lambda s: None
    )
    assert res.rendered == 2  # days 1 and 3
    assert res.skipped_filled == 1  # day 2 already there
    assert frames.frame_path("E1", "2024-01-02_00", tmp_path).read_bytes() == b"prior"


def test_handoff_state_set_to_latest(tmp_path) -> None:
    hist = _history_daily([("m3", 3), ("m2", 2), ("m1", 1)])
    client = FakeClient(hist)
    run(_config(24), client, now=_utc(2024, 1, 3), root=tmp_path, sleep=lambda s: None)
    state = read_state(state_path("E1", tmp_path))
    assert state.last_microversion == "m3"  # newest, so forward job won't re-capture
    assert state.display_name == "Drivetrain"


def test_dry_run_renders_nothing_but_counts(tmp_path) -> None:
    hist = _history_daily([("m3", 3), ("m2", 2), ("m1", 1)])
    client = FakeClient(hist)
    [res] = run(
        _config(24),
        client,
        now=_utc(2024, 1, 3),
        root=tmp_path,
        dry_run=True,
        sleep=lambda s: None,
    )
    assert res.rendered == 3  # would render
    assert client.rendered == []  # but nothing actually rendered
    assert not frames.exists("E1", "2024-01-01_00", tmp_path)
    assert read_state(state_path("E1", tmp_path)).last_microversion is None


def test_render_error_is_tolerated(tmp_path) -> None:
    hist = _history_daily([("m3", 3), ("m2", 2), ("m1", 1)])
    client = FakeClient(hist, fail_render_for={"m2"})
    [res] = run(
        _config(24), client, now=_utc(2024, 1, 3), root=tmp_path, sleep=lambda s: None
    )
    assert res.errors == 1
    assert res.rendered == 2  # m1 and m3 still rendered despite m2 failing
    assert not frames.exists("E1", "2024-01-02_00", tmp_path)


def test_throttle_sleeps_between_renders(tmp_path) -> None:
    hist = _history_daily([("m2", 2), ("m1", 1)])
    client = FakeClient(hist)
    slept: list[float] = []
    run(
        _config(24),
        client,
        now=_utc(2024, 1, 2),
        root=tmp_path,
        render_sleep=2.5,
        sleep=slept.append,
    )
    assert slept == [2.5, 2.5]  # one sleep per actual render


def test_empty_history_noted(tmp_path) -> None:
    client = FakeClient([])
    [res] = run(
        _config(24), client, now=_utc(2024, 1, 2), root=tmp_path, sleep=lambda s: None
    )
    assert "no history" in res.note
