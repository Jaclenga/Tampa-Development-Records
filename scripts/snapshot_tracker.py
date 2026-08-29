#!/usr/bin/env python3
"""Archive source observations and publish deterministic monthly change reports.

The tracker compares what the configured City layers published at two retrieval
times. A disappearance means that a record was not returned in the later
snapshot; it does not prove deletion, cancellation, or completion.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
CHANGES = DATA / "monthly_changes"
REPORTS = ROOT / "reports"
INDEX = CHANGES / "index.json"
FORMAT_VERSION = "1.0.0"

SNAPSHOT_FIELDS = [
    "source_name",
    "source_record_id",
    "source_object_id",
    "source_global_id",
    "source_endpoint",
    "retrieved_at_utc",
    "properties_json",
]

CHANGE_FIELDS = [
    "change_id",
    "comparison_month",
    "before_snapshot_date",
    "after_snapshot_date",
    "change_type",
    "semantic_type",
    "source_name",
    "record_identity",
    "source_record_id",
    "changed_fields",
    "old_value",
    "new_value",
    "source_url",
    "interpretation_note",
]

INVALID_NATIVE_IDS = {"", "N/A", "NA", "NONE", "NULL", "UNKNOWN", "0000000", "0", "-"}
VOLATILE_FIELDS = {
    "objectid",
    "globalid",
    "lastupdate",
    "last_edited_date",
    "editdate",
    "created_date",
}
CAPITAL_SOURCES = {
    "capital_improvements",
    "capital_locations_point",
    "capital_locations_line",
    "capital_locations_polygon",
}
PERMIT_SOURCES = {"construction_inspections", "single_family_permits"}


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical(value: object) -> str:
    return clean(value).upper()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def rows_sha256(rows: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            json.dumps(
                {field: row.get(field, "") for field in SNAPSHOT_FIELDS},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def source_state_sha256(rows: list[dict[str, str]]) -> str:
    """Hash source state while excluding the observation timestamp."""
    digest = hashlib.sha256()
    fields = [field for field in SNAPSHOT_FIELDS if field != "retrieved_at_utc"]
    for row in rows:
        digest.update(
            json.dumps(
                {field: row.get(field, "") for field in fields},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    opener = gzip.open if path.suffix == ".gz" else path.open
    with opener(path, mode="rt", encoding="utf-8", newline="") if path.suffix == ".gz" else opener(
        mode="r", encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def atomic_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def atomic_gzip_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a byte-reproducible gzip snapshot (mtime=0, no embedded name)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(
                        handle,
                        fieldnames=SNAPSHOT_FIELDS,
                        extrasaction="ignore",
                        lineterminator="\n",
                    )
                    writer.writeheader()
                    writer.writerows(rows)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def snapshot_date_from_rows(rows: list[dict[str, str]]) -> tuple[str, str]:
    observed = sorted({clean(row.get("retrieved_at_utc")) for row in rows if clean(row.get("retrieved_at_utc"))})
    if len(observed) != 1:
        raise ValueError(f"Expected one retrieval timestamp in source_records.csv; found {observed}")
    try:
        parsed = dt.datetime.fromisoformat(observed[0].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid retrieval timestamp: {observed[0]}") from exc
    return parsed.date().isoformat(), observed[0]


def canonical_snapshot_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    missing = set(SNAPSHOT_FIELDS) - set(rows[0] if rows else {})
    if missing:
        raise ValueError(f"Source-record table is missing snapshot fields: {sorted(missing)}")
    selected = [{field: row.get(field, "") for field in SNAPSHOT_FIELDS} for row in rows]
    return sorted(
        selected,
        key=lambda row: (
            row["source_name"],
            canonical(row["source_record_id"]),
            canonical(row["source_global_id"]),
            canonical(row["source_object_id"]),
        ),
    )


def archive_snapshot(
    source_path: Path,
    snapshots_dir: Path = SNAPSHOTS,
) -> dict[str, object]:
    return archive_rows(read_csv(source_path), snapshots_dir)


def archive_rows(
    source_rows: list[dict[str, str]],
    snapshots_dir: Path = SNAPSHOTS,
) -> dict[str, object]:
    rows = canonical_snapshot_rows(source_rows)
    snapshot_date, retrieved_at = snapshot_date_from_rows(rows)
    destination = snapshots_dir / snapshot_date
    records_path = destination / "source_records.csv.gz"
    metadata_path = destination / "metadata.json"
    content_hash = rows_sha256(rows)
    state_hash = source_state_sha256(rows)
    counts = dict(sorted(Counter(row["source_name"] for row in rows).items()))
    metadata = {
        "format_version": FORMAT_VERSION,
        "snapshot_date": snapshot_date,
        "retrieved_at_utc": retrieved_at,
        "record_count": len(rows),
        "source_counts": counts,
        "source_count": len(counts),
        "source_records_content_sha256": content_hash,
        "source_state_sha256": state_hash,
        "identity_rule": "source plus native ID; duplicate native identities are disambiguated by GlobalID then OBJECTID",
        "scope_note": "All records in this compact archive came from the eight configured City layers; geometry is retained in the release raw files, not duplicated here.",
    }
    if records_path.exists() or metadata_path.exists():
        if not (records_path.exists() and metadata_path.exists()):
            raise RuntimeError(f"Incomplete existing snapshot directory: {destination}")
        existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        existing_rows = read_csv(records_path)
        if (
            existing_metadata.get("source_records_content_sha256") != rows_sha256(existing_rows)
            or existing_metadata.get("source_state_sha256", source_state_sha256(existing_rows)) != state_hash
        ):
            raise RuntimeError(
                f"Refusing to overwrite immutable snapshot {snapshot_date} with different records"
            )
        return existing_metadata
    destination.mkdir(parents=True, exist_ok=False)
    atomic_gzip_csv(records_path, rows)
    metadata["source_records_gzip_sha256"] = file_sha256(records_path)
    atomic_json(metadata_path, metadata)
    return metadata


def collect_live_rows() -> list[dict[str, str]]:
    """Collect the eight core layers without rebuilding derived validation tables."""
    try:
        from . import build_release
    except ImportError:  # Support direct execution from the scripts directory.
        import build_release

    legacy = build_release.load_legacy_module()
    endpoints = {name: config["url"] for name, config in legacy.SOURCES.items()}
    endpoints.update({name: url for name, (url, _) in build_release.EXTRA_CIP.items()})
    pending: list[tuple[str, str, str, dict[str, object]]] = []
    counts: dict[str, int] = {}
    for source, endpoint in endpoints.items():
        collection = build_release.fetch_arcgis_layer(endpoint)
        features = collection.get("features", [])
        if not features:
            raise RuntimeError(f"Live collection returned zero records for {source}; refusing partial snapshot")
        counts[source] = len(features)
        for feature in features:
            props = feature.get("properties") or {}
            native = build_release.native_id_for(source, props)
            pending.append((source, endpoint, native, props))
    if len(endpoints) != 8 or sum(counts.values()) < 3000:
        raise RuntimeError(f"Live collection failed source-count safeguards: {counts}")
    observed = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    for source, endpoint, native_value, source_props in pending:
        props = dict(source_props)
        native = clean(native_value)
        scrubbed = build_release.scrub_properties(props)
        rows.append({
            "source_name": source,
            "source_record_id": native,
            "source_object_id": clean(props.get("OBJECTID")),
            "source_global_id": clean(props.get("GlobalID")),
            "source_endpoint": endpoint,
            "retrieved_at_utc": observed,
            "properties_json": json.dumps(scrubbed, ensure_ascii=False, separators=(",", ":")),
        })
    return rows


def base_record_identity(row: dict[str, str]) -> str:
    source = canonical(row.get("source_name"))
    native = canonical(row.get("source_record_id"))
    global_id = canonical(row.get("source_global_id"))
    object_id = canonical(row.get("source_object_id"))
    if native not in INVALID_NATIVE_IDS and not re.fullmatch(r"OBJECTID-\d+", native):
        return f"{source}|NATIVE|{native}"
    if global_id:
        return f"{source}|GLOBALID|{global_id}"
    if object_id:
        return f"{source}|OBJECTID|{object_id}"
    raise ValueError(f"Record lacks a usable comparison identity: {row}")


def record_disambiguator(row: dict[str, str]) -> str:
    global_id = canonical(row.get("source_global_id"))
    object_id = canonical(row.get("source_object_id"))
    if global_id:
        return f"GLOBALID|{global_id}"
    if object_id:
        return f"OBJECTID|{object_id}"
    raise ValueError(f"Duplicate native identity lacks a GlobalID or OBJECTID: {row}")


def record_identity(row: dict[str, str], disambiguate: bool = False) -> str:
    identity = base_record_identity(row)
    return f"{identity}|{record_disambiguator(row)}" if disambiguate else identity


def duplicate_bases(rows: list[dict[str, str]]) -> set[str]:
    counts = Counter(base_record_identity(row) for row in rows)
    return {identity for identity, count in counts.items() if count > 1}


def index_records(
    rows: list[dict[str, str]],
    disambiguated_bases: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    disambiguated_bases = duplicate_bases(rows) if disambiguated_bases is None else disambiguated_bases
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        base = base_record_identity(row)
        identity = record_identity(row, base in disambiguated_bases)
        if identity in indexed:
            raise ValueError(f"Duplicate comparison identity in snapshot: {identity}")
        indexed[identity] = row
    return indexed


def properties(row: dict[str, str]) -> dict[str, object]:
    try:
        value = json.loads(row.get("properties_json", "") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid properties_json for {row.get('source_name')}:{row.get('source_record_id')}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"properties_json is not an object for {row.get('source_name')}:{row.get('source_record_id')}")
    return value


def lookup(props: dict[str, object], *names: str) -> object:
    lowered = {key.lower(): value for key, value in props.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return ""


def comparable(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return clean(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def combined_value(props: dict[str, object], *names: str) -> str:
    values = [comparable(lookup(props, name)) for name in names]
    return " | ".join(value for value in values if value)


def source_url(row: dict[str, str], props: dict[str, object]) -> str:
    candidate = clean(lookup(props, "URL", "ProjectSiteURL", "docpath"))
    match = re.search(r"https?://[^\"<> ]+", candidate)
    return (match.group(0) if match else candidate) or row.get("source_endpoint", "")


def tracked_values(source: str, props: dict[str, object]) -> dict[str, str]:
    if source == "construction_inspections":
        return {
            "status": combined_value(props, "PROJECTSTATUS"),
            "description": combined_value(props, "PROJECTDESCRIPTION"),
            "project_name": combined_value(props, "PROJECTNAME1", "PROJECTNAME2"),
            "record_type": combined_value(props, "RECORDTYPE"),
        }
    if source == "single_family_permits":
        return {
            "status": combined_value(props, "APPLICATION_STATUS", "TASK_STATUS"),
            "description": "",
            "project_name": combined_value(props, "APPLICATION_TYPE"),
            "record_type": combined_value(props, "TYPE", "SUBTYPE", "PER_GROUP"),
        }
    if source in {"development_coordination", "historic_preservation"}:
        return {
            "status": combined_value(props, "APPSTATUS"),
            "description": "",
            "project_name": combined_value(props, "RECORDALIAS"),
            "record_type": combined_value(props, "RECORDALIAS"),
        }
    if source in CAPITAL_SOURCES:
        return {
            "status": combined_value(props, "status", "ActivityStatus"),
            "description": combined_value(props, "projdesc"),
            "project_name": combined_value(props, "projname"),
            "record_type": combined_value(props, "projtype"),
            "estimated_cost": combined_value(props, "estcost"),
            "actual_cost": combined_value(props, "actcost"),
            "planned_start": combined_value(props, "planstart"),
            "planned_end": combined_value(props, "planend"),
            "capital_phase": combined_value(props, "projphase"),
        }
    return {}


def meaningful_property_changes(before: dict[str, object], after: dict[str, object]) -> list[str]:
    keys = set(before) | set(after)
    return sorted(
        key
        for key in keys
        if key.lower() not in VOLATILE_FIELDS
        and comparable(before.get(key)) != comparable(after.get(key))
    )


def make_change(
    *,
    before_date: str,
    after_date: str,
    change_type: str,
    semantic_type: str,
    identity: str,
    row: dict[str, str],
    changed_fields: str,
    old_value: str,
    new_value: str,
    url: str,
    note: str,
) -> dict[str, str]:
    token = "|".join((before_date, after_date, change_type, semantic_type, identity, changed_fields))
    return {
        "change_id": f"chg-{hashlib.sha1(token.encode('utf-8')).hexdigest()[:16]}",
        "comparison_month": after_date[:7],
        "before_snapshot_date": before_date,
        "after_snapshot_date": after_date,
        "change_type": change_type,
        "semantic_type": semantic_type,
        "source_name": row.get("source_name", ""),
        "record_identity": identity,
        "source_record_id": row.get("source_record_id", ""),
        "changed_fields": changed_fields,
        "old_value": old_value,
        "new_value": new_value,
        "source_url": url,
        "interpretation_note": note,
    }


def compare_records(
    before_rows: list[dict[str, str]],
    after_rows: list[dict[str, str]],
    before_date: str,
    after_date: str,
) -> list[dict[str, str]]:
    disambiguated_bases = duplicate_bases(before_rows) | duplicate_bases(after_rows)
    before = index_records(before_rows, disambiguated_bases)
    after = index_records(after_rows, disambiguated_bases)
    changes: list[dict[str, str]] = []
    for identity in sorted(set(before) | set(after)):
        old_row, new_row = before.get(identity), after.get(identity)
        if old_row is None and new_row is not None:
            props = properties(new_row)
            semantic = "planning_application_added" if new_row["source_name"] == "development_coordination" else ""
            changes.append(make_change(
                before_date=before_date,
                after_date=after_date,
                change_type="new_record",
                semantic_type=semantic,
                identity=identity,
                row=new_row,
                changed_fields="",
                old_value="",
                new_value="newly observed in later source snapshot",
                url=source_url(new_row, props),
                note="Newly observed does not prove the record or underlying activity was created during the interval.",
            ))
            continue
        if new_row is None and old_row is not None:
            props = properties(old_row)
            changes.append(make_change(
                before_date=before_date,
                after_date=after_date,
                change_type="record_disappeared",
                semantic_type="",
                identity=identity,
                row=old_row,
                changed_fields="",
                old_value="present in earlier source snapshot",
                new_value="not returned in later source snapshot",
                url=source_url(old_row, props),
                note="Absence from a later published layer does not prove deletion, cancellation, or completion.",
            ))
            continue
        assert old_row is not None and new_row is not None
        old_props, new_props = properties(old_row), properties(new_row)
        source = new_row["source_name"]
        old_tracked, new_tracked = tracked_values(source, old_props), tracked_values(source, new_props)
        url = source_url(new_row, new_props)
        emitted_fields: set[str] = set()

        def emit(change_type: str, field_names: list[str], semantic: str = "", note: str = "") -> None:
            old_value = json.dumps({field: old_tracked.get(field, "") for field in field_names}, ensure_ascii=False)
            new_value = json.dumps({field: new_tracked.get(field, "") for field in field_names}, ensure_ascii=False)
            changes.append(make_change(
                before_date=before_date,
                after_date=after_date,
                change_type=change_type,
                semantic_type=semantic,
                identity=identity,
                row=new_row,
                changed_fields=";".join(field_names),
                old_value=old_value,
                new_value=new_value,
                url=url,
                note=note or "Values are source-reported states observed at two retrieval times.",
            ))
            emitted_fields.update(field_names)

        if old_tracked.get("status", "") != new_tracked.get("status", ""):
            new_status = new_tracked.get("status", "").lower()
            semantic = "permit_issued" if source in PERMIT_SOURCES and "issued" in new_status else ""
            emit("status_changed", ["status"], semantic)
        if old_tracked.get("description", "") != new_tracked.get("description", ""):
            emit("description_changed", ["description"])
        if old_tracked.get("project_name", "") != new_tracked.get("project_name", ""):
            emit("project_name_changed", ["project_name"])
        if old_tracked.get("record_type", "") != new_tracked.get("record_type", ""):
            emit("record_type_changed", ["record_type"])
        if old_tracked.get("estimated_cost", "") != new_tracked.get("estimated_cost", ""):
            emit("estimated_cost_changed", ["estimated_cost"], note="Estimated cost is not actual spending or final project cost.")
        if old_tracked.get("actual_cost", "") != new_tracked.get("actual_cost", ""):
            emit("reported_actual_cost_changed", ["actual_cost"], note="This is a source-reported amount, not an independently audited expenditure.")
        planned_fields = [
            field
            for field in ("planned_start", "planned_end")
            if old_tracked.get(field, "") != new_tracked.get(field, "")
        ]
        if planned_fields:
            semantic = "expected_completion_changed" if "planned_end" in planned_fields else ""
            emit("planned_date_changed", planned_fields, semantic, "Planned dates are schedules, not proof of work or completion.")
        if old_tracked.get("capital_phase", "") != new_tracked.get("capital_phase", ""):
            emit("capital_project_phase_changed", ["capital_phase"])

        raw_changed = meaningful_property_changes(old_props, new_props)
        tracked_source_fields = {
            "status": {"projectstatus", "application_status", "task_status", "appstatus", "status", "activitystatus"},
            "description": {"projectdescription", "projdesc"},
            "project_name": {"projectname1", "projectname2", "application_type", "recordalias", "projname"},
            "record_type": {"recordtype", "type", "subtype", "per_group", "recordalias", "projtype"},
            "estimated_cost": {"estcost"},
            "actual_cost": {"actcost"},
            "planned_start": {"planstart"},
            "planned_end": {"planend"},
            "capital_phase": {"projphase"},
        }
        accounted_raw = set().union(*(tracked_source_fields[field] for field in emitted_fields)) if emitted_fields else set()
        other = [field for field in raw_changed if field.lower() not in accounted_raw]
        if other:
            old_values = {field: old_props.get(field, "") for field in other}
            new_values = {field: new_props.get(field, "") for field in other}
            changes.append(make_change(
                before_date=before_date,
                after_date=after_date,
                change_type="other_field_changed",
                semantic_type="",
                identity=identity,
                row=new_row,
                changed_fields=";".join(other),
                old_value=json.dumps(old_values, ensure_ascii=False, sort_keys=True),
                new_value=json.dumps(new_values, ensure_ascii=False, sort_keys=True),
                url=url,
                note="One or more non-volatile source attributes changed outside the headline categories.",
            ))
    return sorted(changes, key=lambda row: (row["change_type"], row["source_name"], row["record_identity"]))


def load_snapshot(snapshot_date: str, snapshots_dir: Path = SNAPSHOTS) -> tuple[dict, list[dict[str, str]]]:
    directory = snapshots_dir / snapshot_date
    metadata_path = directory / "metadata.json"
    records_path = directory / "source_records.csv.gz"
    if not metadata_path.exists() or not records_path.exists():
        raise FileNotFoundError(f"Snapshot {snapshot_date} is incomplete or missing under {snapshots_dir}")
    return json.loads(metadata_path.read_text(encoding="utf-8")), read_csv(records_path)


def comparison_summary(
    changes: list[dict[str, str]],
    before_meta: dict,
    after_meta: dict,
) -> dict[str, object]:
    by_type = Counter(row["change_type"] for row in changes)
    by_semantic = Counter(row["semantic_type"] for row in changes if row["semantic_type"])
    by_source: dict[str, Counter] = defaultdict(Counter)
    for row in changes:
        by_source[row["source_name"]][row["change_type"]] += 1
    changed_records = {row["record_identity"] for row in changes}
    return {
        "format_version": FORMAT_VERSION,
        "comparison_month": str(after_meta["snapshot_date"])[:7],
        "before_snapshot_date": before_meta["snapshot_date"],
        "before_retrieved_at_utc": before_meta["retrieved_at_utc"],
        "after_snapshot_date": after_meta["snapshot_date"],
        "after_retrieved_at_utc": after_meta["retrieved_at_utc"],
        "before_record_count": before_meta["record_count"],
        "after_record_count": after_meta["record_count"],
        "records_with_any_published_change": len(changed_records),
        "change_rows": len(changes),
        "change_type_counts": dict(sorted(by_type.items())),
        "semantic_type_counts": dict(sorted(by_semantic.items())),
        "source_change_counts": {source: dict(sorted(counts.items())) for source, counts in sorted(by_source.items())},
        "interpretation": "Changes describe differences between two bounded public-layer snapshots, not all Tampa development or confirmed real-world outcomes.",
    }


def report_markdown(summary: dict[str, object], changes: list[dict[str, str]]) -> str:
    counts = summary["change_type_counts"]
    semantics = summary["semantic_type_counts"]
    month = dt.date.fromisoformat(str(summary["after_snapshot_date"])).strftime("%B %Y")
    lines = [
        f"# Tampa Published Development Records — {month} update",
        "",
        f"Comparison: **{summary['before_snapshot_date']} → {summary['after_snapshot_date']}**",
        "",
        "## What changed in the published layers",
        "",
        f"- {counts.get('new_record', 0):,} newly observed source records",
        f"- {counts.get('record_disappeared', 0):,} records no longer returned",
        f"- {counts.get('status_changed', 0):,} status changes",
        f"- {semantics.get('planning_application_added', 0):,} newly observed planning applications",
        f"- {counts.get('capital_project_phase_changed', 0):,} capital-project phase changes",
        f"- {counts.get('estimated_cost_changed', 0):,} estimated-cost changes",
        f"- {counts.get('planned_date_changed', 0):,} planned-date changes",
        "",
        f"The earlier snapshot contained {summary['before_record_count']:,} source records; the later snapshot contained {summary['after_record_count']:,}. "
        f"A total of {summary['records_with_any_published_change']:,} record identities had at least one reported change.",
        "",
        "## Changes by source",
        "",
        "| Source | New | No longer returned | Status | Phase | Cost | Planned date | Other |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    source_counts = summary["source_change_counts"]
    for source, source_values in source_counts.items():
        lines.append(
            f"| {source} | {source_values.get('new_record', 0):,} | "
            f"{source_values.get('record_disappeared', 0):,} | {source_values.get('status_changed', 0):,} | "
            f"{source_values.get('capital_project_phase_changed', 0):,} | {source_values.get('estimated_cost_changed', 0):,} | "
            f"{source_values.get('planned_date_changed', 0):,} | {source_values.get('other_field_changed', 0):,} |"
        )
    notable = [
        row
        for row in changes
        if row["change_type"] in {
            "status_changed",
            "capital_project_phase_changed",
            "estimated_cost_changed",
            "planned_date_changed",
        }
    ][:25]
    lines.extend(["", "## Selected field changes", ""])
    if notable:
        lines.extend([
            "| Type | Source record | Old | New |",
            "| --- | --- | --- | --- |",
        ])
        for row in notable:
            label = row["source_record_id"].replace("|", "\\|")
            if row["source_url"].startswith("http"):
                label = f"[{label}]({row['source_url']})"
            old_value = row["old_value"].replace("|", "\\|")[:180]
            new_value = row["new_value"].replace("|", "\\|")[:180]
            lines.append(f"| {row['change_type']} | {label} | {old_value} | {new_value} |")
    else:
        lines.append("No headline field changes were observed in this comparison.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "This report compares two snapshots of eight named City of Tampa public GIS layers. "
        "A newly observed record may have existed before the interval, and a record that is no longer returned is not necessarily deleted, cancelled, or complete. "
        "Permit issuance is authorization, planned dates are schedules, and estimated costs are not actual spending.",
        "",
        f"Full machine-readable changes: [`data/monthly_changes/{summary['comparison_month']}.csv`](../data/monthly_changes/{summary['comparison_month']}.csv)",
        "",
    ])
    return "\n".join(lines)


def compare_snapshots(
    before_date: str,
    after_date: str,
    *,
    snapshots_dir: Path = SNAPSHOTS,
    changes_dir: Path = CHANGES,
    reports_dir: Path = REPORTS,
) -> dict[str, object]:
    if before_date >= after_date:
        raise ValueError("The before snapshot date must precede the after snapshot date")
    before_meta, before_rows = load_snapshot(before_date, snapshots_dir)
    after_meta, after_rows = load_snapshot(after_date, snapshots_dir)
    changes = compare_records(before_rows, after_rows, before_date, after_date)
    summary = comparison_summary(changes, before_meta, after_meta)
    month = after_date[:7]
    csv_path = changes_dir / f"{month}.csv"
    json_path = changes_dir / f"{month}.json"
    report_path = reports_dir / f"{month}.md"
    for path in (csv_path, json_path, report_path):
        if path.exists():
            existing_dates = ""
            if json_path.exists():
                prior = json.loads(json_path.read_text(encoding="utf-8"))
                existing_dates = f"{prior.get('before_snapshot_date')} to {prior.get('after_snapshot_date')}"
            if existing_dates and existing_dates != f"{before_date} to {after_date}":
                raise RuntimeError(f"Refusing to replace comparison month {month}: existing period is {existing_dates}")
    atomic_csv(csv_path, changes, CHANGE_FIELDS)
    atomic_json(json_path, summary)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_markdown(summary, changes), encoding="utf-8", newline="\n")
    return summary


def tracker_index(
    snapshots_dir: Path = SNAPSHOTS,
    changes_dir: Path = CHANGES,
) -> dict[str, object]:
    snapshots = []
    if snapshots_dir.exists():
        for path in sorted(snapshots_dir.glob("*/metadata.json")):
            metadata = json.loads(path.read_text(encoding="utf-8"))
            snapshots.append({
                "snapshot_date": metadata["snapshot_date"],
                "retrieved_at_utc": metadata["retrieved_at_utc"],
                "record_count": metadata["record_count"],
                "source_counts": metadata["source_counts"],
                "path": path.parent.relative_to(ROOT).as_posix() if snapshots_dir == SNAPSHOTS else path.parent.as_posix(),
            })
    comparisons = []
    if changes_dir.exists():
        for path in sorted(changes_dir.glob("????-??.json")):
            summary = json.loads(path.read_text(encoding="utf-8"))
            comparisons.append({
                "comparison_month": summary["comparison_month"],
                "before_snapshot_date": summary["before_snapshot_date"],
                "after_snapshot_date": summary["after_snapshot_date"],
                "records_with_any_published_change": summary["records_with_any_published_change"],
                "csv": f"data/monthly_changes/{summary['comparison_month']}.csv",
                "summary": f"data/monthly_changes/{summary['comparison_month']}.json",
                "report": f"reports/{summary['comparison_month']}.md",
            })
    return {
        "format_version": FORMAT_VERSION,
        "status": "baseline_only" if len(snapshots) == 1 else "longitudinal" if len(snapshots) > 1 else "empty",
        "snapshot_count": len(snapshots),
        "comparison_count": len(comparisons),
        "snapshots": snapshots,
        "comparisons": comparisons,
        "scope_note": "Snapshots and comparisons cover the configured public source layers, not all Tampa development.",
    }


def sync_manifest(index: dict[str, object]) -> None:
    """Keep repository-level tracker pointers current without changing release scope."""
    manifest_path = ROOT / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshots = index.get("snapshots", [])
    latest_date = snapshots[-1]["snapshot_date"] if snapshots else None
    tracker = dict(manifest.get("longitudinal_tracker") or {})
    tracker.update({
        "status": index["status"],
        "snapshot_count": index["snapshot_count"],
        "comparison_count": index["comparison_count"],
        "latest_snapshot_date": latest_date,
        "scope": "Differences between repeated observations of the configured public layers; not confirmed real-world development outcomes.",
    })
    manifest["longitudinal_tracker"] = tracker
    tracked_outputs = {
        path.relative_to(ROOT).as_posix()
        for directory in (DATA / "coverage", SNAPSHOTS, CHANGES, REPORTS)
        if directory.exists()
        for path in directory.rglob("*")
        if path.is_file()
    }
    manifest["outputs"] = sorted(set(manifest.get("outputs", [])) | tracked_outputs)
    atomic_json(manifest_path, manifest)


def update_tracker(
    source_path: Path = DATA / "processed" / "source_records.csv",
    *,
    snapshots_dir: Path = SNAPSHOTS,
    changes_dir: Path = CHANGES,
    reports_dir: Path = REPORTS,
) -> dict[str, object]:
    archived = archive_snapshot(source_path, snapshots_dir)
    dates = sorted(path.parent.name for path in snapshots_dir.glob("*/metadata.json"))
    comparison = None
    if len(dates) >= 2 and archived["snapshot_date"] == dates[-1]:
        comparison = compare_snapshots(
            dates[-2],
            dates[-1],
            snapshots_dir=snapshots_dir,
            changes_dir=changes_dir,
            reports_dir=reports_dir,
        )
    index = tracker_index(snapshots_dir, changes_dir)
    index_path = INDEX if changes_dir == CHANGES else changes_dir / "index.json"
    atomic_json(index_path, index)
    if snapshots_dir == SNAPSHOTS and changes_dir == CHANGES and reports_dir == REPORTS:
        sync_manifest(index)
    return {"archived_snapshot": archived, "comparison": comparison, "index": index}


def collect_live_and_update() -> dict[str, object]:
    rows = collect_live_rows()
    archived = archive_rows(rows, SNAPSHOTS)
    dates = sorted(path.parent.name for path in SNAPSHOTS.glob("*/metadata.json"))
    comparison = None
    if len(dates) >= 2 and archived["snapshot_date"] == dates[-1]:
        comparison = compare_snapshots(dates[-2], dates[-1])
    index = tracker_index()
    atomic_json(INDEX, index)
    sync_manifest(index)
    return {"archived_snapshot": archived, "comparison": comparison, "index": index}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    archive = subparsers.add_parser("archive", help="Archive the current processed source-record table")
    archive.add_argument("--source", type=Path, default=DATA / "processed" / "source_records.csv")
    compare = subparsers.add_parser("compare", help="Compare two already archived snapshots")
    compare.add_argument("--from-date", required=True)
    compare.add_argument("--to-date", required=True)
    update = subparsers.add_parser("update", help="Archive the current table and compare it with the prior snapshot")
    update.add_argument("--source", type=Path, default=DATA / "processed" / "source_records.csv")
    subparsers.add_parser(
        "collect-live",
        help="Collect the eight live layers into the compact tracker without rebuilding validation tables",
    )
    args = parser.parse_args()
    if args.command == "archive":
        result = archive_snapshot(args.source)
        atomic_json(INDEX, tracker_index())
    elif args.command == "compare":
        result = compare_snapshots(args.from_date, args.to_date)
        atomic_json(INDEX, tracker_index())
    elif args.command == "update":
        result = update_tracker(args.source)
    else:
        result = collect_live_and_update()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
