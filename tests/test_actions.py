import errno
import json
import shutil

from tidyup.actions import execute
from tidyup.errors import describe_os_error
from tidyup.rules import parse_rules
from tidyup.scanner import plan
from tidyup.undo import Journal

RULES = parse_rules(
    """
rules:
  - {name: Images, match: {extensions: [jpg]}, destination: Media/Images}
  - {name: Docs, match: {extensions: [txt]}, destination: Documents}
"""
)


def test_execute_moves_files_and_creates_folders(inbox, make_file):
    make_file(inbox / "cat.jpg", "meow")
    make_file(inbox / "notes.txt", "hello")
    journal = Journal.start(inbox)

    results = execute(plan(inbox, RULES), journal)

    assert [r.status for r in results] == ["moved", "moved"]
    assert (inbox / "Media" / "Images" / "cat.jpg").read_text(encoding="utf-8") == "meow"
    assert (inbox / "Documents" / "notes.txt").exists()
    assert not (inbox / "cat.jpg").exists()


def test_journal_records_moves_and_created_folders(inbox, make_file):
    make_file(inbox / "cat.jpg")
    journal = Journal.start(inbox)
    execute(plan(inbox, RULES), journal)

    data = json.loads(journal.path.read_text(encoding="utf-8"))
    assert data["moves"] == [
        {
            "source": str(inbox / "cat.jpg"),
            "destination": str(inbox / "Media" / "Images" / "cat.jpg"),
        }
    ]
    assert data["created_dirs"] == [str(inbox / "Media"), str(inbox / "Media" / "Images")]


def test_source_deleted_after_planning_is_skipped(inbox, make_file):
    path = make_file(inbox / "cat.jpg")
    moves = plan(inbox, RULES)
    path.unlink()

    [result] = execute(moves, Journal.start(inbox))
    assert result.status == "skipped"


def test_destination_taken_after_planning_gets_new_name(inbox, make_file):
    make_file(inbox / "notes.txt", "mine")
    moves = plan(inbox, RULES)
    make_file(inbox / "Documents" / "notes.txt", "appeared meanwhile")

    [result] = execute(moves, Journal.start(inbox))
    assert result.status == "moved"
    assert result.final_destination.name == "notes (1).txt"
    assert (inbox / "Documents" / "notes.txt").read_text(encoding="utf-8") == "appeared meanwhile"


def test_one_failure_does_not_stop_the_run(inbox, make_file, monkeypatch):
    make_file(inbox / "cat.jpg")
    make_file(inbox / "notes.txt")
    real_move = shutil.move

    def flaky_move(src, dst):
        if src.endswith("cat.jpg"):
            raise PermissionError(errno.EACCES, "Permission denied")
        return real_move(src, dst)

    monkeypatch.setattr(shutil, "move", flaky_move)
    journal = Journal.start(inbox)
    results = {r.move.source.name: r for r in execute(plan(inbox, RULES), journal)}

    assert results["cat.jpg"].status == "error"
    assert results["cat.jpg"].message == "permission denied"
    assert results["notes.txt"].status == "moved"
    assert (inbox / "cat.jpg").exists()
    assert len(journal.moves) == 1  # only the successful move is undoable


def test_windows_locked_file_message():
    exc = PermissionError(errno.EACCES, "The process cannot access the file")
    exc.winerror = 32  # what Windows sets when another program has the file open
    assert describe_os_error(exc) == "file is open in another program"


def test_other_error_messages():
    assert describe_os_error(FileNotFoundError(errno.ENOENT, "x")) == (
        "file disappeared before it could be moved"
    )
    assert describe_os_error(OSError(errno.ENOSPC, "No space")) == "disk is full"
