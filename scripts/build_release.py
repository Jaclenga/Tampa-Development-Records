#!/usr/bin/env python3
"""Build the Tampa published-development source-bounded census release.

This orchestrates the official Tampa GIS extraction, preserves every source
feature and geometry, constructs activity records without merging placeholder
IDs, and enriches building-related records with City building footprints and
HCPA parcel centroids. It intentionally does not call permits "completed"
unless a stronger public-data signal supports that interpretation.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import math
import re
import struct
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
DOCS = ROOT / "docs"
CACHE = ROOT / ".cache" / "source_cache"
RELEASE_VERSION = "0.7.0"
DATASET_TITLE = "Tampa Published Development Records: Source-Bounded Census"
PUBLIC_ARCHIVE = ROOT / "dist" / f"tampa_source_bounded_census_v{RELEASE_VERSION}.zip"

PRIVACY_BLOCKED_FIELDS = {
    "pocname", "pocphone", "pocemail", "creator", "editor", "lasteditor",
    "created", "last_edited_user", "created_user",
}

INVALID_IDS = {"", "N/A", "NA", "NONE", "NULL", "UNKNOWN", "0000000", "0", "-"}
BUILDING_SOURCE = "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Location/MapServer/0"
CITYWIDE_CIP = "https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer"

EXTRA_CIP = {
    "capital_locations_point": (f"{CITYWIDE_CIP}/0", "Points"),
    "capital_locations_line": (f"{CITYWIDE_CIP}/1", "Polylines"),
    "capital_locations_polygon": (f"{CITYWIDE_CIP}/2", "Polygons"),
}


def load_legacy_module():
    spec = importlib.util.spec_from_file_location("tampa_legacy", SCRIPTS / "build_tampa_development.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(value: str, length: int = 14) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_hcpa_latlon() -> None:
    archive = CACHE / "hcpa_latlon.zip"
    table = CACHE / "hcpa_tables" / "latlon.dbf"
    if not archive.exists():
        subprocess.run([
            sys.executable, str(SCRIPTS / "download_hcpa.py"), r"^LatLon_Table_.*\.zip", str(archive)
        ], check=True)
    if not table.exists():
        table.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            member = next(name for name in bundle.namelist() if name.lower().endswith("latlon.dbf"))
            with bundle.open(member) as source, table.open("wb") as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_id(value: object) -> str:
    return clean(value).upper()


def valid_native_id(value: object) -> bool:
    return canonical_id(value) not in INVALID_IDS


def safe_date(value: str) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        year = int(text[:4])
        return text if 2000 <= year <= dt.date.today().year + 5 else ""
    except ValueError:
        return ""


def get_json(url: str, params: dict[str, object] | None = None, post: bool = False) -> dict:
    encoded = urllib.parse.urlencode(params or {})
    if post:
        request = urllib.request.Request(url, data=encoded.encode(), headers={"User-Agent": "tampa-development-dataset/0.2"})
    else:
        request = urllib.request.Request(url + ("?" + encoded if encoded else ""), headers={"User-Agent": "tampa-development-dataset/0.2"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def fetch_arcgis_layer(url: str) -> dict:
    features: list[dict] = []
    offset = 0
    while True:
        page = get_json(f"{url}/query", {
            "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": 4326,
            "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": "OBJECTID", "f": "geojson",
        })
        batch = page.get("features", [])
        features.extend(batch)
        if len(batch) < 2000:
            break
        offset += len(batch)
    return {"type": "FeatureCollection", "features": features}


def geometry_points(geometry: dict | None) -> list[tuple[float, float]]:
    if not geometry:
        return []
    coords = geometry.get("coordinates")
    if coords is None:
        return []
    out: list[tuple[float, float]] = []

    def visit(obj: object) -> None:
        if isinstance(obj, list) and len(obj) >= 2 and all(isinstance(x, (int, float)) for x in obj[:2]):
            out.append((float(obj[0]), float(obj[1])))
        elif isinstance(obj, list):
            for child in obj:
                visit(child)

    visit(coords)
    return out


def geometry_centroid(geometry: dict | None) -> tuple[str, str]:
    points = geometry_points(geometry)
    if not points:
        return "", ""
    lon = sum(x for x, _ in points) / len(points)
    lat = sum(y for _, y in points) / len(points)
    return f"{lat:.7f}", f"{lon:.7f}"


def native_id_for(source: str, props: dict) -> str:
    if source in {"construction_inspections", "single_family_permits"}:
        return clean(props.get("RECORD_ID"))
    if source in {"development_coordination", "historic_preservation"}:
        return clean(props.get("RECORDID"))
    return clean(props.get("projid"))


def activity_key(source: str, props: dict) -> tuple[str, str]:
    native = native_id_for(source, props)
    if source in {"construction_inspections", "single_family_permits"}:
        group = "permit"
    elif source.startswith("capital_") or source == "capital_improvements":
        # Capital layers use overlapping numeric and department-specific ID
        # namespaces. Keep source namespaces separate here, then reconcile
        # exact project titles across layers in cluster_capital_activities().
        group = source
    else:
        group = source
    if valid_native_id(native):
        token = canonical_id(native)
        if source.startswith("capital_") or source == "capital_improvements":
            title = re.sub(r"[^A-Z0-9]+", " ", canonical_id(props.get("projname"))).strip()
            token = f"{token}|{title}"
    else:
        token = f"invalid-id|{source}|{props.get('OBJECTID')}|{props.get('GlobalID', '')}"
    return f"tpa-{sha(group + '|' + token)}", native


def source_record_key(source: str, props: dict, native: str) -> str:
    token = f"{source}|{props.get('OBJECTID')}|{props.get('GlobalID', '')}|{native}"
    return f"src-{sha(token, 16)}"


def scrub_properties(props: dict) -> dict:
    return {k: v for k, v in props.items() if k.lower() not in PRIVACY_BLOCKED_FIELDS}


def sanitize_raw_snapshots() -> dict[str, int]:
    """Remove contact and source-user fields before raw snapshots are redistributed."""
    removed: Counter[str] = Counter()
    for path in sorted(RAW.glob("*.geojson")):
        collection = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for feature in collection.get("features", []):
            properties = feature.get("properties") or {}
            for key in list(properties):
                if key.lower() in PRIVACY_BLOCKED_FIELDS:
                    if properties[key] not in (None, ""):
                        removed[key.lower()] += 1
                    del properties[key]
                    changed = True
        if changed:
            path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    return dict(sorted(removed.items()))


def write_csv(
    path: Path, rows: list[dict], columns: list[str] | None = None, *, lineterminator: str | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is None:
        columns = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        options = {"fieldnames": columns, "extrasaction": "ignore"}
        if lineterminator is not None:
            options["lineterminator"] = lineterminator
        writer = csv.DictWriter(handle, **options)
        writer.writeheader()
        writer.writerows(rows)


def validation_review_status() -> dict:
    """Summarize protocol-gated review completion without producing estimates."""
    try:
        from . import review_metrics
    except ImportError:  # Support direct execution from the scripts directory.
        import review_metrics

    result = {"protocol_version": "1.0.0", "random_seed": 20260823}
    all_ready = True
    for phase in ("development", "holdout"):
        first_path = PROCESSED / f"manual_validation_{phase}_sample.csv"
        second_path = PROCESSED / "manual_validation_second_review.csv"
        first = read_csv_path(first_path) if first_path.exists() else []
        second_all = read_csv_path(second_path) if second_path.exists() else []
        second = [row for row in second_all if row.get("sample_phase") == phase]
        first_complete = sum(review_metrics.is_complete(row) for row in first)
        second_complete = sum(review_metrics.is_complete(row) for row in second)
        ready = bool(first) and first_complete == len(first) and bool(second) and second_complete == len(second)
        all_ready = all_ready and ready
        result[phase] = {
            "first_reviews_complete": first_complete, "first_reviews_required": len(first),
            "second_reviews_complete": second_complete, "second_reviews_required": len(second),
            "ready_for_metrics": ready,
        }
    result["status"] = (
        "complete" if all_ready else
        "development_complete_holdout_pending" if result["development"]["ready_for_metrics"] else
        "pending_human_review"
    )
    return result


def read_csv_path(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_source_rows(legacy, retrieved: str) -> tuple[list[dict], list[dict], list[dict], dict[str, int]]:
    sources = {
        "construction_inspections": RAW / "construction_inspections.geojson",
        "development_coordination": RAW / "development_coordination.geojson",
        "single_family_permits": RAW / "single_family_permits.geojson",
        "historic_preservation": RAW / "historic_preservation.geojson",
        "capital_improvements": RAW / "capital_improvements.geojson",
        **{name: RAW / f"{name}.geojson" for name in EXTRA_CIP},
    }
    endpoints = {name: legacy.SOURCES[name]["url"] for name in legacy.SOURCES}
    endpoints.update({name: url for name, (url, _) in EXTRA_CIP.items()})
    priorities = {"capital_improvements": 60, "construction_inspections": 50, "single_family_permits": 40,
                  "capital_locations_point": 35, "capital_locations_line": 35, "capital_locations_polygon": 35,
                  "development_coordination": 20, "historic_preservation": 20}
    source_rows: list[dict] = []
    locations: list[dict] = []
    normalized: list[dict] = []
    counts: dict[str, int] = {}
    for source, path in sources.items():
        collection = json.loads(path.read_text(encoding="utf-8"))
        counts[source] = len(collection.get("features", []))
        for ordinal, feature in enumerate(collection.get("features", []), start=1):
            props = feature.get("properties", {})
            aid, native = activity_key(source, props)
            srk = source_record_key(source, props, native)
            normalize_as = "capital_improvements" if source.startswith("capital_locations_") else source
            row = legacy.normalize(normalize_as, feature, retrieved)
            row["activity_id"] = aid
            row["source_record_id"] = native
            row["source_memberships"] = source
            row["source_endpoint"] = endpoints[source]
            row["_priority"] = priorities[source]
            row["_source_record_key"] = srk
            row["record_created_date"] = safe_date(row.get("opened_date", ""))
            if source == "single_family_permits":
                row["application_or_opened_date"] = legacy.iso_date(props.get("OPENED_DATE"))
            elif source in {"development_coordination", "historic_preservation"}:
                row["application_or_opened_date"] = safe_date(row.get("opened_date", ""))
            else:
                row["application_or_opened_date"] = ""
            row["status_date"] = safe_date(row.get("status_date", ""))
            row["planned_start_date"] = safe_date(row.get("planned_start_date", ""))
            row["planned_end_date"] = safe_date(row.get("planned_end_date", ""))
            row["last_updated"] = safe_date(row.get("last_updated", ""))
            row.pop("project_id", None)
            normalized.append(row)

            geometry = feature.get("geometry")
            lat, lon = geometry_centroid(geometry)
            location_id = f"loc-{sha(srk + '|' + str(ordinal), 16)}"
            locations.append({
                "location_id": location_id, "activity_id": aid, "source_record_key": srk,
                "source_name": source, "source_record_id": native, "source_object_id": props.get("OBJECTID", ""),
                "geometry_type": (geometry or {}).get("type", ""), "latitude": lat, "longitude": lon,
                "address": clean(props.get("ADDRESS") or props.get("FULLADDRESS")),
                "unit": clean(props.get("UNIT")), "neighborhood": clean(props.get("NEIGHBORHOOD") or props.get("Neighborhood")),
                "cra": clean(props.get("CRA")), "council_district": clean(props.get("COUNCIL") or props.get("Council") or props.get("COUNCILDISTRICT")),
                "geometry_geojson": json.dumps(geometry, separators=(",", ":")) if geometry else "",
            })
            source_rows.append({
                "source_record_key": srk, "activity_id": aid, "source_name": source, "source_record_id": native,
                "source_object_id": props.get("OBJECTID", ""), "source_global_id": props.get("GlobalID", ""),
                "source_endpoint": endpoints[source], "retrieved_at_utc": retrieved,
                "properties_json": json.dumps(scrub_properties(props), ensure_ascii=False, separators=(",", ":")),
            })
    return normalized, source_rows, locations, counts


def canonical_project_name(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", canonical_id(value)).strip()


def cluster_capital_activities(
    normalized: list[dict], source_rows: list[dict], locations: list[dict]
) -> list[dict]:
    """Merge exact-name capital records across different City map layers.

    Department IDs and Citywide project IDs use different namespaces, so the
    same project otherwise appears as multiple normalized activities. Exact
    normalized title matching is restricted to groups present in at least two
    distinct capital layers. An alias table preserves every replaced ID.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    capital_rows = []
    for row in normalized:
        source = str(row.get("source_memberships", ""))
        key = canonical_project_name(row.get("project_name"))
        if source.startswith("capital_") and key:
            groups[key].append(row)
            capital_rows.append(row)

    parent: dict[str, str] = {row["activity_id"]: row["activity_id"] for row in capital_rows}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        lroot, rroot = find(left), find(right)
        if lroot != rroot:
            parent[max(lroot, rroot)] = min(lroot, rroot)

    for key, rows in groups.items():
        sources = {str(row["source_memberships"]) for row in rows}
        if len(sources) < 2:
            continue
        ids = sorted({row["activity_id"] for row in rows})
        for other in ids[1:]:
            union(ids[0], other)

    component_ids: dict[str, set[str]] = defaultdict(set)
    component_names: dict[str, set[str]] = defaultdict(set)
    for row in capital_rows:
        root = find(row["activity_id"])
        component_ids[root].add(row["activity_id"])
        component_names[root].add(canonical_project_name(row.get("project_name")))

    aliases: dict[str, dict] = {}
    for root, old_ids in component_ids.items():
        if len(old_ids) < 2:
            continue
        cluster_key = ";".join(sorted(component_names[root]))
        new_id = f"tpa-{sha('capital_connected_exact_names|' + cluster_key)}"
        for old_id in old_ids:
            aliases[old_id] = {
                "old_activity_id": old_id, "new_activity_id": new_id,
                "cluster_basis": "connected_exact_normalized_project_names_across_capital_layers",
                "cluster_key": cluster_key,
            }

    for row in normalized:
        if row["activity_id"] in aliases:
            row["activity_id"] = aliases[row["activity_id"]]["new_activity_id"]

    if aliases:
        for row in source_rows:
            if row["activity_id"] in aliases:
                row["activity_id"] = aliases[row["activity_id"]]["new_activity_id"]
        for row in locations:
            if row["activity_id"] in aliases:
                row["activity_id"] = aliases[row["activity_id"]]["new_activity_id"]
    return sorted(aliases.values(), key=lambda row: (row["new_activity_id"], row["old_activity_id"]))


