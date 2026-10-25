"""Load and validate YAML rules, and decide whether a file matches a rule.

A rules file looks like this:

    rules:
      - name: Images
        match:
          extensions: [jpg, jpeg, png]
        destination: Images

      - name: Old PDFs
        match:
          glob: "*.pdf"
          older_than_days: 30
        destination: Archive/PDFs

Every condition inside ``match`` must be true for the rule to match (logical AND).
Rules are checked from top to bottom, and the first matching rule wins.
"""

from __future__ import annotations

import fnmatch
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SECONDS_PER_DAY = 24 * 60 * 60

_ALLOWED_RULE_KEYS = {"name", "match", "destination"}
_ALLOWED_MATCH_KEYS = {"extensions", "glob", "regex", "older_than_days", "newer_than_days"}


class RuleError(ValueError):
    """Raised when a rules file is missing, unreadable, or invalid."""


@dataclass(frozen=True)
class Match:
    """The conditions a file must satisfy. Unset conditions are ignored."""

    extensions: frozenset[str] = field(default_factory=frozenset)
    glob: str | None = None
    regex: re.Pattern[str] | None = None
    older_than_days: float | None = None
    newer_than_days: float | None = None

    def matches(self, path: Path, *, now: float | None = None) -> bool:
        name = path.name

        if self.extensions and _extension(name) not in self.extensions:
            return False

        # Lower-case both sides so "*.PDF" behaves the same on Mac, Windows and Linux.
        # (fnmatch.fnmatch is case-sensitive on POSIX but not on Windows.)
        if self.glob is not None and not fnmatch.fnmatchcase(name.lower(), self.glob.lower()):
            return False

        if self.regex is not None and self.regex.search(name) is None:
            return False

        if self.older_than_days is not None or self.newer_than_days is not None:
            age_days = _age_in_days(path, now)
            if self.older_than_days is not None and age_days < self.older_than_days:
                return False
            if self.newer_than_days is not None and age_days > self.newer_than_days:
                return False

        return True


@dataclass(frozen=True)
class Rule:
    name: str
    match: Match
    destination: Path

    def matches(self, path: Path, *, now: float | None = None) -> bool:
        return self.match.matches(path, now=now)

    def destination_dir(self, base: Path) -> Path:
        """The destination folder for this rule inside ``base``."""
        return base / self.destination


def _extension(name: str) -> str:
    """Return the lower-cased extension without the dot ("Photo.JPG" -> "jpg")."""
    return Path(name).suffix.lower().lstrip(".")


def _age_in_days(path: Path, now: float | None) -> float:
    now = time.time() if now is None else now
    return (now - path.stat().st_mtime) / SECONDS_PER_DAY


def load_rules(path: Path) -> list[Rule]:
    """Read a YAML rules file and return the validated rules."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuleError(f"Rules file not found: {path}") from None
    except OSError as exc:
        raise RuleError(f"Could not read rules file {path}: {exc}") from None
    return parse_rules(text, source=str(path))


def parse_rules(text: str, *, source: str = "<string>") -> list[Rule]:
    """Parse rules from YAML text. Kept separate from ``load_rules`` to make testing easy."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RuleError(f"{source}: invalid YAML: {exc}") from None

    if not isinstance(data, dict) or "rules" not in data:
        raise RuleError(f"{source}: expected a top-level 'rules:' list")

    raw_rules = data["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise RuleError(f"{source}: 'rules' must be a non-empty list")

    rules = [_parse_rule(raw, index, source) for index, raw in enumerate(raw_rules, start=1)]

    names = [rule.name for rule in rules]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise RuleError(f"{source}: duplicate rule names: {', '.join(duplicates)}")

    return rules


def _parse_rule(raw: Any, index: int, source: str) -> Rule:
    where = f"{source}: rule #{index}"
    if not isinstance(raw, dict):
        raise RuleError(f"{where}: each rule must be a mapping")

    unknown = set(raw) - _ALLOWED_RULE_KEYS
    if unknown:
        raise RuleError(f"{where}: unknown key(s): {', '.join(sorted(map(str, unknown)))}")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RuleError(f"{where}: 'name' must be a non-empty string")
    where = f"{source}: rule '{name}'"

    destination = raw.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        raise RuleError(f"{where}: 'destination' must be a non-empty string")
    # Destinations are always relative to the folder being organized. This keeps a rules
    # file portable between Mac and Windows and stops a rule from moving files elsewhere.
    # Backslashes are normalized so "Archive\\PDFs" also works on Mac.
    dest_path = Path(destination.strip().replace("\\", "/"))
    if not dest_path.parts or ".." in dest_path.parts:
        raise RuleError(f"{where}: 'destination' must be a sub-folder and must not contain '..'")
    if dest_path.anchor or ":" in dest_path.parts[0]:
        raise RuleError(f"{where}: 'destination' must be a relative path like 'Images/2026'")

    match = _parse_match(raw.get("match"), where)
    return Rule(name=name.strip(), match=match, destination=dest_path)


def _parse_match(raw: Any, where: str) -> Match:
    if not isinstance(raw, dict) or not raw:
        raise RuleError(f"{where}: 'match' must be a mapping with at least one condition")

    unknown = set(raw) - _ALLOWED_MATCH_KEYS
    if unknown:
        allowed = ", ".join(sorted(_ALLOWED_MATCH_KEYS))
        raise RuleError(
            f"{where}: unknown match key(s): {', '.join(sorted(map(str, unknown)))} "
            f"(allowed: {allowed})"
        )

    extensions: frozenset[str] = frozenset()
    if "extensions" in raw:
        exts = raw["extensions"]
        if isinstance(exts, str):
            exts = [exts]
        if not isinstance(exts, list) or not exts or not all(isinstance(e, str) for e in exts):
            raise RuleError(f"{where}: 'extensions' must be a list of strings")
        extensions = frozenset(e.strip().lower().lstrip(".") for e in exts)

    glob = raw.get("glob")
    if glob is not None and (not isinstance(glob, str) or not glob):
        raise RuleError(f"{where}: 'glob' must be a non-empty string")

    regex = None
    if "regex" in raw:
        pattern = raw["regex"]
        if not isinstance(pattern, str) or not pattern:
            raise RuleError(f"{where}: 'regex' must be a non-empty string")
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise RuleError(f"{where}: invalid regex {pattern!r}: {exc}") from None

    older = _parse_days(raw, "older_than_days", where)
    newer = _parse_days(raw, "newer_than_days", where)
    if older is not None and newer is not None and older > newer:
        raise RuleError(f"{where}: 'older_than_days' is larger than 'newer_than_days'")

    return Match(
        extensions=extensions,
        glob=glob,
        regex=regex,
        older_than_days=older,
        newer_than_days=newer,
    )


def _parse_days(raw: dict[str, Any], key: str, where: str) -> float | None:
    if key not in raw:
        return None
    value = raw[key]
    # bool is a subclass of int in Python, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise RuleError(f"{where}: '{key}' must be a number >= 0")
    return float(value)
