#!/usr/bin/env python3
"""Build bounded capital-budget and parcel context modules.

These tables are deliberately separate from the eight-layer source-bounded
census.  The Budget Book service supplies historical/public-finance context,
and the parcel service is queried only for folios already exposed by a matched
City building footprint. Source acquisition applies explicit field whitelists
so owner, mailing, contact, editor, and free-text fields are never written to
the public snapshots.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTEXT_RAW = DATA / "context" / "raw"
PROCESSED = DATA / "processed"

BUDGET_BOOK_ENDPOINT = (
    "https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/"
    "CapitalProjectsBudgetBook/FeatureServer/0"
)
PARCEL_ENDPOINT = (
    "https://arcgis.tampagov.net/arcgis/rest/services/Parcels/"
    "TaxParcel/FeatureServer/0"
)

BUDGET_BOOK_FIELDS = (
    "OBJECTID", "GlobalID", "projid", "projname", "projdesc", "rationale",
    "projtype", "fiscalyr", "fundsource", "planstart", "planend", "estcost",
    "funded", "projphase", "actstart", "actend", "actcost", "status",
    "docpath", "EditDate", "Neighborhood", "Council", "ContractNumber",
    "ActivityStatus", "ProjectSiteURL", "DepPrjNum", "BudgetBook",
    "BudgetYear", "CRA",
)

PARCEL_FIELDS = (
    "OBJECTID", "FOLIO", "PIN", "TYPE", "SITE_ADDR", "SITE_CITY",
    "SITE_ZIP", "DOR_C", "ACT", "EFF", "HEAT_AR", "ACREAGE", "JUST",
    "BLDG", "S_DATE", "AMT", "VI", "STORIES", "Shape__Area",
)

PRIVACY_BLOCKED_FIELDS = {
    "owner", "addr_1", "addr_2", "city", "state", "zip", "country",
    "legal1", "legal2", "legal3", "legal4", "dba", "pocname", "pocphone",
    "pocemail", "creator", "editor", "created_user", "last_edited_user",
    "fundcomm",
}

CAPITAL_PROJECT_COLUMNS = [
    "context_record_id", "city_project_id", "activity_id", "master_project_id",
    "project_name", "description", "rationale", "project_type", "fiscal_year",
    "budget_year", "funding_source", "funded_status", "planned_start_date",
    "planned_end_date", "actual_start_date", "actual_end_date", "project_phase",
    "status", "estimated_cost_usd", "reported_actual_cost_usd", "contract_number",
    "department_project_number", "activity_status", "neighborhood",
    "council_district", "cra", "project_document_url", "project_site_url",
    "source_record_last_edited_at_utc", "source_url", "observed_at_utc",
    "geometry_geojson",
]

CAPITAL_COMPARISON_COLUMNS = [
    "city_project_id", "budget_book_context_record_ids", "budget_book_record_count", "activity_id",
    "master_project_id", "comparison_status", "match_method",
    "budget_book_status", "core_status", "budget_book_project_name",
    "core_project_name", "observed_at_utc",
]

FINANCE_EVENT_COLUMNS = [
    "finance_event_id", "activity_id", "master_project_id", "city_project_id",
    "contract_number", "event_type", "event_date", "fiscal_year", "amount_usd",
    "amount_direction", "funding_source", "resolution_number", "source_document",
    "source_url", "observed_at_utc", "source_record_last_edited_at_utc",
    "evidence_strength", "is_inferred", "interpretation_warning",
]

PARCEL_CONTEXT_COLUMNS = [
    "folio", "pin", "site_address", "site_address_normalized", "site_city",
    "site_zip", "parcel_type", "land_use_code", "year_built", "remodel_year",
    "building_area_sqft", "parcel_area_acres", "market_value_usd",
    "building_value_usd", "sale_date", "sale_amount_usd", "vacant_or_improved",
    "stories", "source_object_id", "source_url", "snapshot_date",
    "observed_at_utc", "geometry_geojson",
]

PARCEL_LINK_COLUMNS = [
    "parcel_activity_link_id", "activity_id", "master_project_id", "folio", "pin",
    "site_address_normalized", "link_method", "link_evidence", "link_confidence",
    "valid_from", "valid_to", "review_status", "source_url", "observed_at_utc",
]


FIELD_METADATA = {
    "context_record_id": ("Stable identifier for one Budget Book context row.", "text", "", "Never blank.", "derived", "SHA-1 of the Budget Book project identifier and source object identifier.", "bbp- prefixed identifier.", "Identifies a context-source row, not a core census feature."),
    "city_project_id": ("Project identifier reported by a City capital source.", "text", "", "Never blank for capital context rows.", "source", "Budget Book projid or core capital source_record_id.", "Source-defined identifier.", "Formatting and identifier systems can vary across City capital services."),
    "budget_book_context_record_ids": ("Context-row identifiers for all matching Budget Book records.", "text", "", "Blank means the project is absent from the Budget Book snapshot.", "derived", "Exact city_project_id match, joined with semicolons when the source repeats a project ID.", "One or more bbp- prefixed identifiers.", "Absence does not mean that the project was never budgeted."),
    "budget_book_record_count": ("Number of Budget Book source rows carrying this project identifier.", "integer", "rows", "Zero means the project appears only in the core capital sources.", "derived", "Count of context records sharing city_project_id.", "Non-negative integer.", "Multiple rows can represent source duplication or distinct budget records and are retained without automatic consolidation."),
    "comparison_status": ("Relationship between a Budget Book record and the core capital-project snapshot.", "categorical text", "", "Never blank.", "derived", "Exact project-identifier reconciliation.", "matched_core_activity; budget_book_only; core_capital_only; ambiguous_multiple_core_activities", "This comparison concerns source records, not unique real-world projects."),
    "match_method": ("Rule used to connect records or spatial entities.", "categorical text", "", "Never blank where a link exists.", "derived", "Table-specific exact identifier or building-footprint folio rule.", "Table-defined.", "A heuristic link is not a legal parcel or project determination."),
    "budget_book_status": ("Status reported by the Budget Book context source.", "text", "", "Blank means unavailable or no Budget Book record.", "source", "status.", "Source-defined.", "Status is an administrative label and does not prove physical completion."),
    "core_status": ("Status in the matched core activity snapshot.", "text", "", "Blank means no matched core activity.", "source/derived", "tampa_development_activity.status after exact identifier matching.", "Source-defined.", "The core activity can consolidate more than one source feature."),
    "budget_book_project_name": ("Project name reported by the Budget Book source.", "text", "", "Blank means unavailable.", "source", "projname.", "Source-defined.", "Names are descriptive and are not used as the primary match key."),
    "core_project_name": ("Project name in the matched core activity.", "text", "", "Blank means no matched activity.", "source/derived", "tampa_development_activity.project_name.", "Source-defined.", "Name differences are diagnostic and are not automatic contradictions."),
    "rationale": ("Project rationale reported by the Budget Book source.", "text", "", "Blank means unavailable.", "source", "rationale.", "Source-defined text.", "A stated rationale is not an independently evaluated outcome."),
    "project_type": ("Capital-project type reported by the Budget Book source.", "text", "", "Blank means unavailable.", "source", "projtype.", "Source-defined category.", "Categories can differ from other City services and years."),
    "budget_year": ("Budget Book year reported by the source.", "integer", "year", "Blank means unavailable.", "source", "BudgetYear.", "Four-digit year.", "This is not necessarily the year money was spent."),
    "fiscal_year": ("Fiscal year reported by the source.", "text", "", "Blank means unavailable.", "source", "fiscalyr.", "Source-defined year or label.", "Do not infer an exact event date from a fiscal-year label."),
    "funded_status": ("Whether the Budget Book source labels the project as funded.", "text", "", "Blank means unavailable.", "source", "funded.", "Source-defined, commonly Yes or No.", "Funded status is not an expenditure or completion measure."),
    "actual_start_date": ("Actual project start date reported by the Budget Book source.", "date", "", "Blank means unavailable.", "source", "actstart.", "ISO 8601 date.", "Reported actual start is not independently verified."),
    "actual_end_date": ("Actual project end date reported by the Budget Book source.", "date", "", "Blank means unavailable.", "source", "actend.", "ISO 8601 date.", "Reported actual end is not treated as proof of final inspection or occupancy."),
    "project_phase": ("Capital-project phase reported by the source.", "text", "", "Blank means unavailable.", "source", "projphase.", "Source-defined.", "Closeout is an administrative phase, not necessarily physical completion."),
    "reported_actual_cost_usd": ("Actual-cost value reported by the Budget Book source.", "decimal", "nominal USD", "Blank means unavailable, not zero.", "source", "actcost where positive.", "Positive amount.", "The field is a reported value and is not independently audited."),
    "contract_number": ("Contract identifier reported by the capital source.", "text", "", "Blank means unavailable.", "source", "ContractNumber.", "Source-defined.", "One contract can relate to multiple projects and vice versa."),
    "department_project_number": ("Department-specific project number reported by the Budget Book source.", "text", "", "Blank means unavailable.", "source", "DepPrjNum.", "Source-defined.", "Not interchangeable with city_project_id without verification."),
    "activity_status": ("Detailed activity-status label reported by the Budget Book source.", "text", "", "Blank means unavailable.", "source", "ActivityStatus.", "Source-defined.", "May describe an administrative or financial stage rather than construction."),
    "project_document_url": ("Project-document URL reported by the Budget Book source.", "URL", "", "Blank means unavailable.", "source", "docpath.", "HTTPS URL or source-provided text.", "Links can move or expire."),
    "project_site_url": ("Project-site or linked-document URL extracted from the source field.", "URL", "", "Blank means unavailable.", "source/cleaned", "URL extracted from ProjectSiteURL HTML when present.", "HTTPS URL.", "The linked page or document can change after retrieval."),
    "source_record_last_edited_at_utc": ("Last-edited timestamp reported for the source record.", "timestamp", "UTC", "Blank means unavailable.", "source", "EditDate or equivalent.", "ISO 8601 UTC timestamp.", "Does not identify which field changed."),
    "observed_at_utc": ("UTC time at which this source state was retrieved.", "timestamp", "UTC", "Never blank.", "source acquisition", "Context snapshot completion time.", "ISO 8601 UTC timestamp.", "Observation time is not necessarily the underlying event time."),
    "finance_event_id": ("Stable identifier for one reported public-finance observation.", "text", "", "Never blank.", "derived", "SHA-1 of context record, observation type, and reported value.", "fin- prefixed identifier.", "An observation is not necessarily a budget amendment or cash expenditure."),
    "amount_direction": ("Whether the finance observation represents an increase, decrease, or reported level.", "categorical text", "", "Never blank.", "derived", "Source semantics for the event type.", "reported_level; increase; decrease; not_applicable", "Budget Book snapshots currently provide levels, not amendment directions."),
    "resolution_number": ("City resolution identifier supporting a finance action.", "text", "", "Blank means the current source is not a resolution record.", "source", "Reserved for budget-resolution ingestion.", "Source-defined.", "Do not infer a resolution from a Budget Book row."),
    "source_document": ("Source document or page supporting the observation.", "text", "", "Blank means no record-specific document was supplied.", "source", "Budget Book project-document fields.", "URL or stable reference.", "A general service endpoint can be the only available citation."),
    "evidence_strength": ("Evidence category describing the source support for the event.", "categorical text", "", "Never blank.", "derived", "Conservative source-evidence classification.", "official_source_observation; official_reported_date; official_lifecycle_record", "Strength concerns provenance, not independent truth verification."),
    "is_inferred": ("Whether the event meaning or timing was inferred rather than explicitly reported.", "boolean text", "", "Never blank.", "derived", "yes when a normalized event is inferred from status text; otherwise no.", "yes; no", "An inferred event must not be treated as equivalent to a dated official event."),
    "interpretation_warning": ("Row-specific warning limiting interpretation.", "text", "", "Never blank for finance observations.", "documentation", "Fixed by event type.", "Free text.", "Read before aggregating amounts."),
    "parcel_activity_link_id": ("Stable identifier for one proposed activity-to-parcel link.", "text", "", "Never blank.", "derived", "SHA-1 of activity_id and folio.", "pal- prefixed identifier.", "The link is analytical and is not a legal parcel determination."),
    "pin": ("Property identification number reported by the parcel source.", "text", "", "Blank means unavailable.", "source", "PIN.", "Source-defined identifier.", "Identifier formatting can change."),
    "site_address": ("Parcel site address reported by the parcel source.", "text", "", "Blank means unavailable.", "source", "SITE_ADDR.", "Source-defined address.", "Public but potentially sensitive; aggregate person-focused analyses."),
    "site_address_normalized": ("Parcel site address normalized for comparison.", "text", "", "Blank means the source address is unavailable.", "derived", "Uppercase alphanumeric address normalization.", "Normalized address text.", "Normalization does not establish a parcel match by itself."),
    "site_city": ("Parcel site city reported by the source.", "text", "", "Blank means unavailable.", "source", "SITE_CITY.", "Source-defined.", "Not independently geocoded."),
    "site_zip": ("Parcel site ZIP code reported by the source.", "text", "", "Blank means unavailable.", "source", "SITE_ZIP.", "Source-defined.", "Retained as a site attribute, not an owner mailing field."),
    "parcel_type": ("Parcel-description category reported by the source.", "text", "", "Blank means unavailable.", "source", "TYPE.", "Source-defined.", "Not a harmonized land-use classification."),
    "land_use_code": ("Department of Revenue land-use code reported by the source.", "text", "", "Blank means unavailable.", "source", "DOR_C.", "Source-defined code.", "Code meanings require the applicable source-year lookup."),
    "year_built": ("Actual year built reported by the parcel source.", "integer", "year", "Blank means unavailable.", "source", "ACT.", "Four-digit year.", "Assessment year does not prove a permit was completed."),
    "remodel_year": ("Effective/remodel year reported by the parcel source.", "integer", "year", "Blank means unavailable.", "source", "EFF.", "Four-digit year.", "A remodel year is corroborating context, not proof of a specific activity."),
    "building_area_sqft": ("Living/heated building area reported by the parcel source.", "decimal", "square feet", "Blank means unavailable.", "source", "HEAT_AR.", "Non-negative number.", "Definition may differ from permit square footage."),
    "parcel_area_acres": ("Parcel area reported by the source.", "decimal", "acres", "Blank means unavailable.", "source", "ACREAGE.", "Non-negative number.", "Not a survey measurement."),
    "market_value_usd": ("Market/just value reported by the parcel source.", "decimal", "nominal USD", "Blank means unavailable.", "source", "JUST.", "Non-negative amount.", "Assessment value is not development investment or sale price."),
    "building_value_usd": ("Building value reported by the parcel source.", "decimal", "nominal USD", "Blank means unavailable.", "source", "BLDG.", "Non-negative amount.", "Assessment value is not construction cost."),
    "sale_date": ("Most recent sale date exposed by the parcel source.", "date", "", "Blank means unavailable.", "source", "S_DATE.", "ISO 8601 date.", "A sale does not establish construction."),
    "sale_amount_usd": ("Sale amount exposed by the parcel source.", "decimal", "nominal USD", "Blank means unavailable.", "source", "AMT.", "Non-negative amount.", "A sale amount is not construction investment."),
    "vacant_or_improved": ("Vacant/improved label reported by the parcel source.", "text", "", "Blank means unavailable.", "source", "VI.", "Source-defined.", "This is assessment context, not field verification."),
    "stories": ("Building-story count reported by the parcel source.", "integer", "stories", "Blank means unavailable.", "source", "STORIES.", "Non-negative integer.", "Not independently verified."),
    "source_object_id": ("ArcGIS object identifier in the context source.", "integer", "", "Blank means unavailable.", "source", "OBJECTID.", "Non-negative integer.", "OBJECTID can change if the service is republished."),
    "snapshot_date": ("UTC calendar date of the context-source snapshot.", "date", "", "Never blank.", "source acquisition", "Date portion of observed_at_utc.", "ISO 8601 date.", "Does not date every underlying parcel attribute."),
    "link_evidence": ("Semicolon-delimited building-match methods contributing the folio link.", "text", "", "Never blank.", "derived", "Distinct parcel_building_matches.match_method values.", "Source-defined methods separated by semicolons.", "Methods remain subject to manual match validation."),
    "link_method": ("High-level rule used to create the activity-to-parcel link.", "categorical text", "", "Never blank.", "derived", "Folio carried by a proposed City building-footprint match.", "building_footprint_folio", "This is an analytical link, not a legal parcel determination."),
    "link_confidence": ("Highest configured confidence among evidence contributing to the parcel link.", "categorical text", "", "Never blank.", "derived", "high > medium > low across contributing building matches.", "high; medium; low", "A rule-based tier is not an empirical probability."),
    "valid_from": ("Beginning of the known validity interval for the parcel link.", "date", "", "Blank means the historical validity start is unknown.", "reserved", "Not available from a single current snapshot.", "ISO 8601 date.", "Do not assume the link existed before observation."),
    "valid_to": ("End of the known validity interval for the parcel link.", "date", "", "Blank means no historical end is known.", "reserved", "Not available from a single current snapshot.", "ISO 8601 date.", "Blank is not proof that the relationship is permanent."),
}


def metadata_for(field: str):
    return FIELD_METADATA.get(field)


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def token(value: str, length: int = 16) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def normalize_address(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", clean(value).upper())
    replacements = {
        "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "BOULEVARD": "BLVD",
        "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "PLACE": "PL",
        "TERRACE": "TER", "HIGHWAY": "HWY",
    }
    return " ".join(replacements.get(part, part) for part in text.split())


def iso_timestamp(value: object) -> str:
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


def iso_date(value: object) -> str:
    stamp = iso_timestamp(value)
    if stamp:
        return stamp[:10]
    text = clean(value)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def numeric(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.2f}" if number != int(number) else str(int(number))


def extract_url(value: object) -> str:
    text = clean(value)
    match = re.search(r'https?://[^"<> ]+', text)
    return match.group(0) if match else (text if text.startswith("https://") else "")


def read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    """Atomically publish a JSON snapshot after it is fully serialized."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def fetch_geojson(endpoint: str, fields: tuple[str, ...], where: str = "1=1") -> dict:
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": ",".join(fields),
        "returnGeometry": "true",
        "outSR": 4326,
        "resultRecordCount": 2000,
        "f": "geojson",
    })
    last_error = "ArcGIS query failed"
    for attempt in range(5):
        request = urllib.request.Request(
            f"{endpoint}/query?{params}",
            headers={"User-Agent": "tampa-development-records-context/0.8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            if "error" not in payload:
                return {"type": "FeatureCollection", "features": payload.get("features", [])}
            last_error = payload["error"].get("message", last_error)
        except Exception as exc:  # ArcGIS occasionally returns a transient proxy/backend error.
            last_error = str(exc)
        if attempt < 4:
            time.sleep(attempt + 1)
    raise RuntimeError(last_error)


def whitelist_collection(collection: dict, fields: tuple[str, ...]) -> dict:
    allowed = set(fields)
    features = []
    for feature in collection.get("features", []):
        properties = {
            key: value for key, value in (feature.get("properties") or {}).items()
            if key in allowed
        }
        blocked = {key.lower() for key in properties} & PRIVACY_BLOCKED_FIELDS
        if blocked:
            raise RuntimeError(f"Context whitelist retained blocked fields: {sorted(blocked)}")
        features.append({
            "type": "Feature", "properties": properties,
            "geometry": feature.get("geometry"),
        })
    return {"type": "FeatureCollection", "features": features}


def refresh_context_sources(matches: list[dict[str, str]], observed_at: str) -> dict:
    CONTEXT_RAW.mkdir(parents=True, exist_ok=True)
    budget = whitelist_collection(
        # This ArcGIS service currently rejects explicit outFields lists even
        # though it accepts outFields=*.  The response is therefore reduced to
        # the strict public whitelist in memory before anything is written.
        fetch_geojson(BUDGET_BOOK_ENDPOINT, ("*",)), BUDGET_BOOK_FIELDS
    )
    budget_path = CONTEXT_RAW / "capital_budget_book.geojson"
    write_json(budget_path, budget)

    folios = sorted({clean(row.get("folio")) for row in matches if clean(row.get("folio"))})
    parcel_features = []
    for start in range(0, len(folios), 75):
        values = ",".join("'" + folio.replace("'", "''") + "'" for folio in folios[start:start + 75])
        collection = fetch_geojson(PARCEL_ENDPOINT, PARCEL_FIELDS, f"FOLIO IN ({values})")
        parcel_features.extend(collection.get("features", []))
    parcels = whitelist_collection(
        {"type": "FeatureCollection", "features": parcel_features}, PARCEL_FIELDS
    )
    parcel_path = CONTEXT_RAW / "linked_tax_parcels.geojson"
    write_json(parcel_path, parcels)

    metadata = {
        "observed_at_utc": observed_at,
        "scope_note": "Context sources are separate from the eight-layer bounded census.",
        "privacy_note": "Only whitelisted analytical fields were retained in public snapshots; owner, mailing, contact, editor, legal-description, and free-text funding-comment fields were excluded before writing.",
        "sources": {
            "capital_budget_book": {
                "endpoint": BUDGET_BOOK_ENDPOINT,
                "record_count": len(budget["features"]),
                "fields": list(BUDGET_BOOK_FIELDS),
                "sha256": file_sha256(budget_path),
            },
            "linked_tax_parcels": {
                "endpoint": PARCEL_ENDPOINT,
                "requested_folio_count": len(folios),
                "record_count": len(parcels["features"]),
                "fields": list(PARCEL_FIELDS),
                "sha256": file_sha256(parcel_path),
            },
        },
    }
    write_json(CONTEXT_RAW / "context_snapshot_metadata.json", metadata)
    return metadata


def context_observed_at() -> str:
    path = CONTEXT_RAW / "context_snapshot_metadata.json"
    if not path.exists():
        raise RuntimeError("Context snapshot metadata is missing; refresh sources first")
    return json.loads(path.read_text(encoding="utf-8"))["observed_at_utc"]


def capital_source_map(source_records: list[dict[str, str]]) -> dict[str, set[str]]:
    mapped: dict[str, set[str]] = defaultdict(set)
    for row in source_records:
        if row.get("source_name", "").startswith("capital_") and clean(row.get("source_record_id")):
            mapped[clean(row["source_record_id"])].add(row["activity_id"])
    return mapped


def build_capital_context(
    collection: dict, observed_at: str, activities: list[dict[str, str]],
    source_records: list[dict[str, str]], project_links: list[dict[str, str]],
) -> tuple[list[dict], list[dict], list[dict]]:
    activities_by_id = {row["activity_id"]: row for row in activities}
    master_by_activity = {row["activity_id"]: row["master_project_id"] for row in project_links}
    core_by_project = capital_source_map(source_records)
    budget_rows = []
    budget_by_project: dict[str, list[dict]] = defaultdict(list)
    for feature in collection.get("features", []):
        props = feature.get("properties") or {}
        project_id = clean(props.get("projid"))
        if not project_id:
            continue
        activity_ids = sorted(core_by_project.get(project_id, set()))
        activity_id = activity_ids[0] if len(activity_ids) == 1 else ";".join(activity_ids)
        master_ids = sorted({master_by_activity.get(aid, "") for aid in activity_ids if master_by_activity.get(aid)})
        context_id = f"bbp-{token(project_id + '|' + clean(props.get('OBJECTID')))}"
        row = {
            "context_record_id": context_id,
            "city_project_id": project_id,
            "activity_id": activity_id,
            "master_project_id": ";".join(master_ids),
            "project_name": clean(props.get("projname")),
            "description": clean(props.get("projdesc")),
            "rationale": clean(props.get("rationale")),
            "project_type": clean(props.get("projtype")),
            "fiscal_year": clean(props.get("fiscalyr")),
            "budget_year": clean(props.get("BudgetYear")),
            "funding_source": clean(props.get("fundsource")),
            "funded_status": clean(props.get("funded")),
            "planned_start_date": iso_date(props.get("planstart")),
            "planned_end_date": iso_date(props.get("planend")),
            "actual_start_date": iso_date(props.get("actstart")),
            "actual_end_date": iso_date(props.get("actend")),
            "project_phase": clean(props.get("projphase")),
            "status": clean(props.get("status")),
            "estimated_cost_usd": numeric(props.get("estcost")) if float(props.get("estcost") or 0) > 0 else "",
            "reported_actual_cost_usd": numeric(props.get("actcost")) if float(props.get("actcost") or 0) > 0 else "",
            "contract_number": clean(props.get("ContractNumber")),
            "department_project_number": clean(props.get("DepPrjNum")),
            "activity_status": clean(props.get("ActivityStatus")),
            "neighborhood": clean(props.get("Neighborhood")),
            "council_district": clean(props.get("Council")),
            "cra": clean(props.get("CRA")),
            "project_document_url": extract_url(props.get("docpath")),
            "project_site_url": extract_url(props.get("ProjectSiteURL")),
            "source_record_last_edited_at_utc": iso_timestamp(props.get("EditDate")),
            "source_url": BUDGET_BOOK_ENDPOINT,
            "observed_at_utc": observed_at,
            "geometry_geojson": json.dumps(feature.get("geometry"), separators=(",", ":")) if feature.get("geometry") else "",
        }
        budget_rows.append(row)
        budget_by_project[project_id].append(row)

    comparison = []
    for project_id in sorted(set(core_by_project) | set(budget_by_project)):
        budget_records = budget_by_project.get(project_id, [])
        budget = budget_records[0] if budget_records else None
        activity_ids = sorted(core_by_project.get(project_id, set()))
        core = activities_by_id.get(activity_ids[0], {}) if len(activity_ids) == 1 else {}
        if budget and len(activity_ids) == 1:
            status = "matched_core_activity"
        elif budget and len(activity_ids) > 1:
            status = "ambiguous_multiple_core_activities"
        elif budget:
            status = "budget_book_only"
        else:
            status = "core_capital_only"
        comparison.append({
            "city_project_id": project_id,
            "budget_book_context_record_ids": ";".join(
                sorted(row["context_record_id"] for row in budget_records)
            ),
            "budget_book_record_count": str(len(budget_records)),
            "activity_id": ";".join(activity_ids),
            "master_project_id": ";".join(sorted({master_by_activity.get(aid, "") for aid in activity_ids if master_by_activity.get(aid)})),
            "comparison_status": status,
            "match_method": "exact_city_project_id" if budget and activity_ids else "no_exact_identifier_match",
            "budget_book_status": budget["status"] if budget else "",
            "core_status": clean(core.get("status")),
            "budget_book_project_name": budget["project_name"] if budget else "",
            "core_project_name": clean(core.get("project_name")),
            "observed_at_utc": observed_at,
        })

    finance_events = []
    for row in budget_rows:
        specs = []
        if row["estimated_cost_usd"]:
            specs.append(("capital_estimate_reported", row["estimated_cost_usd"], "reported_level",
                          "Estimated cost is a reported project-level estimate, not spending or a budget amendment."))
        if row["reported_actual_cost_usd"]:
            specs.append(("capital_actual_cost_reported", row["reported_actual_cost_usd"], "reported_level",
                          "Actual cost is source-reported and not independently audited or necessarily final."))
        if row["funded_status"]:
            specs.append(("funded_status_reported", "", "not_applicable",
                          "Funded status is an administrative source label, not an expenditure amount."))
        for event_type, amount, direction, warning in specs:
            seed = "|".join((row["context_record_id"], event_type, amount, row["observed_at_utc"]))
            finance_events.append({
                "finance_event_id": f"fin-{token(seed)}",
                "activity_id": row["activity_id"],
                "master_project_id": row["master_project_id"],
                "city_project_id": row["city_project_id"],
                "contract_number": row["contract_number"],
                "event_type": event_type,
                "event_date": "",
                "fiscal_year": row["fiscal_year"],
                "amount_usd": amount,
                "amount_direction": direction,
                "funding_source": row["funding_source"],
                "resolution_number": "",
                "source_document": row["project_document_url"] or row["project_site_url"],
                "source_url": row["source_url"],
                "observed_at_utc": row["observed_at_utc"],
                "source_record_last_edited_at_utc": row["source_record_last_edited_at_utc"],
                "evidence_strength": "official_source_observation",
                "is_inferred": "no",
                "interpretation_warning": warning,
            })
    return budget_rows, comparison, finance_events


def build_parcel_context(
    collection: dict, observed_at: str, matches: list[dict[str, str]],
    project_links: list[dict[str, str]],
) -> tuple[list[dict], list[dict]]:
    parcel_rows = []
    parcel_by_folio = {}
    for feature in collection.get("features", []):
        props = feature.get("properties") or {}
        folio = clean(props.get("FOLIO"))
        if not folio:
            continue
        row = {
            "folio": folio,
            "pin": clean(props.get("PIN")),
            "site_address": clean(props.get("SITE_ADDR")),
            "site_address_normalized": normalize_address(props.get("SITE_ADDR")),
            "site_city": clean(props.get("SITE_CITY")),
            "site_zip": clean(props.get("SITE_ZIP")),
            "parcel_type": clean(props.get("TYPE")),
            "land_use_code": clean(props.get("DOR_C")),
            "year_built": clean(props.get("ACT")),
            "remodel_year": clean(props.get("EFF")),
            "building_area_sqft": numeric(props.get("HEAT_AR")),
            "parcel_area_acres": numeric(props.get("ACREAGE")),
            "market_value_usd": numeric(props.get("JUST")),
            "building_value_usd": numeric(props.get("BLDG")),
            "sale_date": iso_date(props.get("S_DATE")),
            "sale_amount_usd": numeric(props.get("AMT")),
            "vacant_or_improved": clean(props.get("VI")),
            "stories": clean(props.get("STORIES")),
            "source_object_id": clean(props.get("OBJECTID")),
            "source_url": PARCEL_ENDPOINT,
            "snapshot_date": observed_at[:10],
            "observed_at_utc": observed_at,
            "geometry_geojson": json.dumps(feature.get("geometry"), separators=(",", ":")) if feature.get("geometry") else "",
        }
        parcel_rows.append(row)
        parcel_by_folio[folio] = row

    master_by_activity = {row["activity_id"]: row["master_project_id"] for row in project_links}
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for match in matches:
        folio = clean(match.get("folio"))
        if folio:
            grouped[(match["activity_id"], folio)].append(match)
    rank = {"": 0, "low": 1, "medium": 2, "high": 3}
    links = []
    for (activity_id, folio), evidence in sorted(grouped.items()):
        methods = sorted({clean(row.get("match_method")) for row in evidence if clean(row.get("match_method"))})
        confidence = max((clean(row.get("match_confidence")) for row in evidence), key=lambda value: rank.get(value, 0))
        parcel = parcel_by_folio.get(folio, {})
        links.append({
            "parcel_activity_link_id": f"pal-{token(activity_id + '|' + folio)}",
            "activity_id": activity_id,
            "master_project_id": master_by_activity.get(activity_id, ""),
            "folio": folio,
            "pin": parcel.get("pin", ""),
            "site_address_normalized": parcel.get("site_address_normalized", ""),
            "link_method": "building_footprint_folio",
            "link_evidence": ";".join(methods),
            "link_confidence": confidence,
            "valid_from": "",
            "valid_to": "",
            "review_status": "pending_human_review",
            "source_url": PARCEL_ENDPOINT if parcel else clean(evidence[0].get("building_source_endpoint")),
            "observed_at_utc": observed_at,
        })
    return parcel_rows, links


def build(
    activities: list[dict[str, str]], matches: list[dict[str, str]],
    source_records: list[dict[str, str]], project_links: list[dict[str, str]],
) -> dict:
    observed_at = context_observed_at()
    budget = json.loads((CONTEXT_RAW / "capital_budget_book.geojson").read_text(encoding="utf-8"))
    parcels = json.loads((CONTEXT_RAW / "linked_tax_parcels.geojson").read_text(encoding="utf-8"))
    capital_rows, comparison, finance_events = build_capital_context(
        budget, observed_at, activities, source_records, project_links
    )
    parcel_rows, parcel_links = build_parcel_context(parcels, observed_at, matches, project_links)
    write_csv(PROCESSED / "capital_budget_book_projects.csv", capital_rows, CAPITAL_PROJECT_COLUMNS)
    write_csv(PROCESSED / "capital_budget_book_comparison.csv", comparison, CAPITAL_COMPARISON_COLUMNS)
    write_csv(PROCESSED / "public_finance_events.csv", finance_events, FINANCE_EVENT_COLUMNS)
    write_csv(PROCESSED / "parcel_context.csv", parcel_rows, PARCEL_CONTEXT_COLUMNS)
    write_csv(PROCESSED / "parcel_activity_links.csv", parcel_links, PARCEL_LINK_COLUMNS)
    return {
        "observed_at_utc": observed_at,
        "capital_budget_book_projects": len(capital_rows),
        "capital_budget_book_comparison": len(comparison),
        "public_finance_events": len(finance_events),
        "parcel_context": len(parcel_rows),
        "parcel_activity_links": len(parcel_links),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--use-existing-raw", action="store_true",
        help="Build from bundled privacy-minimized context snapshots without refreshing them.",
    )
    args = parser.parse_args()
    activities = read_csv(PROCESSED / "tampa_development_activity.csv")
    matches = read_csv(PROCESSED / "parcel_building_matches.csv")
    source_records = read_csv(PROCESSED / "source_records.csv")
    project_links = read_csv(PROCESSED / "master_project_activity_links.csv")
    if not args.use_existing_raw:
        observed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        refresh_context_sources(matches, observed_at)
    result = build(activities, matches, source_records, project_links)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
