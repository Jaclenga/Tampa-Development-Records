#!/usr/bin/env python3
"""Deterministic analytics for existing snapshot-comparison artifacts."""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import gzip
import json
import math
import os
from pathlib import Path
import re
import statistics
import tempfile
from typing import Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
CHANGES = DATA / "monthly_changes"
ANALYSIS = CHANGES / "analysis"
REPORTS = ROOT / "reports" / "changes"
THRESHOLDS = ROOT / "config" / "change_analysis_thresholds.json"
SCHEMA_VERSION = "1.0.0"
INVALID_NATIVE_IDS = {"", "N/A", "NA", "NONE", "NULL", "UNKNOWN", "0000000", "0", "-"}

SOURCE_FIELDS = [
    "source_id", "before_count", "after_count", "absolute_delta", "percentage_delta",
    "new_records", "disappeared_records", "retained_records", "union_size",
    "retention_rate", "disappearance_rate", "publication_churn", "unique_changed_identities",
    "changed_identity_rate", "field_change_row_count", "alert_level", "alert_reasons",
]
FIELD_FIELDS = [
    "source_id", "changed_field", "semantic_change_category", "unique_retained_identities_affected",
    "change_row_count", "retained_record_denominator", "affected_retained_rate",
    "common_old_to_new_patterns", "mass_refresh_warning",
]
TRANSITION_FIELDS = ["transition_type", "source_id", "old_value", "new_value", "unique_record_count"]


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def canonical(value: object) -> str:
    return clean(value).upper()


def rate(numerator: int | float, denominator: int | float) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else path.open
    if path.suffix == ".gz":
        handle = opener(path, mode="rt", encoding="utf-8", newline="")
    else:
        handle = opener(mode="r", encoding="utf-8", newline="")
    with handle:
        return list(csv.DictReader(handle))


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def atomic_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def load_thresholds(path: Path = THRESHOLDS) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_snapshot(date: str, snapshots_dir: Path = SNAPSHOTS) -> tuple[dict, list[dict[str, str]]]:
    directory = snapshots_dir / date
    metadata = directory / "metadata.json"
    records = directory / "source_records.csv.gz"
    if not metadata.is_file() or not records.is_file():
        raise FileNotFoundError(f"Snapshot {date} is incomplete or missing under {snapshots_dir}")
    return json.loads(metadata.read_text(encoding="utf-8")), read_csv(records)


def base_identity(row: dict[str, str]) -> str:
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
    return ""


