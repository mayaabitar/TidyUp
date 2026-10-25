"""Make sure the files in examples/ stay valid as the code changes."""

import subprocess
import sys
from pathlib import Path

from tidyup.rules import load_rules
from tidyup.scanner import plan

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_example_rules_are_valid():
    rules = load_rules(EXAMPLES / "rules.yaml")
    assert len(rules) >= 3


def test_sandbox_script_and_example_rules_work_together(tmp_path):
    sandbox = tmp_path / "sandbox"
    subprocess.run(
        [sys.executable, str(EXAMPLES / "make_sandbox.py"), str(sandbox)],
        check=True,
        capture_output=True,
    )
    moves = {m.source.name: m.rule_name for m in plan(sandbox, load_rules(EXAMPLES / "rules.yaml"))}
    assert moves["holiday.JPG"] == "Images"
    assert moves["invoice-2024.pdf"] == "Old PDFs"
    assert moves["boarding-pass.pdf"] == "Documents"
    assert moves["Screenshot 2026-10-01 at 09.15.22.png"] == "Screenshots"
    assert "song.mp3" not in moves
