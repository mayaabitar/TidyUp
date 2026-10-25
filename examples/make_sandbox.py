"""Create a folder of fake files to try TidyUp on safely.

    python examples/make_sandbox.py            # creates ./sandbox
    python examples/make_sandbox.py --fresh    # deletes ./sandbox first

Every file is a tiny text file with a made-up name. Nothing real is touched.
"""

from __future__ import annotations

import argparse
import os
import shutil
import time
from pathlib import Path

DAY = 24 * 60 * 60

# (name, content, age in days)
FAKE_FILES = [
    ("Screenshot 2026-10-01 at 09.15.22.png", "fake screenshot", 23),
    ("holiday.JPG", "fake photo", 5),
    ("cat [best].jpeg", "fake photo with brackets in the name", 2),
    ("invoice-2024.pdf", "fake old invoice", 400),
    ("boarding-pass.pdf", "fake recent pdf", 1),
    ("notes.txt", "fake notes", 3),
    ("Reçu café.md", "fake receipt with accents", 10),
    ("setup.dmg", "fake installer", 60),
    ("backup.zip", "fake archive", 90),
    ("song.mp3", "no rule matches this one", 7),
    ("copy-of-notes.txt", "fake notes", 3),  # same content as notes.txt -> duplicate
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", nargs="?", default="sandbox", type=Path)
    parser.add_argument("--fresh", action="store_true", help="delete the folder first")
    args = parser.parse_args()

    folder: Path = args.folder
    if args.fresh and folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

    now = time.time()
    for name, content, age_days in FAKE_FILES:
        path = folder / name
        path.write_text(content, encoding="utf-8")
        stamp = now - age_days * DAY
        os.utime(path, (stamp, stamp))

    print(f"Created {len(FAKE_FILES)} fake files in {folder.absolute()}")


if __name__ == "__main__":
    main()
