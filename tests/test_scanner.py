from pathlib import Path

import pytest

from tidyup.rules import parse_rules
from tidyup.scanner import plan, scan, unique_destination

RULES = parse_rules(
    """
rules:
  - {name: Images, match: {extensions: [jpg, png]}, destination: Images}
  - {name: Docs, match: {extensions: [pdf, txt]}, destination: Documents}
  - {name: Anything, match: {glob: "*"}, destination: Other}
"""
)


def names(paths):
    return [p.name for p in paths]


def test_scan_lists_files_only_and_skips_hidden(inbox, make_file):
    make_file(inbox / "b.txt")
    make_file(inbox / "A.txt")
    make_file(inbox / ".secret")
    make_file(inbox / ".DS_Store")
    make_file(inbox / "Thumbs.db")
    make_file(inbox / "sub" / "deep.txt")
    assert names(scan(inbox)) == ["A.txt", "b.txt"]  # sorted, case-insensitively


def test_scan_recursive(inbox, make_file):
    make_file(inbox / "top.txt")
    make_file(inbox / "sub" / "deep.txt")
    make_file(inbox / ".hidden_dir" / "skip.txt")
    assert sorted(names(scan(inbox, recursive=True))) == ["deep.txt", "top.txt"]


def test_scan_skips_symlinks(inbox, make_file, tmp_path):
    target = make_file(tmp_path / "elsewhere.txt")
    try:
        (inbox / "link.txt").symlink_to(target)
    except OSError:
        pytest.skip("creating symlinks needs extra permissions on this system")
    assert names(scan(inbox)) == []


def test_first_matching_rule_wins(inbox, make_file):
    make_file(inbox / "cat.jpg")
    make_file(inbox / "cv.pdf")
    make_file(inbox / "song.mp3")
    moves = {m.source.name: m for m in plan(inbox, RULES)}
    assert moves["cat.jpg"].destination == inbox / "Images" / "cat.jpg"
    assert moves["cat.jpg"].rule_name == "Images"
    assert moves["cv.pdf"].destination == inbox / "Documents" / "cv.pdf"
    assert moves["song.mp3"].rule_name == "Anything"


def test_unmatched_files_are_left_alone(inbox, make_file):
    rules = parse_rules("rules: [{name: I, match: {extensions: [jpg]}, destination: I}]")
    make_file(inbox / "keep.txt")
    assert plan(inbox, rules) == []


def test_planning_does_not_change_the_disk(inbox, make_file):
    make_file(inbox / "cat.jpg")
    before = sorted(p.relative_to(inbox) for p in inbox.rglob("*"))
    plan(inbox, RULES)
    after = sorted(p.relative_to(inbox) for p in inbox.rglob("*"))
    assert before == after


def test_collision_with_existing_file_gets_suffix(inbox, make_file):
    make_file(inbox / "Images" / "cat.jpg", "already sorted")
    make_file(inbox / "cat.jpg", "new one")
    [move] = plan(inbox, RULES)
    assert move.destination.name == "cat (1).jpg"
    assert move.renamed


def test_collision_between_planned_moves(inbox, make_file):
    make_file(inbox / "a" / "cat.jpg")
    make_file(inbox / "b" / "cat.jpg")
    make_file(inbox / "c" / "CAT.JPG")  # same file name on case-insensitive disks
    moves = plan(inbox, RULES, recursive=True)
    assert sorted(m.destination.name for m in moves) == ["CAT (2).JPG", "cat (1).jpg", "cat.jpg"]


def test_files_already_in_destination_are_skipped(inbox, make_file):
    make_file(inbox / "Images" / "cat.jpg")
    assert plan(inbox, RULES, recursive=True) == []


def test_running_twice_is_a_no_op(inbox, make_file):
    """After moving, a second recursive plan must not re-sort the sorted files."""
    make_file(inbox / "cat.jpg")
    for move in plan(inbox, RULES, recursive=True):
        move.destination.parent.mkdir(parents=True, exist_ok=True)
        move.source.replace(move.destination)
    assert plan(inbox, RULES, recursive=True) == []


def test_unique_destination(tmp_path, make_file):
    target = tmp_path / "report.pdf"
    assert unique_destination(target) == target
    make_file(target)
    make_file(tmp_path / "report (1).pdf")
    assert unique_destination(target) == tmp_path / "report (2).pdf"


def test_unique_destination_without_extension(tmp_path, make_file):
    make_file(tmp_path / "README")
    assert unique_destination(tmp_path / "README") == Path(tmp_path / "README (1)")
