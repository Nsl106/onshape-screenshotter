"""Forward capture job — the hourly entrypoint (``python -m progressor.capture``).

For each configured target it anchors on the top of the scheduled hour ``T``,
resolves the microversion that was current at ``T``, and renders + files a frame
only if the document changed since the last capture and the slot isn't already
filled. Targets are processed independently: one failing target never stops the
others. Git commit/push is handled by the workflow, not here, so this script has
no side effects beyond writing into ``frames/`` and ``state/`` (and the README
index) — making it safe to run and ``--dry-run`` locally.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import frames, index
from .config import Config, Target, load_config
from .onshape import OnshapeClient, OnshapeError
from .slots import floor_to_hour, microversion_at, slot_key
from .state import State, read_state, state_path, write_state

# Per-target outcomes, in the order they're reported on the one-line summary.
CAPTURED = "captured"
UNCHANGED = "unchanged"
SLOT_FILLED = "skipped (slot filled)"
ABSENT = "absent at T"
ERROR = "error"


@dataclass
class TargetResult:
    """The outcome of processing one target, for logging and the exit code."""

    element_id: str
    status: str
    detail: str = ""

    def line(self) -> str:
        """Format the concise one-line-per-target log entry."""
        suffix = f" {self.detail}" if self.detail else ""
        return f"{self.element_id}: {self.status}{suffix}"


def _resolve_target_type(
    client: OnshapeClient, target: Target, state: State
) -> tuple[str, State]:
    """Return the element type, fetching+caching metadata into state if needed."""
    if state.element_type:
        return state.element_type, state
    meta = client.get_element_metadata(target)
    state.element_type = meta.element_type
    state.display_name = meta.name
    return meta.element_type, state


def _process_target(
    client: OnshapeClient,
    target: Target,
    settings_view: str,
    width: int,
    height: int,
    t: datetime,
    root: Path,
    dry_run: bool,
) -> TargetResult:
    """Run the full forward-capture decision for a single target at instant ``T``.

    Mirrors SPEC's forward-job steps: resolve the microversion current at ``T``,
    skip if unchanged or if the slot is already filled, otherwise render at that
    microversion and write the frame + updated state.
    """
    eid = target.element_id
    state = read_state(state_path(eid, root))
    element_type, state = _resolve_target_type(client, target, state)

    history = client.iter_document_history(target.document_id, target.workspace_id)
    mv = microversion_at(history, t)
    if mv is None:
        return TargetResult(
            eid, ABSENT, f"(document had no microversion at {slot_key(t)})"
        )

    if mv.id == state.last_microversion:
        return TargetResult(eid, UNCHANGED)

    slot = slot_key(t)
    if frames.exists(eid, slot, root):
        return TargetResult(eid, SLOT_FILLED, f"{slot}")

    if dry_run:
        return TargetResult(eid, CAPTURED, f"{slot} (dry-run, not written)")

    png = client.render_shaded_view(
        target, element_type, mv.id, view=settings_view, width=width, height=height
    )
    wrote = frames.write_frame(eid, slot, png, root)
    if not wrote:
        # Another writer filled the slot between the check and now — respect it.
        return TargetResult(eid, SLOT_FILLED, f"{slot}")

    # Refresh display metadata on a real capture so the README index stays current.
    try:
        meta = client.get_element_metadata(target)
        state.element_type = meta.element_type
        state.display_name = meta.name
        state.document_name = client.get_document_name(target.document_id)
    except OnshapeError:
        pass  # Metadata is cosmetic; never fail a successful capture over it.

    state.last_microversion = mv.id
    state.last_captured_at = datetime.now(UTC).isoformat()
    write_state(state_path(eid, root), state)
    return TargetResult(eid, CAPTURED, slot)


def run(
    config: Config,
    client: OnshapeClient,
    *,
    at: datetime | None = None,
    root: Path | str = ".",
    dry_run: bool = False,
) -> list[TargetResult]:
    """Process every target for the hour mark ``T`` and return per-target results.

    ``T`` is ``at`` (if given) or now, floored to the hour. Each target is isolated
    in its own try/except so one failure can't abort the rest. Updates the README
    index once at the end (unless dry-run).
    """
    root = Path(root)
    t = floor_to_hour(at or datetime.now(UTC))
    results: list[TargetResult] = []
    for target in config.targets:
        try:
            results.append(
                _process_target(
                    client,
                    target,
                    config.settings.view,
                    config.settings.image_width,
                    config.settings.image_height,
                    t,
                    root,
                    dry_run,
                )
            )
        except OnshapeError as exc:
            results.append(TargetResult(target.element_id, ERROR, str(exc)))
        except Exception as exc:  # noqa: BLE001 - isolate any target-specific failure
            results.append(TargetResult(target.element_id, ERROR, repr(exc)))

    if not dry_run and any(r.status == CAPTURED for r in results):
        index.update_readme(config.targets, root)
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns 0 unless *every* target errored."""
    parser = argparse.ArgumentParser(
        prog="progressor.capture",
        description="Render the microversion current at the top of the hour for each "
        "configured Onshape target and save it as a timelapse frame.",
    )
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    parser.add_argument(
        "--at",
        metavar="ISO_DATETIME",
        help="capture as of this instant instead of now (ISO-8601, UTC assumed); "
        "for testing and manual gap-filling",
    )
    parser.add_argument(
        "--root", default=".", help="repo root containing frames/ and state/"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve and report what would be captured without writing any files",
    )
    args = parser.parse_args(argv)

    at = datetime.fromisoformat(args.at) if args.at else None
    config = load_config(args.config)
    client = OnshapeClient.from_env()

    results = run(config, client, at=at, root=args.root, dry_run=args.dry_run)
    for result in results:
        print(result.line())

    if results and all(r.status == ERROR for r in results):
        print("All targets failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
