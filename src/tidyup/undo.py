"""The undo journal: one JSON file per run, stored in the user's data folder.

Each journal is rewritten after every successful move (atomically, via a temp file and
``Path.replace``), so even if TidyUp crashes halfway through a run, the moves that did
happen can still be undone.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import platformdirs

from tidyup.errors import describe_os_error

JOURNAL_VERSION = 1
APP_NAME = "tidyup"

# Tests (and curious users) can point TidyUp at a different data folder.
DATA_DIR_ENV = "TIDYUP_DATA_DIR"


def history_dir() -> Path:
    """Where journals live.

    macOS:   ~/Library/Application Support/tidyup/history
    Windows: %LOCALAPPDATA%\\tidyup\\history
    """
    override = os.environ.get(DATA_DIR_ENV)
    base = Path(override) if override else platformdirs.user_data_path(APP_NAME, appauthor=False)
    return base / "history"


@dataclass
class Journal:
    path: Path
    run_id: str
    created: str
    folder: str
    moves: list[dict[str, str]] = field(default_factory=list)
    created_dirs: list[str] = field(default_factory=list)
    undone: bool = False

    @classmethod
    def start(cls, folder: Path) -> Journal:
        now = datetime.now(timezone.utc)
        # Microseconds keep two quick runs from colliding. ISO-ish but without ":",
        # which is not allowed in Windows file names.
        run_id = now.strftime("%Y%m%dT%H%M%S%fZ")
        directory = history_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return cls(
            path=directory / f"run-{run_id}.json",
            run_id=run_id,
            created=now.isoformat(),
            folder=str(Path(folder).absolute()),
        )

    def record_move(self, source: Path, destination: Path) -> None:
        self.moves.append({"source": str(source), "destination": str(destination)})
        self.save()

    def record_created_dir(self, directory: Path) -> None:
        self.created_dirs.append(str(directory))
        self.save()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": JOURNAL_VERSION,
            "run_id": self.run_id,
            "created": self.created,
            "folder": self.folder,
            "moves": self.moves,
            "created_dirs": self.created_dirs,
            "undone": self.undone,
        }

    def save(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic rename on both macOS and Windows

    @classmethod
    def load(cls, path: Path) -> Journal:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != JOURNAL_VERSION:
            raise ValueError(f"{path.name}: unsupported journal version {data.get('version')}")
        return cls(
            path=path,
            run_id=data["run_id"],
            created=data["created"],
            folder=data["folder"],
            moves=list(data.get("moves", [])),
            created_dirs=list(data.get("created_dirs", [])),
            undone=bool(data.get("undone", False)),
        )


def list_journals() -> list[Journal]:
    """All readable journals with at least one move, newest first."""
    directory = history_dir()
    if not directory.is_dir():
        return []
    journals = []
    for path in sorted(directory.glob("run-*.json"), reverse=True):
        try:
            journal = Journal.load(path)
        except (OSError, ValueError, KeyError):
            continue  # skip corrupt or foreign files rather than crash
        if journal.moves:
            journals.append(journal)
    return journals


def latest_undoable() -> Journal | None:
    return next((j for j in list_journals() if not j.undone), None)


@dataclass(frozen=True)
class UndoResult:
    source: Path  # where the file is now (the run's destination)
    destination: Path  # where it goes back to (the run's source)
    status: str  # "restored", "would-restore", "skipped" or "error"
    message: str = ""


def undo(journal: Journal, *, dry_run: bool = False) -> list[UndoResult]:
    """Move every file in ``journal`` back, newest move first.

    A file is skipped (not overwritten) if it's missing or if something now occupies its
    original spot. The journal is only marked as undone when every file was restored.
    """
    results: list[UndoResult] = []

    for entry in reversed(journal.moves):
        original = Path(entry["source"])
        current = Path(entry["destination"])

        if not current.exists():
            results.append(UndoResult(current, original, "skipped", "file is no longer there"))
            continue
        if original.exists():
            results.append(UndoResult(current, original, "skipped", "original location is taken"))
            continue
        if dry_run:
            results.append(UndoResult(current, original, "would-restore"))
            continue

        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current), str(original))
        except OSError as exc:
            results.append(UndoResult(current, original, "error", describe_os_error(exc)))
        else:
            results.append(UndoResult(current, original, "restored"))

    if not dry_run:
        _remove_empty_dirs(journal.created_dirs)
        if all(r.status == "restored" for r in results):
            journal.undone = True
            journal.save()

    return results


def _remove_empty_dirs(directories: list[str]) -> None:
    """Remove folders this run created, deepest first, but only if they're empty."""
    for directory in sorted(directories, key=lambda d: len(Path(d).parts), reverse=True):
        # rmdir refuses non-empty folders, which is exactly what we want here.
        with contextlib.suppress(OSError):
            Path(directory).rmdir()
