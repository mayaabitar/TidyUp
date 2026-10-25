from tidyup.actions import execute
from tidyup.rules import parse_rules
from tidyup.scanner import plan
from tidyup.undo import Journal, history_dir, latest_undoable, list_journals, undo

RULES = parse_rules("rules: [{name: Images, match: {extensions: [jpg]}, destination: A/B}]")


def organize(folder):
    journal = Journal.start(folder)
    execute(plan(folder, RULES), journal)
    return journal


def test_history_dir_respects_env(isolated_data_dir):
    assert history_dir() == isolated_data_dir / "history"


def test_dry_run_creates_no_journal(inbox, make_file):
    make_file(inbox / "cat.jpg")
    plan(inbox, RULES)
    assert list_journals() == []


def test_undo_restores_files_and_removes_created_folders(inbox, make_file):
    make_file(inbox / "cat.jpg", "meow")
    make_file(inbox / "dog.jpg", "woof")
    journal = organize(inbox)
    assert not (inbox / "cat.jpg").exists()

    results = undo(journal)

    assert {r.status for r in results} == {"restored"}
    assert (inbox / "cat.jpg").read_text(encoding="utf-8") == "meow"
    assert (inbox / "dog.jpg").exists()
    assert not (inbox / "A").exists()  # empty folders TidyUp made are cleaned up
    assert Journal.load(journal.path).undone


def test_undo_keeps_folders_that_are_not_empty(inbox, make_file):
    make_file(inbox / "cat.jpg")
    journal = organize(inbox)
    make_file(inbox / "A" / "B" / "user_added.txt")

    undo(journal)
    assert (inbox / "A" / "B" / "user_added.txt").exists()


def test_undo_never_overwrites(inbox, make_file):
    make_file(inbox / "cat.jpg", "original")
    journal = organize(inbox)
    make_file(inbox / "cat.jpg", "a new file with the same name")

    [result] = undo(journal)

    assert result.status == "skipped"
    assert (inbox / "cat.jpg").read_text(encoding="utf-8") == "a new file with the same name"
    assert (inbox / "A" / "B" / "cat.jpg").read_text(encoding="utf-8") == "original"
    assert not Journal.load(journal.path).undone  # still undoable once the user fixes it


def test_undo_dry_run_changes_nothing(inbox, make_file):
    make_file(inbox / "cat.jpg")
    journal = organize(inbox)

    [result] = undo(journal, dry_run=True)

    assert result.status == "would-restore"
    assert (inbox / "A" / "B" / "cat.jpg").exists()
    assert not Journal.load(journal.path).undone


def test_latest_undoable_skips_undone_runs(tmp_path, make_file):
    first, second = tmp_path / "one", tmp_path / "two"
    make_file(first / "a.jpg")
    make_file(second / "b.jpg")
    run1 = organize(first)
    run2 = organize(second)

    assert latest_undoable().run_id == run2.run_id
    undo(run2)
    assert latest_undoable().run_id == run1.run_id
    undo(run1)
    assert latest_undoable() is None


def test_corrupt_journal_is_ignored(inbox, make_file, isolated_data_dir):
    make_file(inbox / "cat.jpg")
    good = organize(inbox)
    (history_dir() / "run-99999999T999999999999Z.json").write_text("{not json", encoding="utf-8")

    assert [j.run_id for j in list_journals()] == [good.run_id]
