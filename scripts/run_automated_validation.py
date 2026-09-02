#!/usr/bin/env python3
"""Run and document a complete deterministic offline validation execution."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import locale
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPRODUCIBILITY = ROOT / "reproducibility"
RULE_REGISTRY = ROOT / "config" / "validation_rules.json"
VALIDATOR_VERSION = "1.0.0"
MANIFEST_FORMAT_VERSION = "1.0.0"
FROZEN_SAMPLE_GLOB = "manual_validation*.csv"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def git_state() -> dict[str, object]:
    status = git_text("status", "--porcelain=v1", "--untracked-files=all")
    entries = [] if not status or status == "unavailable" else status.splitlines()
    return {
        "commit": git_text("rev-parse", "HEAD"),
        "clean": not entries,
        "status_entries": entries,
    }


def role_for(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    name = path.name
    if relative.startswith("data/processed/manual_validation") or name == "external_verification_pilot.csv":
        return "frozen_validation_sample"
    if relative.startswith("data/frozen/accela/"):
        return "archived_accela_evidence"
    if relative.startswith("data/raw/") or relative.startswith("data/snapshots/"):
        return "archived_gis_evidence"
    if relative.startswith("data/context/raw/"):
        return "archived_context_evidence"
    if relative.startswith("data/") and "inspection" in name.lower():
        return "inspection_evidence"
    if relative.startswith("data/processed/") or relative.startswith("data/integrated/"):
        return "processed_evidence_table"
    if relative.startswith("data/monthly_") or relative.startswith("data/planned_events/"):
        return "derived_longitudinal_evidence"
    if relative == "config/validation_rules.json":
        return "rule_registry"
    if relative.startswith("config/") or name in {"manifest.json", "requirements.txt", "pytest.ini"}:
        return "configuration"
    if relative.startswith("scripts/") or relative.startswith("src/"):
        return "validator_source_code"
    if relative.startswith("tests/"):
        return "test_source_code"
    return "validation_protocol_or_metadata"


def input_paths() -> list[Path]:
    # Start with publishable files so private caches, raw authenticated
    # responses, and operational checkpoints cannot accidentally become run
    # dependencies. New implementation files are included through --others.
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    included_prefixes = ("config/", "data/", "docs/", "scripts/", "src/", "tests/")
    paths = {
        ROOT / os.fsdecode(relative)
        for relative in result.stdout.split(b"\0")
        if relative
        and os.fsdecode(relative).startswith(included_prefixes)
        and not os.fsdecode(relative).startswith("reproducibility/runs/")
        and not os.fsdecode(relative).startswith("reproducibility/.determinism_tmp/")
    }
    for relative in (
        "manifest.json", "requirements.txt", "pytest.ini",
    ):
        path = ROOT / relative
        if path.exists():
            paths.add(path)
    return sorted(
        (
            path for path in paths
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix.lower() not in {".pyc", ".pyo"}
            and path not in {
                ROOT / "docs" / "validation_report.json",
                ROOT / "docs" / "accuracy_verification_report.json",
            }
        ),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "role": role_for(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def frozen_sample_hashes() -> dict[str, str]:
    processed = ROOT / "data" / "processed"
    return {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in sorted(processed.glob(FROZEN_SAMPLE_GLOB))
        if path.is_file()
    }


def validate_frozen_archive_manifests() -> list[str]:
    failures: list[str] = []
    for manifest_path in sorted((ROOT / "data" / "frozen").rglob("manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("files", []):
            archived = manifest_path.parent / item["path"]
            observed = sha256_file(archived) if archived.exists() else None
            if observed != item.get("sha256"):
                failures.append(archived.relative_to(ROOT).as_posix())
    return failures


def command_environment() -> dict[str, str]:
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    additions = [str(ROOT / "src")]
    if existing:
        additions.append(existing)
    environment["PYTHONPATH"] = os.pathsep.join(additions)
    environment["TMP"] = str(ROOT / ".cache")
    environment["TEMP"] = str(ROOT / ".cache")
    return environment


def run_command(command: list[str], log_path: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=command_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    return result


def substantive_commands(
    output_dir: Path, *, include_privacy: bool = True
) -> list[tuple[str, list[str], Path]]:
    commands = [
        (
            "release",
            [sys.executable, str(ROOT / "scripts" / "validate_release.py"), "--report", str(output_dir / "validation_report.json")],
            output_dir.parent / "logs" / "validate_release.log",
        ),
        (
            "accuracy",
            [
                sys.executable, str(ROOT / "scripts" / "verify_data_accuracy.py"),
                "--report", str(output_dir / "accuracy_verification_report.json"),
                "--deterministic-report",
            ],
            output_dir.parent / "logs" / "verify_data_accuracy.log",
        ),
    ]
    if include_privacy:
        commands.append((
            "privacy",
            [sys.executable, str(ROOT / "scripts" / "check_repository_privacy.py")],
            output_dir / "repository_privacy_check.txt",
        ))
    return commands


def generate_substantive_outputs(
    output_dir: Path, *, include_privacy: bool = True
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, int] = {}
    for name, command, log_path in substantive_commands(
        output_dir, include_privacy=include_privacy
    ):
        result = run_command(command, log_path)
        statuses[name] = result.returncode
    return statuses


def output_manifest(output_dir: Path) -> dict[str, object]:
    records = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.is_file():
            records.append({
                "path": f"outputs/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return {"format_version": MANIFEST_FORMAT_VERSION, "outputs": records}


def analytical_output_manifest(output_dir: Path) -> dict[str, object]:
    manifest = output_manifest(output_dir)
    manifest["outputs"] = [
        record for record in manifest["outputs"]
        if str(record["path"]).endswith(".json")
    ]
    return manifest


def invoked_rule_ids(output_dir: Path) -> list[str]:
    registry = json.loads(RULE_REGISTRY.read_text(encoding="utf-8"))
    ids: list[str] = []
    for suite in registry["suites"]:
        report_name = suite.get("report", "").removeprefix("outputs/")
        check_keys = suite.get("fixed_check_keys", [])
        report_path = output_dir / report_name
        if suite.get("check_container") and report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            check_keys = sorted(report[suite["check_container"]])
        ids.extend(f"{suite['suite_id']}:{key}" for key in check_keys)
    return sorted(ids)


def normalized_command_lines(run_relative: str) -> list[str]:
    return [
        f"python scripts/validate_release.py --report {run_relative}/outputs/validation_report.json",
        f"python scripts/verify_data_accuracy.py --report {run_relative}/outputs/accuracy_verification_report.json --deterministic-report",
        "python scripts/check_repository_privacy.py",
        "PYTHONPATH=src python -m unittest discover -s tests -v",
        "python scripts/run_automated_validation.py --all --offline",
    ]


def manifest_digest(path: Path) -> str:
    return sha256_file(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run every automated validation suite and tests.")
    parser.add_argument("--offline", action="store_true", help="Forbid live-source validation and use archived evidence only.")
    parser.add_argument("--skip-tests", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.all or not args.offline:
        parser.error("a complete reproducibility run requires --all --offline")

    started = utc_now()
    initial_git = git_state()
    commit = str(initial_git["commit"])
    short_commit = commit[:8] if commit != "unavailable" else "nogit"
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}_{short_commit}"
    run_dir = REPRODUCIBILITY / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir.relative_to(ROOT)}")
    outputs = run_dir / "outputs"
    run_dir.mkdir(parents=True)

    frozen_before = frozen_sample_hashes()
    archive_failures = validate_frozen_archive_manifests()
    records = [file_record(path) for path in input_paths()]
    warnings = []
    if not any(record["role"] == "inspection_evidence" for record in records):
        warnings.append("No standalone inspection evidence file was present; inspection-dependent conclusions were not added by this runner.")
    inputs = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "input_count": len(records),
        "inputs": records,
        "frozen_sample_hashes_before": frozen_before,
    }
    inputs_path = run_dir / "inputs_manifest.json"
    write_json(inputs_path, inputs)

    statuses = generate_substantive_outputs(outputs)
    final_outputs = output_manifest(outputs)

    repeat_root = REPRODUCIBILITY / ".determinism_tmp" / run_id
    repeat_outputs = repeat_root / "outputs"
    repeat_statuses = generate_substantive_outputs(repeat_outputs, include_privacy=False)
    repeat_manifest = analytical_output_manifest(repeat_outputs)
    deterministic_repeat = analytical_output_manifest(outputs) == repeat_manifest and all(
        code == 0 for code in (*statuses.values(), *repeat_statuses.values())
    )
    if repeat_root.exists():
        shutil.rmtree(repeat_root)

    test_status = "skipped"
    test_count = None
    if not args.skip_tests:
        test_result = run_command(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            run_dir / "test_suite.log",
        )
        test_status = "passed" if test_result.returncode == 0 else "failed"
        match = re.search(r"Ran (\d+) tests?", test_result.stdout + test_result.stderr)
        test_count = int(match.group(1)) if match else None

    frozen_after = frozen_sample_hashes()
    frozen_unchanged = frozen_before == frozen_after
    inputs["frozen_sample_hashes_after"] = frozen_after
    inputs["frozen_samples_unchanged"] = frozen_unchanged
    write_json(inputs_path, inputs)

    outputs_path = run_dir / "outputs_manifest.json"
    write_json(outputs_path, final_outputs)
    network = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "mode": "offline",
        "network_access_status": "not_requested",
        "requests": [],
        "statement": "Computational reproduction used archived evidence. No mutable live source was queried.",
    }
    write_json(run_dir / "network_manifest.json", network)
    run_relative = run_dir.relative_to(ROOT).as_posix()
    (run_dir / "commands.log").write_text(
        "\n".join(normalized_command_lines(run_relative)) + "\n", encoding="utf-8"
    )

    registry = json.loads(RULE_REGISTRY.read_text(encoding="utf-8"))
    release_report = json.loads((outputs / "validation_report.json").read_text(encoding="utf-8")) if (outputs / "validation_report.json").exists() else {}
    accuracy_report = json.loads((outputs / "accuracy_verification_report.json").read_text(encoding="utf-8")) if (outputs / "accuracy_verification_report.json").exists() else {}
    validation_passed = (
        all(code == 0 for code in statuses.values())
        and deterministic_repeat
        and frozen_unchanged
        and not archive_failures
        and test_status in {"passed", "skipped"}
    )
    completed = utc_now()
    manifest = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "run_id": run_id,
        "utc_start_time": iso_utc(started),
        "utc_completion_time": iso_utc(completed),
        "git_commit": commit,
        "working_tree_state_at_start": initial_git,
        "validator_version": VALIDATOR_VERSION,
        "rule_set_version": registry["rule_set_version"],
        "rule_set_hash": sha256_file(RULE_REGISTRY),
        "rule_ids_invoked": invoked_rule_ids(outputs),
        "python": {"implementation": platform.python_implementation(), "version": platform.python_version()},
        "platform": {"operating_system": platform.system(), "release": platform.release(), "architecture": platform.machine()},
        "locale": {"current": list(locale.getlocale()), "preferred_encoding": locale.getencoding()},
        "timezone": {"system_names": list(time.tzname), "utc_offset_seconds": -time.timezone},
        "command_invoked": "python scripts/run_automated_validation.py --all --offline",
        "cli_arguments": sys.argv[1:],
        "mode": "offline",
        "input_manifest": inputs_path.relative_to(ROOT).as_posix(),
        "input_manifest_hash": manifest_digest(inputs_path),
        "output_manifest": outputs_path.relative_to(ROOT).as_posix(),
        "output_manifest_hash": manifest_digest(outputs_path),
        "records_processed_by_study": release_report.get("row_counts", {}),
        "test_suite": {"status": test_status, "tests_run": test_count},
        "validation_status": "passed" if validation_passed else "failed",
        "suite_exit_codes": statuses,
        "release_validation_passed": release_report.get("passed"),
        "snapshot_fidelity_validation_passed": accuracy_report.get("machine_verification_passed"),
        "frozen_samples_unchanged": frozen_unchanged,
        "frozen_archive_manifest_failures": archive_failures,
        "deterministic_repeat_run_passed": deterministic_repeat,
        "network_access_status": "not_requested_offline",
        "ai_involvement_during_validation_run": {
            "used": False,
            "statement": "No LLM or generative-AI call is made by the deterministic validator.",
        },
        "warnings": warnings,
        "errors": [name for name, code in statuses.items() if code != 0],
    }
    write_json(run_dir / "run_manifest.json", manifest)
    print(json.dumps({
        "run_id": run_id,
        "validation_status": manifest["validation_status"],
        "deterministic_repeat_run_passed": deterministic_repeat,
        "test_suite": manifest["test_suite"],
        "run_manifest": (run_dir / "run_manifest.json").relative_to(ROOT).as_posix(),
    }, indent=2))
    return 0 if validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
