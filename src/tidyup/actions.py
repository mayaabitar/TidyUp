"""Carry out planned moves, record them in the undo journal, and report what happened."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tidyup.errors import describe_os_error
from tidyup.scanner import PlannedMove, unique_destination
from tidyup.undo import Journal


@dataclass(frozen=True)
class MoveResult:
    move: PlannedMove
    status: str  # "moved", "skipped" or "error"
    final_destination: Path | None = None
    message: str = ""


def execute(
    moves: list[PlannedMove],
    journal: Journal,
    *,
    on_result: Callable[[MoveResult], None] | None = None,
) -> list[MoveResult]:
    """Perform each move. One failure never stops the rest of the run.

    The plan was made a moment ago, so the disk may have changed since: we re-check that
    the source still exists and re-pick a free name if the destination got taken.
    """
    results = []
    for move in moves:
        result = _execute_one(move, journal)
        results.append(result)
        if on_result is not None:
            on_result(result)
    return results


def _execute_one(move: PlannedMove, journal: Journal) -> MoveResult:
    if not move.source.is_file():
        return MoveResult(move, "skipped", message="file no longer exists")

    try:
        _make_dirs(move.destination.parent, journal)
        target = unique_destination(move.destination)
        # shutil.move renames when it can and falls back to copy + delete across drives.
        # Note: there is a tiny window between unique_destination() and the move where
        # another program could create the same file; that's acceptable for this tool.
        shutil.move(str(move.source), str(target))
    except OSError as exc:
        return MoveResult(move, "error", message=describe_os_error(exc))

    journal.record_move(move.source, target)
    note = f"renamed to {target.name}" if target.name != move.source.name else ""
    return MoveResult(move, "moved", final_destination=target, message=note)


def _make_dirs(directory: Path, journal: Journal) -> None:
    """Create ``directory`` and any missing parents, remembering each one for undo."""
    missing = []
    current = directory
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for folder in reversed(missing):
        folder.mkdir(exist_ok=True)
        journal.record_created_dir(folder)
