"""Typed models shared by collection, normalization, and output code."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


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
        values = asdict(self)
        return {field: values.get(field) for field in NORMALIZED_FIELDS}


INSPECTION_FIELDS = [
    "record_id",
    "record_number",
    "inspection_id",
    "inspection_type",
    "inspection_status",
    "scheduled_date",
    "completed_date",
    "result",
    "result_date",
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
    inspection_type: str | None = None
    inspection_status: str | None = None
    scheduled_date: str | None = None
    completed_date: str | None = None
    result: str | None = None
    result_date: str | None = None
    inspector_name: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    raw_source_file: str | None = None

    def as_row(self) -> dict[str, Any]:
        values = asdict(self)
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
