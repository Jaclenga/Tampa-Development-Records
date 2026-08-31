"""Deterministic normalization for publicly displayed Tampa ACA fields."""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import hashlib
import re
from typing import Mapping

from .models import Inspection, NormalizedRecord


SPACE = re.compile(r"\s+")
POSTAL = re.compile(r"\b\d{5}(?:-\d{4})?\b")


def clean(value: object) -> str | None:
    if value is None:
        return None
    text = SPACE.sub(" ", str(value)).strip(" \t\r\n,*")
    return text or None


def iso_date(value: object) -> str | None:
    text = clean(value)
    if text is None:
        return None
    text = text.split(" ", 1)[0]
    for pattern in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return None


def money(value: object) -> str | None:
    text = clean(value)
    if text is None:
        return None
    candidate = re.sub(r"[^0-9.\-]", "", text)
    if candidate in {"", "-", ".", "-."}:
        return None
    try:
        amount = decimal.Decimal(candidate)
    except decimal.InvalidOperation:
        return None
    return format(amount.quantize(decimal.Decimal("0.01")), "f")


def stable_record_id(
    module: str,
    record_number: str | None,
    cap_id_parts: tuple[str, str, str] | None = None,
) -> str:
    if cap_id_parts and all(clean(part) for part in cap_id_parts):
        identity = "|".join(("TAMPA", module.upper(), *(part.upper() for part in cap_id_parts)))
    elif clean(record_number):
        identity = "|".join(("TAMPA", module.upper(), "PUBLIC_NUMBER", clean(record_number).upper()))
    else:
        raise ValueError("A stable Accela record ID requires capID1/2/3 or a record number")
    return "acc-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def address_parts(address: object) -> dict[str, str | None]:
    text = clean(address)
    if text is None:
        return {
            "address": None,
            "street_number": None,
            "street_name": None,
            "city": None,
            "state": None,
            "postal_code": None,
        }
    first = text.split(",", 1)[0].strip()
    match = re.match(r"^(\d+[A-Za-z]?(?:-\d+)?)\s+(.+)$", first)
    postal = POSTAL.search(text)
    return {
        "address": text,
        "street_number": match.group(1) if match else None,
        "street_name": clean(match.group(2)) if match else first,
        "city": None,
        "state": None,
        "postal_code": postal.group(0) if postal else None,
    }


def canonical_headers(row: Mapping[str, object]) -> dict[str, object]:
    return {SPACE.sub(" ", key).strip().lower(): value for key, value in row.items()}


def normalize_search_row(
    row: Mapping[str, object],
    *,
    module: str,
    retrieved_at: str,
    raw_source_file: str,
) -> NormalizedRecord:
    values = canonical_headers(row)
    record_number = clean(values.get("record number") or values.get("record_number"))
    cap_parts_value = values.get("_cap_id_parts")
    cap_parts = tuple(cap_parts_value) if isinstance(cap_parts_value, (list, tuple)) else None
    location = address_parts(values.get("address"))
    return NormalizedRecord(
        source_module=module,
        record_id=stable_record_id(module, record_number, cap_parts),
        record_number=record_number,
        record_type=clean(values.get("record type") or values.get("record_type")),
        record_status=clean(values.get("status") or values.get("record status")),
        opened_date=iso_date(values.get("date") or values.get("opened date")),
        expiration_date=iso_date(values.get("expiration date")),
        description=clean(values.get("short notes") or values.get("description")),
        source_url=clean(values.get("_source_url")),
        retrieved_at=retrieved_at,
        raw_source_file=raw_source_file,
        **location,
    )


def apply_detail(record: NormalizedRecord, detail: Mapping[str, object]) -> NormalizedRecord:
    """Return a copy enriched only with explicitly labeled public detail values."""
    values = canonical_headers(detail)
    location = address_parts(values.get("address") or record.address)
    replacements = {
        "record_number": clean(values.get("record number")) or record.record_number,
        "record_type": clean(values.get("record type")) or record.record_type,
        "record_status": clean(values.get("record status")) or record.record_status,
        "record_category": clean(values.get("record category") or values.get("category")) or record.record_category,
        "record_subtype": clean(values.get("record subtype") or values.get("subtype")) or record.record_subtype,
        "filed_date": iso_date(values.get("filed date") or values.get("application date")) or record.filed_date,
        "issued_date": iso_date(values.get("issued date") or values.get("issue date")) or record.issued_date,
        "expiration_date": iso_date(values.get("expiration date")) or record.expiration_date,
        "completed_date": iso_date(values.get("completed date") or values.get("completion date")) or record.completed_date,
        "closed_date": iso_date(values.get("closed date")) or record.closed_date,
        "updated_date": iso_date(values.get("updated date") or values.get("last updated")) or record.updated_date,
        "description": clean(values.get("project description")) or record.description,
        "work_description": clean(values.get("work description")),
        "parcel_id": clean(values.get("parcel number")),
        "property_id": clean(values.get("property id")),
        "valuation": money(values.get("job value") or values.get("valuation")),
        "estimated_cost": money(values.get("estimated cost")),
        "owner_name": clean(values.get("owner")),
        "applicant_name": clean(values.get("applicant")),
        "contractor_name": clean(values.get("licensed professional") or values.get("contractor")),
        "contractor_license": clean(values.get("contractor license")),
        "parent_record_number": clean(values.get("parent record number")),
        "related_record_numbers": clean(values.get("related record numbers")),
        **location,
    }
    return dataclasses.replace(record, **{key: value for key, value in replacements.items() if value is not None})


