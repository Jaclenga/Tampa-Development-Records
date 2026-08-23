#!/usr/bin/env python3
"""Build a centralized City of Tampa development-activity dataset.

Only Python's standard library is required. The script downloads four official
City of Tampa GIS layers, preserves raw GeoJSON snapshots, normalizes their
fields, de-duplicates exact permit IDs, and writes analysis-ready CSV files.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path


SOURCES = {
    "construction_inspections": {
        "url": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/30",
        "id": "RECORD_ID",
        "priority": 40,
    },
    "development_coordination": {
        "url": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/31",
        "id": "RECORDID",
        "priority": 10,
    },
    "single_family_permits": {
        "url": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/32",
        "id": "RECORD_ID",
        "priority": 30,
    },
    "historic_preservation": {
        "url": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/33",
        "id": "RECORDID",
        "priority": 10,
    },
    "capital_improvements": {
        "url": "https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0",
        "id": "projid",
        "priority": 50,
    },
}


COLUMNS = [
    "project_id", "source_memberships", "source_record_id", "raw_component_rows", "project_name",
    "description", "activity_class", "activity_stage", "status", "record_type",
    "address", "unit", "zip", "neighborhood", "cra", "council_district",
    "latitude", "longitude", "opened_date", "status_date", "planned_start_date",
    "planned_end_date", "last_updated", "new_construction_sqft", "housing_units",
    "estimated_cost_usd", "actual_cost_usd", "funding_source", "is_public",
    "physical_development_candidate", "completion_evidence", "evidence_confidence",
    "source_url", "source_endpoint", "retrieved_at_utc",
]


def get_json(url: str, params: dict[str, object] | None = None, retries: int = 3) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tampa-development-dataset/0.1"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except Exception:
            if attempt + 1 == retries:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def fetch_layer(base_url: str) -> dict:
    features: list[dict] = []
    offset = 0
    page_size = 2000
    while True:
        page = get_json(
            f"{base_url}/query",
            {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "orderByFields": "OBJECTID",
                "f": "geojson",
            },
        )
        batch = page.get("features", [])
        features.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return {"type": "FeatureCollection", "features": features}


def iso_date(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).date().isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
        return dt.datetime.strptime(text, "%m/%d/%Y").date().isoformat()
    return text[:10]


def number(value: object) -> int | float | str:
    if value in (None, ""):
        return ""
    try:
        n = float(value)
        return int(n) if n.is_integer() else n
    except (TypeError, ValueError):
        return ""


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def extract_url(value: object) -> str:
    text = clean_text(value)
    match = re.search(r'https?://[^"<> ]+', text)
    return match.group(0) if match else text


def point(feature: dict) -> tuple[str, str]:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") == "Point" and len(coords) >= 2:
        return str(round(coords[1], 7)), str(round(coords[0], 7))
    return "", ""


def classify_stage(status: str, source: str) -> tuple[str, str, str]:
    s = status.lower()
    if any(x in s for x in ("complete", "closeout", "closed", "final inspection")):
        return "completed_or_closeout", "official_status", "medium"
    if "construction" in s or "inspection" in s:
        return "construction_or_inspection", "official_status", "medium"
    if "issued" in s or "approved" in s:
        return "permit_or_funding_approved", "authorization_only", "low"
    if any(x in s for x in ("cancel", "withdraw", "deny", "expire")):
        return "inactive", "official_status", "medium"
    if source in {"development_coordination", "historic_preservation"}:
        return "planning_review", "application_only", "low"
    return "preconstruction_or_unknown", "official_record_only", "low"


def normalize(source: str, feature: dict, retrieved_at: str) -> dict[str, object]:
    p = feature.get("properties", {})
    cfg = SOURCES[source]
    native_id = clean_text(p.get(cfg["id"])) or f"objectid-{p.get('OBJECTID')}"
    lat, lon = point(feature)

    if source == "capital_improvements":
        status = clean_text(p.get("status") or p.get("projphase"))
        stage, evidence, confidence = classify_stage(status, source)
        row = {
            "project_name": clean_text(p.get("projname")),
            "description": clean_text(p.get("projdesc")),
            "activity_class": f"public_capital:{clean_text(p.get('projtype')).lower().replace(' ', '_')}",
            "record_type": clean_text(p.get("projtype")),
            "address": "", "unit": "", "zip": "",
            "neighborhood": clean_text(p.get("Neighborhood")),
            "cra": clean_text(p.get("CRA")), "council_district": clean_text(p.get("Council")),
            "opened_date": iso_date(p.get("CreationDate")), "status_date": "",
            "planned_start_date": iso_date(p.get("planstart")), "planned_end_date": iso_date(p.get("planend")),
            "last_updated": iso_date(p.get("last_edited_date") or p.get("EditDate")),
            "new_construction_sqft": "", "housing_units": "",
            "estimated_cost_usd": number(p.get("estcost")), "actual_cost_usd": number(p.get("actcost")),
            "funding_source": clean_text(p.get("fundsource")), "is_public": 1,
            "physical_development_candidate": int(stage in {"construction_or_inspection", "completed_or_closeout"}),
            "source_url": extract_url(p.get("ProjectSiteURL")),
        }
    elif source == "construction_inspections":
        status = clean_text(p.get("PROJECTSTATUS"))
        stage, evidence, confidence = classify_stage(status, source)
        rtype = clean_text(p.get("RECORDTYPE"))
        desc = clean_text(p.get("PROJECTDESCRIPTION"))
        sf = number(p.get("NEWCONSTRUCTIONSF"))
        title = clean_text(p.get("PROJECTNAME1") or p.get("PROJECTNAME2"))
        corpus = f"{rtype} {title} {desc}".lower()
        title_lower = title.lower()
        dedicated_demolition = bool(
            re.search(r"\b(demo|demolition|demolish)\b", title_lower)
            and not re.search(r"\b(addition|remodel|renovation|alteration|repair|rebuild|new sfr|new construction|build[- ]?out)\b", title_lower)
        )
        building_signal = (
            (isinstance(sf, (int, float)) and sf > 0)
            or bool(re.search(r"\b(new construction|new sfr|addition|foundation|rebuild|renovation|remodel|alteration|build[- ]?out)\b", corpus))
        )
        if dedicated_demolition:
            aclass = "demolition"
        elif building_signal:
            aclass = "building_construction"
        else:
            aclass = "other_permitted_work"
        row = {
            "project_name": title, "description": desc,
            "activity_class": aclass, "record_type": rtype, "address": clean_text(p.get("ADDRESS")),
            "unit": clean_text(p.get("UNIT")), "zip": clean_text(p.get("ZIP")),
            "neighborhood": clean_text(p.get("NEIGHBORHOOD")), "cra": clean_text(p.get("CRA")),
            "council_district": clean_text(p.get("COUNCIL")), "opened_date": iso_date(p.get("CREATEDDATE")),
            "status_date": iso_date(p.get("LASTUPDATE")), "planned_start_date": "", "planned_end_date": "",
            "last_updated": iso_date(p.get("LASTUPDATE")), "new_construction_sqft": sf,
            "housing_units": number(p.get("NBROFUNITS")), "estimated_cost_usd": "", "actual_cost_usd": "",
            "funding_source": "", "is_public": "",
            "physical_development_candidate": int(aclass in {"demolition", "building_construction"}),
            "source_url": clean_text(p.get("URL")),
        }
    elif source == "single_family_permits":
        status = clean_text(p.get("APPLICATION_STATUS") or p.get("TASK_STATUS"))
        stage, evidence, confidence = classify_stage(status, source)
        row = {
            "project_name": clean_text(p.get("APPLICATION_TYPE")), "description": "",
            "activity_class": "single_family_new_construction_or_addition",
            "record_type": clean_text(p.get("APPLICATION_TYPE")), "address": clean_text(p.get("ADDRESS")),
            "unit": clean_text(p.get("UNIT")), "zip": clean_text(p.get("ZIP")),
            "neighborhood": clean_text(p.get("NEIGHBORHOOD")), "cra": clean_text(p.get("CRA")),
            "council_district": clean_text(p.get("COUNCIL")), "opened_date": iso_date(p.get("OPENED_DATE")),
            "status_date": iso_date(p.get("TASK_STATUS_DATE")), "planned_start_date": "", "planned_end_date": "",
            "last_updated": iso_date(p.get("LASTUPDATE")), "new_construction_sqft": "", "housing_units": 1,
            "estimated_cost_usd": "", "actual_cost_usd": "", "funding_source": "", "is_public": "",
            "physical_development_candidate": 1, "source_url": "https://aca-prod.accela.com/TAMPA/Default.aspx",
        }
    else:
        status = clean_text(p.get("APPSTATUS"))
        stage, evidence, confidence = classify_stage(status, source)
        row = {
            "project_name": clean_text(p.get("RECORDALIAS")), "description": "",
            "activity_class": "planning_application" if source == "development_coordination" else "historic_preservation_application",
            "record_type": clean_text(p.get("RECORDALIAS")), "address": clean_text(p.get("ADDRESS")),
            "unit": clean_text(p.get("UNIT")), "zip": "", "neighborhood": clean_text(p.get("NEIGHBORHOOD")),
            "cra": clean_text(p.get("CRA")), "council_district": clean_text(p.get("COUNCILDISTRICT")),
            "opened_date": iso_date(p.get("CREATEDDATE")), "status_date": iso_date(p.get("LASTUPDATE")),
            "planned_start_date": "", "planned_end_date": "", "last_updated": iso_date(p.get("LASTUPDATE")),
            "new_construction_sqft": "", "housing_units": "", "estimated_cost_usd": "", "actual_cost_usd": "",
            "funding_source": "", "is_public": "", "physical_development_candidate": 0,
            "source_url": clean_text(p.get("URL")),
        }

    stable_group = "permit" if source in {"construction_inspections", "single_family_permits"} else source
    digest = hashlib.sha1(f"{stable_group}|{native_id}".encode()).hexdigest()[:12]
    return {
        "project_id": f"tpa-{digest}", "source_memberships": source,
        "source_record_id": native_id, "activity_stage": stage, "status": status,
        "latitude": lat, "longitude": lon, "completion_evidence": evidence,
        "evidence_confidence": confidence, "source_endpoint": cfg["url"],
        "retrieved_at_utc": retrieved_at, "_priority": cfg["priority"], **row,
    }


def merge_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["project_id"])].append(row)
    merged = []
    for _, candidates in grouped.items():
        candidates.sort(key=lambda r: int(r["_priority"]), reverse=True)
        base = dict(candidates[0])
        base["source_memberships"] = ";".join(sorted({str(r["source_memberships"]) for r in candidates}))
        base["raw_component_rows"] = len(candidates)
        for other in candidates[1:]:
            for col in COLUMNS:
                if base.get(col) in (None, "") and other.get(col) not in (None, ""):
                    base[col] = other[col]
        # A richer construction row can report zero units while the dedicated
        # single-family layer supplies the defensible one-potential-unit signal.
        numeric_units = [r.get("housing_units") for r in candidates if isinstance(r.get("housing_units"), (int, float))]
        if numeric_units:
            base["housing_units"] = max(numeric_units)
        base.pop("_priority", None)
        merged.append(base)
    return sorted(merged, key=lambda r: (str(r["activity_class"]), str(r["source_record_id"])))


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str] = COLUMNS) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_dictionary(path: Path) -> None:
    definitions = {
        "project_id": "Stable SHA-1-derived identifier; exact permit IDs shared across source layers are merged.",
        "source_memberships": "Semicolon-separated normalized source names contributing to the row.",
        "raw_component_rows": "Number of raw source rows merged into this centralized row.",
        "physical_development_candidate": "1 if the official record describes construction/demolition or an active/closed CIP; not proof visible work occurred.",
        "completion_evidence": "What the official source proves: application, authorization, status, or completion/closeout status.",
        "evidence_confidence": "Low/medium assessment of whether physical work occurred; no row is high without independent completion/remote-sensing verification.",
        "estimated_cost_usd": "City CIP estimated cost. Blank for permits because the open layers do not publish valuation.",
        "actual_cost_usd": "City CIP actual cost when published; blank is unknown, not zero.",
        "is_public": "1 for City capital projects; blank for permit/application rows because ownership sector is not established by these layers.",
        "housing_units": "Reported project units, or 1 for a single-family permit record; not a verified net housing-unit addition.",
        "new_construction_sqft": "New-construction square feet reported in the Construction Inspections layer.",
    }
    rows = [{"field": c, "definition": definitions.get(c, c.replace("_", " ").capitalize())} for c in COLUMNS]
    write_csv(path, rows, ["field", "definition"])


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for r in rows:
        groups[(str(r.get("neighborhood") or "Unknown"), str(r.get("activity_class") or "Unknown"))].append(r)
    out = []
    for (neighborhood, activity), items in sorted(groups.items()):
        def total(field: str) -> float:
            return sum(float(x[field]) for x in items if isinstance(x.get(field), (int, float)))
        out.append({
            "neighborhood": neighborhood, "activity_class": activity, "project_count": len(items),
            "physical_candidate_count": sum(int(x.get("physical_development_candidate") or 0) for x in items),
            "new_construction_sqft": total("new_construction_sqft"), "housing_units": total("housing_units"),
            "estimated_cost_usd": total("estimated_cost_usd"), "actual_cost_usd": total("actual_cost_usd"),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(Path(__file__).with_name("data")))
    args = parser.parse_args()
    root = Path(args.output_dir)
    raw_dir, processed_dir, docs_dir = root / "raw", root / "processed", root.parent / "docs"
    for d in (raw_dir, processed_dir, docs_dir):
        d.mkdir(parents=True, exist_ok=True)

    retrieved = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    all_rows: list[dict[str, object]] = []
    counts = {}
    for name, cfg in SOURCES.items():
        collection = fetch_layer(str(cfg["url"]))
        (raw_dir / f"{name}.geojson").write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
        counts[name] = len(collection["features"])
        all_rows.extend(normalize(name, f, retrieved) for f in collection["features"])

    central = merge_rows(all_rows)
    candidates = [r for r in central if int(r["physical_development_candidate"]) == 1]
    write_csv(processed_dir / "tampa_development_activity.csv", central)
    write_csv(processed_dir / "tampa_physical_development_candidates.csv", candidates)
    summary = summarize(central)
    write_csv(processed_dir / "tampa_neighborhood_summary.csv", summary, list(summary[0]) if summary else [])
    write_dictionary(docs_dir / "data_dictionary.csv")

    qa = {
        "retrieved_at_utc": retrieved,
        "raw_record_counts": counts,
        "raw_total": sum(counts.values()),
        "central_rows_after_exact_id_deduplication": len(central),
        "exact_rows_merged": len(all_rows) - len(central),
        "physical_development_candidates": len(candidates),
        "missing_coordinates": sum(not r["latitude"] or not r["longitude"] for r in central),
        "duplicate_project_ids": len(central) - len({r["project_id"] for r in central}),
        "activity_class_counts": dict(Counter(str(r["activity_class"]) for r in central)),
        "status_counts": dict(Counter(str(r["status"]) for r in central)),
        "warnings": [
            "Permit issuance is authorization, not proof that construction started or finished.",
            "CIP cost fields are not comparable to absent permit valuation fields.",
            "Blank numeric values mean unknown and are not zero.",
            "The physical-candidate file is a research queue, not a verified inventory of built development.",
        ],
    }
    (docs_dir / "qa_report.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    manifest = {
        "title": "City of Tampa Centralized Development Activity Dataset",
        "version": "0.1.0", "retrieved_at_utc": retrieved, "geography": "City of Tampa, Florida",
        "license_note": "Check each City of Tampa source's terms before redistribution; preserve source attribution.",
        "sources": [{"name": k, "endpoint": v["url"], "raw_records": counts[k]} for k, v in SOURCES.items()],
        "outputs": [
            "data/processed/tampa_development_activity.csv",
            "data/processed/tampa_physical_development_candidates.csv",
            "data/processed/tampa_neighborhood_summary.csv",
            "docs/data_dictionary.csv", "docs/qa_report.json",
        ],
    }
    (root.parent / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    main()
