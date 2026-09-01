#!/usr/bin/env python3
"""Reject publishable files containing workstation paths or private Git emails."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


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
    return patterns


def scan(paths: list[Path], patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                if b"\0" in handle.read(8192):
                    continue
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, start=1):
                    for label, pattern in patterns:
                        if pattern.search(line):
                            findings.append(f"{path.relative_to(ROOT).as_posix()}:{line_number}: {label}")
        except OSError as exc:
            findings.append(f"{path.relative_to(ROOT).as_posix()}: unreadable file: {exc}")
    return findings


def main() -> int:
    findings = scan(publishable_files(), forbidden_patterns())
    if findings:
        print("Repository privacy check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Repository privacy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
