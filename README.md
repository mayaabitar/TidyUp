# TidyUp

[![CI](https://github.com/OWNER/tidyup/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/tidyup/actions/workflows/ci.yml)

A small cross-platform (macOS and Windows) command-line tool that sorts files into folders
using simple YAML rules. It shows you the plan before touching anything, and every run
can be undone.

```text
$ tidyup run ~/Downloads --rules rules.yaml --dry-run
                                 Planned moves
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ File             ┃ Rule      ┃ Destination                   ┃ Status     ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ holiday.JPG      │ Images    │ Images/holiday.JPG            │ would move │
│ invoice-2024.pdf │ Old PDFs  │ Archive/PDFs/invoice-2024.pdf │ would move │
│ notes.txt        │ Documents │ Documents/notes.txt           │ would move │
└──────────────────┴───────────┴───────────────────────────────┴────────────┘
Dry run: 3 file(s) would be moved. Nothing was changed.
```

## Features

- **Rules in YAML**: match by extension, glob, regular expression and file age.
- **Dry run**: see exactly what would happen in a table before anything moves.
- **Undo**: every run is recorded; `tidyup undo` puts files back where they were.
- **Safe with name clashes**: never overwrites; `report.pdf` becomes `report (1).pdf`.
- **Keeps going on errors**: a locked or protected file is reported and skipped, not fatal.
- **Duplicate finder**: `tidyup dupes` reports files with identical content (SHA-256).
- **Cross-platform**: tested on macOS and Windows in CI.

## Install

Requires Python 3.10 or newer.

```bash
git clone https://github.com/OWNER/tidyup.git
cd tidyup
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## Try it safely on fake files

The repo includes a script that makes a `sandbox/` folder full of tiny fake files
(it's git-ignored), so you never have to experiment on real files.

```bash
python examples/make_sandbox.py --fresh
tidyup run sandbox --rules examples/rules.yaml --dry-run
tidyup run sandbox --rules examples/rules.yaml
tidyup history
tidyup undo
tidyup dupes sandbox
```

## Commands

| Command | What it does |
|---|---|
| `tidyup run FOLDER --rules FILE` | Sort files in `FOLDER`. Add `--dry-run` (`-n`) to only preview, `--recursive` (`-R`) to include sub-folders. |
| `tidyup undo` | Undo the most recent run that hasn't been undone. `--dry-run` previews. |
| `tidyup history` | List past runs. |
| `tidyup dupes FOLDER` | Report duplicate files. Read-only; nothing is moved or deleted. `--no-recursive` to stay at the top level. |
| `tidyup --version` | Show the version. |

Exit codes: `0` success, `1` some files failed, `2` invalid rules or arguments.

## Writing rules

```yaml
rules:
  - name: Screenshots
    match:
      regex: "^(Screenshot|Screen Shot)"
    destination: Images/Screenshots

  - name: Old PDFs
    match:
      glob: "*.pdf"
      older_than_days: 30
    destination: Archive/PDFs

  - name: Images
    match:
      extensions: [jpg, jpeg, png, heic]
    destination: Images
```

- Rules are checked **top to bottom**; the **first match wins**.
- All conditions inside `match` must be true.
- `destination` is a folder **relative to the folder being organized**. It's created if
  needed. Absolute paths and `..` are rejected so a rule can't send files elsewhere.

| Condition | Example | Notes |
|---|---|---|
| `extensions` | `[jpg, .PNG]` | Case-insensitive; the dot is optional. |
| `glob` | `"IMG_*.heic"` | Matches the file name, case-insensitive on every OS. |
| `regex` | `"^\\d{4}-\\d{2}"` | Python regex searched in the file name. Case-sensitive; prefix with `(?i)` to ignore case. |
| `older_than_days` | `30` | Last modified at least this long ago. |
| `newer_than_days` | `7` | Last modified at most this long ago. |

See [`examples/rules.yaml`](examples/rules.yaml) for a fuller example.

## What TidyUp skips

Hidden files (names starting with `.`, plus files with the Windows hidden attribute),
symlinks, folders, OS clutter (`.DS_Store`, `Thumbs.db`, `desktop.ini`), and files already
inside their rule's destination folder. With `--recursive`, destination folders and hidden
folders are not entered, so running TidyUp twice is harmless.

## How undo works

Each real run writes a JSON journal to your user data folder:

- macOS: `~/Library/Application Support/tidyup/history/`
- Windows: `%LOCALAPPDATA%\tidyup\history\`

The journal is saved after every single move, so even a crash halfway through can be
undone. Undo restores files newest-first, never overwrites anything (a file is skipped if
its original spot is taken), and removes folders TidyUp created if they're empty again.
If some files couldn't be restored, fix the problem and run `tidyup undo` again.

Set `TIDYUP_DATA_DIR` to store journals somewhere else (the tests use this).

## Development

```bash
pytest                 # run the tests
ruff check .           # lint
ruff format .          # format
```

The tests only ever create fake files in temporary folders and redirect the undo journal,
so they never touch your real files or data folder.

Project layout:

```text
src/tidyup/
  cli.py         command-line interface (Typer + Rich)
  rules.py       load/validate YAML rules and match files
  scanner.py     list files and plan moves (collision-safe names)
  actions.py     perform moves, record them for undo
  undo.py        JSON journal and undo
  duplicates.py  SHA-256 duplicate detection
  errors.py      friendly messages for OS errors (locked files, permissions...)
tests/           pytest suite
examples/        example rules + fake-file sandbox script
```

## License

MIT. See [LICENSE](LICENSE).