def merge_activities(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["activity_id"]].append(row)
    out: list[dict] = []
    for aid, components in groups.items():
        components.sort(key=lambda r: int(r["_priority"]), reverse=True)
        base = dict(components[0])
        base["activity_id"] = aid
        base["source_memberships"] = ";".join(sorted({str(r["source_memberships"]) for r in components}))
        base["raw_component_rows"] = len(components)
        # Filled from distinct geometry values after the source-location table
        # is available. Multiple source layers can repeat the same point.
        base["location_count"] = ""
        for other in components[1:]:
            for key, value in other.items():
                if key.startswith("_"):
                    continue
                if base.get(key) in (None, "") and value not in (None, ""):
                    base[key] = value
        unit_values = [r.get("housing_units") for r in components if isinstance(r.get("housing_units"), (int, float))]
        if unit_values:
            base["housing_units"] = max(unit_values)
        # Cross-layer capital duplicates can expose zero in one geometry layer
        # and a nonzero amount in the authoritative project layer. Preserve the
        # strongest reported value without double-counting duplicate records.
        for field in ("estimated_cost_usd", "actual_cost_usd"):
            values = [float(r[field]) for r in components if isinstance(r.get(field), (int, float))]
            if values:
                strongest = max(values)
                base[field] = int(strongest) if strongest.is_integer() else strongest
        for key in list(base):
            if key.startswith("_"):
                base.pop(key)
        out.append(base)
    return sorted(out, key=lambda r: (str(r.get("activity_class")), str(r.get("source_record_id")), r["activity_id"]))


def normalize_address(value: object) -> str:
    text = canonical_id(value)
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    replacements = {" STREET ": " ST ", " AVENUE ": " AVE ", " ROAD ": " RD ", " BOULEVARD ": " BLVD ",
                    " DRIVE ": " DR ", " LANE ": " LN ", " COURT ": " CT ", " PLACE ": " PL ", " TERRACE ": " TER "}
    text = f" {re.sub(r'\s+', ' ', text).strip()} "
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1 - a)))


def bbox(geometry: dict) -> tuple[float, float, float, float]:
    points = geometry_points(geometry)
    return min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point[:2]
        xj, yj = ring[j][:2]
        if ((yi > lat) != (yj > lat)) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict) -> bool:
    coords = geometry.get("coordinates", [])
    polygons = [coords] if geometry.get("type") == "Polygon" else coords if geometry.get("type") == "MultiPolygon" else []
    for polygon in polygons:
        if polygon and point_in_ring(lon, lat, polygon[0]):
            if not any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
                return True
    return False


def fetch_nearby_buildings(points: list[tuple[float, float]]) -> dict:
    unique: dict[int, dict] = {}
    fields = "OBJECTID,STRAP,FOLIO,FULLADDRESS,YEAR_BUILT,GROSS_AREA,HEAT_AREA,RES_UNITS,COM_UNITS,FLOORCOUNT,BUILDINGID,LASTUPDATE"
    for start in range(0, len(points), 100):
        batch = points[start:start + 100]
        geometry = json.dumps({"points": [[lon, lat] for lon, lat in batch], "spatialReference": {"wkid": 4326}})
        page = get_json(f"{BUILDING_SOURCE}/query", {
            "where": "1=1", "geometry": geometry, "geometryType": "esriGeometryMultipoint",
            "spatialRel": "esriSpatialRelIntersects", "distance": 100, "units": "esriSRUnit_Meter",
            "outFields": fields, "returnGeometry": "true", "outSR": 4326, "f": "geojson",
        }, post=True)
        for feature in page.get("features", []):
            unique[int(feature["properties"]["OBJECTID"])] = feature
    return {"type": "FeatureCollection", "features": list(unique.values())}


def grid_key(lon: float, lat: float, step: float = 0.002) -> tuple[int, int]:
    return math.floor(lon / step), math.floor(lat / step)


