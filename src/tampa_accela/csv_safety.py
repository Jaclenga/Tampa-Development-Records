"""Spreadsheet-safe CSV serialization for untrusted public-source text."""

from __future__ import annotations

import re
from typing import Mapping


FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
SIGNED_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")


def _is_signed_number(value: str) -> bool:
    candidate = value.strip()
    return candidate.startswith(("+", "-")) and bool(SIGNED_NUMBER.fullmatch(candidate))


def _looks_like_formula(value: str) -> bool:
    candidate = value.lstrip(" ")
    return (
        bool(candidate)
        and candidate.startswith(FORMULA_PREFIXES)
        and not _is_signed_number(candidate)
    )


def neutralize_csv_cell(value: object) -> object:
    """Prefix spreadsheet-active text with an apostrophe for CSV export."""
    if not isinstance(value, str):
        return value
    remainder = value.lstrip("'")
    must_escape_literal_apostrophe = value.startswith("'") and _is_signed_number(remainder)
    return "'" + value if _looks_like_formula(remainder) or must_escape_literal_apostrophe else value


def restore_csv_cell(value: str) -> str:
    """Reverse only the precise apostrophe added by neutralize_csv_cell."""
    remainder = value.lstrip("'")
    if value.startswith("'") and (_looks_like_formula(remainder) or _is_signed_number(remainder)):
        return value[1:]
    return value


def safe_csv_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: "" if value is None else neutralize_csv_cell(value)
        for key, value in row.items()
    }


def restore_csv_row(row: Mapping[str, str]) -> dict[str, str]:
    return {key: restore_csv_cell(value) for key, value in row.items()}
