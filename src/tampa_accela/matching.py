"""Conservative, auditable matching of Accela records to existing GIS rows."""

from __future__ import annotations

import csv
import datetime as dt
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from typing import Iterable, Mapping

from .models import NormalizedRecord
from .output import write_csv


CROSSWALK_FIELDS = [
    "gis_source", "gis_record_id", "accela_record_id", "accela_record_number",
    "match_method", "match_score", "match_status", "matched_on_permit_number",
    "matched_on_parcel", "matched_on_address", "matched_on_date", "review_required",
]


def _token(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def normalize_address(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper())
    substitutions = {
        " STREET ": " ST ", " AVENUE ": " AVE ", " ROAD ": " RD ",
        " BOULEVARD ": " BLVD ", " DRIVE ": " DR ", " LANE ": " LN ",
        " COURT ": " CT ", " HIGHWAY ": " HWY ", " NORTH ": " N ",
        " SOUTH ": " S ", " EAST ": " E ", " WEST ": " W ",
    }
    text = f" {' '.join(text.split())} "
    for old, new in substitutions.items():
        text = text.replace(old, new)
    return " ".join(text.split())


def _date(value: object) -> dt.date | None:
    if value in {None, ""}:
        return None
    try:
        if str(value).isdigit() and int(str(value)) > 10_000_000_000:
            return dt.datetime.fromtimestamp(int(str(value)) / 1000, tz=dt.timezone.utc).date()
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, OSError):
        return None


def _props(row: Mapping[str, str]) -> dict[str, object]:
    try:
        value = json.loads(row.get("properties_json") or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _pick(props: Mapping[str, object], *names: str) -> object:
    folded = {str(key).upper(): value for key, value in props.items()}
    for name in names:
        value = folded.get(name.upper())
        if value is not None and value != "":
            return value
    return None


def _candidate(record: NormalizedRecord, gis: Mapping[str, str]) -> dict[str, object]:
    props = _props(gis)
    numbers = {
        _token(gis.get("source_record_id")),
        *(_token(_pick(props, name)) for name in ("RECORD_ID", "RECORDID", "PERMIT", "PERMIT_NO", "APPLICATION_NUMBER")),
    }
    number = bool(_token(record.record_number)) and _token(record.record_number) in numbers
    gis_parcel = _token(_pick(props, "PARCEL", "PARCEL_ID", "FOLIO", "FOLIO_NUMBER", "PROPERTY_ID"))
    parcel = bool(_token(record.parcel_id or record.property_id)) and _token(record.parcel_id or record.property_id) == gis_parcel
    gis_address = normalize_address(_pick(props, "ADDRESS", "SITE_ADDRESS", "FULL_ADDRESS", "LOCATION"))
    accela_address = normalize_address(record.address)
    ratio = SequenceMatcher(None, accela_address, gis_address).ratio() if accela_address and gis_address else 0.0
    address = bool(accela_address) and accela_address == gis_address
    gis_date = _date(_pick(props, "CREATEDDATE", "DATE", "OPENED_DATE", "APPLICATION_DATE"))
    accela_date = _date(record.opened_date or record.filed_date)
    date_match = bool(gis_date and accela_date and abs((gis_date - accela_date).days) <= 45)
    if number:
        method, score, status, review = "exact_record_number", 1.0, "matched", False
    elif parcel:
        method, score, status, review = "exact_parcel", 0.95, "matched", False
    elif address and date_match:
        method, score, status, review = "exact_address_compatible_date", 0.90, "matched", False
    elif ratio >= 0.84 and date_match:
        method, score, status, review = "fuzzy_address_candidate", round(0.55 + 0.25 * ratio, 3), "candidate", True
    else:
        method, score, status, review = "none", 0.0, "unmatched", False
    return {
        "gis_source": gis.get("source_name") or "",
        "gis_record_id": gis.get("source_record_key") or gis.get("source_record_id") or "",
        "accela_record_id": record.record_id or "",
        "accela_record_number": record.record_number or "",
        "match_method": method,
        "match_score": f"{score:.3f}",
        "match_status": status,
        "matched_on_permit_number": str(number).lower(),
        "matched_on_parcel": str(parcel).lower(),
        "matched_on_address": str(address).lower(),
        "matched_on_date": str(date_match).lower(),
        "review_required": str(review).lower(),
    }


def match_records(records: Iterable[NormalizedRecord], gis_rows: Iterable[Mapping[str, str]]) -> list[dict[str, object]]:
    gis = list(gis_rows)
    output: list[dict[str, object]] = []
    for record in records:
        candidates = [_candidate(record, row) for row in gis]
        candidates.sort(key=lambda row: (-float(row["match_score"]), str(row["gis_record_id"])))
        best = candidates[0] if candidates else None
        if best and float(best["match_score"]) > 0:
            tied = [candidate for candidate in candidates if candidate["match_score"] == best["match_score"]]
            if len({str(candidate["gis_record_id"]) for candidate in tied}) > 1:
                best = dict(best)
                best["match_method"] = f"{best['match_method']}_ambiguous"
                best["match_status"] = "candidate"
                best["review_required"] = "true"
            output.append(best)
        else:
            output.append({
                "gis_source": "", "gis_record_id": "", "accela_record_id": record.record_id or "",
                "accela_record_number": record.record_number or "", "match_method": "none",
                "match_score": "0.000", "match_status": "unmatched",
                "matched_on_permit_number": "false", "matched_on_parcel": "false",
                "matched_on_address": "false", "matched_on_date": "false", "review_required": "false",
            })
    return output


def match_gis_file(records: Iterable[NormalizedRecord], source: Path, output: Path) -> list[dict[str, object]]:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    matches = match_records(records, rows)
    write_csv(output, matches, CROSSWALK_FIELDS)
    return matches
