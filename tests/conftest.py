"""Shared test fixtures.

Every test works only on fake files inside pytest's ``tmp_path``. The undo journal is
redirected there too, so tests never touch your real data folder or real files.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

DAY = 24 * 60 * 60


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "_tidyup_data"
    monkeypatch.setenv("TIDYUP_DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    """An empty folder to fill with fake files."""
    folder = tmp_path / "inbox"
    folder.mkdir()
    return folder


@pytest.fixture
def make_file() -> Callable[..., Path]:
    """Create a fake file. ``age_days`` back-dates its modification time."""

    def _make(path: Path, content: str = "fake", *, age_days: float | None = None) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if age_days is not None:
            stamp = time.time() - age_days * DAY
            os.utime(path, (stamp, stamp))
        return path

    return _make


@pytest.fixture
def write_rules(tmp_path: Path) -> Callable[[str], Path]:
    """Write a rules YAML file (outside the inbox, so it isn't organized itself)."""

    def _write(text: str) -> Path:
        path = tmp_path / "rules.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    return _write
