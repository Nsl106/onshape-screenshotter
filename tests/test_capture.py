"""Forward-capture scenario tests with a fake client (no network, no real files)."""

from __future__ import annotations

from datetime import UTC, datetime

from progressor import frames
from progressor.capture import ABSENT, CAPTURED, ERROR, SLOT_FILLED, UNCHANGED, run
from progressor.config import Config, Settings, Target
from progressor.onshape import ElementMetadata, OnshapeAPIError
from progressor.slots import Microversion
from progressor.state import State, read_state, state_path, write_state


def _utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def _target(eid="E1", did="D1", wid="W1") -> Target:
    return Target(
        url=f"https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}",
        document_id=did,
        workspace_id=wid,
        element_id=eid,
    )


def _config(*targets: Target) -> Config:
    settings = Settings(
        image_width=64,
        image_height=64,
        view="isometric",
        backfill_interval_hours=1,
        timelapse_fps=10,
        keepalive=True,
    )
    return Config(settings=settings, targets=targets or (_target(),))


class FakeClient:
    """Configurable stand-in for OnshapeClient."""

    def __init__(
        self,
        history: dict[str, list[Microversion]] | None = None,
        element_type: str = "assembly",
        name: str = "Drivetrain",
        doc_name: str = "Robot 2026",
        render_error: bool = False,
        metadata_error: bool = False,
    ) -> None:
        self._history = history or {}
        self._element_type = element_type
        self._name = name
        self._doc_name = doc_name
        self._render_error = render_error
        self._metadata_error = metadata_error
        self.rendered: list[str] = []

    def get_element_metadata(self, target):
        if self._metadata_error:
            raise OnshapeAPIError(500, "metadata boom")
        return ElementMetadata(name=self._name, element_type=self._element_type)

    def get_document_name(self, did):
        return self._doc_name

    def iter_document_history(self, did, wid):
        yield from self._history.get(did, [])

    def render_shaded_view(self, target, element_type, mid, *, view, width, height):
        if self._render_error:
            raise OnshapeAPIError(500, "render boom")
        self.rendered.append(mid)
        return f"PNG-{mid}".encode()


def test_changed_writes_frame_and_state(tmp_path) -> None:
    hist = {"D1": [Microversion("m2", _utc(2024, 1, 5, 9))]}
    client = FakeClient(history=hist)
    [result] = run(_config(), client, at=_utc(2024, 1, 5, 9, 30), root=tmp_path)
    assert result.status == CAPTURED
    assert frames.frame_path("E1", "2024-01-05_09", tmp_path).read_bytes() == b"PNG-m2"
    state = read_state(state_path("E1", tmp_path))
    assert state.last_microversion == "m2"
    assert state.display_name == "Drivetrain"
    assert state.document_name == "Robot 2026"


def test_unchanged_skips(tmp_path) -> None:
    hist = {"D1": [Microversion("m2", _utc(2024, 1, 5, 9))]}
    write_state(state_path("E1", tmp_path), State(last_microversion="m2"))
    client = FakeClient(history=hist)
    [result] = run(_config(), client, at=_utc(2024, 1, 5, 9, 30), root=tmp_path)
    assert result.status == UNCHANGED
    assert client.rendered == []  # never rendered


def test_changed_but_slot_filled_skips(tmp_path) -> None:
    hist = {"D1": [Microversion("m2", _utc(2024, 1, 5, 9))]}
    frames.write_frame("E1", "2024-01-05_09", b"existing", tmp_path)
    client = FakeClient(history=hist)
    [result] = run(_config(), client, at=_utc(2024, 1, 5, 9, 30), root=tmp_path)
    assert result.status == SLOT_FILLED
    assert client.rendered == []
    # Existing frame untouched.
    assert (
        frames.frame_path("E1", "2024-01-05_09", tmp_path).read_bytes() == b"existing"
    )


def test_absent_at_t(tmp_path) -> None:
    # Only microversion is newer than T -> nothing current at T.
    hist = {"D1": [Microversion("m2", _utc(2024, 1, 5, 12))]}
    client = FakeClient(history=hist)
    [result] = run(_config(), client, at=_utc(2024, 1, 5, 9), root=tmp_path)
    assert result.status == ABSENT


def test_t_is_floored_to_hour(tmp_path) -> None:
    # A microversion created at 09:00 is current at the 09:00 mark recovered from 09:47.
    hist = {"D1": [Microversion("m2", _utc(2024, 1, 5, 9))]}
    client = FakeClient(history=hist)
    [result] = run(
        _config(), client, at=datetime(2024, 1, 5, 9, 47, tzinfo=UTC), root=tmp_path
    )
    assert result.status == CAPTURED
    assert frames.exists("E1", "2024-01-05_09", tmp_path)


def test_dry_run_writes_nothing(tmp_path) -> None:
    hist = {"D1": [Microversion("m2", _utc(2024, 1, 5, 9))]}
    client = FakeClient(history=hist)
    [result] = run(
        _config(), client, at=_utc(2024, 1, 5, 9), root=tmp_path, dry_run=True
    )
    assert result.status == CAPTURED
    assert "dry-run" in result.detail
    assert not frames.exists("E1", "2024-01-05_09", tmp_path)
    assert read_state(state_path("E1", tmp_path)).last_microversion is None


def test_one_target_errors_other_succeeds(tmp_path) -> None:
    t_ok = _target(eid="OK", did="DOK")
    t_bad = _target(eid="BAD", did="DBAD")
    hist = {
        "DOK": [Microversion("m9", _utc(2024, 1, 5, 9))],
        "DBAD": [Microversion("m1", _utc(2024, 1, 5, 9))],
    }

    class HalfBroken(FakeClient):
        def render_shaded_view(self, target, element_type, mid, **kw):
            if target.document_id == "DBAD":
                raise OnshapeAPIError(500, "render boom")
            return super().render_shaded_view(target, element_type, mid, **kw)

    client = HalfBroken(history=hist)
    results = run(_config(t_ok, t_bad), client, at=_utc(2024, 1, 5, 9), root=tmp_path)
    by_id = {r.element_id: r for r in results}
    assert by_id["OK"].status == CAPTURED
    assert by_id["BAD"].status == ERROR
    assert frames.exists("OK", "2024-01-05_09", tmp_path)


def test_readme_index_updated_after_capture(tmp_path) -> None:
    (tmp_path / "README.md").write_text(
        "# Title\n<!-- targets:start -->\nold\n<!-- targets:end -->\n", encoding="utf-8"
    )
    hist = {"D1": [Microversion("m2", _utc(2024, 1, 5, 9))]}
    client = FakeClient(history=hist)
    run(_config(), client, at=_utc(2024, 1, 5, 9), root=tmp_path)
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Robot 2026 / Drivetrain" in text
    assert "frames/E1/" in text
    assert "1 frame" in text
