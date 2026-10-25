from pathlib import Path

import pytest

from tidyup.rules import RuleError, load_rules, parse_rules

BASIC = """
rules:
  - name: Images
    match:
      extensions: [jpg, .PNG]
    destination: Images
  - name: Old PDFs
    match:
      glob: "*.pdf"
      older_than_days: 30
    destination: Archive/PDFs
"""


def test_parse_basic_rules():
    rules = parse_rules(BASIC)
    assert [r.name for r in rules] == ["Images", "Old PDFs"]
    assert rules[0].match.extensions == {"jpg", "png"}  # dots stripped, lower-cased
    assert rules[1].destination == Path("Archive") / "PDFs"


def test_extension_match_is_case_insensitive(inbox, make_file):
    rule = parse_rules(BASIC)[0]
    assert rule.matches(make_file(inbox / "Holiday.JPG"))
    assert rule.matches(make_file(inbox / "shot.png"))
    assert not rule.matches(make_file(inbox / "notes.txt"))
    assert not rule.matches(make_file(inbox / "no_extension"))


def test_glob_is_case_insensitive_on_every_os(inbox, make_file):
    rule = parse_rules('rules: [{name: R, match: {glob: "*.pdf"}, destination: D}]')[0]
    assert rule.matches(make_file(inbox / "REPORT.PDF"))
    assert not rule.matches(make_file(inbox / "report.pdf.txt"))


def test_regex_searches_the_file_name(inbox, make_file):
    rule = parse_rules(r'rules: [{name: R, match: {regex: "^IMG_\\d{4}"}, destination: D}]')[0]
    assert rule.matches(make_file(inbox / "IMG_1234.heic"))
    assert not rule.matches(make_file(inbox / "my_IMG_1234.heic"))


def test_age_conditions(inbox, make_file):
    rules = parse_rules(
        """
rules:
  - {name: Old, match: {older_than_days: 30}, destination: Old}
  - {name: Recent, match: {newer_than_days: 7}, destination: Recent}
"""
    )
    old, recent = rules
    ancient = make_file(inbox / "ancient.txt", age_days=60)
    fresh = make_file(inbox / "fresh.txt", age_days=1)
    assert old.matches(ancient) and not old.matches(fresh)
    assert recent.matches(fresh) and not recent.matches(ancient)


def test_all_conditions_must_match(inbox, make_file):
    rule = parse_rules(BASIC)[1]  # *.pdf AND older than 30 days
    assert rule.matches(make_file(inbox / "old.pdf", age_days=45))
    assert not rule.matches(make_file(inbox / "new.pdf", age_days=2))
    assert not rule.matches(make_file(inbox / "old.txt", age_days=45))


def test_backslash_destination_works_on_any_os():
    rule = parse_rules(r'rules: [{name: R, match: {glob: "*"}, destination: "A\\B"}]')[0]
    assert rule.destination.parts == ("A", "B")


def test_non_ascii_rules_are_read_as_utf8(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules: [{name: Reçus, match: {glob: '*.pdf'}, destination: Reçus}]", encoding="utf-8"
    )
    assert load_rules(path)[0].name == "Reçus"


def test_missing_rules_file(tmp_path):
    with pytest.raises(RuleError, match="not found"):
        load_rules(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "top-level 'rules:'"),
        ("rules: []", "non-empty list"),
        ("rules: [oops]", "must be a mapping"),
        ("rules: [{match: {glob: '*'}, destination: D}]", "'name'"),
        ("rules: [{name: R, match: {glob: '*'}}]", "'destination'"),
        ("rules: [{name: R, destination: D}]", "'match'"),
        ("rules: [{name: R, match: {}, destination: D}]", "'match'"),
        ("rules: [{name: R, match: {size: 3}, destination: D}]", "unknown match key"),
        ("rules: [{name: R, match: {glob: '*'}, destination: D, x: 1}]", "unknown key"),
        ("rules: [{name: R, match: {regex: '('}, destination: D}]", "invalid regex"),
        ("rules: [{name: R, match: {older_than_days: -1}, destination: D}]", ">= 0"),
        ("rules: [{name: R, match: {older_than_days: yes}, destination: D}]", ">= 0"),
        ("rules: [{name: R, match: {extensions: [1]}, destination: D}]", "list of strings"),
        ("rules: [{name: R, match: {glob: '*'}, destination: ../up}]", "'..'"),
        ("rules: [{name: R, match: {glob: '*'}, destination: /abs}]", "relative path"),
        ("rules: [{name: R, match: {glob: '*'}, destination: 'C:/abs'}]", "relative path"),
        ("rules: [{name: R, match: {glob: '*'}, destination: .}]", "sub-folder"),
        (
            "rules: [{name: R, match: {glob: '*'}, destination: A},"
            " {name: R, match: {glob: '*'}, destination: B}]",
            "duplicate rule names",
        ),
        (
            "rules: [{name: R, match: {older_than_days: 9, newer_than_days: 3}, destination: D}]",
            "larger than",
        ),
        ("rules: [unclosed", "invalid YAML"),
    ],
)
def test_invalid_rules_give_clear_errors(text, message):
    with pytest.raises(RuleError, match=message):
        parse_rules(text)
