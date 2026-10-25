"""Find files in a folder and plan where each one should go.

Planning never touches the disk except to read file names and metadata, which is what
makes ``--dry-run`` safe.
"""

from __future__ import annotations

import stat
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tidyup.rules import Rule

# Files the OS creates on its own. Moving them around is never what the user wants.
IGNORED_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini", "icon\r"})

# Windows "hidden" file attribute. getattr() keeps this safe on Mac, where it doesn't exist.
_FILE_ATTRIBUTE_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2)


@dataclass(frozen=True)
class PlannedMove:
    source: Path
    destination: Path
    rule_name: str

    @property
    def renamed(self) -> bool:
        """True when the file gets a new name to avoid a collision."""
        return self.source.name != self.destination.name


def is_hidden(path: Path) -> bool:
    """Hidden on Mac/Linux = name starts with a dot. On Windows, also the hidden attribute."""
    if path.name.startswith("."):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _FILE_ATTRIBUTE_HIDDEN)


def scan(folder: Path, *, recursive: bool = False, exclude: Iterable[Path] = ()) -> Iterator[Path]:
    """Yield regular files in ``folder``, sorted by name for stable output.

    Skips symlinks, hidden files, OS clutter and anything inside ``exclude`` folders.
    Hidden folders are not entered when ``recursive`` is True.
    """
    excluded = {_normalize(p) for p in exclude}
    yield from _scan_dir(Path(folder), recursive, excluded)


def _scan_dir(folder: Path, recursive: bool, excluded: set[str]) -> Iterator[Path]:
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
    except (PermissionError, FileNotFoundError):
        return

    for entry in entries:
        if entry.is_symlink() or is_hidden(entry) or entry.name.casefold() in IGNORED_NAMES:
            continue
        if entry.is_dir():
            if recursive and _normalize(entry) not in excluded:
                yield from _scan_dir(entry, recursive, excluded)
        elif entry.is_file():
            yield entry


def plan(
    folder: Path,
    rules: list[Rule],
    *,
    recursive: bool = False,
    now: float | None = None,
) -> list[PlannedMove]:
    """Decide where each file in ``folder`` should go. The first matching rule wins.

    Files already sitting in their rule's destination folder are left alone, and name
    collisions (with files on disk or with other planned moves) get a " (1)" style suffix.
    """
    folder = Path(folder)
    now = time.time() if now is None else now

    # When recursing, don't descend into destination folders, or a second run would
    # try to re-sort files that are already sorted.
    destinations = [rule.destination_dir(folder) for rule in rules]
    claimed: set[str] = set()
    moves: list[PlannedMove] = []

    for path in scan(folder, recursive=recursive, exclude=destinations):
        rule = next((r for r in rules if _safe_matches(r, path, now)), None)
        if rule is None:
            continue

        dest_dir = rule.destination_dir(folder)
        if _normalize(path.parent) == _normalize(dest_dir):
            continue

        target = unique_destination(dest_dir / path.name, claimed=claimed)
        claimed.add(_normalize(target))
        moves.append(PlannedMove(source=path, destination=target, rule_name=rule.name))

    return moves


def _safe_matches(rule: Rule, path: Path, now: float) -> bool:
    try:
        return rule.matches(path, now=now)
    except OSError:
        # The file vanished or became unreadable between listing and stat().
        return False


def unique_destination(target: Path, *, claimed: set[str] | None = None) -> Path:
    """Return ``target`` or the first free "name (n).ext" variant.

    A name is taken if it exists on disk or its normalized form is in ``claimed``.
    """
    claimed = claimed or set()

    def taken(candidate: Path) -> bool:
        return candidate.exists() or _normalize(candidate) in claimed

    if not taken(target):
        return target

    # Path.stem/suffix only handle the last dot: "archive.tar.gz" -> "archive.tar (1).gz".
    # That's the same thing Finder and Explorer do, so it's fine.
    stem, suffix = target.stem, target.suffix
    counter = 1
    while True:
        candidate = target.with_name(f"{stem} ({counter}){suffix}")
        if not taken(candidate):
            return candidate
        counter += 1


def _normalize(path: Path) -> str:
    """Key for comparing paths. casefold() because macOS (APFS default) and Windows
    file systems are case-insensitive: "Report.pdf" and "report.pdf" are the same file."""
    return str(Path(path).absolute()).casefold()
