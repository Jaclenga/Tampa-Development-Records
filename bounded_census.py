#!/usr/bin/env python3
"""Create the source-bounded census views for the Tampa release."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


SOURCE_LABELS = {
    "construction_inspections": "Construction Inspections published layer",
    "development_coordination": "Development Coordination published layer",
    "single_family_permits": "Single-Family Permits published layer",
    "historic_preservation": "Historic Preservation published layer",
    "capital_improvements": "Capital Improvements published layer",
    "capital_locations_point": "Citywide Capital Projects point layer",
    "capital_locations_line": "Citywide Capital Projects line layer",
    "capital_locations_polygon": "Citywide Capital Projects polygon layer",
}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(processed: Path, raw: Path, source_rows: list[dict], locations: list[dict], counts: dict[str, int]) -> dict:
    """Write one row per published feature and one row per bounded universe."""
    location_by_source = {row["source_record_key"]: row for row in locations}
    source_counts = Counter(row["source_name"] for row in source_rows)
    records = []
    for source in source_rows:
        location = location_by_source[source["source_record_key"]]
        records.append({
            "universe_id": f"tampa_arcgis_{source['source_name']}",
            "source_record_key": source["source_record_key"],
            "source_name": source["source_name"],
            "source_record_id": source["source_record_id"],
            "source_object_id": source["source_object_id"],
            "source_global_id": source["source_global_id"],
            "activity_id": source["activity_id"],
            "location_id": location["location_id"],
            "source_endpoint": source["source_endpoint"],
            "retrieved_at_utc": source["retrieved_at_utc"],
            "geometry_type": location["geometry_type"],
            "geometry_geojson": location["geometry_geojson"],
            "properties_json": source["properties_json"],
            "record_inclusion_status": "included",
            "attribute_scope": "public_source_attributes_after_privacy_field_suppression",
        })

    universes = []
    for source_name in sorted(counts):
        rows = [row for row in source_rows if row["source_name"] == source_name]
        endpoint = rows[0]["source_endpoint"] if rows else ""
        retrieved = rows[0]["retrieved_at_utc"] if rows else ""
        raw_path = raw / f"{source_name}.geojson"
        raw_count = counts[source_name]
        included = source_counts[source_name]
        universes.append({
            "universe_id": f"tampa_arcgis_{source_name}",
            "source_name": source_name,
            "source_label": SOURCE_LABELS[source_name],
            "source_endpoint": endpoint,
            "snapshot_file": raw_path.relative_to(raw.parent).as_posix(),
            "snapshot_retrieved_at_utc": retrieved,
            "raw_feature_count": raw_count,
            "included_record_count": included,
            "excluded_record_count": raw_count - included,
            "record_coverage_status": "complete" if raw_count == included else "incomplete",
            "attribute_coverage_status": "privacy_minimized",
            "unit_of_observation": "one ArcGIS feature returned by the published layer query",
            "geographic_scope": "features published by the City layer; not independently clipped to legal city limits",
            "temporal_scope": "contents exposed at snapshot retrieval; not a complete historical period",
            "census_claim": f"All {raw_count} features returned by the named published City layer at the snapshot retrieval time are included.",
            "exclusions_and_warnings": "Configured contact/editor attributes are suppressed; source publication omissions and historical deletions cannot be observed.",
        })

    summary = [{
        "bounded_census_id": "tampa_published_arcgis_layers_snapshot",
        "source_universe_count": len(universes),
        "published_feature_count": len(records),
        "included_feature_count": sum(int(row["included_record_count"]) for row in universes),
        "excluded_feature_count": sum(int(row["excluded_record_count"]) for row in universes),
        "record_coverage_status": "complete" if all(row["record_coverage_status"] == "complete" for row in universes) else "incomplete",
        "primary_unit": "published ArcGIS feature",
        "valid_claim": "Census of features returned by eight named City of Tampa ArcGIS layers at the recorded snapshot time.",
        "invalid_claim": "Not a census of all Tampa permits, projects, construction, completed development, or investment.",
    }]

    write_csv(processed / "bounded_census_records.csv", records, list(records[0]))
    write_csv(processed / "source_universes.csv", universes, list(universes[0]))
    write_csv(processed / "bounded_census_summary.csv", summary, list(summary[0]))
    return {"records": len(records), "universes": len(universes), "summary": summary[0]}


FIELD_DEFINITIONS = {
    "universe_id": "Stable identifier for one explicitly bounded published-source universe.",
    "source_label": "Human-readable name of the bounded City source layer.",
    "snapshot_file": "Bundled raw GeoJSON snapshot used to construct the bounded census.",
    "snapshot_retrieved_at_utc": "UTC time at which the bounded source snapshot was assembled.",
    "raw_feature_count": "Number of features returned by the complete paginated layer query.",
    "included_record_count": "Number of returned source features retained as census records.",
    "excluded_record_count": "Returned source features not retained as census records.",
    "record_coverage_status": "Whether every feature returned by the published layer query was retained.",
    "attribute_coverage_status": "Attribute-retention scope after configured privacy minimization.",
    "unit_of_observation": "Definition of one row in the bounded source universe.",
    "geographic_scope": "Geographic boundary supplied or implied by the source publisher.",
    "temporal_scope": "Time boundary actually supported by the source snapshot.",
    "census_claim": "Exact completeness claim supported for the named source universe.",
    "exclusions_and_warnings": "Known exclusions and interpretation warnings for the universe.",
    "record_inclusion_status": "Whether the returned source feature is included in the census view.",
    "attribute_scope": "Description of which source attributes are retained.",
    "bounded_census_id": "Stable identifier for the combined eight-layer snapshot census.",
    "source_universe_count": "Number of independently named source universes in the release.",
    "published_feature_count": "Total features returned across the named published layers.",
    "included_feature_count": "Total returned features included in the bounded census.",
    "excluded_feature_count": "Total returned features excluded from the bounded census.",
    "primary_unit": "Primary unit to which the bounded-census claim applies.",
    "valid_claim": "Coverage statement supported by the source counts.",
    "invalid_claim": "Completeness statement outside the dataset's source boundary.",
}


def metadata_for(field: str):
    if field not in FIELD_DEFINITIONS:
        return None
    count = field.endswith("_count")
    status = field.endswith("_status")
    return (
        FIELD_DEFINITIONS[field], "integer" if count else "categorical text" if status else "text",
        "features" if count else "", "Never blank.", "derived census metadata",
        "Direct count or description of the bundled paginated City ArcGIS snapshot.",
        "Non-negative integer." if count else "complete; incomplete" if field == "record_coverage_status" else "Source- or release-defined.",
        "Completeness is limited to records returned by the named layer at retrieval.",
    )
