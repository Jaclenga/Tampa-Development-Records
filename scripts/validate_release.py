#!/usr/bin/env python3
"""Cross-table and semantic validation for the v0.2 release."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from .validation_study import (
        CLAIM_RESULT_FIELDS, PHASE_QUOTAS, PROTOCOL_VERSION, RANDOM_SEED, REVIEW_FIELDS,
        SECOND_REVIEW_QUOTAS,
    )
except ImportError:  # Support direct execution: python scripts/validate_release.py
    from validation_study import (
        CLAIM_RESULT_FIELDS, PHASE_QUOTAS, PROTOCOL_VERSION, RANDOM_SEED, REVIEW_FIELDS,
        SECOND_REVIEW_QUOTAS,
    )


ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
PRIVACY_BLOCKED_FIELDS = {
    "pocname", "pocphone", "pocemail", "creator", "editor", "lasteditor",
    "created", "last_edited_user", "created_user",
}


def read(name: str) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with (P / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def review_values_valid(row: dict[str, str]) -> bool:
    return (
        row.get("review_status", "") in {"", "in_progress", "complete"}
        and all(row.get(field, "") in {"", "supported", "contradicted", "inconclusive", "not_applicable"}
                for field in CLAIM_RESULT_FIELDS)
        and row.get("physical_work_evidence", "") in {"", "present", "absent", "unknown", "not_applicable"}
        and row.get("ai_assistance_used", "") in {"", "yes", "no"}
        and row.get("manual_evidence_confirmed", "") in {"", "yes", "no"}
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-hcpa", action="store_true", help="Allow optional HCPA fallback rows in a non-public local build.")
    args = parser.parse_args()
    activities = read("tampa_development_activity.csv")
    sources = read("source_records.csv")
    locations = read("activity_locations.csv")
    links = read("activity_source_links.csv")
    aliases = read("activity_id_aliases.csv")
    matches = read("parcel_building_matches.csv")
    queue = read("tampa_development_verification_queue.csv")
    audit = read("manual_validation_sample.csv")
    audit_development = read("manual_validation_development_sample.csv")
    audit_holdout = read("manual_validation_holdout_sample.csv")
    pilot = read("external_verification_pilot.csv")
    truth = read("activity_truth_status.csv")
    projects = read("master_projects.csv")
    project_links = read("master_project_activity_links.csv")
    candidates = read("master_project_candidates.csv")
    events = read("development_events.csv")
    amounts = read("investment_amounts.csv")
    match_audit = read("building_match_audit.csv")
    match_diagnostics = read("building_match_diagnostics.csv")
    review2 = read("manual_validation_second_review.csv")
    census_records = read("bounded_census_records.csv")
    universes = read("source_universes.csv")
    census_summary = read("bounded_census_summary.csv")
    with (ROOT / "docs" / "data_dictionary.csv").open(encoding="utf-8", newline="") as handle:
        dictionary = list(csv.DictReader(handle))
    documented_fields = {(x["table"], x["field"]) for x in dictionary}
    processed_fields = set()
    for path in P.glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as handle:
            for field in next(csv.reader(handle)):
                processed_fields.add((path.name, field))

    activity_ids = {x["activity_id"] for x in activities}
    source_keys = {x["source_record_key"] for x in sources}
    location_ids = {x["location_id"] for x in locations}
    master_ids = {x["master_project_id"] for x in projects}
    truth_values = {"yes", "no", "unknown", "not_applicable"}
    universe_ids = {x["universe_id"] for x in universes}
    audit_by_id = {x["audit_sample_id"]: x for x in audit}
    expected_phase_strata = {
        (phase, stratum): quota
        for phase, quotas in PHASE_QUOTAS.items()
        for stratum, quota in quotas.items()
    }
    actual_phase_strata = {
        (phase, stratum): sum(
            x["sample_phase"] == phase and x["sampling_stratum"] == stratum for x in audit
        )
        for phase, stratum in expected_phase_strata
    }
    raw_privacy_fields = []
    for path in RAW.glob("*.geojson"):
        collection = json.loads(path.read_text(encoding="utf-8"))
        for feature in collection.get("features", []):
            for field in (feature.get("properties") or {}):
                if field.lower() in PRIVACY_BLOCKED_FIELDS:
                    raw_privacy_fields.append(f"{path.name}:{field}")
    checks = {
        "activity_ids_unique": len(activity_ids) == len(activities),
        "source_record_keys_unique": len(source_keys) == len(sources),
        "location_ids_unique": len(location_ids) == len(locations),
        "source_activity_foreign_keys": all(x["activity_id"] in activity_ids for x in sources),
        "location_activity_foreign_keys": all(x["activity_id"] in activity_ids for x in locations),
        "links_reference_sources": all(x["source_record_key"] in source_keys for x in links),
        "links_reference_activities": all(x["activity_id"] in activity_ids for x in links),
        "activity_alias_old_ids_unique": len({x["old_activity_id"] for x in aliases}) == len(aliases),
        "activity_aliases_reference_current_activities": all(x["new_activity_id"] in activity_ids for x in aliases),
        "activity_aliases_replace_retired_ids": all(x["old_activity_id"] not in activity_ids for x in aliases),
        "matches_reference_activities": all(x["activity_id"] in activity_ids for x in matches),
        "matches_reference_locations": all(x["location_id"] in location_ids for x in matches),
        "raw_source_and_location_counts_equal": len(sources) == len(locations),
        "no_pre_2000_sentinel_dates": all(
            not str(x.get(field, "")).startswith("1899")
            for x in activities
            for field in ("record_created_date", "application_or_opened_date", "planned_start_date", "planned_end_date")
        ),
        "queue_contains_only_unverified_candidates": all(
            x["physical_development_candidate"] == "1" and x["likely_realized"] != "1" for x in queue
        ),
        "coordinates_within_tampa_region": all(
            (not x["latitude"] and not x["longitude"])
            or (27.5 <= float(x["latitude"]) <= 28.3 and -83.0 <= float(x["longitude"]) <= -82.0)
            for x in locations
        ),
        "contact_fields_suppressed": all(
            not any(token in x["properties_json"].lower() for token in ('"pocname"', '"pocphone"', '"pocemail"'))
            for x in sources
        ),
        "raw_geojson_privacy_fields_suppressed": not raw_privacy_fields,
        "public_edition_excludes_hcpa_fallback": args.allow_hcpa or all(
            "hcpa" not in x["match_method"].lower() and "hcpafl.org" not in x["building_source_endpoint"].lower()
            for x in matches
        ),
        "manual_audit_sample_has_150_unique_activities": (
            len(audit) == 150 and len({x["activity_id"] for x in audit}) == 150
            and len(audit_by_id) == 150
        ),
        "manual_audit_sample_references_activities": all(x["activity_id"] in activity_ids for x in audit),
        "manual_audit_uses_frozen_seeded_protocol": all(
            x["protocol_version"] == PROTOCOL_VERSION and x["random_seed"] == str(RANDOM_SEED)
            for x in audit
        ),
        "manual_audit_phase_stratum_quotas_match_design": actual_phase_strata == expected_phase_strata,
        "manual_audit_selection_weights_reconcile": all(
            abs(float(x["selection_probability"]) - int(x["phase_sample_size"]) / int(x["stratum_population"])) < 1e-9
            and abs(float(x["sampling_weight"]) - int(x["stratum_population"]) / int(x["phase_sample_size"])) < 1e-8
            for x in audit
        ),
        "development_and_holdout_files_partition_sample": (
            len(audit_development) == 100 and len(audit_holdout) == 50
            and {x["audit_sample_id"] for x in audit_development}.isdisjoint(
                {x["audit_sample_id"] for x in audit_holdout}
            )
            and {x["audit_sample_id"] for x in audit_development + audit_holdout} == set(audit_by_id)
            and all(x["sample_phase"] == "development" for x in audit_development)
            and all(x["sample_phase"] == "holdout" for x in audit_holdout)
        ),
        "phase_file_context_matches_combined_sample": all(
            all(
                row.get(field, "") == audit_by_id[row["audit_sample_id"]].get(field, "")
                for field in row if field not in REVIEW_FIELDS
            )
            for row in audit_development + audit_holdout
        ),
        "manual_audit_review_values_use_protocol_vocabularies": all(
            review_values_valid(x) for x in audit + audit_development + audit_holdout
        ),
        "external_pilot_has_12_unique_checks": len(pilot) == 12 and len({x["verification_id"] for x in pilot}) == 12,
        "external_pilot_references_release_activities": all(x["activity_id"] in activity_ids for x in pilot),
        "external_pilot_has_cited_results": all(
            x["evidence_result"] in {"supported", "contradicted", "inconclusive"}
            and x["evidence_url"].startswith("https://") and x["verification_notes"].strip()
            for x in pilot
        ),
        "data_dictionary_covers_all_processed_fields": processed_fields == documented_fields,
        "data_dictionary_has_required_metadata": all(
            all(x.get(field, "").strip() for field in (
                "definition", "data_type", "nullable", "null_meaning", "origin",
                "source_field_or_derivation", "valid_values", "interpretation_warning",
            )) for x in dictionary
        ),
        "publication_metadata_present": all(
            (ROOT / name).exists() for name in ("LICENSE", "DATA_LICENSE.md", "CITATION.cff", "README.md")
        ),
        "demolition_titles_are_semantically_consistent": all(
            x["activity_class"] != "demolition"
            or (
                any(token in x["project_name"].lower() for token in ("demo", "demolition", "demolish"))
                and not any(token in x["project_name"].lower() for token in (
                    "addition", "remodel", "renovation", "alteration", "repair", "rebuild", "new sfr", "new construction",
                ))
            )
            for x in activities
        ),
        "truth_has_one_row_per_activity": len(truth) == len(activities) and {x["activity_id"] for x in truth} == activity_ids,
        "truth_outcomes_use_closed_vocabulary": all(
            x[field] in truth_values for x in truth for field in (
                "physical_work_started", "physical_work_completed", "certificate_of_occupancy_issued",
                "final_inspection_passed", "project_cancelled")
        ),
        "no_completion_claim_without_qualifying_grade": all(
            x["physical_work_completed"] != "yes" or x["verification_grade"] in {"A1", "A2", "A3", "B1", "B2"}
            for x in truth
        ),
        "no_gis_derived_a_or_b_claims": all(x["verification_grade"] in {"C", "D", "P", "X", "U"} for x in truth),
        "master_projects_unique": len(master_ids) == len(projects),
        "project_links_cover_every_activity_once": len(project_links) == len(activities) and {x["activity_id"] for x in project_links} == activity_ids,
        "project_links_reference_projects": all(x["master_project_id"] in master_ids for x in project_links),
        "candidate_merges_are_only_proposals": all(x["merge_applied"] == "no" and x["review_status"] == "pending_human_review" for x in candidates),
        "events_reference_projects": all(x["master_project_id"] in master_ids for x in events),
        "events_use_allowed_types": all(x["event_type"] in {
            "permit_applied", "permit_issued", "inspection_passed", "inspection_failed", "final_inspection_passed",
            "certificate_of_occupancy_issued", "construction_started", "substantial_completion", "project_closeout",
            "permit_expired", "permit_cancelled", "planning_application"} for x in events),
        "no_false_completion_events": not any(x["event_type"] in {"final_inspection_passed", "certificate_of_occupancy_issued", "substantial_completion"} for x in events),
        "amounts_are_positive_and_typed": all(float(x["amount_usd"]) > 0 and x["amount_type"] and x["is_final"] == "unknown" for x in amounts),
        "building_audit_covers_all_matches": len(match_audit) == len(matches),
        "building_precision_pending_review": all(not x["empirical_precision"] and x["human_reviewed_count"] == "0" for x in match_diagnostics),
        "second_review_assignment_has_50_blinded_rows": (
            len(review2) == 50
            and len({x["audit_sample_id"] for x in review2}) == 50
            and all(x["audit_sample_id"] in audit_by_id for x in review2)
            and all(review_values_valid(x) for x in review2)
            and all(
                sum(
                    x["sample_phase"] == phase and x["sampling_stratum"] == stratum for x in review2
                ) == quota
                for phase, quotas in SECOND_REVIEW_QUOTAS.items()
                for stratum, quota in quotas.items()
            )
        ),
        "second_review_context_matches_first_review": all(
            all(
                row.get(field, "") == audit_by_id[row["audit_sample_id"]].get(field, "")
                for field in row if field not in REVIEW_FIELDS
            )
            for row in review2
        ),
        "validation_study_design_is_published": (ROOT / "docs" / "validation_study_design.json").exists(),
        "bounded_census_has_eight_named_universes": len(universes) == 8 and len(universe_ids) == 8,
        "bounded_census_contains_every_source_feature_once": (
            len(census_records) == len(sources)
            and {x["source_record_key"] for x in census_records} == source_keys
            and len({x["source_record_key"] for x in census_records}) == len(census_records)
        ),
        "bounded_census_records_reference_universes": all(x["universe_id"] in universe_ids for x in census_records),
        "bounded_census_universe_counts_reconcile": (
            sum(int(x["raw_feature_count"]) for x in universes) == len(sources)
            and sum(int(x["included_record_count"]) for x in universes) == len(census_records)
            and sum(int(x["excluded_record_count"]) for x in universes) == 0
        ),
        "bounded_census_scope_is_explicit": all(
            x["record_coverage_status"] == "complete"
            and "returned by the named published City layer" in x["census_claim"]
            and "not a complete historical period" in x["temporal_scope"]
            for x in universes
        ),
        "bounded_census_summary_is_conservative": (
            len(census_summary) == 1
            and census_summary[0]["published_feature_count"] == str(len(sources))
            and "not" in census_summary[0]["invalid_claim"].lower()
            and census_summary[0]["record_coverage_status"] == "complete"
        ),
    }
    report = {
        "release": "0.7.0", "edition": "city_plus_optional_hcpa" if args.allow_hcpa else "source_bounded_city_arcgis_snapshot",
        "passed": all(checks.values()), "checks": checks,
        "row_counts": {
            "activities": len(activities), "source_records": len(sources), "locations": len(locations),
            "links": len(links), "activity_id_aliases": len(aliases),
            "parcel_building_matches": len(matches), "verification_queue": len(queue),
            "manual_validation_sample": len(audit),
            "manual_validation_development_sample": len(audit_development),
            "manual_validation_holdout_sample": len(audit_holdout),
            "manual_validation_second_review": len(review2),
            "external_verification_pilot": len(pilot),
            "activity_truth_status": len(truth), "master_projects": len(projects),
            "master_project_candidates": len(candidates), "development_events": len(events),
            "investment_amounts": len(amounts), "building_match_audit": len(match_audit),
            "bounded_census_records": len(census_records), "source_universes": len(universes),
        },
    }
    (ROOT / "docs" / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
