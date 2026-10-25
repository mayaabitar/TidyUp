import pytest
from typer.testing import CliRunner

from tidyup import __version__
from tidyup.cli import app

RULES = """
rules:
  - {name: Images, match: {extensions: [jpg, png]}, destination: Images}
  - {name: Docs, match: {glob: "*.pdf"}, destination: Documents}
"""

# A wide fake terminal so Rich doesn't wrap file names across table lines.
ENV = {"COLUMNS": "200", "NO_COLOR": "1"}


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli(runner):
    def _invoke(*args):
        return runner.invoke(app, [str(a) for a in args], env=ENV)

    return _invoke


def test_version(cli):
    result = cli("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_dry_run_shows_plan_and_changes_nothing(cli, inbox, make_file, write_rules):
    make_file(inbox / "cat.jpg")
    make_file(inbox / "cv.pdf")
    make_file(inbox / "song.mp3")

    result = cli("run", inbox, "--rules", write_rules(RULES), "--dry-run")

    assert result.exit_code == 0, result.output
    assert "cat.jpg" in result.output and "cv.pdf" in result.output
    assert "song.mp3" not in result.output
    assert "2 file(s) would be moved" in result.output
    assert sorted(p.name for p in inbox.iterdir()) == ["cat.jpg", "cv.pdf", "song.mp3"]


def test_run_then_undo_round_trip(cli, inbox, make_file, write_rules):
    make_file(inbox / "cat.jpg")
    make_file(inbox / "cv.pdf")
    rules = write_rules(RULES)

    result = cli("run", inbox, "--rules", rules)
    assert result.exit_code == 0, result.output
    assert "Moved 2" in result.output
    assert (inbox / "Images" / "cat.jpg").exists()
    assert (inbox / "Documents" / "cv.pdf").exists()

    result = cli("history")
    assert result.exit_code == 0 and "active" in result.output

    result = cli("undo")
    assert result.exit_code == 0, result.output
    assert "Restored 2" in result.output
    assert sorted(p.name for p in inbox.iterdir()) == ["cat.jpg", "cv.pdf"]

    assert "Nothing to undo" in cli("undo").output


def test_file_names_with_brackets_are_shown_correctly(cli, inbox, make_file, write_rules):
    make_file(inbox / "photo [red].jpg")
    result = cli("run", inbox, "--rules", write_rules(RULES), "--dry-run")
    assert result.exit_code == 0, result.output
    assert "photo [red].jpg" in result.output


def test_nothing_to_do(cli, inbox, make_file, write_rules):
    make_file(inbox / "song.mp3")
    result = cli("run", inbox, "--rules", write_rules(RULES))
    assert result.exit_code == 0
    assert "Nothing to do" in result.output


def test_bad_rules_exit_with_code_2(cli, inbox, write_rules):
    result = cli("run", inbox, "--rules", write_rules("rules: []"))
    assert result.exit_code == 2


def test_missing_folder_is_rejected(cli, tmp_path, write_rules):
    result = cli("run", tmp_path / "nope", "--rules", write_rules(RULES))
    assert result.exit_code != 0


def test_dupes(cli, inbox, make_file):
    make_file(inbox / "a.txt", "twin")
    make_file(inbox / "sub" / "b.txt", "twin")
    result = cli("dupes", inbox)
    assert result.exit_code == 0, result.output
    assert "1 group(s)" in result.output
    assert "a.txt" in result.output and "b.txt" in result.output


def test_history_empty(cli):
    assert "No runs recorded yet" in cli("history").output
