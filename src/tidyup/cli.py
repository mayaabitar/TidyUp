"""Command-line interface: ``tidyup run``, ``undo``, ``history`` and ``dupes``."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from tidyup import __version__
from tidyup.actions import MoveResult, execute
from tidyup.duplicates import find_duplicates
from tidyup.rules import RuleError, load_rules
from tidyup.scanner import PlannedMove, plan
from tidyup.undo import Journal, latest_undoable, list_journals, undo

app = typer.Typer(
    help="Organize files into folders using YAML rules. Safe by default: try --dry-run first.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)

FolderArg = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=False, dir_okay=True, help="Folder to organize."),
]


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"tidyup {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show the version."
        ),
    ] = False,
) -> None:
    """TidyUp: organize files using YAML rules, with dry-run and undo."""


@app.command()
def run(
    folder: FolderArg,
    rules: Annotated[
        Path,
        typer.Option(
            "--rules",
            "-r",
            exists=True,
            file_okay=True,
            dir_okay=False,
            help="YAML rules file.",
        ),
    ],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Show what would happen without moving.")
    ] = False,
    recursive: Annotated[
        bool, typer.Option("--recursive", "-R", help="Also look inside sub-folders.")
    ] = False,
) -> None:
    """Sort the files in FOLDER according to the rules file."""
    folder = folder.absolute()
    try:
        rule_list = load_rules(rules)
    except RuleError as exc:
        err_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=2) from None

    moves = plan(folder, rule_list, recursive=recursive)
    if not moves:
        console.print("Nothing to do: no files matched any rule.")
        return

    if dry_run:
        console.print(_plan_table(moves, folder))
        console.print(
            f"[bold]Dry run:[/bold] {len(moves)} file(s) would be moved. Nothing was changed."
        )
        return

    journal = Journal.start(folder)
    results = execute(moves, journal)
    console.print(_results_table(results, folder))

    moved = sum(r.status == "moved" for r in results)
    skipped = sum(r.status == "skipped" for r in results)
    failed = sum(r.status == "error" for r in results)
    console.print(f"[bold]Moved {moved}[/bold], skipped {skipped}, failed {failed}.")
    if moved:
        console.print("Changed your mind? Run [bold]tidyup undo[/bold].")
    if failed:
        raise typer.Exit(code=1)


@app.command(name="undo")
def undo_command(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Show what would be restored.")
    ] = False,
) -> None:
    """Move the files from the most recent run back where they came from."""
    journal = latest_undoable()
    if journal is None:
        console.print("Nothing to undo.")
        return

    console.print(f"Undoing run from {_friendly_time(journal.created)} in {escape(journal.folder)}")
    results = undo(journal, dry_run=dry_run)

    folder = Path(journal.folder)
    table = Table("File", "Back to", "Status")
    for r in results:
        table.add_row(
            _relative(r.source, folder),
            _relative(r.destination, folder),
            _status_text(r.status, r.message),
        )
    console.print(table)

    if dry_run:
        console.print("[bold]Dry run:[/bold] nothing was changed.")
        return

    restored = sum(r.status == "restored" for r in results)
    problems = len(results) - restored
    console.print(f"[bold]Restored {restored}[/bold] file(s).")
    if problems:
        console.print(
            f"[yellow]{problems} file(s) could not be restored.[/yellow] "
            "Fix the issue and run [bold]tidyup undo[/bold] again to retry."
        )
        raise typer.Exit(code=1)


@app.command()
def history() -> None:
    """List past runs, newest first."""
    journals = list_journals()
    if not journals:
        console.print("No runs recorded yet.")
        return
    table = Table("When", "Folder", "Files", "Status")
    for j in journals:
        status = "[dim]undone[/dim]" if j.undone else "[green]active[/green]"
        table.add_row(_friendly_time(j.created), escape(j.folder), str(len(j.moves)), status)
    console.print(table)


@app.command()
def dupes(
    folder: FolderArg,
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", help="Look inside sub-folders.")
    ] = True,
) -> None:
    """Report files with identical content (SHA-256). Nothing is moved or deleted."""
    folder = folder.absolute()
    groups = find_duplicates(folder, recursive=recursive)
    if not groups:
        console.print("No duplicates found.")
        return

    wasted = 0
    for number, group in enumerate(groups, start=1):
        size = group[0].stat().st_size
        wasted += size * (len(group) - 1)
        console.print(f"[bold]Group {number}[/bold] ({_human_size(size)} each)")
        for path in group:
            console.print(f"  {_relative(path, folder)}")
    console.print(f"\n{len(groups)} group(s) of duplicates; {_human_size(wasted)} could be freed.")


# --- helpers -------------------------------------------------------------------------


def _plan_table(moves: list[PlannedMove], folder: Path) -> Table:
    table = Table("File", "Rule", "Destination", "Status", title="Planned moves")
    for m in moves:
        status = "would rename" if m.renamed else "would move"
        table.add_row(
            _relative(m.source, folder),
            escape(m.rule_name),
            _relative(m.destination, folder),
            _status_text(status),
        )
    return table


def _results_table(results: list[MoveResult], folder: Path) -> Table:
    table = Table("File", "Rule", "Destination", "Status")
    for r in results:
        destination = r.final_destination or r.move.destination
        table.add_row(
            _relative(r.move.source, folder),
            escape(r.move.rule_name),
            _relative(destination, folder),
            _status_text(r.status, r.message),
        )
    return table


_STATUS_STYLES = {
    "moved": "green",
    "restored": "green",
    "would move": "cyan",
    "would rename": "yellow",
    "would-restore": "cyan",
    "skipped": "yellow",
    "error": "red",
}


def _status_text(status: str, message: str = "") -> str:
    style = _STATUS_STYLES.get(status, "white")
    text = f"[{style}]{status}[/{style}]"
    return f"{text} ({escape(message)})" if message else text


def _relative(path: Path, folder: Path) -> str:
    # escape() matters: a file called "photo [1].jpg" would otherwise be read as Rich markup.
    try:
        return escape(str(path.relative_to(folder)))
    except ValueError:
        return escape(str(path))


def _friendly_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover
