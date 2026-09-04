#!/usr/bin/env python3
"""Build conservative ground-truth scaffolding from normalized Tampa records.

This module never treats a permit, footprint, assessment year, or capital
closeout label as proof of completed physical work.  It creates the relational
tables needed to add Accela inspections/COs and independent review later.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


TRUTH_VALUES = {"yes", "no", "unknown", "not_applicable"}
EVENT_TYPES = {
    "source_record_observed", "application_filed", "hearing_scheduled",
    "permit_issued", "permit_issued_reported", "permit_revision_reported",
    "application_withdrawn", "application_denied", "permit_expired",
    "permit_cancelled", "permit_closed", "capital_phase_reported",
    "planned_start_reported", "planned_end_reported", "actual_start_reported",
    "actual_end_reported", "construction_started_reported",
    "project_closeout_reported", "inspection_passed", "inspection_failed",
    "final_inspection_passed", "temporary_co_issued",
    "certificate_of_occupancy_issued", "construction_completion_reported",
}

FIELD_DEFINITIONS = {
    "physical_work_started": "Whether qualifying evidence establishes that physical work started.",
    "physical_work_completed": "Whether qualifying evidence establishes that physical work completed.",
    "certificate_of_occupancy_issued": "Whether an official certificate-of-occupancy event is present.",
    "final_inspection_passed": "Whether an official passed-final-inspection event is present.",
    "project_cancelled": "Whether an official cancelled, withdrawn, denied, or expired status is present.",
    "completion_date": "Date of the qualifying completion event, when one exists.",
    "verification_grade": "Highest evidence-hierarchy grade supported by current evidence.",
    "verification_basis": "Machine-readable explanation for the evidence grade.",
    "verification_source": "Source endpoint or evidence record used for the truth assessment.",
    "verification_date": "Date on which the cited evidence was assessed or retrieved.",
    "verification_method": "Method used to turn evidence into the truth-status fields.",
    "building_year_supporting_evidence": "Whether a compatible building-year inference exists as non-dispositive support.",
    "human_review_status": "Status of required human ground-truth review.",
    "master_project_id": "Stable provisional identifier for a real-world master-project entity.",
    "activity_count": "Number of activities currently assigned to the master project.",
    "entity_resolution_status": "Whether master-project grouping is provisional or reviewed.",
    "relationship_type": "Semantic relationship between an activity and its master project.",
    "candidate_id": "Stable identifier for a proposed cross-activity project match.",
    "activity_id_a": "First activity in a candidate master-project pair.",
    "activity_id_b": "Second activity in a candidate master-project pair.",
    "candidate_reasons": "Semicolon-delimited deterministic signals proposing a match.",
    "candidate_confidence": "Rule-based priority tier for candidate review.",
    "merge_applied": "Whether the candidate pair was actually merged.",
    "event_id": "Stable identifier for one dated or undated development event.",
    "event_type": "Normalized development-event category.",
    "event_date": "Date reported for the event.",
    "source_status_raw": "Unmodified status text reported by the contributing source record.",
    "normalized_stage": "Activity stage produced by the release normalization rules.",
    "source_field": "Source field or fields supporting the normalized event.",
    "event_value": "Source value represented by the normalized event.",
    "interpretation_note": "Conservative note limiting interpretation of the event.",
    "amount_id": "Stable identifier for one reported monetary amount.",
    "amount_usd": "Reported nominal-dollar amount; not a harmonized investment total.",
    "amount_type": "Meaning of the reported amount.",
    "price_year": "Nominal price year inferred from the associated record date, when available.",
    "public_or_private": "Financing/owner sector supported by the source.",
    "is_estimate": "Whether the amount is explicitly an estimate.",
    "is_final": "Whether the source establishes that the amount is final.",
    "building_match_audit_id": "Stable identifier for one building-match audit row.",
    "normalized_address_agreement": "Whether normalized activity and footprint addresses exactly agree.",
    "multiple_matched_buildings": "Whether the activity has more than one matched footprint.",
    "geometry_check": "Spatial rule used by the building match.",
    "historical_imagery_checked": "Whether dated historical imagery was reviewed.",
    "new_footprint_vs_addition": "Reviewer judgment distinguishing a new footprint from an addition.",
    "human_match_correct": "Human judgment of building-match correctness.",
    "evidence_url": "Public URL supporting a review judgment.",
    "exact_address_agreement_count": "Rows in the stratum with exact normalized-address agreement.",
    "multiple_building_activity_count": "Rows in the stratum attached to a multi-match activity.",
    "human_reviewed_count": "Rows in the stratum with a completed human match judgment.",
    "empirical_precision": "Human-reviewed correct matches divided by reviewed matches.",
    "reviewer_2_id": "Identifier for an independent second reviewer.",
    "reviewer_2_one_activity_one_development": "Second-reviewer judgment of activity-to-development uniqueness.",
    "reviewer_2_building_match_correct": "Second-reviewer judgment of building-match correctness.",
    "reviewer_2_completion_classification": "Second-reviewer judgment of completion classification.",
    "reviewer_2_notes": "Second reviewer rationale and evidence notes.",
    "reviewer_2_reviewed_at_utc": "UTC timestamp of the independent second review.",
}


def metadata_for(field: str):
    if field not in FIELD_DEFINITIONS:
        return None
    truth = field in {"physical_work_started", "physical_work_completed", "certificate_of_occupancy_issued", "final_inspection_passed", "project_cancelled"}
    reviewer = field.startswith("reviewer_2") or field in {"human_match_correct", "historical_imagery_checked", "new_footprint_vs_addition"}
    valid = "yes; no; unknown; not_applicable" if truth else "Protocol- or source-defined."
    if field == "verification_grade": valid = "A1; A2; A3; B1; B2; C; D; P; X; U"
    if field == "event_type": valid = "; ".join(sorted(EVENT_TYPES))
    if field == "merge_applied": valid = "yes; no"
    null = "Blank means unavailable or not yet reviewed; unknown is represented explicitly where required."
    return (FIELD_DEFINITIONS[field], "categorical text" if truth or reviewer else "text", "", null,
            "reviewer-entered" if reviewer else "derived/source evidence", "See docs/methodology/GROUND_TRUTH_METHODOLOGY.md and scripts/ground_truth.py.", valid,
            "Do not interpret absence or unknown as no; this field is not proof beyond its cited evidence.")


def token(value: str, length: int = 16) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_address(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", clean(value).upper())
    replacements = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "BOULEVARD": "BLVD", "DRIVE": "DR"}
    return " ".join(replacements.get(part, part) for part in text.split())


def arcgis_timestamp(value: object) -> str:
    """Normalize an ArcGIS millisecond or ISO timestamp without inventing one."""
    if value in (None, ""):
        return ""
    text = clean(value)
    try:
        number = float(text)
        if number > 10_000_000_000:
            stamp = dt.datetime.fromtimestamp(number / 1000, tz=dt.timezone.utc)
            return stamp.replace(microsecond=0).isoformat()
    except ValueError:
        pass
    try:
        stamp = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return stamp.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        return ""


def source_date(value: object) -> str:
    timestamp = arcgis_timestamp(value)
    if timestamp:
        return timestamp[:10]
    text = clean(value)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def evidence_for(activity: dict) -> tuple[str, str, str, str]:
    """Return grade, basis, started, cancelled without inventing completion."""
    status = clean(activity.get("status")).lower()
    activity_class = clean(activity.get("activity_class"))
    stage = clean(activity.get("activity_stage"))
    if any(word in status for word in ("cancel", "withdraw", "denied", "expired")):
        return "X", "inactive_official_status", "unknown", "yes"
    if "construction" in status or stage == "construction_or_inspection":
        return "C", "official_construction_or_inspection_status", "yes", "unknown"
    if activity_class in {"planning_application", "historic_preservation_application"}:
        return "P", "planning_application_only", "not_applicable", "unknown"
    if stage == "permit_or_funding_approved" or "issued" in status or "approved" in status:
        return "D", "permit_or_funding_approved_only", "unknown", "unknown"
    return "U", "insufficient_completion_evidence", "unknown", "unknown"


def build_truth(activities: list[dict]) -> list[dict]:
    rows = []
    for a in activities:
        grade, basis, started, cancelled = evidence_for(a)
        planning = a.get("activity_class") in {"planning_application", "historic_preservation_application"}
        na = "not_applicable" if planning else "unknown"
        rows.append({
            "activity_id": a["activity_id"],
            "physical_work_started": started,
            "physical_work_completed": na,
            "certificate_of_occupancy_issued": na,
            "final_inspection_passed": na,
            "project_cancelled": cancelled,
            "completion_date": "",
            "verification_grade": grade,
            "verification_basis": basis,
            "verification_source": clean(a.get("source_endpoint")),
            "verification_date": clean(a.get("retrieved_at_utc"))[:10],
            "verification_method": "deterministic_official_status_classification",
            "building_year_supporting_evidence": "yes" if str(a.get("realization_basis", "")).startswith("permit_plus_current_footprint_year_built") else "no",
            "human_review_status": "pending",
        })
    return rows


def build_projects(activities: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    projects, links = [], []
    for a in activities:
        mid = f"mp-{token(a['activity_id'])}"
        projects.append({
            "master_project_id": mid, "project_name": clean(a.get("project_name")),
            "address": clean(a.get("address")), "activity_count": "1",
            "entity_resolution_status": "provisional_singleton",
        })
        links.append({
            "master_project_id": mid, "activity_id": a["activity_id"],
            "relationship_type": "provisional_singleton",
            "match_method": "no_safe_cross_activity_merge",
            "match_confidence": "unknown", "review_status": "needs_review",
        })

    # Candidate pairs are proposals only; they never alter master_project_id.
    by_address: dict[str, list[dict]] = defaultdict(list)
    by_folio: dict[str, list[dict]] = defaultdict(list)
    for a in activities:
        address = normalize_address(a.get("address"))
        if address:
            by_address[address].append(a)
        for folio in clean(a.get("matched_folios")).split(";"):
            if folio:
                by_folio[folio].append(a)
    proposed: dict[tuple[str, str], set[str]] = defaultdict(set)
    for label, groups in (("exact_normalized_address", by_address), ("shared_city_building_folio", by_folio)):
        for rows in groups.values():
            if 1 < len(rows) <= 25:
                ids = sorted({r["activity_id"] for r in rows})
                for i, left in enumerate(ids):
                    for right in ids[i + 1:]:
                        proposed[(left, right)].add(label)
    candidates = []
    for (left, right), reasons in sorted(proposed.items()):
        candidates.append({
            "candidate_id": f"cand-{token(left + '|' + right)}",
            "activity_id_a": left, "activity_id_b": right,
            "candidate_reasons": ";".join(sorted(reasons)),
            "candidate_confidence": "medium" if len(reasons) > 1 else "low",
            "review_status": "pending_human_review", "merge_applied": "no",
        })
    return projects, links, candidates


def build_events(
    activities: list[dict], links: list[dict], source_records: list[dict] | None = None,
) -> list[dict]:
    """Build source-observation and explicitly dated lifecycle events.

    One observation row is retained for every source feature.  Additional
    lifecycle rows are emitted only when a source exposes an explicit date or
    an explicit status/phase label.  Completion/occupancy events are reserved
    for future official inspection or certificate data and are never inferred
    from permit issuance, footprints, planned dates, or capital closeout.
    """
    master = {r["activity_id"]: r["master_project_id"] for r in links}
    by_activity = {r["activity_id"]: r for r in activities}
    rows = []
    if source_records is None:
        source_records = [{
            "source_record_key": "", "activity_id": a["activity_id"],
            "source_name": clean(a.get("source_memberships")),
            "source_record_id": clean(a.get("source_record_id")),
            "source_endpoint": clean(a.get("source_endpoint")),
            "retrieved_at_utc": clean(a.get("retrieved_at_utc")),
            "properties_json": "{}",
        } for a in activities]

    def append_event(
        source: dict, activity: dict, event_type: str, event_date: str,
        source_field: str, event_value: str, evidence_strength: str,
        is_inferred: str, note: str,
    ) -> None:
        observed = clean(source.get("retrieved_at_utc"))
        seed_parts = [
            clean(source.get("source_record_key")),
            clean(source.get("source_name")), clean(source.get("source_record_id")),
            event_type, event_date, event_value,
        ]
        if event_type == "source_record_observed":
            seed_parts.append(observed)
        rows.append({
            "event_id": f"evt-{token('|'.join(seed_parts))}",
            "activity_id": activity["activity_id"],
            "master_project_id": master[activity["activity_id"]],
            "source_record_key": clean(source.get("source_record_key")),
            "source_record_id": clean(source.get("source_record_id")),
            "event_type": event_type,
            "event_date": event_date,
            "source_status_raw": clean(activity.get("status")),
            "normalized_stage": clean(activity.get("activity_stage")),
            "evidence_url": clean(activity.get("source_url")) or clean(source.get("source_endpoint")),
            "source_name": clean(source.get("source_name")),
            "observed_at_utc": observed,
            "evidence_strength": evidence_strength,
            "is_inferred": is_inferred,
            "source_field": source_field,
            "event_value": event_value,
            "interpretation_note": note,
        })

    for source in source_records:
        activity = by_activity[source["activity_id"]]
        try:
            props = json.loads(source.get("properties_json") or "{}")
        except json.JSONDecodeError:
            props = {}
        source_name = clean(source.get("source_name"))
        status = clean(
            props.get("PROJECTSTATUS") or props.get("APPLICATION_STATUS")
            or props.get("APPSTATUS") or props.get("status") or activity.get("status")
        )
        activity_for_event = dict(activity)
        activity_for_event["status"] = status
        append_event(
            source, activity_for_event, "source_record_observed", "", "source feature",
            status or clean(source.get("source_record_id")), "official_source_observation",
            "no", "Records the source state at retrieval; it is not a lifecycle outcome by itself.",
        )

        created = source_date(props.get("OPENED_DATE") or props.get("CREATEDDATE") or props.get("CreationDate"))
        if created and source_name in {
            "construction_inspections", "single_family_permits",
            "development_coordination", "historic_preservation",
        }:
            append_event(
                source, activity_for_event, "application_filed", created,
                "OPENED_DATE/CREATEDDATE", created, "official_reported_date", "no",
                "Administrative filing/opened date; it does not establish approval or construction.",
            )

        if source_name == "single_family_permits":
            task = clean(props.get("TASK"))
            task_status = clean(props.get("TASK_STATUS"))
            task_date = source_date(props.get("TASK_STATUS_DATE"))
            if task.lower() == "issuance" and task_status.lower() == "issued" and task_date:
                append_event(
                    source, activity_for_event, "permit_issued", task_date,
                    "TASK;TASK_STATUS;TASK_STATUS_DATE", task_status,
                    "official_lifecycle_record", "no",
                    "Dated issuance workflow event; issuance does not establish that physical work started.",
                )
        elif source_name == "construction_inspections":
            if status.lower() == "issued":
                append_event(
                    source, activity_for_event, "permit_issued_reported", "", "PROJECTSTATUS",
                    status, "official_source_observation", "no",
                    "Source reports Issued but does not expose a dedicated issuance date in this layer.",
                )
            elif status.lower() == "revision":
                append_event(
                    source, activity_for_event, "permit_revision_reported", "", "PROJECTSTATUS",
                    status, "official_source_observation", "no",
                    "Source reports Revision; this is not a new permit or evidence of construction.",
                )

        if source_name in {"development_coordination", "historic_preservation"}:
            hearing_value = props.get("TENTATIVEHEARING") or props.get("TEANTATIVEHEARING")
            hearing_date = source_date(hearing_value)
            if hearing_date:
                append_event(
                    source, activity_for_event, "hearing_scheduled", hearing_date,
                    "TENTATIVEHEARING/TEANTATIVEHEARING", clean(hearing_value),
                    "official_reported_date", "no",
                    "Tentative hearing date; it does not establish that the hearing occurred or a decision was issued.",
                )
            lowered = status.lower()
            if "withdraw" in lowered:
                append_event(source, activity_for_event, "application_withdrawn", "", "APPSTATUS", status,
                             "official_source_observation", "no", "Status reported at retrieval; exact withdrawal date is unavailable.")
            if "denied" in lowered:
                append_event(source, activity_for_event, "application_denied", "", "APPSTATUS", status,
                             "official_source_observation", "no", "Status reported at retrieval; exact decision date is unavailable.")

        if source_name.startswith("capital_"):
            phase = clean(props.get("projphase"))
            if phase or status:
                append_event(
                    source, activity_for_event, "capital_phase_reported", "", "projphase;status",
                    "; ".join(value for value in (phase, status) if value),
                    "official_source_observation", "no",
                    "Current administrative phase/status observed at retrieval; it is not a physical-completion finding.",
                )
            for event_type, field, note in (
                ("planned_start_reported", "planstart", "Planned date; it is not evidence that work started."),
                ("planned_end_reported", "planend", "Planned date; it is not evidence that work finished."),
                ("actual_start_reported", "actstart", "Source-reported actual start; not independently verified."),
                ("actual_end_reported", "actend", "Source-reported actual end; not proof of final inspection or occupancy."),
            ):
                value = source_date(props.get(field))
                if value:
                    append_event(source, activity_for_event, event_type, value, field, value,
                                 "official_reported_date", "no", note)
            lowered = (phase + " " + status).lower()
            if "construction" in lowered:
                append_event(
                    source, activity_for_event, "construction_started_reported", "", "projphase;status",
                    "; ".join(value for value in (phase, status) if value),
                    "official_source_observation", "yes",
                    "Construction activity is inferred from the reported phase/status; an exact start date is not established.",
                )
            if "closeout" in lowered:
                append_event(
                    source, activity_for_event, "project_closeout_reported", "", "projphase;status",
                    "; ".join(value for value in (phase, status) if value),
                    "official_source_observation", "no",
                    "Administrative closeout does not establish physical completion, final inspection, or occupancy.",
                )
    return rows


def build_amounts(activities: list[dict]) -> list[dict]:
    rows = []
    for a in activities:
        for field, kind, estimate in (
            ("estimated_cost_usd", "city_capital_project_estimated_cost", "yes"),
            ("actual_cost_usd", "city_capital_project_reported_actual_cost", "no"),
        ):
            raw = clean(a.get(field))
            try:
                amount = float(raw)
            except ValueError:
                continue
            if amount <= 0:
                continue
            date = clean(a.get("status_date")) or clean(a.get("record_created_date"))
            rows.append({
                "amount_id": f"amt-{token(a['activity_id'] + '|' + field)}", "activity_id": a["activity_id"],
                "amount_usd": f"{amount:.2f}", "amount_type": kind,
                "price_year": date[:4] if re.match(r"^20\d{2}", date) else "",
                "public_or_private": "public", "source": clean(a.get("source_endpoint")),
                "is_estimate": estimate, "is_final": "unknown",
            })
    return rows


def build_match_audit(activities: list[dict], matches: list[dict]) -> tuple[list[dict], list[dict]]:
    by_id = {a["activity_id"]: a for a in activities}
    counts = Counter(m["activity_id"] for m in matches)
    audit = []
    for m in matches:
        a = by_id[m["activity_id"]]
        address_agree = "yes" if normalize_address(a.get("address")) and normalize_address(a.get("address")) == normalize_address(m.get("building_address")) else "no"
        audit.append({
            "building_match_audit_id": f"bma-{token(m['activity_id'] + '|' + clean(m.get('location_id')) + '|' + clean(m.get('building_object_id')))}",
            "activity_id": m["activity_id"], "location_id": clean(m.get("location_id")),
            "building_object_id": clean(m.get("building_object_id")), "match_method": clean(m.get("match_method")),
            "match_confidence": clean(m.get("match_confidence")), "match_distance_m": clean(m.get("match_distance_m")),
            "normalized_address_agreement": address_agree,
            "multiple_matched_buildings": "yes" if counts[m["activity_id"]] > 1 else "no",
            "geometry_check": "point_in_footprint" if m.get("match_method") == "point_in_building_footprint" else "proximity_or_address_rule",
            "historical_imagery_checked": "unknown", "new_footprint_vs_addition": "unknown",
            "human_match_correct": "unknown", "reviewer_id": "", "reviewed_at_utc": "", "evidence_url": "", "review_notes": "",
        })
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in audit:
        grouped[(row["match_method"], row["match_confidence"])].append(row)
    diagnostics = []
    for (method, confidence), rows in sorted(grouped.items()):
        diagnostics.append({
            "match_method": method, "match_confidence": confidence, "match_count": len(rows),
            "exact_address_agreement_count": sum(r["normalized_address_agreement"] == "yes" for r in rows),
            "multiple_building_activity_count": sum(r["multiple_matched_buildings"] == "yes" for r in rows),
            "human_reviewed_count": "0", "empirical_precision": "",
        })
    return audit, diagnostics


def build_all(
    processed: Path, activities: list[dict], matches: list[dict], sample: list[dict],
    source_records: list[dict] | None = None,
) -> dict[str, int]:
    truth = build_truth(activities)
    projects, links, candidates = build_projects(activities)
    events = build_events(activities, links, source_records)
    amounts = build_amounts(activities)
    audit, diagnostics = build_match_audit(activities, matches)
    tables = {
        "activity_truth_status.csv": (truth, list(truth[0])),
        "master_projects.csv": (projects, list(projects[0])),
        "master_project_activity_links.csv": (links, list(links[0])),
        "master_project_candidates.csv": (candidates, ["candidate_id", "activity_id_a", "activity_id_b", "candidate_reasons", "candidate_confidence", "review_status", "merge_applied"]),
        "development_events.csv": (events, [
            "event_id", "activity_id", "master_project_id", "source_record_key",
            "source_record_id", "event_type", "event_date", "source_status_raw",
            "normalized_stage", "evidence_url", "source_name", "observed_at_utc",
            "evidence_strength", "is_inferred", "source_field", "event_value",
            "interpretation_note",
        ]),
        "investment_amounts.csv": (amounts, ["amount_id", "activity_id", "amount_usd", "amount_type", "price_year", "public_or_private", "source", "is_estimate", "is_final"]),
        "building_match_audit.csv": (audit, list(audit[0]) if audit else []),
        "building_match_diagnostics.csv": (diagnostics, list(diagnostics[0]) if diagnostics else []),
    }
    for name, (rows, columns) in tables.items():
        write_csv(processed / name, rows, columns)
    return {name: len(rows) for name, (rows, _) in tables.items()}