def deduplicate_records(records: list[NormalizedRecord]) -> list[NormalizedRecord]:
    """Merge duplicate IDs deterministically, preferring later non-null observations."""
    merged: dict[str, NormalizedRecord] = {}
    for record in sorted(records, key=lambda item: (item.record_id or "", item.retrieved_at or "")):
        if not record.record_id:
            raise ValueError("Normalized record is missing record_id")
        previous = merged.get(record.record_id)
        if previous is None:
            merged[record.record_id] = record
            continue
        updates = {
            field.name: getattr(record, field.name) or getattr(previous, field.name)
            for field in dataclasses.fields(record)
        }
        first_observed = [
            value for value in (record.as_row().get("first_observed_date"), previous.as_row().get("first_observed_date"))
            if value
        ]
        last_observed = [
            value for value in (record.as_row().get("last_observed_date"), previous.as_row().get("last_observed_date"))
            if value
        ]
        if first_observed:
            updates["first_observed_date"] = min(first_observed)
        if last_observed:
            updates["last_observed_date"] = max(last_observed)
        merged[record.record_id] = NormalizedRecord(**updates)
    return [merged[key] for key in sorted(merged)]


def deduplicate_public_records(records: list[NormalizedRecord]) -> list[NormalizedRecord]:
    """Collapse stable-ID variants that share one module/public record number."""
    groups: dict[tuple[str, str], list[NormalizedRecord]] = {}
    unkeyed: list[NormalizedRecord] = []
    for record in records:
        module = clean(record.source_module)
        number = re.sub(r"[^A-Z0-9]", "", (clean(record.record_number) or "").upper())
        if not module or not number:
            unkeyed.append(record)
            continue
        groups.setdefault((module.upper(), number), []).append(record)
    output = list(unkeyed)
    for key in sorted(groups):
        group = groups[key]
        preferred = max(
            group,
            key=lambda item: (
                bool(clean(item.source_url)),
                sum(bool(clean(getattr(item, field.name))) for field in dataclasses.fields(item)),
                clean(item.retrieved_at) or "",
                clean(item.record_id) or "",
            ),
        )
        updates = {field.name: getattr(preferred, field.name) for field in dataclasses.fields(preferred)}
        for record in sorted(group, key=lambda item: clean(item.retrieved_at) or ""):
            for field in dataclasses.fields(record):
                value = getattr(record, field.name)
                if value and not updates.get(field.name):
                    updates[field.name] = value
        first = [record.as_row().get("first_observed_date") for record in group]
        last = [record.as_row().get("last_observed_date") for record in group]
        updates["first_observed_date"] = min(value for value in first if value)
        updates["last_observed_date"] = max(value for value in last if value)
        updates["record_id"] = preferred.record_id
        output.append(NormalizedRecord(**updates))
    return sorted(output, key=lambda item: (clean(item.source_module) or "", clean(item.record_number) or ""))


def normalize_inspection_row(
    row: Mapping[str, object],
    *,
    record: NormalizedRecord,
    retrieved_at: str,
    raw_source_file: str,
) -> Inspection:
    values = canonical_headers(row)
    inspection_type = clean(values.get("inspection type") or values.get("type"))
    status = clean(values.get("status") or values.get("inspection status"))
    result = clean(values.get("result") or values.get("result status"))
    source_identifier = clean(values.get("inspection id") or values.get("id") or values.get("inspection number"))
    scheduled_date = iso_date(values.get("scheduled date") or values.get("schedule date"))
    completed_date = iso_date(values.get("completed date") or values.get("completion date"))
    result_date = iso_date(values.get("result date") or values.get("date"))
    # Namespace even source-provided numbers to the parent record. Accela does
    # not document that the displayed inspection number is agency-global.
    identifier = stable_inspection_id(
        record.record_id,
        source_identifier=source_identifier,
        inspection_type=inspection_type,
        scheduled_date=scheduled_date,
        completed_date=completed_date,
        result_date=result_date,
    )
    return Inspection(
        record_id=record.record_id,
        record_number=record.record_number,
        inspection_id=identifier,
        source_inspection_id=source_identifier,
        inspection_type=inspection_type,
        inspection_status=status,
        scheduled_date=scheduled_date,
        completed_date=completed_date,
        result=result,
        result_date=result_date,
        inspector_name=clean(values.get("inspector") or values.get("inspector name")),
        source_url=record.source_url,
        retrieved_at=retrieved_at,
        raw_source_file=raw_source_file,
    )


def stable_inspection_id(
    record_id: object,
    *,
    source_identifier: object = None,
    inspection_type: object = None,
    scheduled_date: object = None,
    completed_date: object = None,
    result_date: object = None,
) -> str:
    """Namespace an inspection identity to its canonical Accela parent row."""
    identity = clean(source_identifier) or "|".join(
        clean(value) or ""
        for value in (inspection_type, scheduled_date, completed_date, result_date)
    )
    seed = "|".join((clean(record_id) or "", identity))
    return "ins-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
