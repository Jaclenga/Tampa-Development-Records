#!/usr/bin/env python3
"""Verify the released tables against the bundled City of Tampa snapshots.

This program tests source fidelity, lineage, geometry calculations, counts,
dates, amount provenance, and file integrity. It does not treat those tests as
ground-truth evidence that a development started or finished.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CONTEXT_RAW = ROOT / "data" / "context" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORT = ROOT / "reports" / "validation" / "accuracy_verification_report.json"

ENDPOINTS = {
    "construction_inspections": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/30",
    "development_coordination": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/31",
    "single_family_permits": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/32",
    "historic_preservation": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/33",
    "capital_improvements": "https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0",
    "capital_locations_point": "https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/0",
    "capital_locations_line": "https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/1",
    "capital_locations_polygon": "https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/2",
}

BLOCKED_FIELDS = {
    "pocname", "pocphone", "pocemail", "creator", "editor", "lasteditor",
    "created", "last_edited_user", "created_user",
}
INVALID_IDS = {"", "N/A", "NA", "NONE", "NULL", "UNKNOWN", "0000000", "0", "-"}


def read_csv(name: str) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with (PROCESSED / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha1(value: str, length: int) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def native_id(source: str, properties: dict) -> str:
    if source in {"construction_inspections", "single_family_permits"}:
        return clean(properties.get("RECORD_ID"))
    if source in {"development_coordination", "historic_preservation"}:
        return clean(properties.get("RECORDID"))
    return clean(properties.get("projid"))


def source_key(source: str, properties: dict) -> str:
    native = native_id(source, properties)
    token = f"{source}|{properties.get('OBJECTID')}|{properties.get('GlobalID', '')}|{native}"
    return f"src-{sha1(token, 16)}"


def scrub(properties: dict) -> dict:
    return {key: value for key, value in properties.items() if key.lower() not in BLOCKED_FIELDS}


def geometry_points(geometry: dict | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []

    def visit(value: object) -> None:
        if isinstance(value, list) and len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
            points.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for child in value:
                visit(child)

    if geometry:
        visit(geometry.get("coordinates"))
    return points


def centroid(geometry: dict | None) -> tuple[str, str]:
    points = geometry_points(geometry)
    if not points:
        return "", ""
    return f"{sum(y for _, y in points) / len(points):.7f}", f"{sum(x for x, _ in points) / len(points):.7f}"


def parse_date(value: str) -> bool:
    if not value:
        return True
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def live_inventory(endpoint: str) -> dict:
    params = urllib.parse.urlencode({"where": "1=1", "returnIdsOnly": "true", "f": "json"})
    request = urllib.request.Request(f"{endpoint}/query?{params}", headers={"User-Agent": "tampa-development-verifier/0.6"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message", "ArcGIS query failed"))
    ids = payload.get("objectIds") or []
    return {"object_id_field": payload.get("objectIdFieldName", "OBJECTID"), "count": len(ids), "object_ids": sorted(ids)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Also compare snapshot OBJECTIDs with the layers as they exist now.")
    parser.add_argument("--report", type=Path, default=REPORT, help="JSON report path.")
    parser.add_argument(
        "--deterministic-report",
        action="store_true",
        help="Omit the volatile verification timestamp; the run manifest records execution time.",
    )
    args = parser.parse_args()

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    sources = read_csv("source_records.csv")
    locations = read_csv("activity_locations.csv")
    bounded = read_csv("bounded_census_records.csv")
    universes = read_csv("source_universes.csv")
    activities = read_csv("tampa_development_activity.csv")
    links = read_csv("activity_source_links.csv")
    amounts = read_csv("investment_amounts.csv")
    manual = read_csv("manual_validation_sample.csv")
    review2 = read_csv("manual_validation_second_review.csv")

    source_by_key = {row["source_record_key"]: row for row in sources}
    location_by_key = {row["source_record_key"]: row for row in locations}
    bounded_by_key = {row["source_record_key"]: row for row in bounded}
    activities_by_id = {row["activity_id"]: row for row in activities}
    raw_counts: Counter[str] = Counter()
    mismatches: Counter[str] = Counter()
    raw_keys: set[str] = set()
    source_object_ids: dict[str, list[int]] = {name: [] for name in ENDPOINTS}

    for source, endpoint in ENDPOINTS.items():
        collection = json.loads((RAW / f"{source}.geojson").read_text(encoding="utf-8"))
        if collection.get("type") != "FeatureCollection":
            mismatches["invalid_geojson_collection"] += 1
        features = collection.get("features", [])
        raw_counts[source] = len(features)
        for feature in features:
            properties = feature.get("properties") or {}
            geometry = feature.get("geometry")
            key = source_key(source, properties)
            raw_keys.add(key)
            if isinstance(properties.get("OBJECTID"), int):
                source_object_ids[source].append(properties["OBJECTID"])
            source_row = source_by_key.get(key)
            location = location_by_key.get(key)
            census_row = bounded_by_key.get(key)
            if source_row is None:
                mismatches["raw_feature_missing_from_source_records"] += 1
                continue
            if location is None:
                mismatches["raw_feature_missing_from_locations"] += 1
            if census_row is None:
                mismatches["raw_feature_missing_from_bounded_census"] += 1
            if source_row["source_name"] != source or source_row["source_endpoint"] != endpoint:
                mismatches["source_name_or_endpoint"] += 1
            if source_row["source_record_id"] != native_id(source, properties):
                mismatches["native_record_id"] += 1
            if source_row["source_object_id"] != clean(properties.get("OBJECTID")):
                mismatches["object_id"] += 1
            if source_row["source_global_id"] != clean(properties.get("GlobalID")):
                mismatches["global_id"] += 1
            try:
                saved_properties = json.loads(source_row["properties_json"])
            except json.JSONDecodeError:
                saved_properties = None
            if saved_properties != scrub(properties):
                mismatches["source_properties"] += 1
            if location:
                expected_geometry = json.dumps(geometry, separators=(",", ":")) if geometry else ""
                expected_lat, expected_lon = centroid(geometry)
                if location["geometry_geojson"] != expected_geometry:
                    mismatches["geometry"] += 1
                if location["geometry_type"] != (geometry or {}).get("type", ""):
                    mismatches["geometry_type"] += 1
                if location["latitude"] != expected_lat or location["longitude"] != expected_lon:
                    mismatches["geometry_centroid"] += 1
                if location["activity_id"] != source_row["activity_id"]:
                    mismatches["source_location_activity_link"] += 1
            if census_row:
                copied = {
                    "source_name": source_row["source_name"], "source_record_id": source_row["source_record_id"],
                    "source_object_id": source_row["source_object_id"], "source_global_id": source_row["source_global_id"],
                    "activity_id": source_row["activity_id"], "source_endpoint": source_row["source_endpoint"],
                    "retrieved_at_utc": source_row["retrieved_at_utc"], "properties_json": source_row["properties_json"],
                    "geometry_type": location["geometry_type"] if location else "",
                    "geometry_geojson": location["geometry_geojson"] if location else "",
                }
                if any(census_row[field] != value for field, value in copied.items()):
                    mismatches["bounded_census_copy"] += 1

    manifest_hash_failures = []
    for item in manifest.get("bundled_source_files", []):
        path = ROOT / item["path"]
        actual = sha256_file(path) if path.exists() else None
        if actual != item["sha256"]:
            manifest_hash_failures.append({"path": item["path"], "expected": item["sha256"], "actual": actual})
    context_manifest_hash_failures = []
    for item in manifest.get("bundled_context_files", []):
        path = ROOT / item["path"]
        actual = sha256_file(path) if path.exists() else None
        if actual != item["sha256"]:
            context_manifest_hash_failures.append({
                "path": item["path"], "expected": item["sha256"], "actual": actual,
            })

    universe_by_source = {row["source_name"]: row for row in universes}
    universe_count_errors = {
        source: {
            "raw": count,
            "declared_raw": int(universe_by_source.get(source, {}).get("raw_feature_count", -1)),
            "included": sum(row["source_name"] == source for row in bounded),
            "declared_included": int(universe_by_source.get(source, {}).get("included_record_count", -1)),
        }
        for source, count in raw_counts.items()
        if source not in universe_by_source
        or count != int(universe_by_source[source]["raw_feature_count"])
        or sum(row["source_name"] == source for row in bounded) != int(universe_by_source[source]["included_record_count"])
    }

    date_fields = ("record_created_date", "application_or_opened_date", "status_date", "planned_start_date", "planned_end_date", "last_updated")
    invalid_dates = [
        {"activity_id": row["activity_id"], "field": field, "value": row[field]}
        for row in activities for field in date_fields if not parse_date(row.get(field, ""))
    ]
    invalid_coordinates = [
        row["location_id"] for row in locations
        if bool(row["latitude"]) != bool(row["longitude"])
        or (row["latitude"] and not (math.isfinite(float(row["latitude"])) and math.isfinite(float(row["longitude"]))))
    ]
    privacy_leaks = [
        row["source_record_key"] for row in sources
        if any(key.lower() in BLOCKED_FIELDS for key in json.loads(row["properties_json"]))
    ]
    raw_privacy_leaks = []
    for source in ENDPOINTS:
        collection = json.loads((RAW / f"{source}.geojson").read_text(encoding="utf-8"))
        for feature in collection.get("features", []):
            for key in (feature.get("properties") or {}):
                if key.lower() in BLOCKED_FIELDS:
                    raw_privacy_leaks.append(f"{source}:{key}")
    context_blocked_fields = {
        "owner", "addr_1", "addr_2", "city", "state", "zip", "country",
        "legal1", "legal2", "legal3", "legal4", "dba", "pocname", "pocphone",
        "pocemail", "creator", "editor", "created_user", "last_edited_user", "fundcomm",
    }
    context_privacy_leaks = []
    for path in CONTEXT_RAW.glob("*.geojson"):
        collection = json.loads(path.read_text(encoding="utf-8"))
        for feature in collection.get("features", []):
            for key in (feature.get("properties") or {}):
                if key.lower() in context_blocked_fields:
                    context_privacy_leaks.append(f"{path.name}:{key}")
    broken_links = [row for row in links if row["activity_id"] not in activities_by_id or row["source_record_key"] not in source_by_key]

    amount_errors = []
    for row in amounts:
        activity = activities_by_id.get(row["activity_id"])
        field = "estimated_cost_usd" if row["amount_type"] == "city_capital_project_estimated_cost" else "actual_cost_usd"
        if not activity or not activity.get(field) or abs(float(activity[field]) - float(row["amount_usd"])) > 0.005:
            amount_errors.append(row["amount_id"])

    manual_reviewed = sum(bool(row.get("reviewed_at_utc")) for row in manual)
    double_reviewed = sum(bool(row.get("reviewer_2_reviewed_at_utc")) for row in review2)
    checks = {
        "all_raw_features_have_source_rows": raw_keys == set(source_by_key),
        "all_raw_features_have_locations": raw_keys == set(location_by_key),
        "all_raw_features_have_bounded_rows": raw_keys == set(bounded_by_key),
        "raw_to_processed_fields_match": not mismatches,
        "manifest_source_hashes_match": not manifest_hash_failures,
        "manifest_context_hashes_match": not context_manifest_hash_failures,
        "source_universe_counts_reconcile": not universe_count_errors,
        "activity_and_source_links_resolve": not broken_links and len(links) == len(sources),
        "activity_dates_are_iso_dates": not invalid_dates,
        "coordinates_are_finite_pairs": not invalid_coordinates,
        "configured_private_contact_fields_are_absent": not privacy_leaks,
        "raw_snapshots_are_privacy_minimized": not raw_privacy_leaks,
        "context_snapshots_are_privacy_minimized": not context_privacy_leaks,
        "investment_amount_rows_match_activity_fields": not amount_errors,
    }

    live = {"status": "not_requested", "layers": {}}
    if args.live:
        live["status"] = "checked"
        for source, endpoint in ENDPOINTS.items():
            try:
                current = live_inventory(endpoint)
                snapshot_ids = sorted(source_object_ids[source])
                live["layers"][source] = {
                    "status": "unchanged" if current["object_ids"] == snapshot_ids else "changed_since_snapshot",
                    "snapshot_count": len(snapshot_ids), "current_count": current["count"],
                    "added_object_ids": sorted(set(current["object_ids"]) - set(snapshot_ids)),
                    "removed_object_ids": sorted(set(snapshot_ids) - set(current["object_ids"])),
                }
            except Exception as exc:  # live availability must not invalidate an archived snapshot
                live["layers"][source] = {"status": "query_failed", "error": str(exc)}
        if any(row["status"] == "query_failed" for row in live["layers"].values()):
            live["status"] = "partially_checked"

    report = {
        "dataset_version": manifest.get("version"),
        "verified_at_utc": (
            None if args.deterministic_report
            else dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        ),
        "machine_verification_passed": all(checks.values()),
        "source_snapshot_fidelity": "verified" if all(checks.values()) else "failed",
        "ground_truth_status": "not_established",
        "ground_truth_note": "Passing checks show that the released rows accurately reproduce the bundled public-source snapshots and programmed transformations. They do not prove that physical work occurred, that records form unique projects, or that all Tampa development is present.",
        "checks": checks,
        "counts": {
            "raw_features": sum(raw_counts.values()), "source_records": len(sources),
            "bounded_census_records": len(bounded), "activities": len(activities),
            "manual_sample_rows": len(manual), "manually_reviewed_rows": manual_reviewed,
            "double_review_assignment_rows": len(review2), "double_reviewed_rows": double_reviewed,
        },
        "raw_feature_counts": dict(raw_counts),
        "mismatch_counts": dict(mismatches),
        "manifest_hash_failures": manifest_hash_failures,
        "context_manifest_hash_failures": context_manifest_hash_failures,
        "universe_count_errors": universe_count_errors,
        "invalid_dates": invalid_dates[:100],
        "invalid_coordinate_ids": invalid_coordinates[:100],
        "privacy_leak_record_keys": privacy_leaks[:100],
        "raw_privacy_leak_fields": raw_privacy_leaks[:100],
        "context_privacy_leak_fields": context_privacy_leaks[:100],
        "broken_link_count": len(broken_links),
        "amount_error_ids": amount_errors[:100],
        "live_source_comparison": live,
        "interpretation": {
            "verified": [
                "Every bundled source feature is represented once in the source and bounded-census tables.",
                "Retained source properties and geometries match the bundled GeoJSON after documented field suppression.",
                "Identifiers, source lineage, centroids, counts, dates, hashes, and extracted amount rows satisfy the coded rules.",
            ],
            "not_verified": [
                "Whether each record represents one distinct real-world development.",
                "Whether construction started or was completed.",
                "Whether building-footprint matches are correct.",
                "Whether the eight layers contain all Tampa development or investment.",
            ],
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["machine_verification_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
