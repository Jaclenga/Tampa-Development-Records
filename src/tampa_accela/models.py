"""Typed models shared by collection, normalization, and output code."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Mapping


PROSPECTIVE_MONITORING_START = date(2026, 8, 1)


def _calendar_date(value: object) -> str | None:
    """Return the ISO calendar date encoded by an ISO date/timestamp.

    Collector timestamps are UTC, and observation dates deliberately retain
    that UTC calendar boundary so they match the raw archive directory.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _primary_event(values: Mapping[str, object]) -> tuple[str | None, str | None]:
    """Select one documented cohort event without discarding lifecycle dates."""
    module = str(values.get("source_module") or "").strip().lower()
    if module in {"building", "rightofway"}:
        candidates = (
            ("issued_date", "permit_issued"),
            ("filed_date", "application_filed"),
            ("opened_date", "application_opened"),
            ("completed_date", "administrative_completed"),
            ("closed_date", "administrative_closed"),
        )
    else:
        candidates = (
            ("filed_date", "application_filed"),
            ("opened_date", "application_opened"),
            ("issued_date", "record_issued"),
            ("completed_date", "administrative_completed"),
            ("closed_date", "administrative_closed"),
        )
    for field_name, event_type in candidates:
        candidate = _calendar_date(values.get(field_name))
        if candidate:
            return candidate, event_type
    return _calendar_date(values.get("event_date")), str(values.get("event_date_type") or "").strip() or None


def temporalize_row(values: Mapping[str, object]) -> dict[str, Any]:
    """Add auditable event-versus-observation semantics to an Accela row."""
    result = dict(values)
    event_date, event_type = _primary_event(result)
    snapshot_date = _calendar_date(result.get("snapshot_date") or result.get("retrieved_at"))
    first_observed = _calendar_date(result.get("first_observed_date")) or snapshot_date
    last_observed = _calendar_date(result.get("last_observed_date")) or snapshot_date
    result.update({
        "event_date": event_date,
        "event_date_type": event_type,
        "first_observed_date": first_observed,
        "snapshot_date": snapshot_date,
        "last_observed_date": last_observed,
    })
    if event_date is None:
        result["historical_reconstruction"] = ""
        result["temporal_evidence"] = "unknown"
    elif date.fromisoformat(event_date) < PROSPECTIVE_MONITORING_START:
        result["historical_reconstruction"] = "1"
        result["temporal_evidence"] = "retrospective_source_record"
    else:
        result["historical_reconstruction"] = "0"
        result["temporal_evidence"] = "prospective_snapshot"
    return result


def temporalize_inspection_row(values: Mapping[str, object]) -> dict[str, Any]:
    """Add event/observation semantics to one dated inspection observation."""
    result = dict(values)
    candidates = (
        ("result_date", "inspection_result"),
        ("completed_date", "inspection_completed"),
        ("scheduled_date", "inspection_scheduled"),
    )
    event_date = None
    event_type = None
    for field_name, candidate_type in candidates:
        if candidate := _calendar_date(result.get(field_name)):
            event_date = candidate
            event_type = candidate_type
            break
    snapshot_date = _calendar_date(result.get("snapshot_date") or result.get("retrieved_at"))
    first_observed = _calendar_date(result.get("first_observed_date")) or snapshot_date
    last_observed = _calendar_date(result.get("last_observed_date")) or snapshot_date
    result.update({
        "event_date": event_date,
        "event_date_type": event_type,
        "first_observed_date": first_observed,
        "snapshot_date": snapshot_date,
        "last_observed_date": last_observed,
    })
    if event_date is None:
        result["historical_reconstruction"] = ""
        result["temporal_evidence"] = "unknown"
    elif date.fromisoformat(event_date) < PROSPECTIVE_MONITORING_START:
        result["historical_reconstruction"] = "1"
        result["temporal_evidence"] = "retrospective_event_history"
    else:
        result["historical_reconstruction"] = "0"
        result["temporal_evidence"] = "prospective_snapshot"
    return result


