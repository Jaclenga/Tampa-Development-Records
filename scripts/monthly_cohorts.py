#!/usr/bin/env python3
"""Build source-date cohorts without conflating them with TDR observations.

The output has one row per source-record identity ever retained in an immutable
snapshot. ``event_month`` comes from a documented source field, while
``first_observed_month`` and ``snapshot_month`` come from TDR collection dates.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from . import snapshot_tracker
except ImportError:  # Support direct execution: python scripts/monthly_cohorts.py
    import snapshot_tracker


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
SNAPSHOTS = DATA / "snapshots"
MONTHLY_EVENTS = DATA / "monthly_events"
PLANNED_EVENTS = DATA / "planned_events"
OUTPUT = PROCESSED / "activity_by_month.csv"
FORMAT_VERSION = "2.0.0"

COHORT_FIELDS = [
    "record_id",
    "record_identity",
    "source_record_key",
    "activity_id",
    "source_name",
    "source_record_id",
    "event_date",
    "event_month",
    "event_date_type",
    "event_date_source_field",
    "event_date_basis",
    "event_date_is_planned",
    "event_date_is_after_snapshot",
    "first_observed_date",
    "first_observed_month",
    "last_observed_date",
    "last_observed_month",
    "snapshot_date",
    "snapshot_month",
    "observation_count",
    "currently_observed",
    "status",
    "project_name",
    "record_type",
    "address",
    "neighborhood",
    "source_url",
]


FIELD_METADATA = {
    "record_id": ("Stable hashed identifier for one cross-snapshot source-record identity.", "text", "", "Never blank.", "derived identifier", "SHA-1 of record_identity, truncated to 16 hexadecimal characters.", "rec-*", "Identifies a published source record, not necessarily a real-world development."),
    "record_identity": ("Comparison identity used to link the same source record across snapshots.", "text", "", "Never blank.", "derived identifier", "Source plus native ID, with GlobalID or OBJECTID disambiguation for duplicates.", "Tracker-defined identity string.", "An upstream identifier replacement can still split one record into two identities."),
    "source_record_key": ("Current-release source feature key when the record is present in the processed release.", "text", "", "Blank for a historical record absent from the current processed release.", "derived identifier", "Copied from current source_records.csv by record identity.", "src-* or blank.", "Use record_id for cross-snapshot cohort work."),
    "activity_id": ("Current normalized activity identifier linked to the source record when available.", "text", "", "Blank for a historical record absent from the current processed release.", "derived identifier", "Copied from current source_records.csv by record identity.", "tpa-* or blank.", "Activity IDs are a secondary analytical view and may change with entity-resolution rules."),
    "source_name": ("Machine-readable name of the originating City GIS layer.", "text", "", "Never blank.", "source metadata", "Retained from the latest snapshot containing the record.", "One of the eight configured source names.", "Source layers have different scopes and date semantics."),
    "source_record_id": ("Native record or project identifier reported by the source.", "text", "", "Blank when the source supplied no usable native identifier.", "source", "Retained from the latest snapshot containing the record.", "Source-defined.", "May be reused or missing in upstream data."),
    "event_date": ("Selected source-derived date used to assign the record to an event cohort.", "date", "", "Blank when no supported source date is available.", "source/derived selection", "Source-specific hierarchy documented in TEMPORAL_COHORTS.md.", "ISO 8601 date.", "Interpret only with event_date_type and event_date_basis; meanings differ across sources."),
    "event_month": ("Calendar month derived from event_date.", "year-month", "", "Blank when event_date is blank.", "derived", "First seven characters of event_date.", "YYYY-MM.", "This is not the month TDR first observed the record."),
    "event_date_type": ("Meaning assigned to the selected source date.", "categorical text", "", "Blank when no supported source date is available.", "derived semantic label", "Source-specific date-selection rule.", "permit_issued; permit_application_opened; permit_record_created; planning_application_created; preservation_application_created; capital_actual_start; capital_planned_start; source_record_created", "Do not pool different types as one homogeneous development-event measure."),
    "event_date_source_field": ("Exact source attribute from which event_date was parsed.", "text", "", "Blank when event_date is blank.", "source metadata", "First valid field in the documented source-specific hierarchy.", "Source field name.", "Field names do not make unlike source concepts directly comparable."),
    "event_date_basis": ("Broad evidence class for the selected event date.", "categorical text", "", "Blank when event_date is blank.", "derived", "Assigned from event_date_type.", "source_reported_event; source_reported_plan; source_record_metadata", "A plan or record-metadata date does not prove real-world work occurred."),
    "event_date_is_planned": ("Whether event_date is explicitly a planned rather than observed date.", "boolean/integer", "", "Never blank.", "derived", "1 only for a capital planned-start date; otherwise 0.", "0; 1", "A value of 0 does not independently validate that an underlying physical event occurred."),
    "event_date_is_after_snapshot": ("Whether event_date falls after the snapshot supplying the row attributes.", "boolean/integer", "", "Never blank.", "derived", "event_date greater than snapshot_date.", "0; 1", "Expected for some planned dates; unexpected values merit source-level review."),
    "first_observed_date": ("First TDR snapshot date in which the record identity appears.", "date", "", "Never blank.", "TDR observation history", "Minimum archived observation date for record_identity.", "ISO 8601 date.", "Does not identify when the record entered the City's system."),
    "first_observed_month": ("Calendar month of first_observed_date.", "year-month", "", "Never blank.", "derived", "First seven characters of first_observed_date.", "YYYY-MM.", "Newly observed by TDR is not necessarily newly created by the source."),
    "last_observed_date": ("Most recent TDR snapshot date in which the record identity appears.", "date", "", "Never blank.", "TDR observation history", "Maximum archived observation date for record_identity.", "ISO 8601 date.", "A final observation does not prove deletion, cancellation, or completion."),
    "last_observed_month": ("Calendar month of last_observed_date.", "year-month", "", "Never blank.", "derived", "First seven characters of last_observed_date.", "YYYY-MM.", "This is an observation month, not an underlying event month."),
    "snapshot_date": ("Snapshot date supplying the source attributes represented in this row.", "date", "", "Never blank.", "TDR observation history", "Latest snapshot containing record_identity.", "ISO 8601 date.", "Attributes may have had different values in earlier snapshots."),
    "snapshot_month": ("Calendar month of the snapshot supplying the row attributes.", "year-month", "", "Never blank.", "derived", "First seven characters of snapshot_date.", "YYYY-MM.", "This is a TDR collection month, not an underlying event month."),
    "observation_count": ("Number of distinct TDR snapshot dates containing the record identity.", "integer", "snapshots", "Never blank.", "derived", "Count of distinct snapshot dates for record_identity.", "Positive integer.", "Snapshot cadence determines the observation opportunity count."),
    "currently_observed": ("Whether the record appears in the latest available TDR snapshot.", "boolean/integer", "", "Never blank.", "derived", "1 when last_observed_date equals the latest snapshot date; otherwise 0.", "0; 1", "Absence from the latest layer does not prove deletion, cancellation, or completion."),
    "status": ("Status text reported in the snapshot supplying this row.", "text", "", "Blank means unavailable.", "source", "Source-specific status fields normalized by snapshot_tracker.tracked_values().", "Source-defined.", "Status semantics differ across sources and snapshots."),
    "project_name": ("Project, application, or permit name reported in the snapshot supplying this row.", "text", "", "Blank means unavailable.", "source", "Source-specific name fields normalized by snapshot_tracker.tracked_values().", "Source-defined.", "Names are not standardized across source systems."),
    "record_type": ("Record type reported in the snapshot supplying this row.", "text", "", "Blank means unavailable.", "source", "Source-specific type fields normalized by snapshot_tracker.tracked_values().", "Source-defined.", "Types are not harmonized across source systems."),
    "address": ("Site address reported in the snapshot supplying this row.", "text", "", "Blank means unavailable.", "source", "ADDRESS or FULLADDRESS.", "Source-defined street address.", "Public but potentially sensitive; aggregate person-focused analyses."),
    "neighborhood": ("City neighborhood label reported in the snapshot supplying this row.", "text", "", "Blank means unavailable.", "source", "NEIGHBORHOOD or Neighborhood.", "City-defined label.", "Not spatially recomputed against a boundary vintage."),
    "source_url": ("Public record, project, or layer URL available for the snapshot row.", "URL", "", "Never blank because the source endpoint is used as a fallback.", "source metadata", "URL, ProjectSiteURL, docpath, or source endpoint.", "HTTP(S) URL.", "The target can move or its live contents can change."),
}


def metadata_for(field: str) -> tuple[str, str, str, str, str, str, str, str] | None:
    return FIELD_METADATA.get(field)


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_source_date(value: object) -> str:
    """Return a reproducible ISO date, rejecting sentinels and implausible years."""
    if value in (None, ""):
        return ""
    parsed: dt.date | None = None
    if isinstance(value, (int, float)) or re.fullmatch(r"-?\d+(?:\.\d+)?", clean(value)):
        try:
            numeric = float(value)
            seconds = numeric / 1000 if abs(numeric) > 10_000_000_000 else numeric
            parsed = (dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=seconds)).date()
        except (OverflowError, TypeError, ValueError):
            return ""
    else:
        text = clean(value)
        for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                parsed = dt.datetime.strptime(text[:10], pattern).date()
                break
            except ValueError:
                continue
    if parsed is None or not 2000 <= parsed.year <= 2100:
        return ""
    return parsed.isoformat()


def first_valid_date(props: dict[str, object], *fields: str) -> tuple[str, str]:
    lowered = {key.lower(): (key, value) for key, value in props.items()}
    for field in fields:
        original, value = lowered.get(field.lower(), (field, ""))
        parsed = parse_source_date(value)
        if parsed:
            return parsed, original
    return "", ""


def select_event_date(source: str, props: dict[str, object]) -> tuple[str, str, str, str, str]:
    """Select one explicit source-date concept for a source record.

    Returns date, type, source field, basis, and planned flag. The hierarchy is
    source-specific and deliberately avoids treating a generic last-update date
    as a permit issuance or a real-world construction event.
    """
    if source == "single_family_permits":
        task_text = " ".join(
            clean(snapshot_tracker.lookup(props, field)).lower()
            for field in ("TASK", "TASK_STATUS", "TASK_HISTORY", "TASK_HISTORY_STATUS", "APPLICATION_STATUS")
        )
        if "issued" in task_text:
            date, field = first_valid_date(props, "TASK_STATUS_DATE", "TASK_HISTORY_STATUS_DATE")
            if date:
                return date, "permit_issued", field, "source_reported_event", "0"
        date, field = first_valid_date(props, "OPENED_DATE")
        if date:
            return date, "permit_application_opened", field, "source_reported_event", "0"
        date, field = first_valid_date(props, "CREATEDDATE")
        return date, "source_record_created" if date else "", field, "source_record_metadata" if date else "", "0"

    if source == "construction_inspections":
        date, field = first_valid_date(props, "CREATEDDATE")
        return date, "permit_record_created" if date else "", field, "source_record_metadata" if date else "", "0"

    if source == "development_coordination":
        date, field = first_valid_date(props, "CREATEDDATE")
        return date, "planning_application_created" if date else "", field, "source_reported_event" if date else "", "0"

    if source == "historic_preservation":
        date, field = first_valid_date(props, "CREATEDDATE")
        return date, "preservation_application_created" if date else "", field, "source_reported_event" if date else "", "0"

    if source in snapshot_tracker.CAPITAL_SOURCES:
        date, field = first_valid_date(props, "actstart")
        if date:
            return date, "capital_actual_start", field, "source_reported_event", "0"
        date, field = first_valid_date(props, "planstart")
        if date:
            return date, "capital_planned_start", field, "source_reported_plan", "1"
        date, field = first_valid_date(props, "CreationDate", "created_date")
        return date, "source_record_created" if date else "", field, "source_record_metadata" if date else "", "0"

    return "", "", "", "", "0"


def read_current(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    return snapshot_tracker.read_csv(path)


def load_observations(
    snapshots_dir: Path,
    current_source_path: Path | None,
) -> tuple[list[tuple[str, list[dict[str, str]]]], list[dict[str, str]]]:
    observations = []
    for metadata_path in sorted(snapshots_dir.glob("*/metadata.json")):
        snapshot_date = metadata_path.parent.name
        _, rows = snapshot_tracker.load_snapshot(snapshot_date, snapshots_dir)
        observations.append((snapshot_date, rows))

    current = read_current(current_source_path)
    if current:
        current_date, _ = snapshot_tracker.snapshot_date_from_rows(current)
        existing = {date: rows for date, rows in observations}
        if current_date in existing:
            archived = snapshot_tracker.source_state_sha256(
                snapshot_tracker.canonical_snapshot_rows(existing[current_date])
            )
            candidate = snapshot_tracker.source_state_sha256(
                snapshot_tracker.canonical_snapshot_rows(current)
            )
            if archived != candidate:
                raise RuntimeError(
                    f"Current source table conflicts with immutable snapshot {current_date}"
                )
        else:
            observations.append((current_date, snapshot_tracker.canonical_snapshot_rows(current)))
    observations.sort(key=lambda item: item[0])
    if not observations:
        raise ValueError("No archived snapshot or current source-record table was available")
    return observations, current


def build_rows(
    snapshots_dir: Path = SNAPSHOTS,
    current_source_path: Path | None = PROCESSED / "source_records.csv",
) -> list[dict[str, str]]:
    observations, current = load_observations(snapshots_dir, current_source_path)
    all_rows = [row for _, rows in observations for row in rows]
    disambiguated = set().union(*(snapshot_tracker.duplicate_bases(rows) for _, rows in observations))

    enrichment: dict[str, dict[str, str]] = {}
    for row in current:
        base = snapshot_tracker.base_record_identity(row)
        identity = snapshot_tracker.record_identity(row, base in disambiguated)
        enrichment[identity] = row

    history: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
    for snapshot_date, rows in observations:
        indexed = snapshot_tracker.index_records(rows, disambiguated)
        for identity, row in indexed.items():
            history[identity].append((snapshot_date, row))

    latest_snapshot_date = observations[-1][0]
    output = []
    for identity, seen in sorted(history.items()):
        seen.sort(key=lambda item: item[0])
        snapshot_date, row = seen[-1]
        props = snapshot_tracker.properties(row)
        source = row["source_name"]
        event_date, event_type, event_field, event_basis, planned = select_event_date(source, props)
        tracked = snapshot_tracker.tracked_values(source, props)
        extra = enrichment.get(identity, {})
        first_date = seen[0][0]
        last_date = seen[-1][0]
        output.append({
            "record_id": f"rec-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:16]}",
            "record_identity": identity,
            "source_record_key": extra.get("source_record_key", ""),
            "activity_id": extra.get("activity_id", ""),
            "source_name": source,
            "source_record_id": row.get("source_record_id", ""),
            "event_date": event_date,
            "event_month": event_date[:7] if event_date else "",
            "event_date_type": event_type,
            "event_date_source_field": event_field,
            "event_date_basis": event_basis,
            "event_date_is_planned": planned,
            "event_date_is_after_snapshot": "1" if event_date and event_date > snapshot_date else "0",
            "first_observed_date": first_date,
            "first_observed_month": first_date[:7],
            "last_observed_date": last_date,
            "last_observed_month": last_date[:7],
            "snapshot_date": snapshot_date,
            "snapshot_month": snapshot_date[:7],
            "observation_count": str(len({date for date, _ in seen})),
            "currently_observed": "1" if last_date == latest_snapshot_date else "0",
            "status": tracked.get("status", ""),
            "project_name": tracked.get("project_name", ""),
            "record_type": tracked.get("record_type", ""),
            "address": clean(snapshot_tracker.lookup(props, "ADDRESS", "FULLADDRESS")),
            "neighborhood": clean(snapshot_tracker.lookup(props, "NEIGHBORHOOD", "Neighborhood")),
            "source_url": snapshot_tracker.source_url(row, props),
        })
    return output


def write_outputs(
    rows: list[dict[str, str]],
    output_path: Path = OUTPUT,
    monthly_events_dir: Path = MONTHLY_EVENTS,
    planned_events_dir: Path = PLANNED_EVENTS,
) -> dict[str, object]:
    future_non_plans = [
        row for row in rows
        if row["event_month"]
        and row["event_date_is_after_snapshot"] == "1"
        and row["event_date_is_planned"] != "1"
    ]
    if future_non_plans:
        ids = ", ".join(row["record_id"] for row in future_non_plans[:5])
        raise ValueError(
            "Future-dated source events must be explicit plans before publication; "
            f"found {len(future_non_plans)} non-plan rows (examples: {ids})"
        )

    monthly_rows = [
        row for row in rows
        if row["event_month"] and row["event_date_is_after_snapshot"] == "0"
    ]
    planned_rows = [
        row for row in rows
        if row["event_month"] and row["event_date_is_after_snapshot"] == "1"
    ]

    snapshot_tracker.atomic_csv(output_path, rows, COHORT_FIELDS)
    monthly_index = write_partition(
        monthly_rows,
        monthly_events_dir,
        extract_type="monthly_events",
        selection_rule="event_date is on or before the source row's snapshot_date",
        scope_note=(
            "Source-described dates that are not forward-looking relative to the TDR "
            "snapshot supplying the row. These are not TDR observation months, and "
            "different event_date_type values must not be pooled without qualification."
        ),
    )
    planned_index = write_partition(
        planned_rows,
        planned_events_dir,
        extract_type="planned_events",
        selection_rule=(
            "event_date is after snapshot_date and event_date_is_planned equals 1"
        ),
        scope_note=(
            "Forward-looking dates explicitly reported by the source as plans. They are "
            "not historical observations, actual starts, or proof that work occurred."
        ),
    )

    dated_count = sum(bool(row["event_month"]) for row in rows)
    return {
        "format_version": FORMAT_VERSION,
        "row_count": len(rows),
        "records_with_event_month": dated_count,
        "records_without_event_month": len(rows) - dated_count,
        "monthly_event_record_count": len(monthly_rows),
        "planned_event_record_count": len(planned_rows),
        "unexpected_future_event_count": len(future_non_plans),
        "first_monthly_event_month": monthly_index["first_event_month"],
        "last_monthly_event_month": monthly_index["last_event_month"],
        "monthly_event_month_count": monthly_index["month_count"],
        "first_planned_event_month": planned_index["first_event_month"],
        "last_planned_event_month": planned_index["last_event_month"],
        "planned_event_month_count": planned_index["month_count"],
        "monthly_events": monthly_index,
        "planned_events": planned_index,
    }


def write_partition(
    rows: list[dict[str, str]],
    directory: Path,
    *,
    extract_type: str,
    selection_rule: str,
    scope_note: str,
) -> dict[str, object]:
    by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_month[row["event_month"]].append(row)

    directory.mkdir(parents=True, exist_ok=True)
    expected = {directory / f"{month}.csv" for month in by_month}
    for stale in directory.glob("????-??.csv"):
        if stale not in expected:
            stale.unlink()
    month_summaries = []
    for month, month_rows in sorted(by_month.items()):
        month_rows.sort(key=lambda row: (row["source_name"], row["record_id"]))
        path = directory / f"{month}.csv"
        snapshot_tracker.atomic_csv(path, month_rows, COHORT_FIELDS)
        month_summaries.append({
            "event_month": month,
            "record_count": len(month_rows),
            "source_counts": dict(sorted(Counter(row["source_name"] for row in month_rows).items())),
            "event_date_type_counts": dict(sorted(Counter(row["event_date_type"] for row in month_rows).items())),
            "path": f"data/{directory.name}/{month}.csv",
        })

    index = {
        "format_version": FORMAT_VERSION,
        "extract_type": extract_type,
        "record_count": len(rows),
        "first_event_month": month_summaries[0]["event_month"] if month_summaries else None,
        "last_event_month": month_summaries[-1]["event_month"] if month_summaries else None,
        "month_count": len(month_summaries),
        "months": month_summaries,
        "selection_rule": selection_rule,
        "scope_note": scope_note,
    }
    snapshot_tracker.atomic_json(directory / "index.json", index)
    return index


def build(
    snapshots_dir: Path = SNAPSHOTS,
    current_source_path: Path | None = PROCESSED / "source_records.csv",
    output_path: Path = OUTPUT,
    monthly_events_dir: Path = MONTHLY_EVENTS,
    planned_events_dir: Path = PLANNED_EVENTS,
) -> dict[str, object]:
    return write_outputs(
        build_rows(snapshots_dir, current_source_path),
        output_path,
        monthly_events_dir,
        planned_events_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PROCESSED / "source_records.csv")
    parser.add_argument("--snapshots-dir", type=Path, default=SNAPSHOTS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--monthly-events-dir", type=Path, default=MONTHLY_EVENTS)
    parser.add_argument("--planned-events-dir", type=Path, default=PLANNED_EVENTS)
    args = parser.parse_args()
    result = build(
        args.snapshots_dir,
        args.source,
        args.output,
        args.monthly_events_dir,
        args.planned_events_dir,
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
