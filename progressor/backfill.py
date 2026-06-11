"""History backfill — the one-time reconstruction entrypoint.

Run as ``python -m progressor.backfill``.

Enumerates a document's full history once, steps through boundary instants at
``backfill_interval_hours``, and at each boundary ``T`` resolves the microversion
current at ``T`` (the same state-as-of-``T`` rule the forward job uses) and renders
it into ``T``'s slot — unless that slot is already filled or the period saw no
change. After a target finishes, its state is set to the latest microversion so the
hourly forward job picks up without re-capturing. Backfill is intentionally a
separate manual trigger (slow, rate-limited) and is resumable: the per-slot
existence check alone lets an interrupted run continue from where it stopped.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import frames, index
from .config import Config, ConfigError, Target, load_config
from .onshape import OnshapeAuthError, OnshapeClient, OnshapeError
from .slots import Microversion, boundaries, microversion_at, slot_key
from .state import read_state, state_path, write_state

# Polite default pause between renders, on top of the client's own 429 handling —
# a backfill can be hundreds of renders, so we avoid hammering the API.
DEFAULT_RENDER_SLEEP = 2.0


@dataclass
class BackfillResult:
    """Per-target tally of what the backfill did (or would do, in dry-run)."""

    element_id: str
    rendered: int = 0
    skipped_filled: int = 0
    skipped_unchanged: int = 0
    errors: int = 0
    note: str = ""

    def line(self) -> str:
        """Concise one-line-per-target summary."""
        if self.note:
            return f"{self.element_id}: {self.note}"
        return (
            f"{self.element_id}: rendered {self.rendered}, "
            f"skipped {self.skipped_filled} filled / "
            f"{self.skipped_unchanged} unchanged, errors {self.errors}"
        )


def _backfill_target(
    client: OnshapeClient,
    target: Target,
    view: str,
    width: int,
    height: int,
    interval_hours: int,
    now: datetime,
    root: Path,
    dry_run: bool,
    render_sleep: float,
    sleep: Callable[[float], None],
) -> BackfillResult:
    """Reconstruct one target's history into frames; return a tally."""
    eid = target.element_id
    result = BackfillResult(element_id=eid)

    meta = client.get_element_metadata(target)
    # Enumerating full history can be many sequential pages for an active document
    # (Onshape caps the page size), so report progress instead of going silent.
    history: list[Microversion] = []
    for mv in client.iter_document_history(target.document_id, target.workspace_id):
        history.append(mv)
        if len(history) % 1000 == 0:
            print(f"{eid}: …enumerated {len(history)} microversions", file=sys.stderr)
    if not history:
        result.note = "no history (document has no microversions yet)"
        return result

    # History is newest-first: the oldest entry sets where sampling begins.
    start = history[-1].created_at
    prev_mid: str | None = None

    for t in boundaries(start, now, interval_hours):
        mv = microversion_at(history, t)
        if mv is None:
            continue  # boundary predates the first microversion
        slot = slot_key(t)

        if mv.id == prev_mid:
            result.skipped_unchanged += 1
            prev_mid = mv.id
            continue
        prev_mid = mv.id

        # The slot-existence check is what makes backfill resumable and keeps it
        # from overwriting forward-job or prior-backfill frames (first-writer-wins).
        if frames.exists(eid, slot, root):
            result.skipped_filled += 1
            continue

        if dry_run:
            result.rendered += 1  # "would render"
            continue

        try:
            png = client.render_shaded_view(
                target, meta.element_type, mv.id, view=view, width=width, height=height
            )
        except OnshapeError:
            # An old microversion may be unrenderable; log via the tally and go on.
            result.errors += 1
            continue
        if frames.write_frame(eid, slot, png, root):
            result.rendered += 1
        else:
            result.skipped_filled += 1
        sleep(render_sleep)

    if not dry_run:
        # Hand off to the forward job: point state at the latest microversion so it
        # won't re-capture the present, and cache metadata for the README index.
        state = read_state(state_path(eid, root))
        state.last_microversion = history[0].id
        state.last_captured_at = datetime.now(UTC).isoformat()
        state.element_type = meta.element_type
        state.display_name = meta.name
        try:
            state.document_name = client.get_document_name(target.document_id)
        except OnshapeError:
            pass
        write_state(state_path(eid, root), state)

    return result


def run(
    config: Config,
    client: OnshapeClient,
    *,
    now: datetime | None = None,
    root: Path | str = ".",
    dry_run: bool = False,
    render_sleep: float = DEFAULT_RENDER_SLEEP,
    sleep: Callable[[float], None] | None = None,
) -> list[BackfillResult]:
    """Backfill every configured target and return per-target tallies.

    Targets are isolated: a failure enumerating or handing off one target is
    recorded and the rest still run. Updates the README index at the end unless
    this is a dry run.
    """
    root = Path(root)
    now = now or datetime.now(UTC)
    sleep = sleep or time.sleep
    results: list[BackfillResult] = []
    for target in config.targets:
        try:
            results.append(
                _backfill_target(
                    client,
                    target,
                    config.settings.view,
                    config.settings.image_width,
                    config.settings.image_height,
                    config.settings.backfill_interval_hours,
                    now,
                    root,
                    dry_run,
                    render_sleep,
                    sleep,
                )
            )
        except OnshapeError as exc:
            results.append(BackfillResult(target.element_id, note=f"error: {exc}"))
        except Exception as exc:  # noqa: BLE001 - isolate per-target failures
            results.append(BackfillResult(target.element_id, note=f"error: {exc!r}"))

    if not dry_run and any(r.rendered for r in results):
        index.update_readme(config.targets, root)
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns 0 unless *every* target failed outright."""
    parser = argparse.ArgumentParser(
        prog="progressor.backfill",
        description="Reconstruct timelapse frames from an Onshape document's existing "
        "history, sampling at the configured interval.",
    )
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    parser.add_argument(
        "--root", default=".", help="repo root containing frames/ and state/"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print how many frames would be rendered vs. already filled, without "
        "rendering or spending API quota",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_RENDER_SLEEP,
        help=f"seconds to pause between renders (default {DEFAULT_RENDER_SLEEP})",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        client = OnshapeClient.from_env()
    except (ConfigError, OnshapeAuthError) as exc:
        print(exc, file=sys.stderr)
        return 1
    results = run(
        config,
        client,
        root=args.root,
        dry_run=args.dry_run,
        render_sleep=args.sleep,
    )
    for result in results:
        print(result.line())

    if results and all(r.note.startswith("error:") for r in results):
        print("All targets failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