def canonical_identities(before: list[dict[str, str]], after: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    before_bases = Counter(base_identity(row) for row in before if base_identity(row))
    after_bases = Counter(base_identity(row) for row in after if base_identity(row))
    duplicated = {
        value for value in set(before_bases) | set(after_bases)
        if before_bases[value] > 1 or after_bases[value] > 1
    }

    def identity(row: dict[str, str]) -> str:
        base = base_identity(row)
        if not base or base not in duplicated:
            return base
        global_id = canonical(row.get("source_global_id"))
        object_id = canonical(row.get("source_object_id"))
        suffix = f"GLOBALID|{global_id}" if global_id else f"OBJECTID|{object_id}" if object_id else ""
        return f"{base}|{suffix}" if suffix else base

    return [identity(row) for row in before], [identity(row) for row in after]


def valid_url(value: str) -> bool:
    parsed = urlparse(clean(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_month_end(value: dt.date) -> bool:
    return value.day == calendar.monthrange(value.year, value.month)[1]


def adjacent_months(before: dt.date, after: dt.date) -> bool:
    return (after.year * 12 + after.month) - (before.year * 12 + before.month) == 1


def classify_comparison(before_date: str, after_date: str, thresholds: dict[str, object]) -> tuple[str, bool]:
    try:
        before = dt.date.fromisoformat(before_date)
        after = dt.date.fromisoformat(after_date)
    except ValueError:
        return "unknown", False
    semantics = thresholds.get("interval_semantics", {})
    if before_date == semantics.get("baseline_snapshot"):
        return "baseline_followup", False
    canonical_start = dt.date.fromisoformat(str(semantics.get("canonical_month_end_start", "9999-12-31")))
    if before >= canonical_start and is_month_end(before) and is_month_end(after) and adjacent_months(before, after):
        return "month_end_to_month_end", True
    return "manual_interval", False


def decoded_mapping(value: str) -> dict[str, object]:
    try:
        decoded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def field_value(value: str, field: str) -> object:
    mapping = decoded_mapping(value)
    if field in mapping:
        return mapping[field]
    lowered = {str(key).lower(): item for key, item in mapping.items()}
    return lowered.get(field.lower(), value if not mapping else "")


def display_value(value: object) -> str:
    if value in (None, ""):
        return "(blank)"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return clean(value)


def split_fields(row: dict[str, str]) -> list[str]:
    values = [value for value in row.get("changed_fields", "").split(";") if value]
    return sorted(set(values))


def parse_date(value: object) -> dt.date | None:
    text = clean(value)
    if not text:
        return None
    try:
        number = float(text)
        if math.isfinite(number):
            seconds = number / 1000 if abs(number) > 10_000_000_000 else number
            return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).date()
    except (ValueError, OverflowError, OSError):
        pass
    normalized = text.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None


def parse_cost(value: object) -> Decimal | None:
    text = clean(value)
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "").strip()
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return -result if negative else result


def median(values: list[float]) -> float | None:
    return None if not values else round(float(statistics.median(values)), 6)


def summarize_numeric_events(events: list[dict[str, object]], delta_key: str) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for event in events:
        grouped[(str(event["source_id"]), str(event.get("field", event.get("cost_type", ""))))].append(event)
    summaries = []
    for (source, field), rows in sorted(grouped.items()):
        deltas = [float(row[delta_key]) for row in rows if row.get(delta_key) is not None]
        categories = Counter(str(row["classification"]) for row in rows)
        summaries.append({
            "source_id": source,
            "field": field,
            "change_count": len(rows),
            "classification_counts": dict(sorted(categories.items())),
            f"median_{delta_key}": median(deltas),
            f"minimum_{delta_key}": round(min(deltas), 6) if deltas else None,
            f"maximum_{delta_key}": round(max(deltas), 6) if deltas else None,
        })
    return summaries


def identity_quality(
    before_rows: list[dict[str, str]],
    after_rows: list[dict[str, str]],
    changes: list[dict[str, str]],
) -> dict[str, object]:
    before_ids, after_ids = canonical_identities(before_rows, after_rows)

    def duplicate_native(rows: list[dict[str, str]]) -> tuple[int, int]:
        counts = Counter(
            (canonical(row.get("source_name")), canonical(row.get("source_record_id")))
            for row in rows if canonical(row.get("source_record_id")) not in INVALID_NATIVE_IDS
        )
        groups = [count for count in counts.values() if count > 1]
        return len(groups), sum(groups)

    before_groups, before_records = duplicate_native(before_rows)
    after_groups, after_records = duplicate_native(after_rows)
    native_to_canonical: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in changes:
        native = canonical(row.get("source_record_id"))
        if native not in INVALID_NATIVE_IDS:
            native_to_canonical[(row.get("source_name", ""), native)].add(row.get("record_identity", ""))
    ambiguous = [
        {"source_id": key[0], "source_record_id": key[1], "canonical_identity_count": len(values)}
        for key, values in sorted(native_to_canonical.items()) if len(values) > 1
    ]
    return {
        "duplicate_native_id_groups_before": before_groups,
        "duplicate_native_id_records_before": before_records,
        "duplicate_native_id_groups_after": after_groups,
        "duplicate_native_id_records_after": after_records,
        "blank_native_ids_before": sum(canonical(row.get("source_record_id")) in INVALID_NATIVE_IDS for row in before_rows),
        "blank_native_ids_after": sum(canonical(row.get("source_record_id")) in INVALID_NATIVE_IDS for row in after_rows),
        "missing_record_identities": sum(not clean(row.get("record_identity")) for row in changes),
        "duplicate_canonical_identities_before": len(before_ids) - len(set(before_ids)),
        "duplicate_canonical_identities_after": len(after_ids) - len(set(after_ids)),
        "blank_source_links": sum(not clean(row.get("source_url")) for row in changes),
        "malformed_source_links": sum(bool(clean(row.get("source_url"))) and not valid_url(row.get("source_url", "")) for row in changes),
        "native_ids_with_multiple_canonical_identities": ambiguous,
    }


def alert(
    code: str,
    severity: str,
    metric: str,
    observed: object,
    threshold: object,
    affected: int,
    explanation: str,
    *,
    source: str | None = None,
    prevents_trend: bool = False,
) -> dict[str, object]:
    return {
        "alert_code": code,
        "severity": severity,
        "source_id": source,
        "metric_name": metric,
        "observed_value": observed,
        "threshold": threshold,
        "affected_count": affected,
        "explanation": explanation,
        "prevents_aggregate_trend_interpretation": prevents_trend,
    }


def analyze_comparison(
    before_meta: dict,
    after_meta: dict,
    before_rows: list[dict[str, str]],
    after_rows: list[dict[str, str]],
    changes: list[dict[str, str]],
    raw_summary: dict,
    thresholds: dict[str, object],
) -> dict[str, object]:
    before_date = str(before_meta["snapshot_date"])
    after_date = str(after_meta["snapshot_date"])
    month = str(raw_summary["comparison_month"])
    kind, canonical_monthly = classify_comparison(before_date, after_date, thresholds)
    change_counts = Counter(row["change_type"] for row in changes)
    semantic_counts = Counter(row["semantic_type"] for row in changes if row.get("semantic_type"))
    before_count = int(before_meta["record_count"])
    after_count = int(after_meta["record_count"])
    new = change_counts["new_record"]
    disappeared = change_counts["record_disappeared"]
    retained = before_count - disappeared
    union = retained + disappeared + new
    changed = len({row["record_identity"] for row in changes})
    overall = {
        "count_before": before_count,
        "count_after": after_count,
        "absolute_net_change": after_count - before_count,
        "percentage_net_change": rate(after_count - before_count, before_count),
        "new_records": new,
        "disappeared_records": disappeared,
        "retained_records": retained,
        "union_size": union,
        "retention_rate": rate(retained, before_count),
        "disappearance_rate": rate(disappeared, before_count),
        "publication_churn": rate(new + disappeared, union),
        "unique_changed_record_identities": changed,
        "total_change_rows": len(changes),
        "change_type_counts": dict(sorted(change_counts.items())),
        "semantic_change_category_counts": dict(sorted(semantic_counts.items())),
        "denominators": {
            "percentage_net_change": "count_before",
            "retention_rate": "count_before",
            "disappearance_rate": "count_before",
            "publication_churn": "union_size",
        },
    }

    expected_sources = sorted(set(before_meta.get("source_counts", {})) | set(after_meta.get("source_counts", {})))
    source_changes: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in changes:
        source_changes[row["source_name"]].append(row)
    source_health = []
    for source in expected_sources:
        rows = source_changes[source]
        counts = Counter(row["change_type"] for row in rows)
        before = int(before_meta.get("source_counts", {}).get(source, 0))
        after = int(after_meta.get("source_counts", {}).get(source, 0))
        source_new = counts["new_record"]
        source_disappeared = counts["record_disappeared"]
        source_retained = before - source_disappeared
        source_union = source_retained + source_disappeared + source_new
        field_rows = [row for row in rows if split_fields(row)]
        source_health.append({
            "source_id": source,
            "before_count": before,
            "after_count": after,
            "absolute_delta": after - before,
            "percentage_delta": rate(after - before, before),
            "new_records": source_new,
            "disappeared_records": source_disappeared,
            "retained_records": source_retained,
            "union_size": source_union,
            "retention_rate": rate(source_retained, before),
            "disappearance_rate": rate(source_disappeared, before),
            "publication_churn": rate(source_new + source_disappeared, source_union),
            "unique_changed_identities": len({row["record_identity"] for row in rows}),
            "changed_identity_rate": rate(len({row["record_identity"] for row in rows}), source_union),
            "field_change_row_count": len(field_rows),
            "alert_level": "healthy",
            "alert_reasons": [],
        })

    field_groups: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in changes:
        if row["change_type"] in {"new_record", "record_disappeared"}:
            continue
        for field in split_fields(row):
            field_groups[(row["source_name"], field, row["change_type"])].append({
                "identity": row["record_identity"],
                "old": field_value(row.get("old_value", ""), field),
                "new": field_value(row.get("new_value", ""), field),
            })
    retained_by_source = {row["source_id"]: row["retained_records"] for row in source_health}
    field_concentration = []
    warning_cfg = thresholds["warning"]
    for (source, field, category), rows in sorted(field_groups.items()):
        identities = {str(row["identity"]) for row in rows}
        denominator = int(retained_by_source.get(source, 0))
        affected_rate = rate(len(identities), denominator)
        patterns = Counter((display_value(row["old"]), display_value(row["new"])) for row in rows)
        common = [
            {"old_value": old, "new_value": new, "record_count": count}
            for (old, new), count in sorted(patterns.items(), key=lambda item: (-item[1], item[0]))[:10]
        ]
        mass = (
            denominator >= int(warning_cfg["mass_field_refresh_min_records"])
            and affected_rate is not None
            and affected_rate >= float(warning_cfg["mass_field_refresh_rate"])
        )
        field_concentration.append({
            "source_id": source,
            "changed_field": field,
            "semantic_change_category": category,
            "unique_retained_identities_affected": len(identities),
            "change_row_count": len(rows),
            "retained_record_denominator": denominator,
            "affected_retained_rate": affected_rate,
            "common_old_to_new_patterns": common,
            "mass_refresh_warning": mass,
        })

    def transitions(change_type: str, field: str) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        for row in changes:
            if row["change_type"] != change_type:
                continue
            grouped[(
                row["source_name"],
                display_value(field_value(row.get("old_value", ""), field)),
                display_value(field_value(row.get("new_value", ""), field)),
            )].add(row["record_identity"])
        return [
            {"source_id": source, "old_value": old, "new_value": new, "unique_record_count": len(ids)}
            for (source, old, new), ids in sorted(grouped.items(), key=lambda item: (item[0], item[0][1], item[0][2]))
        ]

    status_transitions = transitions("status_changed", "status")
    phase_transitions = transitions("capital_project_phase_changed", "capital_phase")

    date_events = []
    for row in changes:
        if row["change_type"] != "planned_date_changed":
            continue
        for field in split_fields(row):
            old_raw = field_value(row.get("old_value", ""), field)
            new_raw = field_value(row.get("new_value", ""), field)
            old_date, new_date = parse_date(old_raw), parse_date(new_raw)
            if not clean(old_raw) and clean(new_raw):
                classification, difference = "value_added", None
            elif clean(old_raw) and not clean(new_raw):
                classification, difference = "value_removed", None
            elif old_date is None or new_date is None:
                classification, difference = "unparseable", None
            else:
                difference = (new_date - old_date).days
                classification = "moved_later" if difference > 0 else "moved_earlier" if difference < 0 else "unchanged_after_normalization"
            date_events.append({
                "source_id": row["source_name"], "record_identity": row["record_identity"], "field": field,
                "old_raw": display_value(old_raw), "new_raw": display_value(new_raw),
                "old_normalized": old_date.isoformat() if old_date else None,
                "new_normalized": new_date.isoformat() if new_date else None,
                "classification": classification, "day_difference": difference,
            })
    date_events.sort(key=lambda row: (row["source_id"], row["field"], row["record_identity"]))

    cost_events = []
    cost_type_by_change = {"estimated_cost_changed": "estimated_cost", "reported_actual_cost_changed": "actual_cost"}
    for row in changes:
        if row["change_type"] not in cost_type_by_change:
            continue
        cost_type = cost_type_by_change[row["change_type"]]
        old_raw = field_value(row.get("old_value", ""), cost_type)
        new_raw = field_value(row.get("new_value", ""), cost_type)
        old_cost, new_cost = parse_cost(old_raw), parse_cost(new_raw)
        if not clean(old_raw) and clean(new_raw):
            classification, difference = "value_added", None
        elif clean(old_raw) and not clean(new_raw):
            classification, difference = "value_removed", None
        elif old_cost is None or new_cost is None:
            classification, difference = "unparseable", None
        elif old_cost == new_cost:
            classification, difference = "formatting_only_or_equivalent", Decimal(0)
        else:
            difference = new_cost - old_cost
            classification = "increase" if difference > 0 else "decrease"
        cost_events.append({
            "source_id": row["source_name"], "record_identity": row["record_identity"], "cost_type": cost_type,
            "old_raw": display_value(old_raw), "new_raw": display_value(new_raw),
            "old_normalized": str(old_cost) if old_cost is not None else None,
            "new_normalized": str(new_cost) if new_cost is not None else None,
            "classification": classification,
            "amount_difference": float(difference) if difference is not None else None,
        })
    cost_events.sort(key=lambda row: (row["source_id"], row["cost_type"], row["record_identity"]))

    alerts = []
    critical_cfg = thresholds["critical"]
    info_cfg = thresholds["informational"]
    source_audit_status = after_meta.get("source_audit_status") or {}
    if after_meta.get("collection_integrity_passed") is False:
        affected_sources = sorted(source_audit_status) or [None]
        for affected_source in affected_sources:
            details = source_audit_status.get(affected_source, {}) if affected_source else {}
            alerts.append(alert(
                "collection_integrity_failure", "critical", "collection_integrity_passed", False,
                True, int(details.get("archived_feature_count", after_count)),
                "The later snapshot has a documented collection-integrity concern. Preserve it as provenance, but do not interpret its apparent disappearances as source-publication or real-world outcomes.",
                source=affected_source, prevents_trend=True,
            ))
    for source in source_health:
        reasons = []
        if source["source_id"] in source_audit_status:
            reasons.append("collection_integrity_failure")
        drop_rate = rate(max(0, -int(source["absolute_delta"])), int(source["before_count"]))
        if (
            drop_rate is not None and drop_rate >= float(critical_cfg["source_drop_pct"])
            and -int(source["absolute_delta"]) >= int(critical_cfg["source_drop_min_records"])
        ):
            reasons.append("source_count_collapse")
            alerts.append(alert(
                "source_count_collapse", "critical", "source_drop_pct", drop_rate,
                critical_cfg["source_drop_pct"], -int(source["absolute_delta"]),
                "Published source count collapsed relative to the earlier observation; investigate source filters or availability.",
                source=source["source_id"], prevents_trend=True,
            ))
        if (
            source["disappearance_rate"] is not None
            and source["disappearance_rate"] >= float(critical_cfg["disappearance_rate"])
            and source["disappeared_records"] >= int(critical_cfg["disappearance_min_records"])
        ):
            reasons.append("critical_disappearance_rate")
            alerts.append(alert(
                "critical_disappearance_rate", "critical", "disappearance_rate", source["disappearance_rate"],
                critical_cfg["disappearance_rate"], source["disappeared_records"],
                "Most earlier records were no longer returned. This does not prove deletion or cancellation.",
                source=source["source_id"], prevents_trend=True,
            ))
        pct = source["percentage_delta"]
        if (
            pct is not None and abs(pct) >= float(warning_cfg["source_net_change_pct"])
            and abs(source["absolute_delta"]) >= int(warning_cfg["source_net_change_min_records"])
            and not reasons
        ):
            reasons.append("large_source_net_change")
            alerts.append(alert(
                "large_source_net_change", "warning", "percentage_delta", pct,
                warning_cfg["source_net_change_pct"], abs(source["absolute_delta"]),
                "Source count changed beyond the configured review threshold.", source=source["source_id"],
            ))
        if (
            source["publication_churn"] is not None
            and source["publication_churn"] >= float(warning_cfg["publication_churn_rate"])
            and source["union_size"] >= int(warning_cfg["source_net_change_min_records"])
        ):
            reasons.append("high_publication_churn")
            alerts.append(alert(
                "high_publication_churn", "warning", "publication_churn", source["publication_churn"],
                warning_cfg["publication_churn_rate"], source["new_records"] + source["disappeared_records"],
                "A large share of the source union entered or left the published result.", source=source["source_id"],
            ))
        if pct is not None and abs(pct) >= float(info_cfg["source_net_change_pct"]) and not reasons:
            reasons.append("notable_source_net_change")
            alerts.append(alert(
                "notable_source_net_change", "informational", "percentage_delta", pct,
                info_cfg["source_net_change_pct"], abs(source["absolute_delta"]),
                "Source count moved beyond the informational threshold.", source=source["source_id"],
            ))
        source["alert_reasons"] = sorted(set(reasons))

    for field in field_concentration:
        if field["mass_refresh_warning"]:
            alerts.append(alert(
                "mass_field_refresh", "warning", "affected_retained_rate", field["affected_retained_rate"],
                warning_cfg["mass_field_refresh_rate"], field["unique_retained_identities_affected"],
                f"Field {field['changed_field']} changed across most retained records, suggesting a systematic refresh.",
                source=field["source_id"],
            ))
            matching = next(item for item in source_health if item["source_id"] == field["source_id"])
            matching["alert_reasons"] = sorted(set(matching["alert_reasons"] + ["mass_field_refresh"]))

    if bool(warning_cfg.get("flag_noncanonical_interval")) and not canonical_monthly:
        alerts.append(alert(
            "noncanonical_interval", "warning", "canonical_monthly_comparison", False, True,
            (dt.date.fromisoformat(after_date) - dt.date.fromisoformat(before_date)).days,
            "This interval is a baseline follow-up or manual observation, not a canonical month-end trend point.",
            prevents_trend=True,
        ))

    severity_rank = {"informational": 1, "warning": 2, "critical": 3}
    alerts.sort(key=lambda item: (-severity_rank[item["severity"]], item["alert_code"], item.get("source_id") or "", item["metric_name"]))
    critical_sources = sorted({str(item["source_id"]) for item in alerts if item["severity"] == "critical" and item.get("source_id")})
    for source in source_health:
        source_alerts = [item["severity"] for item in alerts if item.get("source_id") == source["source_id"]]
        source["alert_level"] = "critical" if "critical" in source_alerts else "review" if "warning" in source_alerts else "healthy"

    if critical_sources:
        included = [source for source in source_health if source["source_id"] not in critical_sources]
        excluded_before = sum(source["before_count"] for source in included)
        excluded_after = sum(source["after_count"] for source in included)
        excluded_new = sum(source["new_records"] for source in included)
        excluded_disappeared = sum(source["disappeared_records"] for source in included)
        excluded_retained = sum(source["retained_records"] for source in included)
        excluded_union = sum(source["union_size"] for source in included)
        overall["excluding_critical_sources"] = {
            "excluded_source_ids": critical_sources,
            "count_before": excluded_before,
            "count_after": excluded_after,
            "absolute_net_change": excluded_after - excluded_before,
            "percentage_net_change": rate(excluded_after - excluded_before, excluded_before),
            "new_records": excluded_new,
            "disappeared_records": excluded_disappeared,
            "retained_records": excluded_retained,
            "union_size": excluded_union,
            "retention_rate": rate(excluded_retained, excluded_before),
            "disappearance_rate": rate(excluded_disappeared, excluded_before),
            "publication_churn": rate(excluded_new + excluded_disappeared, excluded_union),
            "diagnostic_note": "Diagnostic view only; it does not replace or alter the raw all-source result.",
        }
    else:
        overall["excluding_critical_sources"] = None

    comparison_status = "critical" if any(item["severity"] == "critical" for item in alerts) else "review" if any(item["severity"] == "warning" for item in alerts) else "healthy"
    trend = {
        "usable_for_raw_reporting": True,
        "usable_for_global_aggregate_trend": canonical_monthly and comparison_status != "critical",
        "usable_for_unflagged_source_trends": True,
        "exclusion_reasons": [item["alert_code"] for item in alerts if item["prevents_aggregate_trend_interpretation"]],
        "critical_sources": critical_sources,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "comparison": {
            "snapshot_from": before_date,
            "snapshot_to": after_date,
            "interval_days": (dt.date.fromisoformat(after_date) - dt.date.fromisoformat(before_date)).days,
            "comparison_month": month,
            "comparison_kind": kind,
            "canonical_monthly_comparison": canonical_monthly,
            "generated_from": [
                f"data/snapshots/{before_date}/metadata.json",
                f"data/snapshots/{after_date}/metadata.json",
                f"data/monthly_changes/{month}.csv",
                f"data/monthly_changes/{month}.json",
            ],
            "raw_change_csv": f"data/monthly_changes/{month}.csv",
            "raw_summary_json": f"data/monthly_changes/{month}.json",
        },
        "overall_status": comparison_status,
        "collection_integrity": {
            "status": after_meta.get("audit_status", "not_audited"),
            "passed": after_meta.get("collection_integrity_passed"),
            "source_status": source_audit_status,
        },
        "overall": overall,
        "source_health": sorted(source_health, key=lambda row: row["source_id"]),
        "field_change_concentration": field_concentration,
        "status_transitions": status_transitions,
        "phase_transitions": phase_transitions,
        "planned_date_changes": {"events": date_events, "summaries_by_source": summarize_numeric_events(date_events, "day_difference")},
        "cost_changes": {
            "events": cost_events,
            "summaries_by_source": summarize_numeric_events(cost_events, "amount_difference"),
            "aggregation_warning": "Amounts are source-level changes. Overlapping sources must not be summed as total Tampa investment.",
        },
        "identity_quality": identity_quality(before_rows, after_rows, changes),
        "alerts": alerts,
        "trend_eligibility": trend,
        "interpretation": "This analysis measures source-publication behavior, not verified physical development outcomes.",
    }


def analyze_paths(
    before_date: str,
    after_date: str,
    *,
    snapshots_dir: Path = SNAPSHOTS,
    changes_dir: Path = CHANGES,
    thresholds_path: Path = THRESHOLDS,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    if before_date >= after_date:
        raise ValueError("The before snapshot date must precede the after snapshot date")
    before_meta, before_rows = load_snapshot(before_date, snapshots_dir)
    after_meta, after_rows = load_snapshot(after_date, snapshots_dir)
    month = after_date[:7]
    raw_csv = changes_dir / f"{month}.csv"
    raw_json = changes_dir / f"{month}.json"
    if not raw_csv.is_file() or not raw_json.is_file():
        raise FileNotFoundError(f"Comparison artifacts for {month} are missing")
    summary = json.loads(raw_json.read_text(encoding="utf-8"))
    if summary.get("before_snapshot_date") != before_date or summary.get("after_snapshot_date") != after_date:
        raise ValueError(f"Comparison {month} covers different snapshots")
    changes = read_csv(raw_csv)
    return analyze_comparison(before_meta, after_meta, before_rows, after_rows, changes, summary, load_thresholds(thresholds_path)), changes


def write_analysis_artifacts(
    analysis: dict[str, object],
    *,
    analysis_dir: Path = ANALYSIS,
) -> dict[str, str]:
    month = analysis["comparison"]["comparison_month"]
    json_path = analysis_dir / f"{month}.json"
    sources_path = analysis_dir / f"{month}_sources.csv"
    fields_path = analysis_dir / f"{month}_fields.csv"
    transitions_path = analysis_dir / f"{month}_transitions.csv"
    atomic_json(json_path, analysis)
    source_rows = []
    for row in analysis["source_health"]:
        output = dict(row)
        output["alert_reasons"] = json.dumps(row["alert_reasons"], separators=(",", ":"))
        source_rows.append(output)
    field_rows = []
    for row in analysis["field_change_concentration"]:
        output = dict(row)
        output["common_old_to_new_patterns"] = json.dumps(row["common_old_to_new_patterns"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        field_rows.append(output)
    transition_rows = [
        dict(row, transition_type=kind)
        for kind, rows in (("status", analysis["status_transitions"]), ("phase", analysis["phase_transitions"]))
        for row in rows
    ]
    transition_rows.sort(key=lambda row: (row["transition_type"], row["source_id"], row["old_value"], row["new_value"]))
    atomic_csv(sources_path, source_rows, SOURCE_FIELDS)
    atomic_csv(fields_path, field_rows, FIELD_FIELDS)
    atomic_csv(transitions_path, transition_rows, TRANSITION_FIELDS)
    def path_text(path: Path) -> str:
        return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)

    return {
        "analysis_json": path_text(json_path),
        "sources_csv": path_text(sources_path),
        "fields_csv": path_text(fields_path),
        "transitions_csv": path_text(transitions_path),
    }


def update_index(index_path: Path = CHANGES / "index.json", analysis_dir: Path = ANALYSIS) -> None:
    if not index_path.is_file():
        return
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for item in index.get("comparisons", []):
        month = item["comparison_month"]
        path = analysis_dir / f"{month}.json"
        if not path.is_file():
            continue
        analysis = json.loads(path.read_text(encoding="utf-8"))
        severities = Counter(alert["severity"] for alert in analysis["alerts"])
        item.update({
            "analysis_json": f"data/monthly_changes/analysis/{month}.json",
            "analysis_status": analysis["overall_status"],
            "critical_alert_count": severities["critical"],
            "warning_alert_count": severities["warning"],
            "canonical_monthly_comparison": analysis["comparison"]["canonical_monthly_comparison"],
            "usable_for_global_aggregate_trend": analysis["trend_eligibility"]["usable_for_global_aggregate_trend"],
            "dashboard_page": f"reports/dashboard/comparisons/{month}.html",
        })
    atomic_json(index_path, index)
