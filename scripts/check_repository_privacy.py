#!/usr/bin/env python3
"""Reject publishable files containing direct personal information."""

from __future__ import annotations

import csv
import gzip
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

INTEGRATED_BLOCKED_HEADER_TOKENS = (
    "owner", "applicant", "contractor", "contact", "phone", "email",
    "mailing", "pocname", "pocphone", "pocemail", "creator", "editor",
    "first_name", "last_name",
)
INTEGRATED_VALUE_PATTERNS = (
    ("email address", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
    ("phone number", re.compile(
        r"(?<!\d)(?:\+?1[-. ]?)?(?:\(\d{3}\)|\d{3}[-. ])\d{3}[-. ]\d{4}(?!\d)"
    )),
    ("Social Security number", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
)


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def publishable_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [ROOT / os.fsdecode(value) for value in output.split(b"\0") if value]


def private_emails() -> set[str]:
    emails = {
        value.strip().lower()
        for value in git_output("log", "--all", "--format=%ae").splitlines()
        if value.strip() and "noreply" not in value.lower()
    }
    configured_result = subprocess.run(
        ["git", "config", "--get", "user.email"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if configured_result.returncode not in {0, 1}:
        raise RuntimeError(configured_result.stderr.strip() or "git config lookup failed")
    configured = configured_result.stdout.strip().lower()
    if configured and "noreply" not in configured:
        emails.add(configured)
    return emails


def forbidden_patterns() -> list[tuple[str, re.Pattern[str]]]:
    windows_home = re.compile(r"(?i)[A-Z]:[\\/]+" + "Users" + r"[\\/]+[^\\/\r\n]+")
    mac_home = re.compile(r"/" + "Users" + r"/[^/\r\n]+")
    linux_home = re.compile(r"/" + "home" + r"/[^/\r\n]+")
    patterns = [
        ("absolute Windows user path", windows_home),
        ("absolute macOS user path", mac_home),
        ("absolute Linux user path", linux_home),
    ]
    for email in sorted(private_emails()):
        patterns.append(("private Git author email", re.compile(re.escape(email), re.IGNORECASE)))
    account_name = Path.home().name.strip()
    if len(account_name) >= 4:
        patterns.append((
            "workstation account name",
            re.compile(rf"(?i)(?<![A-Z0-9]){re.escape(account_name)}(?![A-Z0-9])"),
        ))
    return patterns


def text_lines(path: Path):
    if path.suffix.lower() == ".gz":
        with gzip.open(path, mode="rt", encoding="utf-8", errors="replace") as handle:
            yield from handle
        return
    with path.open("rb") as handle:
        if b"\0" in handle.read(8192):
            return
    with path.open(encoding="utf-8", errors="replace") as handle:
        yield from handle


def scan(paths: list[Path], patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            for line_number, line in enumerate(text_lines(path), start=1):
                for label, pattern in patterns:
                    if pattern.search(line):
                        findings.append(f"{path.relative_to(ROOT).as_posix()}:{line_number}: {label}")
        except OSError as exc:
            findings.append(f"{path.relative_to(ROOT).as_posix()}: unreadable file: {exc}")
    return findings


def is_integrated_csv(path: Path) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    return relative.startswith("data/integrated/") and (
        path.name.endswith(".csv") or path.name.endswith(".csv.gz")
    )


def scan_integrated_csv_pii(
    paths: list[Path],
    repository_patterns: list[tuple[str, re.Pattern[str]]] | None = None,
) -> list[str]:
    """Enforce the public integrated edition's no-direct-contact-data contract."""
    findings: list[str] = []
    value_patterns = (*INTEGRATED_VALUE_PATTERNS, *(repository_patterns or []))
    combined_parts = []
    for index, (_label, pattern) in enumerate(value_patterns):
        source = pattern.pattern
        if source.startswith("(?i)"):
            source = f"(?i:{source[4:]})"
        combined_parts.append(f"(?P<pattern_{index}>{source})")
    combined_pattern = re.compile("|".join(combined_parts))
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if not is_integrated_csv(path):
            continue
        opener = gzip.open if path.name.endswith(".gz") else open
        try:
            with opener(path, mode="rt", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fields = reader.fieldnames or []
                for field in fields:
                    lowered = field.lower()
                    if any(token in lowered for token in INTEGRATED_BLOCKED_HEADER_TOKENS):
                        findings.append(f"{relative}:1: privacy-blocked column: {field}")
                for row_number, row in enumerate(reader, start=2):
                    joined = "\x1f".join(value or "" for value in row.values())
                    match = combined_pattern.search(joined)
                    if match:
                        index = int(match.lastgroup.removeprefix("pattern_"))
                        findings.append(f"{relative}:{row_number}: {value_patterns[index][0]}")
        except (OSError, csv.Error, gzip.BadGzipFile) as exc:
            findings.append(f"{relative}: privacy scan failed: {exc}")
    return findings


def main() -> int:
    paths = publishable_files()
    patterns = forbidden_patterns()
    findings = scan([path for path in paths if not is_integrated_csv(path)], patterns)
    findings.extend(scan_integrated_csv_pii(paths, patterns))
    if findings:
        print("Repository privacy check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Repository privacy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