def build_footprint_matches(activities: list[dict], locations: list[dict], refresh: bool = True) -> tuple[list[dict], dict]:
    by_activity = {a["activity_id"]: a for a in activities}
    relevant = []
    for loc in locations:
        activity = by_activity[loc["activity_id"]]
        if activity.get("activity_class") in {"building_construction", "single_family_new_construction_or_addition", "demolition"} and loc["latitude"] and loc["longitude"]:
            relevant.append(loc)
    points = sorted({(float(x["longitude"]), float(x["latitude"])) for x in relevant})
    footprint_snapshot = RAW / "matched_building_footprints.geojson"
    if refresh:
        collection = fetch_nearby_buildings(points)
        footprint_snapshot.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    else:
        if not footprint_snapshot.exists():
            raise FileNotFoundError("--use-existing-raw requires data/raw/matched_building_footprints.geojson")
        collection = json.loads(footprint_snapshot.read_text(encoding="utf-8"))

    index: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for feature in collection["features"]:
        geometry = feature.get("geometry") or {}
        if not geometry_points(geometry):
            continue
        xmin, ymin, xmax, ymax = bbox(geometry)
        feature["_bbox"] = (xmin, ymin, xmax, ymax)
        for gx in range(grid_key(xmin, ymin)[0], grid_key(xmax, ymax)[0] + 1):
            for gy in range(grid_key(xmin, ymin)[1], grid_key(xmax, ymax)[1] + 1):
                index[(gx, gy)].append(feature)

    matches: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for loc in relevant:
        lon, lat = float(loc["longitude"]), float(loc["latitude"])
        candidates: dict[int, dict] = {}
        gx, gy = grid_key(lon, lat)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for feature in index.get((gx + dx, gy + dy), []):
                    candidates[int(feature["properties"]["OBJECTID"])] = feature
        containing = [f for f in candidates.values() if point_in_geometry(lon, lat, f["geometry"])]
        target_addr = normalize_address(loc.get("address"))
        address_matches = [f for f in candidates.values() if target_addr and normalize_address(f["properties"].get("FULLADDRESS")) == target_addr]
        selected: list[tuple[dict, str, str, float]] = []
        if containing:
            selected = [(f, "point_in_building_footprint", "high", 0.0) for f in containing]
        elif address_matches:
            for f in address_matches:
                xmin, ymin, xmax, ymax = f["_bbox"]
                distance = haversine_m(lon, lat, (xmin + xmax) / 2, (ymin + ymax) / 2)
                if distance <= 150:
                    selected.append((f, "exact_address_nearby_footprint", "high", distance))
        else:
            ranked = []
            for f in candidates.values():
                xmin, ymin, xmax, ymax = f["_bbox"]
                distance = haversine_m(lon, lat, (xmin + xmax) / 2, (ymin + ymax) / 2)
                ranked.append((distance, f))
            if ranked and min(ranked)[0] <= 35:
                distance, f = min(ranked, key=lambda x: x[0])
                selected = [(f, "nearest_footprint_within_35m", "medium", distance)]
        for feature, method, confidence, distance in selected:
            props = feature["properties"]
            key = (loc["activity_id"], int(props["OBJECTID"]))
            if key in seen:
                continue
            seen.add(key)
            matches.append({
                "activity_id": loc["activity_id"], "location_id": loc["location_id"],
                "building_object_id": props.get("OBJECTID", ""), "folio": clean(props.get("FOLIO")),
                "strap": clean(props.get("STRAP")), "building_id": clean(props.get("BUILDINGID")),
                "building_address": clean(props.get("FULLADDRESS")), "year_built": props.get("YEAR_BUILT") or "",
                "gross_area_sqft": props.get("GROSS_AREA") or "", "heated_area_sqft": props.get("HEAT_AREA") or "",
                "residential_units": props.get("RES_UNITS") or "", "commercial_units": props.get("COM_UNITS") or "",
                "floor_count": props.get("FLOORCOUNT") or "", "match_method": method,
                "match_confidence": confidence, "match_distance_m": round(distance, 2),
                "building_source_endpoint": BUILDING_SOURCE,
            })
    return matches, collection


def read_dbf(path: Path):
    with path.open("rb") as handle:
        header = handle.read(32)
        count = struct.unpack("<I", header[4:8])[0]
        header_len = struct.unpack("<H", header[8:10])[0]
        record_len = struct.unpack("<H", header[10:12])[0]
        fields = []
        while handle.tell() < header_len - 1:
            descriptor = handle.read(32)
            if descriptor[0] == 13:
                break
            fields.append((descriptor[:11].split(b"\0", 1)[0].decode("ascii"), chr(descriptor[11]), descriptor[16]))
        handle.seek(header_len)
        for _ in range(count):
            record = handle.read(record_len)
            if not record or record[:1] == b"*":
                continue
            pos, row = 1, {}
            for name, _, length in fields:
                row[name] = record[pos:pos + length].decode("latin1").strip()
                pos += length
            yield row


