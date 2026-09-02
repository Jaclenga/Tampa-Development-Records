#!/usr/bin/env python3
"""Verify the pre-human-audit freeze of the evaluated agent benchmark."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREEZE = ROOT / "reproducibility" / "agent_benchmark_freeze_v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_manifest(path: Path) -> tuple[str, int]:
    files = sorted(
        item
        for item in path.rglob("*")
        if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"
    )
    rendered = "".join(
        f"{item.relative_to(path).as_posix()}\t{sha256_file(item)}\n"
        for item in files
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest(), len(files)


def freeze_root_hash(manifest: dict[str, Any]) -> str:
    lines = [
        f"file\t{item['path']}\t{item['sha256']}\n"
        for item in manifest["artifacts"]["files"]
    ]
    lines.extend(
        f"directory\t{item['path']}\t{item['manifest_sha256']}\t{item['file_count']}\n"
        for item in manifest["artifacts"]["directories"]
    )
    return hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()


def verify_freeze(path: Path = DEFAULT_FREEZE) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for item in manifest["artifacts"]["files"]:
        target = ROOT / item["path"]
        if not target.is_file():
            errors.append(f"missing frozen file: {item['path']}")
        elif sha256_file(target) != item["sha256"]:
            errors.append(f"frozen file changed: {item['path']}")
    for item in manifest["artifacts"]["directories"]:
        target = ROOT / item["path"]
        if not target.is_dir():
            errors.append(f"missing frozen directory: {item['path']}")
            continue
        observed_hash, observed_count = directory_manifest(target)
        if observed_hash != item["manifest_sha256"] or observed_count != item["file_count"]:
            errors.append(f"frozen directory changed: {item['path']}")
    observed_root = freeze_root_hash(manifest)
    if observed_root != manifest["freeze_root_sha256"]:
        errors.append("freeze manifest root hash is inconsistent")
    if errors:
        raise RuntimeError("agent benchmark freeze verification failed: " + "; ".join(errors))
    return {
        "freeze_id": manifest["freeze_id"],
        "freeze_root_sha256": observed_root,
        "files_verified": len(manifest["artifacts"]["files"]),
        "directories_verified": len(manifest["artifacts"]["directories"]),
    }


def main() -> int:
    print(json.dumps(verify_freeze(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
