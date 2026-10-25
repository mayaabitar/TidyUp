"""Find files with identical content using SHA-256.

Hashing every file is slow, so files are first grouped by size: two files can only be
duplicates if they're the same size, and most files have a unique size.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tidyup.scanner import scan

CHUNK_SIZE = 1024 * 1024  # read 1 MiB at a time so huge files don't fill memory


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(folder: Path, *, recursive: bool = True) -> list[list[Path]]:
    """Return groups of 2+ files with identical content, each group sorted by path."""
    return group_duplicates(scan(Path(folder), recursive=recursive))


def group_duplicates(paths: Iterable[Path]) -> list[list[Path]]:
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in paths:
        try:
            by_size[path.stat().st_size].append(path)
        except OSError:
            continue

    groups: list[list[Path]] = []
    for size, same_size in by_size.items():
        if len(same_size) < 2:
            continue
        if size == 0:
            # Empty files are all "identical", but reporting them is just noise.
            continue
        by_hash: dict[str, list[Path]] = defaultdict(list)
        for path in same_size:
            try:
                by_hash[sha256_of(path)].append(path)
            except OSError:
                continue  # unreadable or locked; skip it
        groups.extend(sorted(g) for g in by_hash.values() if len(g) > 1)

    return sorted(groups, key=lambda g: str(g[0]).casefold())