def normalize_hcpa_folio(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return f"{digits[:-4]}.{digits[-4:]}" if len(digits) > 4 else value


def add_hcpa_centroid_fallback(matches: list[dict], activities: list[dict], locations: list[dict]) -> list[dict]:
    path = CACHE / "hcpa_tables" / "latlon.dbf"
    if not path.exists():
        return matches
    index: dict[tuple[int, int], list[tuple[float, float, str]]] = defaultdict(list)
    for row in read_dbf(path):
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except ValueError:
            continue
        index[grid_key(lon, lat, 0.005)].append((lon, lat, normalize_hcpa_folio(row["FOLIO"])))
    matched_activities = {m["activity_id"] for m in matches}
    by_activity = {a["activity_id"]: a for a in activities}
    seen = set(matched_activities)
    for loc in locations:
        aid = loc["activity_id"]
        if aid in seen or not loc["latitude"] or not loc["longitude"]:
            continue
        activity = by_activity[aid]
        if activity.get("activity_class") not in {"building_construction", "single_family_new_construction_or_addition", "demolition"}:
            continue
        lon, lat = float(loc["longitude"]), float(loc["latitude"])
        gx, gy = grid_key(lon, lat, 0.005)
        nearby = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for plon, plat, folio in index.get((gx + dx, gy + dy), []):
                    nearby.append((haversine_m(lon, lat, plon, plat), folio))
        if nearby and min(nearby)[0] <= 150:
            distance, folio = min(nearby)
            matches.append({
                "activity_id": aid, "location_id": loc["location_id"], "building_object_id": "",
                "folio": folio, "strap": "", "building_id": "", "building_address": "", "year_built": "",
                "gross_area_sqft": "", "heated_area_sqft": "", "residential_units": "", "commercial_units": "",
                "floor_count": "", "match_method": "nearest_hcpa_parcel_centroid_within_150m",
                "match_confidence": "low", "match_distance_m": round(distance, 2),
                "building_source_endpoint": "https://downloads.hcpafl.org/Default.aspx (LatLon table)",
            })
            seen.add(aid)
    return matches


def apply_matches_and_evidence(activities: list[dict], matches: list[dict]) -> None:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for match in matches:
        grouped[match["activity_id"]].append(match)
    for activity in activities:
        items = grouped.get(activity["activity_id"], [])
        activity["matched_folios"] = ";".join(sorted({clean(x["folio"]) for x in items if clean(x["folio"])}))
        buildings = {str(x["building_object_id"]) for x in items if x["building_object_id"] != ""}
        activity["matched_building_count"] = len(buildings) if items else ""
        years = [int(x["year_built"]) for x in items if str(x["year_built"]).isdigit()]
        activity["matched_year_built_min"] = min(years) if years else ""
        activity["matched_year_built_max"] = max(years) if years else ""
        activity["parcel_match_confidence"] = "high" if any(x["match_confidence"] == "high" for x in items) else "medium" if any(x["match_confidence"] == "medium" for x in items) else "low" if items else ""

        status = clean(activity.get("status")).lower()
        source = activity.get("source_memberships", "")
        activity_date = activity.get("application_or_opened_date") or activity.get("record_created_date") or ""
        permit_year = int(str(activity_date)[:4]) if re.match(r"^20\d{2}", str(activity_date)) else None
        consistent_new_build = bool(permit_year and years and max(years) >= permit_year - 1 and activity.get("activity_class") in {"building_construction", "single_family_new_construction_or_addition"})
        if any(x in status for x in ("cancel", "withdraw", "deny", "expire")):
            grade, realized, basis = "X", "", "inactive_official_status"
        elif consistent_new_build:
            grade, realized, basis = "D", "", "permit_plus_current_footprint_year_built_supporting_only"
        elif "capital_" in source and "closeout" in status:
            grade, realized, basis = "D", "", "city_capital_project_closeout_status_supporting_only"
        elif "capital_" in source and "construction" in status:
            grade, realized, basis = "C", "", "city_capital_project_construction_status"
        elif activity.get("activity_class") in {"planning_application", "historic_preservation_application"}:
            grade, realized, basis = "P", "", "planning_application_only"
        else:
            grade, realized, basis = "U", "", "insufficient_completion_evidence"
        activity["realization_evidence_grade"] = grade
        activity["likely_realized"] = realized
        activity["realization_basis"] = basis


def create_manual_validation_sample(activities: list[dict], matches: list[dict], target: int = 150) -> list[dict]:
    """Create the frozen, seeded study sample and blinded review assignment."""
    if target != 150:
        raise ValueError("Protocol 1.0.0 fixes the validation sample at 150 rows")
    try:
        from . import validation_study
    except ImportError:  # Support direct execution from the scripts directory.
        import validation_study

    rows, _ = validation_study.write_study_files(activities, matches)
    return rows


FIELD_METADATA = {
    "verification_id": ("Stable identifier for one externally checked pilot claim.", "text", "", "Never blank.", "verification workflow", "Assigned in the v0.4 external evidence audit.", "verify-*", "Pilot claims are not a population accuracy estimate."),
    "claim_tested": ("Specific dataset assertion compared with external public evidence.", "text", "", "Never blank.", "verification workflow", "Defined before evaluating the cited evidence.", "Free text.", "Only the stated claim was evaluated."),
    "dataset_value": ("Dataset value or assertion subjected to the external check.", "text", "", "Never blank.", "dataset snapshot", "Copied from the referenced activity.", "Free text.", "Interpret together with claim_tested."),
    "evidence_result": ("Outcome of comparing the stated claim with the cited evidence.", "categorical text", "", "Never blank.", "verification workflow", "Evidence review documented in VERIFICATION_REPORT.md.", "supported; contradicted; inconclusive", "Supported does not imply physical completion unless separately stated."),
    "evidence_type": ("Provenance category of the external evidence.", "categorical text", "", "Never blank.", "verification workflow", "Classified from the cited publisher/source.", "authoritative_city_page; authoritative_city_news; independent_city_data_mirror; third_party_permit_aggregation", "City pages can reflect the same administrative system as the GIS layer."),
    "evidence_url": ("Primary public URL supporting the verification judgment.", "URL", "", "Never blank.", "external evidence", "Public-source review.", "HTTP(S) URL.", "Web content can change after the review date."),
    "secondary_evidence_url": ("Optional second public URL used to corroborate the judgment.", "URL", "", "Blank means one evidence source was used.", "external evidence", "Public-source review.", "HTTP(S) URL.", "A second URL is not necessarily independent of the first."),
    "physical_realization_verified": ("Whether the cited evidence independently establishes physical work for this claim.", "categorical text", "", "Never blank.", "verification workflow", "Conservative evidence assessment.", "yes; partial; no; not_applicable; not_established", "Administrative closeout alone is recorded as not_established."),
    "review_method": ("Method and reviewer class used for the pilot check.", "text", "", "Never blank.", "verification provenance", "Recorded for the v0.4 audit.", "AI-assisted public-web evidence review", "This is not a blinded human ground-truth review."),
    "reviewed_at_utc": ("UTC date or timestamp of the evidence review.", "datetime", "UTC", "Blank in the untouched manual sample; populated in completed pilot checks.", "reviewer-entered", "ISO 8601 UTC value.", "ISO 8601 date or timestamp.", "Evidence may change later."),
    "verification_notes": ("Concise explanation of what the cited evidence does and does not establish.", "text", "", "Never blank.", "verification workflow", "Written during evidence review.", "Free text.", "Read before generalizing the result."),
    "old_activity_id": ("Activity identifier assigned before cross-layer capital-project clustering.", "text", "", "Never blank.", "derived identifier", "Pre-clustering activity_id.", "tpa-*", "Use new_activity_id for the current release."),
    "new_activity_id": ("Current activity identifier after verified exact-name cross-layer capital clustering.", "text", "", "Never blank.", "derived identifier", "Hash of the normalized capital-project name.", "tpa-*", "Several source records may map to this identifier."),
    "cluster_basis": ("Rule used to replace the old activity identifier.", "categorical text", "", "Never blank.", "derived", "Capital clustering rule.", "connected_exact_normalized_project_names_across_capital_layers", "This is deterministic entity resolution, not universal master-project clustering."),
    "cluster_key": ("Uppercase punctuation-normalized capital-project title used for clustering.", "text", "", "Never blank.", "derived", "canonical_project_name(project_name).", "Normalized title text.", "Exact-name matching can still under-merge title variants."),
    "activity_id": ("Stable identifier for one normalized activity record; not a guaranteed master-project identifier.", "text", "", "Never blank.", "derived identifier", "SHA-1-derived token from source family and native ID; invalid native IDs are isolated by source object.", "tpa-*", "Several activities may belong to one real development."),
    "source_record_key": ("Stable key for one source feature after privacy-field suppression.", "text", "", "Never blank.", "derived identifier", "Hash of source name, object/global IDs, and native record ID.", "src-*", "Identifies a source feature, not a development."),
    "location_id": ("Stable key for one preserved source geometry.", "text", "", "Never blank.", "derived identifier", "Hash of source-record key and source ordinal.", "loc-*", "An activity may have multiple locations."),
    "source_memberships": ("Semicolon-delimited source layers contributing to the normalized activity.", "text", "", "Never blank.", "derived", "Distinct source names linked by activity_id.", "Named source layers separated by semicolons.", "Membership does not establish completeness."),
    "source_name": ("Machine-readable name of the originating City GIS layer.", "text", "", "Never blank.", "source metadata", "Assigned from the extraction configuration.", "construction_inspections; development_coordination; single_family_permits; historic_preservation; capital_*", "Layer names describe source systems, not ground-truth stages."),
    "source_record_id": ("Native public record or project identifier supplied by the source, when available.", "text", "", "Blank means the source supplied no usable native identifier.", "source", "Source-specific record ID field.", "Source-defined.", "May be reused or missing in source data."),
    "source_object_id": ("ArcGIS OBJECTID for the source feature at retrieval time.", "integer", "", "Blank if the source omitted OBJECTID.", "source", "OBJECTID.", "Non-negative integer.", "ArcGIS OBJECTIDs are not guaranteed stable across republishing."),
    "source_global_id": ("ArcGIS GlobalID for the source feature, when supplied.", "text", "", "Blank if unavailable.", "source", "GlobalID.", "UUID-like source value.", "Source stability is not guaranteed by this dataset."),
    "source_endpoint": ("Official ArcGIS service endpoint used to retrieve the contributing record.", "URL", "", "Never blank for extracted records.", "source metadata", "Extraction configuration.", "HTTPS URL.", "Endpoint contents can change after the snapshot date."),
    "source_url": ("Public record or project-detail URL supplied by the source, when available.", "URL", "", "Blank means no record-level URL was supplied.", "source", "Source URL field.", "HTTP(S) URL.", "A URL may later move or expire."),
    "retrieved_at_utc": ("UTC timestamp when the source snapshot was assembled.", "datetime", "UTC", "Never blank.", "derived metadata", "Build timestamp.", "ISO 8601 timestamp.", "This is retrieval time, not activity time."),
    "properties_json": ("Source attributes serialized as JSON after configured contact/editor fields are removed.", "JSON text", "", "Blank only if a feature had no attributes.", "source snapshot", "All allowed source properties serialized without geometry.", "Valid JSON object.", "May contain other public attributes; inspect before person-level publication."),
    "project_name": ("Project or application name as reported by the source.", "text", "", "Blank means unavailable.", "source", "Source-specific project-name field.", "Source-defined.", "Names are not standardized across layers."),
    "description": ("Free-text project description reported by the source.", "text", "", "Blank means unavailable.", "source", "Source-specific description field.", "Source-defined.", "May be incomplete or use administrative language."),
    "activity_class": ("Normalized broad category assigned from source layer, record type, description, and reported square footage.", "categorical text", "", "Never blank.", "derived", "Rules in scripts/build_tampa_development.py.", "building_construction; demolition; other_permitted_work; planning_application; historic_preservation_application; public_capital:*; single_family_new_construction_or_addition", "Classification has not yet been manually accuracy-tested."),
    "activity_stage": ("Normalized procedural stage inferred from official status text and source type.", "categorical text", "", "Never blank.", "derived", "Status keyword rules in classify_stage().", "preconstruction_or_unknown; planning_review; permit_or_funding_approved; construction_or_inspection; completed_or_closeout; inactive", "A procedural stage does not prove physical completion."),
    "status": ("Status text reported by the source at retrieval.", "text", "", "Blank means unavailable.", "source", "Source-specific status field.", "Source-defined.", "Status semantics differ across sources."),
    "record_type": ("Permit, application, capital-project, or preservation record type reported by the source.", "text", "", "Blank means unavailable.", "source", "Source-specific record-type field.", "Source-defined.", "Not harmonized across source systems."),
    "address": ("Site address reported by the source.", "text", "", "Blank means unavailable.", "source", "ADDRESS or FULLADDRESS.", "Source-defined street address.", "Public but potentially sensitive; aggregate person-focused analyses."),
    "unit": ("Unit or suite reported by the source.", "text", "", "Blank means unavailable or not applicable.", "source", "UNIT.", "Source-defined.", "Can increase re-identification risk."),
    "zip": ("ZIP code reported by the source.", "text", "", "Blank means unavailable.", "source", "ZIP.", "Five-digit or source-defined text.", "Not independently geocoded or verified."),
    "neighborhood": ("City neighborhood label reported by the source.", "text", "", "Blank means unavailable.", "source", "NEIGHBORHOOD/Neighborhood.", "City-defined label.", "Not spatially recomputed against a boundary vintage."),
    "cra": ("Community Redevelopment Area label reported by the source.", "text", "", "Blank means outside a reported CRA or unavailable; these are not distinguishable.", "source", "CRA.", "City-defined label.", "Blank must not automatically be interpreted as outside all CRAs."),
    "council_district": ("City Council district reported by the source.", "text", "", "Blank means unavailable.", "source", "COUNCIL/COUNCILDISTRICT.", "Source-defined district.", "District boundaries and assignments can change."),
    "latitude": ("Latitude of the point feature or arithmetic centroid of the preserved source geometry.", "decimal", "degrees WGS84", "Blank means no geometry.", "source/derived geometry", "Point coordinate or average of geometry vertices.", "Approximately 27.5 to 28.3.", "Vertex-average centroids can fall outside complex line/polygon features."),
    "longitude": ("Longitude of the point feature or arithmetic centroid of the preserved source geometry.", "decimal", "degrees WGS84", "Blank means no geometry.", "source/derived geometry", "Point coordinate or average of geometry vertices.", "Approximately -83.0 to -82.0.", "Vertex-average centroids can fall outside complex line/polygon features."),
    "geometry_type": ("GeoJSON geometry type supplied by the source.", "categorical text", "", "Blank means no geometry.", "source", "geometry.type.", "Point; LineString; MultiLineString; Polygon; MultiPolygon.", "Geometry types vary by layer."),
    "geometry_geojson": ("Complete source geometry serialized as compact GeoJSON.", "JSON text", "", "Blank means no geometry.", "source", "Unmodified source geometry after WGS84 output request.", "Valid GeoJSON geometry object.", "Map geometry is not a legal survey."),
    "record_created_date": ("Date the source record was created, where available.", "date", "", "Blank means unavailable or an invalid sentinel date was removed.", "source/cleaned", "Source creation date restricted to plausible years.", "ISO 8601 date.", "Not necessarily the application or construction date."),
    "application_or_opened_date": ("Application/opened date only where the source field supports that interpretation.", "date", "", "Blank means unavailable or unsupported for that source.", "source/cleaned", "Source opened/application date restricted to plausible years.", "ISO 8601 date.", "Meanings still differ across source systems."),
    "status_date": ("Date associated with the reported status or last status update.", "date", "", "Blank means unavailable.", "source/cleaned", "Source status-date field.", "ISO 8601 date.", "Not a completion date unless explicitly supported by status."),
    "planned_start_date": ("Planned capital-project start date reported by the source.", "date", "", "Blank means unavailable or not applicable.", "source/cleaned", "planstart.", "ISO 8601 date.", "Planned dates may change and do not show actual starts."),
    "planned_end_date": ("Planned capital-project end date reported by the source.", "date", "", "Blank means unavailable or not applicable.", "source/cleaned", "planend.", "ISO 8601 date.", "Planned dates may change and do not show completion."),
    "last_updated": ("Latest update date exposed by the contributing source record.", "date", "", "Blank means unavailable.", "source/cleaned", "Source last-update field.", "ISO 8601 date.", "Does not identify which attribute changed."),
    "new_construction_sqft": ("New-construction square footage reported in the permit source.", "decimal", "square feet", "Blank means unavailable, not zero.", "source", "NEWCONSTRUCTIONSF.", "Non-negative number.", "Not independently verified; may not cover additions or all sources consistently."),
    "housing_units": ("Reported or assigned housing-unit count.", "decimal", "dwelling units", "Blank means unavailable, not zero.", "source/derived", "NBROFUNITS; single-family layer assigns one unit.", "Non-negative number.", "Single-family assignment is a rule, and values are not completion counts."),
    "estimated_cost_usd": ("Estimated project cost reported for City capital projects.", "decimal", "nominal USD", "Blank means unavailable, not zero.", "source", "estcost.", "Non-negative amount.", "Not available for most private permits and not comparable to realized expenditure."),
    "actual_cost_usd": ("Actual project cost value reported by the City capital-project viewer.", "decimal", "nominal USD", "Blank means unavailable; source zeros may also mean unavailable.", "source", "actcost.", "Non-negative amount.", "Only a small number of rows are nonzero; do not sum as total local investment."),
    "funding_source": ("Capital-project funding description reported by the source.", "text", "", "Blank means unavailable or not applicable.", "source", "fundsource.", "Source-defined.", "Categories are not standardized."),
    "is_public": ("Indicator that the activity is a City capital project.", "boolean/integer", "", "Blank means not classified by this field, not necessarily private.", "derived", "1 for capital-project source rows.", "1 or blank.", "Blank must not be interpreted as privately financed."),
    "physical_development_candidate": ("Rule-based flag for activities potentially involving physical construction or demolition.", "boolean/integer", "", "Never blank.", "derived", "Activity-class and stage rules.", "0; 1", "Candidate status is not proof that work occurred."),
    "raw_component_rows": ("Count of source features consolidated into this normalized activity.", "integer", "source records", "Never blank.", "derived", "Count of linked source records sharing activity_id.", "Positive integer.", "A count greater than one does not prove duplicate source records."),
    "location_count": ("Count of distinct nonblank source geometries linked to the activity.", "integer", "geometries", "Zero means no nonblank preserved geometry.", "derived", "Count of distinct geometry_geojson values by activity_id.", "Non-negative integer.", "Repeated identical geometries count once."),
    "matched_folios": ("Semicolon-delimited folio identifiers from matched City building-footprint records.", "text", "", "Blank means no folio-bearing City building match.", "derived from City layer", "Distinct FOLIO values across matches.", "Source-defined identifiers separated by semicolons.", "A spatial/address match is not a legal parcel join."),
    "matched_building_count": ("Number of distinct City building-footprint objects matched to the activity.", "integer", "buildings", "Blank means no match record.", "derived from City layer", "Distinct building_object_id values.", "Non-negative integer.", "Count depends on match rules and current footprint snapshot."),
    "matched_year_built_min": ("Minimum assessed year built among matched City building footprints.", "integer", "year", "Blank means unavailable.", "derived from City layer", "Minimum YEAR_BUILT across matches.", "Four-digit year.", "Assessment year can lag or represent an earlier structure."),
    "matched_year_built_max": ("Maximum assessed year built among matched City building footprints.", "integer", "year", "Blank means unavailable.", "derived from City layer", "Maximum YEAR_BUILT across matches.", "Four-digit year.", "Assessment year can lag or represent an earlier structure."),
    "parcel_match_confidence": ("Highest configured confidence among City building-footprint matches.", "categorical text", "", "Blank means no match.", "derived", "Maximum of match_confidence using high > medium.", "high; medium", "Confidence is rule-based and awaits manual accuracy measurement."),
    "realization_evidence_grade": ("Legacy activity-level evidence grade retained for compatibility; use activity_truth_status.verification_grade.", "categorical text", "", "Never blank.", "derived", "Conservative status rules; footprint and closeout signals cannot exceed D.", "C; D; P; X; U", "This field does not establish completion."),
    "likely_realized": ("Deprecated legacy realization flag; deliberately unpopulated in v0.5.", "boolean/integer", "", "Blank means unknown, not false.", "derived", "No longer assigned from footprint year or capital closeout.", "blank", "Use explicit truth outcomes and qualifying events instead."),
    "realization_basis": ("Machine-readable reason for the legacy evidence grade.", "categorical text", "", "Never blank.", "derived", "Evidence-rule branch used by apply_matches_and_evidence().", "Supporting/status rule name.", "Footprint/year and closeout bases are supporting evidence only."),
    "building_object_id": ("ArcGIS OBJECTID of the matched City building-footprint feature.", "integer", "", "Blank is not used in the City-only release.", "City building layer", "OBJECTID.", "Non-negative integer.", "OBJECTID may change if the service is republished."),
    "folio": ("Property folio identifier exposed by the matched City building-footprint layer.", "text", "", "Blank means unavailable.", "City building layer", "FOLIO.", "Source-defined.", "Not independently verified against the property appraiser parcel layer."),
    "strap": ("STRAP parcel identifier exposed by the matched City building-footprint layer.", "text", "", "Blank means unavailable.", "City building layer", "STRAP.", "Source-defined.", "Not a legal parcel determination."),
    "building_id": ("Building identifier exposed by the City building-footprint layer.", "text", "", "Blank means unavailable.", "City building layer", "BUILDINGID.", "Source-defined.", "Identifier stability is source-dependent."),
    "building_address": ("Address exposed by the matched City building-footprint feature.", "text", "", "Blank means unavailable.", "City building layer", "FULLADDRESS.", "Source-defined address.", "Public but potentially sensitive."),
    "year_built": ("Assessed year built exposed by the matched City building-footprint feature.", "integer", "year", "Blank means unavailable.", "City building layer", "YEAR_BUILT.", "Four-digit year.", "Can reflect assessment lag, renovation, or an earlier structure."),
    "gross_area_sqft": ("Gross building area exposed by the City building-footprint feature.", "decimal", "square feet", "Blank means unavailable.", "City building layer", "GROSS_AREA.", "Non-negative number.", "Definition may differ from permit square footage."),
    "heated_area_sqft": ("Heated building area exposed by the City building-footprint feature.", "decimal", "square feet", "Blank means unavailable.", "City building layer", "HEAT_AREA.", "Non-negative number.", "Assessment measure, not permit measure."),
    "residential_units": ("Residential-unit count exposed by the City building-footprint feature.", "decimal", "units", "Blank means unavailable.", "City building layer", "RES_UNITS.", "Non-negative number.", "Not independently verified."),
    "commercial_units": ("Commercial-unit count exposed by the City building-footprint feature.", "decimal", "units", "Blank means unavailable.", "City building layer", "COM_UNITS.", "Non-negative number.", "Not independently verified."),
    "floor_count": ("Floor count exposed by the City building-footprint feature.", "decimal", "floors", "Blank means unavailable.", "City building layer", "FLOORCOUNT.", "Non-negative number.", "Not independently verified."),
    "match_method": ("Rule that linked an activity location to a City building footprint.", "categorical text", "", "Never blank.", "derived", "Spatial containment, exact normalized address nearby, or nearest footprint threshold.", "point_in_building_footprint; exact_address_nearby_footprint; nearest_footprint_within_35m", "Methods await manual precision measurement."),
    "match_confidence": ("Configured confidence tier for the building match method.", "categorical text", "", "Never blank.", "derived", "High for containment/address; medium for nearest within 35 m.", "high; medium", "This is heuristic confidence, not an empirical probability."),
    "match_distance_m": ("Approximate distance between activity point and matched footprint reference point.", "decimal", "meters", "Never blank; containment uses zero.", "derived", "Haversine distance to footprint bounding-box center, except containment.", "Non-negative number.", "Distance to bounding-box center is not boundary distance."),
    "building_source_endpoint": ("Official City building-footprint service used for the match.", "URL", "", "Never blank.", "source metadata", "Configured building-layer endpoint.", "HTTPS URL.", "Service contents can change after retrieval."),
    "period": ("Benchmark reporting period label.", "text", "", "Never blank.", "source metadata", "Fiscal-year label from the cited utilization report.", "FY24; FY25", "Compared GIS count uses calendar-year creation dates."),
    "official_building_permits_issued_or_approved": ("City-reported total permits issued or approved in the fiscal year.", "integer", "permits", "Never blank.", "external official benchmark", "Value transcribed from cited City utilization report.", "Non-negative integer.", "Denominator includes permit categories absent from the GIS display layer."),
    "gis_construction_records_created_in_calendar_year": ("Count of extracted construction-layer activities with record-created year equal to the benchmark year.", "integer", "records", "Never blank.", "derived", "Count from construction_inspections source membership and record_created_date.", "Non-negative integer.", "Calendar-year numerator is not directly comparable to fiscal-year permit total."),
    "diagnostic_ratio_not_coverage_rate": ("GIS record count divided by official permit total, provided only to demonstrate denominator mismatch.", "decimal", "ratio", "Never blank.", "derived", "gis_construction_records_created_in_calendar_year / official_building_permits_issued_or_approved.", "0 to 1.", "Must not be reported as an estimated coverage rate."),
    "comparability": ("Explanation of why the two benchmark counts are not directly comparable.", "text", "", "Never blank.", "documentation", "Fixed release note.", "Free text.", "Read before using the diagnostic ratio."),
    "conclusion": ("Interpretive conclusion supported by the benchmark comparison.", "text", "", "Never blank.", "documentation", "Fixed release note.", "Free text.", "Does not quantify exact missingness."),
    "official_source": ("Official City URL supporting the benchmark total.", "URL", "", "Never blank.", "source metadata", "Utilization-report URL.", "HTTPS URL.", "Reports may be revised or moved."),
}


def metadata_for(field: str) -> tuple[str, str, str, str, str, str, str, str]:
    if field in FIELD_METADATA:
        return FIELD_METADATA[field]
    try:
        from . import bounded_census
    except ImportError:  # Support direct execution from the scripts directory.
        import bounded_census
    bounded_metadata = bounded_census.metadata_for(field)
    if bounded_metadata:
        return bounded_metadata
    try:
        from . import ground_truth
    except ImportError:  # Support direct execution from the scripts directory.
        import ground_truth
    ground_truth_metadata = ground_truth.metadata_for(field)
    if ground_truth_metadata:
        return ground_truth_metadata
    if field.startswith("audit_"):
        return ("Identifier or metadata for the manual-validation audit row.", "text", "", "Blank until human review where applicable.", "audit workflow", "See MANUAL_VALIDATION_PROTOCOL.md.", "Protocol-defined.", "Not a validation result until completed by a reviewer.")
    if field == "protocol_version":
        return ("Frozen validation-protocol version governing the row.", "text", "", "Never blank.", "validation study design", "validation_study.PROTOCOL_VERSION.", "Semantic version.", "Do not combine results governed by different protocol versions.")
    if field == "random_seed":
        return ("Integer seed used for the reproducible pseudo-random draw.", "integer", "", "Never blank.", "validation study design", "validation_study.RANDOM_SEED.", "20260823 for protocol 1.0.0.", "Changing the seed changes the sample.")
    if field == "sample_phase":
        return ("Role of the row in rule development or final evaluation.", "categorical text", "", "Never blank.", "validation study design", "Separate seeded draws.", "development; holdout", "Do not tune rules using holdout results.")
    if field == "stratum_population":
        return ("Number of eligible activities in the row's mutually exclusive stratum.", "integer", "activities", "Never blank.", "derived sampling frame", "Count after validation-study stratum assignment.", "Positive integer.", "Applies to the current release snapshot.")
    if field == "phase_sample_size":
        return ("Number drawn from this stratum for the row's phase.", "integer", "activities", "Never blank.", "validation study design", "Frozen phase-stratum quota.", "Positive integer.", "Use with stratum_population to recover inclusion probability.")
    if field == "selection_probability":
        return ("Phase-specific probability of selection within the stratum.", "decimal", "proportion", "Never blank.", "derived sampling design", "phase_sample_size / stratum_population.", "Greater than 0 and at most 1.", "Use phase-specific probabilities; do not combine phases for final inference.")
    if field == "sampling_weight":
        return ("Inverse phase-specific selection probability.", "decimal", "activities represented", "Never blank.", "derived sampling design", "stratum_population / phase_sample_size.", "At least 1.", "Needed for estimates across disproportionate strata.")
    if field == "sample_order":
        return ("Stable display order within the sample phase.", "integer", "", "Never blank.", "validation workflow", "Sequential order after the seeded draw.", "Positive integer.", "Not a random score and not an analysis weight.")
    if field == "physical_work_started_dataset":
        return ("Dataset's pre-review claim about whether physical work started.", "categorical text", "", "Never blank.", "derived", "Same rules as activity_truth_status.physical_work_started.", "yes; no; unknown; not_applicable", "This is the claim under review, not reviewer evidence.")
    if field in {"sampling_stratum", "match_methods", "match_distances_m"}:
        return ("Sampling or match context included to support manual review.", "text", "", "Blank when not applicable.", "derived audit context", "Created by create_manual_validation_sample().", "Protocol-defined.", "Context is not a human judgment.")
    if field == "review_status":
        return ("Reviewer workflow state for the row.", "categorical text", "", "Blank means not started.", "reviewer-entered", "See MANUAL_VALIDATION_PROTOCOL.md.", "in_progress; complete", "Metrics require complete plus all evidence gates.")
    if field.endswith("_result") and field in {
        "source_identity_result", "activity_classification_result", "cross_source_linkage_result",
        "status_interpretation_result", "building_footprint_match_result",
    }:
        return ("Human-review outcome for the named dataset claim.", "categorical text", "", "Blank means not yet reviewed.", "reviewer-entered", "Frozen field-level rules in MANUAL_VALIDATION_PROTOCOL.md.", "supported; contradicted; inconclusive; not_applicable", "An unsuccessful evidence search is inconclusive, not contradicted.")
    if field == "reviewed_activity_class":
        return ("Evidence-based activity class assigned by the reviewer.", "categorical text", "", "Blank when classification is inconclusive or not applicable.", "reviewer-entered", "Frozen activity-classification rule.", "Dataset activity_class vocabulary.", "Requires cited, manually confirmed evidence.")
    if field == "reviewed_activity_stage":
        return ("Evidence-based procedural stage assigned by the reviewer.", "categorical text", "", "Blank when status is inconclusive or not applicable.", "reviewer-entered", "Frozen status-interpretation rule.", "Dataset activity_stage vocabulary.", "Must describe the status at the relevant snapshot date.")
    if field == "physical_work_evidence":
        return ("Reviewer's finding about affirmative evidence of physical work.", "categorical text", "", "Blank means not yet reviewed.", "reviewer-entered", "Frozen physical-evidence rule.", "present; absent; unknown; not_applicable", "Failure to find evidence must be coded unknown, not absent.")
    if field == "evidence_source_types":
        return ("Semicolon-delimited categories of sources manually reviewed.", "text", "", "Blank means not yet reviewed.", "reviewer-entered", "Acceptable-source list in MANUAL_VALIDATION_PROTOCOL.md.", "Protocol-defined source categories.", "AI output alone is not an evidence source.")
    if field in {"primary_evidence_url", "secondary_evidence_url"}:
        return ("Public URL for evidence used in the review.", "URL", "", "Blank when unavailable; a stable document reference is required if the primary URL is blank.", "reviewer-entered", "Manually opened evidence source.", "HTTP(S) URL.", "Links can change; record access time and document reference when possible.")
    if field == "evidence_document_reference":
        return ("Stable document title, identifier, archive reference, or local citation for reviewed evidence.", "text", "", "Blank when the primary evidence URL is sufficient.", "reviewer-entered", "Recorded during evidence review.", "Free text.", "Must be specific enough to relocate the evidence.")
    if field in {"evidence_accessed_at_utc", "reviewed_at_utc"}:
        return ("UTC timestamp for evidence access or review completion.", "datetime", "UTC", "Blank means not yet reviewed.", "reviewer-entered", "ISO 8601 UTC timestamp.", "ISO 8601 timestamp.", "Evidence can change after access.")
    if field == "ai_assistance_used":
        return ("Whether AI assisted in locating candidate evidence.", "categorical text", "", "Blank means not yet reviewed.", "reviewer-entered", "Disclosure required by the protocol.", "yes; no", "AI assistance does not replace human confirmation.")
    if field == "manual_evidence_confirmed":
        return ("Whether a human opened and confirmed the cited evidence.", "categorical text", "", "Blank means not yet reviewed.", "reviewer-entered", "Completion gate in scripts/review_metrics.py.", "yes; no", "Only yes is accepted for a completed review.")
    if field in {"review_notes", "reviewer_id"}:
        return ("Reviewer-entered audit evidence or provenance.", "text", "", "Blank means not yet reviewed or not applicable.", "reviewer-entered", "See MANUAL_VALIDATION_PROTOCOL.md.", "Protocol-defined.", "Independent evidence URLs and reviewer provenance are required for completed judgments where specified.")
    if field in {"review_status", "match_count", "source"}:
        return ("Workflow status, stratum count, or cited source for the table row.", "text", "", "Blank means unavailable or pending.", "derived/source metadata", "See the table-specific methodology documentation.", "Table-defined.", "Interpret only in the context of its table.")
    raise KeyError(f"Missing data-dictionary metadata for field: {field}")


def write_data_dictionary() -> None:
    dictionary = []
    for path in sorted(PROCESSED.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            fields = next(csv.reader(handle))
        for field in fields:
            definition, dtype, unit, null_meaning, origin, derivation, valid_values, warning = metadata_for(field)
            dictionary.append({
                "table": path.name, "field": field, "definition": definition, "data_type": dtype,
                "unit": unit, "nullable": "no" if "Never blank" in null_meaning else "yes",
                "null_meaning": null_meaning, "origin": origin,
                "source_field_or_derivation": derivation, "valid_values": valid_values,
                "interpretation_warning": warning,
            })
    write_csv(DOCS / "data_dictionary.csv", dictionary, lineterminator="\n")


def write_documentation(counts: dict[str, int], activities: list[dict], matches: list[dict], retrieved: str) -> None:
    source_counts = Counter()
    for activity in activities:
        for source in str(activity["source_memberships"]).split(";"):
            source_counts[source] += 1
    benchmark_rows = []
    for fiscal_year, official in [(2024, 24062), (2025, 29835)]:
        extracted = sum(
            1 for a in activities
            if "construction_inspections" in a["source_memberships"]
            and str(a.get("record_created_date", "")).startswith(str(fiscal_year))
        )
        benchmark_rows.append({
            "period": f"FY{str(fiscal_year)[2:]}", "official_building_permits_issued_or_approved": official,
            "gis_construction_records_created_in_calendar_year": extracted,
            "diagnostic_ratio_not_coverage_rate": round(extracted / official, 4),
            "comparability": "Not directly comparable: fiscal-year all-building-permit total versus calendar-year selected GIS display records.",
            "conclusion": "GIS extract is not a complete permit census.",
            "official_source": "https://www.tampa.gov/construction-services/permit-utilization-report" if fiscal_year == 2025 else "https://www.tampa.gov/construction-services/permit-utilization-report/fy24",
        })
    write_csv(PROCESSED / "completeness_benchmarks.csv", benchmark_rows)

    with (PROCESSED / "external_verification_pilot.csv").open(encoding="utf-8", newline="") as handle:
        pilot_rows = list(csv.DictReader(handle))
    with (PROCESSED / "activity_id_aliases.csv").open(encoding="utf-8", newline="") as handle:
        alias_rows = list(csv.DictReader(handle))
    review_status = validation_review_status()
    qa = {
        "release": RELEASE_VERSION, "edition": "source_bounded_city_arcgis_snapshot", "retrieved_at_utc": retrieved, "raw_feature_counts": counts,
        "raw_feature_total": sum(counts.values()), "central_activity_rows": len(activities),
        "location_rows": sum(counts.values()), "multi_location_activities": sum(int(a.get("location_count", 0)) > 1 for a in activities),
        "placeholder_id_activities_kept_separate": sum(not valid_native_id(a.get("source_record_id")) for a in activities),
        "city_building_footprint_matches": len(matches), "activities_with_city_building_match": len({m["activity_id"] for m in matches}),
        "likely_realized_activities": sum(a.get("likely_realized") == 1 for a in activities),
        "evidence_grade_counts": dict(Counter(a.get("realization_evidence_grade", "") for a in activities)),
        "invalid_pre_2000_dates_remaining": sum(any(str(a.get(k, "")).startswith("1899") for k in ("record_created_date", "application_or_opened_date", "planned_start_date", "planned_end_date")) for a in activities),
        "actual_cost_nonzero_rows": sum(bool(a.get("actual_cost_usd")) and float(a.get("actual_cost_usd") or 0) != 0 for a in activities),
        "capital_activity_id_aliases": len(alias_rows),
        "external_verification_pilot_rows": len(pilot_rows),
        "external_pilot_supported_claims": sum(row["evidence_result"] == "supported" for row in pilot_rows),
        "external_pilot_physical_realization_yes": sum(row["physical_realization_verified"] == "yes" for row in pilot_rows),
        "validation_study": review_status,
        "publication_assessment": {
            "official_source_provenance": "pass", "identifier_uniqueness": "pass",
            "multi_location_preservation": "pass", "complete_permit_census": "fail",
            "bounded_source_record_census": "pass",
            "verified_completion": "not_established_by_gis_extract", "permit_valuation": "unavailable", "redistribution_scope": "city_sources_only_hcpa_fallback_excluded",
        },
        "warnings": [
            "The City GIS construction layer is a selected display layer, not the complete Accela permit database.",
            "Footprint/year-built compatibility is supporting evidence only and is not assigned Grade B or treated as completion.",
            "The public City-only edition excludes the optional HCPA nearest-centroid fallback.",
            "CIP viewer data covers active projects for some City departments rather than the complete adopted capital program.",
            "Blank numeric fields mean unknown, not zero.",
            "The 12-row external verification pilot is purposive and is not a population accuracy estimate.",
            "The frozen 150-row study reports no accuracy estimate until human review and the phase-specific completion gates are satisfied.",
        ],
    }
    (DOCS / "qa_report.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")

    write_data_dictionary()

def create_public_archive() -> None:
    PUBLIC_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_ARCHIVE.unlink(missing_ok=True)
    files = [
        ROOT / ".gitignore", ROOT / "README.md", ROOT / "LICENSE", ROOT / "DATA_LICENSE.md",
        ROOT / "CITATION.cff", SCRIPTS / "README.md", *sorted(SCRIPTS.glob("*.py")),
        ROOT / "manifest.json", *sorted((ROOT / "tests").glob("*.py")),
        *sorted((ROOT / ".github").rglob("*")), *sorted((DATA / "templates").glob("*.csv")),
        RAW / "snapshot_metadata.json",
        *sorted(RAW.glob("*.geojson")), *sorted(PROCESSED.glob("*.csv")), *sorted(DOCS.glob("*")),
    ]
    with zipfile.ZipFile(PUBLIC_ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            if path.is_file():
                relative = Path("tampa_development_dataset") / path.relative_to(ROOT)
                bundle.write(path, relative.as_posix())
    with zipfile.ZipFile(PUBLIC_ARCHIVE) as bundle:
        names = bundle.namelist()
        forbidden = [name for name in names if "source_cache/" in name.lower() or name.lower().endswith(".dbf")]
        if forbidden:
            raise RuntimeError(f"Public archive contains forbidden HCPA/cache files: {forbidden}")
        required_study_files = (
            "data/processed/manual_validation_sample.csv",
            "data/processed/manual_validation_development_sample.csv",
            "data/processed/manual_validation_holdout_sample.csv",
            "data/processed/manual_validation_second_review.csv",
            "scripts/validation_study.py",
        )
        missing_study_files = [item for item in required_study_files if not any(name.endswith(item) for name in names)]
        if missing_study_files:
            raise RuntimeError(f"Public archive is missing validation-study files: {missing_study_files}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-hcpa", action="store_true",
        help="Add experimental HCPA nearest-centroid fallback rows. Not used in the public City-only archive.",
    )
    parser.add_argument(
        "--use-existing-raw", action="store_true",
        help="Rebuild from bundled raw snapshots without refreshing live ArcGIS layers.",
    )
    args = parser.parse_args()
    for directory in (RAW, PROCESSED, DOCS, CACHE):
        directory.mkdir(parents=True, exist_ok=True)
    if args.include_hcpa:
        ensure_hcpa_latlon()
    if not args.use_existing_raw:
        subprocess.run([sys.executable, str(SCRIPTS / "build_tampa_development.py")], check=True, stdout=subprocess.DEVNULL)
        for name, (url, _) in EXTRA_CIP.items():
            collection = fetch_arcgis_layer(url)
            (RAW / f"{name}.geojson").write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
        retrieved = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        (RAW / "snapshot_metadata.json").write_text(json.dumps({
            "snapshot_retrieved_at_utc": retrieved,
            "basis": "Completion time of the eight City ArcGIS source-layer downloads",
            "source_layer_count": 8,
        }, indent=2), encoding="utf-8")
    else:
        snapshot_metadata = RAW / "snapshot_metadata.json"
        if not snapshot_metadata.exists():
            raise RuntimeError("Bundled raw snapshot is missing data/raw/snapshot_metadata.json")
        retrieved = json.loads(snapshot_metadata.read_text(encoding="utf-8"))["snapshot_retrieved_at_utc"]
    removed_privacy_values = sanitize_raw_snapshots()
    snapshot_metadata_path = RAW / "snapshot_metadata.json"
    snapshot_metadata = json.loads(snapshot_metadata_path.read_text(encoding="utf-8"))
    previous_removed = snapshot_metadata.get("privacy_suppressed_nonblank_value_counts", {})
    snapshot_metadata.update({
        "redistribution_scope": "privacy-minimized City GeoJSON snapshot",
        "privacy_suppressed_fields": sorted(PRIVACY_BLOCKED_FIELDS),
        "privacy_suppressed_nonblank_value_counts": removed_privacy_values or previous_removed,
        "privacy_note": "The listed contact and source-user fields were removed before public redistribution; feature attributes, identifiers, and geometries otherwise remain source-derived.",
    })
    snapshot_metadata_path.write_text(json.dumps(snapshot_metadata, indent=2), encoding="utf-8")

    legacy = load_legacy_module()
    normalized, source_rows, locations, counts = normalize_source_rows(legacy, retrieved)
    aliases = cluster_capital_activities(normalized, source_rows, locations)
    activities = merge_activities(normalized)
    distinct_geometries: dict[str, set[str]] = defaultdict(set)
    for location in locations:
        if location["geometry_geojson"]:
            distinct_geometries[location["activity_id"]].add(location["geometry_geojson"])
    for activity in activities:
        activity["location_count"] = len(distinct_geometries.get(activity["activity_id"], set()))
    matches, _ = build_footprint_matches(activities, locations, refresh=not args.use_existing_raw)
    if args.include_hcpa:
        matches = add_hcpa_centroid_fallback(matches, activities, locations)
    apply_matches_and_evidence(activities, matches)

    # Remove deprecated names and keep a stable, explicit release schema.
    for activity in activities:
        activity.pop("opened_date", None)
        activity.pop("completion_evidence", None)
        activity.pop("evidence_confidence", None)

    write_csv(PROCESSED / "tampa_development_activity.csv", activities)
    queue = [a for a in activities if int(a.get("physical_development_candidate") or 0) == 1 and a.get("likely_realized") != 1]
    write_csv(PROCESSED / "tampa_development_verification_queue.csv", queue, list(activities[0]))
    write_csv(PROCESSED / "source_records.csv", source_rows)
    write_csv(PROCESSED / "activity_locations.csv", locations)
    write_csv(PROCESSED / "activity_source_links.csv", [{"activity_id": r["activity_id"], "source_record_key": r["source_record_key"], "source_name": r["source_name"]} for r in source_rows])
    write_csv(PROCESSED / "activity_id_aliases.csv", aliases, ["old_activity_id", "new_activity_id", "cluster_basis", "cluster_key"])
    write_csv(PROCESSED / "parcel_building_matches.csv", matches)
    sample = create_manual_validation_sample(activities, matches)
    try:
        from . import ground_truth
    except ImportError:  # Support direct execution from the scripts directory.
        import ground_truth
    ground_truth.build_all(PROCESSED, activities, matches, sample)
    try:
        from . import bounded_census
    except ImportError:  # Support direct execution from the scripts directory.
        import bounded_census
    bounded_census.build(PROCESSED, RAW, source_rows, locations, counts)
    write_documentation(counts, activities, matches, retrieved)
    validation_command = [sys.executable, str(SCRIPTS / "validate_release.py")]
    if args.include_hcpa:
        validation_command.append("--allow-hcpa")
    subprocess.run(validation_command, check=True, stdout=subprocess.DEVNULL)

    review_status = validation_review_status()
    manifest = {
        "title": DATASET_TITLE, "version": RELEASE_VERSION,
        "edition": "city_plus_optional_hcpa" if args.include_hcpa else "source_bounded_city_arcgis_snapshot", "retrieved_at_utc": retrieved,
        "geography": "City of Tampa-published layers, Florida", "unit_of_observation": "published ArcGIS feature; activity/project tables are secondary derived views",
        "outputs": sorted(p.relative_to(ROOT).as_posix() for p in [
            PROCESSED / "tampa_development_activity.csv", PROCESSED / "tampa_development_verification_queue.csv",
            PROCESSED / "source_records.csv", PROCESSED / "activity_locations.csv",
            PROCESSED / "activity_source_links.csv", PROCESSED / "activity_id_aliases.csv",
            PROCESSED / "parcel_building_matches.csv",
            PROCESSED / "external_verification_pilot.csv",
            PROCESSED / "manual_validation_sample.csv",
            PROCESSED / "manual_validation_development_sample.csv",
            PROCESSED / "manual_validation_holdout_sample.csv",
            PROCESSED / "manual_validation_second_review.csv",
            PROCESSED / "activity_truth_status.csv", PROCESSED / "master_projects.csv",
            PROCESSED / "master_project_activity_links.csv", PROCESSED / "master_project_candidates.csv",
            PROCESSED / "development_events.csv", PROCESSED / "investment_amounts.csv",
            PROCESSED / "building_match_audit.csv", PROCESSED / "building_match_diagnostics.csv",
            PROCESSED / "bounded_census_records.csv", PROCESSED / "source_universes.csv",
            PROCESSED / "bounded_census_summary.csv",
            PROCESSED / "completeness_benchmarks.csv", DOCS / "data_dictionary.csv", DOCS / "qa_report.json",
            DOCS / "validation_report.json", DOCS / "KNOWN_LIMITATIONS.md",
            DOCS / "accuracy_verification_report.json",
            DOCS / "validation_study_design.json",
            DOCS / "review_metrics_development.json", DOCS / "review_metrics_holdout.json",
            DOCS / "LICENSE_NOTES.md", DOCS / "PUBLIC_RECORDS_REQUEST.md", DOCS / "MANUAL_VALIDATION_PROTOCOL.md",
            DOCS / "VERIFICATION_REPORT.md", DOCS / "GROUND_TRUTH_METHODOLOGY.md", DOCS / "BOUNDED_CENSUS_SCOPE.md",
        ]),
        "license_note": "The public archive contains City-hosted source snapshots only. Code is MIT-licensed; source data remain subject to City terms described in DATA_LICENSE.md.",
        "bounded_census_claim": "All features returned by eight named City ArcGIS layers at the recorded snapshot retrieval time are included.",
        "bounded_census_nonclaim": "This is not a census of all Tampa permits, projects, construction, completions, or investment.",
        "manual_validation_status": f"protocol_1.0.0_frozen_150_rows_{review_status['status']}",
        "validation_study": {
            **review_status, "development_rows": 100, "holdout_rows": 50,
            "independent_second_reviews": 50, "final_inference_phase": "holdout",
        },
        "external_verification_status": "historical_12_row_pilot_retained_not_used_as_population_estimate",
        "privacy_minimization": {
            "scope": "raw GeoJSON and processed source properties",
            "suppressed_fields": sorted(PRIVACY_BLOCKED_FIELDS),
            "note": "Contact and source-user fields are removed before public packaging.",
        },
        "bundled_source_files": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": file_sha256(path)}
            for path in sorted(RAW.glob("*.geojson"))
        ],
    }
    if args.include_hcpa:
        manifest["license_note"] += " This local build also contains optional HCPA-derived fallback matches and must not be published as the City-only edition."
        manifest["optional_external_source"] = {
            "path": ".cache/source_cache/hcpa_latlon.zip", "sha256": file_sha256(CACHE / "hcpa_latlon.zip"),
            "source": "https://downloads.hcpafl.org/Default.aspx",
        }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPTS / "verify_data_accuracy.py")], check=True, stdout=subprocess.DEVNULL)
    for phase in ("development", "holdout"):
        subprocess.run([
            sys.executable, str(SCRIPTS / "review_metrics.py"), "--phase", phase, "--allow-partial"
        ], check=True, stdout=subprocess.DEVNULL)
    for deprecated in (
        PROCESSED / "tampa_neighborhood_summary.csv",
        PROCESSED / "tampa_physical_development_candidates.csv",
    ):
        deprecated.unlink(missing_ok=True)
    if not args.include_hcpa:
        create_public_archive()
    print(json.dumps(json.loads((DOCS / "qa_report.json").read_text()), indent=2))


if __name__ == "__main__":
    main()