@dataclass(frozen=True)
class SearchQuery:
    module: str
    from_date: date | None = None
    to_date: date | None = None
    record_number: str | None = None
    updated_since: date | None = None

    def validate(self) -> None:
        if self.updated_since is not None:
            raise ValueError(
                "Tampa's verified public ACA form does not expose a last-updated filter; "
                "--updated-since cannot be implemented without mislabeling opened dates"
            )
        if self.record_number:
            return
        if self.from_date is None or self.to_date is None:
            raise ValueError("A bounded search requires both --from-date and --to-date")
        if self.from_date > self.to_date:
            raise ValueError("--from-date must be on or before --to-date")


NORMALIZED_FIELDS = [
    "source",
    "source_system",
    "source_module",
    "record_id",
    "record_number",
    "record_type",
    "record_subtype",
    "record_category",
    "record_status",
    "opened_date",
    "filed_date",
    "issued_date",
    "expiration_date",
    "completed_date",
    "closed_date",
    "updated_date",
    "event_date",
    "event_date_type",
    "first_observed_date",
    "snapshot_date",
    "last_observed_date",
    "historical_reconstruction",
    "temporal_evidence",
    "description",
    "work_description",
    "address",
    "street_number",
    "street_name",
    "city",
    "state",
    "postal_code",
    "parcel_id",
    "property_id",
    "valuation",
    "estimated_cost",
    "owner_name",
    "applicant_name",
    "contractor_name",
    "contractor_license",
    "parent_record_number",
    "related_record_numbers",
    "latitude",
    "longitude",
    "source_url",
    "retrieved_at",
    "raw_source_file",
]


@dataclass
class NormalizedRecord:
    source: str = "City of Tampa"
    source_system: str = "Accela Citizen Access"
    source_module: str | None = None
    record_id: str | None = None
    record_number: str | None = None
    record_type: str | None = None
    record_subtype: str | None = None
    record_category: str | None = None
    record_status: str | None = None
    opened_date: str | None = None
    filed_date: str | None = None
    issued_date: str | None = None
    expiration_date: str | None = None
    completed_date: str | None = None
    closed_date: str | None = None
    updated_date: str | None = None
    event_date: str | None = None
    event_date_type: str | None = None
    first_observed_date: str | None = None
    snapshot_date: str | None = None
    last_observed_date: str | None = None
    historical_reconstruction: str | None = None
    temporal_evidence: str | None = None
    description: str | None = None
    work_description: str | None = None
    address: str | None = None
    street_number: str | None = None
    street_name: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    parcel_id: str | None = None
    property_id: str | None = None
    valuation: str | None = None
    estimated_cost: str | None = None
    owner_name: str | None = None
    applicant_name: str | None = None
    contractor_name: str | None = None
    contractor_license: str | None = None
    parent_record_number: str | None = None
    related_record_numbers: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    raw_source_file: str | None = None

    def as_row(self) -> dict[str, Any]:
        values = temporalize_row(asdict(self))
        return {field: values.get(field) for field in NORMALIZED_FIELDS}


INSPECTION_FIELDS = [
    "record_id",
    "record_number",
    "inspection_id",
    "source_inspection_id",
    "inspection_type",
    "inspection_status",
    "scheduled_date",
    "completed_date",
    "result",
    "result_date",
    "event_date",
    "event_date_type",
    "first_observed_date",
    "snapshot_date",
    "last_observed_date",
    "historical_reconstruction",
    "temporal_evidence",
    "inspector_name",
    "source_url",
    "retrieved_at",
    "raw_source_file",
]


@dataclass
class Inspection:
    record_id: str | None = None
    record_number: str | None = None
    inspection_id: str | None = None
    source_inspection_id: str | None = None
    inspection_type: str | None = None
    inspection_status: str | None = None
    scheduled_date: str | None = None
    completed_date: str | None = None
    result: str | None = None
    result_date: str | None = None
    event_date: str | None = None
    event_date_type: str | None = None
    first_observed_date: str | None = None
    snapshot_date: str | None = None
    last_observed_date: str | None = None
    historical_reconstruction: str | None = None
    temporal_evidence: str | None = None
    inspector_name: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    raw_source_file: str | None = None

    def as_row(self) -> dict[str, Any]:
        values = temporalize_inspection_row(asdict(self))
        return {name: values.get(name) for name in INSPECTION_FIELDS}


@dataclass
class CollectionResult:
    records: list[NormalizedRecord] = field(default_factory=list)
    inspections: list[Inspection] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    pages: int = 0
    truncated: bool = False
    checkpoint_path: str | None = None
