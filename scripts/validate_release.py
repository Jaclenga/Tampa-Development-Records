#!/usr/bin/env python3
"""Cross-table and semantic validation for the current release."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from .validation_study import (
        CLAIM_RESULT_FIELDS, PHASE_QUOTAS, PROTOCOL_VERSION, RANDOM_SEED, REVIEW_FIELDS,
        SECOND_REVIEW_QUOTAS, assert_frozen_assignments,
    )
except ImportError:  # Support direct execution: python scripts/validate_release.py
    from validation_study import (
        CLAIM_RESULT_FIELDS, PHASE_QUOTAS, PROTOCOL_VERSION, RANDOM_SEED, REVIEW_FIELDS,
        SECOND_REVIEW_QUOTAS, assert_frozen_assignments,
    )

try:
    from . import context_modules, ground_truth, monthly_cohorts as monthly_cohort_builder, snapshot_tracker
except ImportError:  # Support direct execution: python scripts/validate_release.py
    import context_modules
    import ground_truth
    import monthly_cohorts as monthly_cohort_builder
    import snapshot_tracker


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


def expanded_review_values_valid(row: dict[str, str]) -> bool:
    allowed = {"", "yes", "no", "unknown", "not_applicable"}
    outcome_fields = [
        field for field in row
        if field.endswith("_outcome") or field in {
            "source_record_found", "record_number_matches", "module_matches",
            "record_type_matches", "status_matches", "primary_date_matches",
            "identity_matches", "event_type_correct", "event_date_source_field_correct",
            "event_date_value_correct", "status_normalization_correct",
            "retrospective_flag_correct", "planned_date_flag_correct",
            "activity_mapping_correct", "record_identity_correct", "false_positive_link",
            "false_negative_link", "ambiguous", "source_change_confirmed",
            "likely_publication_artifact",
        }
    ]
    return (
        row.get("review_status", "") in {"", "pending", "in_progress", "complete", "excluded"}
        and all(row.get(field, "") in allowed for field in outcome_fields)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-hcpa", action="store_true", help="Allow optional HCPA fallback rows in a non-public local build.")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "docs" / "validation_report.json",
        help="JSON report path (defaults to the published report).",
    )
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
    capital_budget = read("capital_budget_book_projects.csv")
    capital_comparison = read("capital_budget_book_comparison.csv")
    finance_events = read("public_finance_events.csv")
    parcel_context = read("parcel_context.csv")
    parcel_links = read("parcel_activity_links.csv")
    review2 = read("manual_validation_second_review.csv")
    accela_source_review = read("manual_validation_accela_source_fidelity.csv")
    accela_source_review2 = read("manual_validation_accela_source_fidelity_second_review.csv")
    accela_normalization_review = read("manual_validation_accela_normalization.csv")
    accela_normalization_review2 = read("manual_validation_accela_normalization_second_review.csv")
    integration_review = read("manual_validation_integration_links.csv")
    integration_review2 = read("manual_validation_integration_links_second_review.csv")
    change_review = read("manual_validation_change_events.csv")
    change_review2 = read("manual_validation_change_events_second_review.csv")
    census_records = read("bounded_census_records.csv")
    universes = read("source_universes.csv")
    census_summary = read("bounded_census_summary.csv")
    monthly_cohorts = read("activity_by_month.csv")
    monthly_events_dir = ROOT / "data" / "monthly_events"
    planned_events_dir = ROOT / "data" / "planned_events"
    assert_frozen_assignments()

    def read_extracts(directory: Path) -> list[dict[str, str]]:
        extracted = []
        for path in sorted(directory.glob("????-??.csv")):
            with path.open(encoding="utf-8", newline="") as handle:
                extracted.extend(csv.DictReader(handle))
        return extracted

    def read_index(directory: Path) -> dict[str, object]:
        path = directory / "index.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    monthly_event_extracts = read_extracts(monthly_events_dir)
    planned_event_extracts = read_extracts(planned_events_dir)
    monthly_events_index = read_index(monthly_events_dir)
    planned_events_index = read_index(planned_events_dir)
    tracker_index_path = ROOT / "data" / "monthly_changes" / "index.json"
    tracker_index = (
        json.loads(tracker_index_path.read_text(encoding="utf-8"))
        if tracker_index_path.exists() else {}
    )
    tracker_snapshots = []
    tracker_integrity = []
    tracker_privacy_fields = []
    for item in tracker_index.get("snapshots", []):
        snapshot_dir = ROOT / item["path"]
        metadata = json.loads((snapshot_dir / "metadata.json").read_text(encoding="utf-8"))
        snapshot_rows = snapshot_tracker.read_csv(snapshot_dir / "source_records.csv.gz")
        tracker_snapshots.append((metadata, snapshot_rows))
        tracker_integrity.append(
            metadata["record_count"] == len(snapshot_rows)
            and metadata["source_records_content_sha256"] == snapshot_tracker.rows_sha256(snapshot_rows)
            and metadata["source_state_sha256"] == snapshot_tracker.source_state_sha256(snapshot_rows)
            and metadata["source_counts"] == dict(sorted(
                Counter(row["source_name"] for row in snapshot_rows).items()
            ))
            and len(snapshot_tracker.index_records(snapshot_rows)) == len(snapshot_rows)
        )
        for row in snapshot_rows:
            for field in json.loads(row["properties_json"]):
                if field.lower() in PRIVACY_BLOCKED_FIELDS:
                    tracker_privacy_fields.append(f"{metadata['snapshot_date']}:{field}")
    with (ROOT / "docs" / "data_dictionary.csv").open(encoding="utf-8", newline="") as handle:
        dictionary = list(csv.DictReader(handle))
    documented_fields = {(x["table"], x["field"]) for x in dictionary}
    processed_fields = set()
    for path in P.glob("*.csv"):
        # Optional live Accela working outputs are Git-ignored inputs to the
        # separately documented integrated edition, not v0.9.0 release tables.
        if path.name.startswith("accela_"):
            continue
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
    context_privacy_fields = []
    context_raw = ROOT / "data" / "context" / "raw"
    for path in context_raw.glob("*.geojson"):
        collection = json.loads(path.read_text(encoding="utf-8"))
        for feature in collection.get("features", []):
            for field in (feature.get("properties") or {}):
                if field.lower() in context_modules.PRIVACY_BLOCKED_FIELDS:
                    context_privacy_fields.append(f"{path.name}:{field}")
    context_metadata_path = context_raw / "context_snapshot_metadata.json"
    context_metadata = (
        json.loads(context_metadata_path.read_text(encoding="utf-8"))
        if context_metadata_path.exists() else {}
    )
    event_ids = {x["event_id"] for x in events}
    event_source_keys = {x["source_record_key"] for x in events if x["event_type"] == "source_record_observed"}
    parcel_folios = {x["folio"] for x in parcel_context}
    current_snapshot_rows = snapshot_tracker.canonical_snapshot_rows(sources)
    current_snapshot_hash = snapshot_tracker.rows_sha256(current_snapshot_rows)
    tracker_matches_current_release = any(
        metadata["source_records_content_sha256"] == current_snapshot_hash
        for metadata, _ in tracker_snapshots
    )
    tracker_comparison_outputs_complete = all(
        (ROOT / comparison["csv"]).exists()
        and (ROOT / comparison["summary"]).exists()
        and (ROOT / comparison["report"]).exists()
        for comparison in tracker_index.get("comparisons", [])
    )
    expanded_primary = {
        "accela_source_fidelity_manual_validation": accela_source_review,
        "accela_normalization_validation": accela_normalization_review,
        "gis_accela_linkage_audit": integration_review,
        "longitudinal_change_event_validation": change_review,
    }
    expanded_second = [
        *accela_source_review2, *accela_normalization_review2,
        *integration_review2, *change_review2,
    ]
    with (ROOT / "verification" / "verification_summary.csv").open(encoding="utf-8", newline="") as handle:
        verification_summary = {row["verification_type"]: row for row in csv.DictReader(handle)}

    def expanded_design_valid(rows: list[dict[str, str]]) -> bool:
        return bool(rows) and (
            len({row["validation_sample_id"] for row in rows}) == len(rows)
            and len({row["sampling_universe_sha256"] for row in rows}) == 1
            and all(
                abs(float(row["inclusion_probability"]) - int(row["stratum_sample_size"]) / int(row["stratum_population"])) < 1e-10
                and abs(float(row["sampling_weight"]) - int(row["stratum_population"]) / int(row["stratum_sample_size"])) < 1e-8
                for row in rows
            )
            and all(expanded_review_values_valid(row) for row in rows)
        )
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
        "expanded_validation_sample_sizes_match_design": (
            len(accela_source_review) == 200
            and len(accela_normalization_review) == 125
            and len(integration_review) == 100
            and len(change_review) == 75
        ),
        "expanded_validation_samples_are_seeded_weighted_and_unique": all(
            expanded_design_valid(rows) for rows in expanded_primary.values()
        ),
        "accela_validation_studies_do_not_overlap": (
            {row["record_id"] for row in accela_source_review}.isdisjoint(
                {row["record_id"] for row in accela_normalization_review}
            )
        ),
        "expanded_second_reviews_are_blinded_and_independent": (
            len(accela_source_review2) == 50
            and len(accela_normalization_review2) == 31
            and len(integration_review2) == 25
            and len(change_review2) == 19
            and len({row["second_review_assignment_id"] for row in expanded_second}) == 125
            and all(
                not row["first_reviewer_code"] and not row["first_outcome"]
                and row["second_review_status"] in {"", "pending", "in_progress", "complete", "excluded"}
                for row in expanded_second
            )
        ),
        "verification_summary_reconciles_expanded_studies": all(
            study in verification_summary
            and verification_summary[study]["eligible_records"] == str(len(rows))
            for study, rows in expanded_primary.items()
        ) and verification_summary.get("expanded_double_review", {}).get("eligible_records") == "125",
        "verification_summary_has_no_composite_score": (
            not any("composite" in key.lower() for key in verification_summary)
            and len(verification_summary) == 12
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
        "longitudinal_index_counts_reconcile": (
            bool(tracker_index)
            and tracker_index["snapshot_count"] == len(tracker_index.get("snapshots", []))
            and tracker_index["comparison_count"] == len(tracker_index.get("comparisons", []))
            and tracker_index["status"] == (
                "baseline_only" if len(tracker_snapshots) == 1 else
                "longitudinal" if len(tracker_snapshots) > 1 else "empty"
            )
        ),
        "longitudinal_snapshots_are_complete_and_unique": bool(tracker_integrity) and all(tracker_integrity),
        "longitudinal_archive_contains_current_release": tracker_matches_current_release,
        "longitudinal_snapshots_are_privacy_minimized": not tracker_privacy_fields,
        "longitudinal_comparison_outputs_are_complete": tracker_comparison_outputs_complete,
        "monthly_cohort_record_ids_are_unique": (
            len(monthly_cohorts) == len({x["record_id"] for x in monthly_cohorts})
            and len(monthly_cohorts) == len({x["record_identity"] for x in monthly_cohorts})
        ),
        "monthly_cohort_temporal_fields_reconcile": all(
            (not x["event_date"] or x["event_month"] == x["event_date"][:7])
            and x["first_observed_month"] == x["first_observed_date"][:7]
            and x["last_observed_month"] == x["last_observed_date"][:7]
            and x["snapshot_month"] == x["snapshot_date"][:7]
            and x["first_observed_date"] <= x["last_observed_date"] == x["snapshot_date"]
            and int(x["observation_count"]) >= 1
            and x["event_date_is_planned"] in {"0", "1"}
            and x["event_date_is_after_snapshot"]
            == ("1" if x["event_date"] and x["event_date"] > x["snapshot_date"] else "0")
            and x["event_date_is_planned"]
            == ("1" if x["event_date_basis"] == "source_reported_plan" else "0")
            and x["currently_observed"] in {"0", "1"}
            for x in monthly_cohorts
        ),
        "monthly_cohort_date_semantics_are_explicit": all(
            (not x["event_date"] and not x["event_month"] and not x["event_date_type"]
             and not x["event_date_source_field"] and not x["event_date_basis"])
            or (
                bool(x["event_month"])
                and bool(x["event_date_type"])
                and bool(x["event_date_source_field"])
                and x["event_date_basis"] in {
                    "source_reported_event", "source_reported_plan", "source_record_metadata"
                }
            )
            for x in monthly_cohorts
        ),
        "future_source_dates_are_explicit_plans": all(
            x["event_date_is_after_snapshot"] != "1"
            or (
                x["event_date_is_planned"] == "1"
                and x["event_date_basis"] == "source_reported_plan"
            )
            for x in monthly_cohorts
        ),
        "monthly_cohort_current_observations_match_latest_snapshot": (
            bool(tracker_snapshots)
            and {
                x["record_identity"] for x in monthly_cohorts if x["currently_observed"] == "1"
            } == {
                identity
                for identity, row in snapshot_tracker.index_records(
                    tracker_snapshots[-1][1],
                    set().union(*(
                        snapshot_tracker.duplicate_bases(rows)
                        for _, rows in tracker_snapshots
                    )),
                ).items()
                if not (event_date := monthly_cohort_builder.select_event_date(
                    row["source_name"], snapshot_tracker.properties(row)
                )[0])
                or event_date >= monthly_cohort_builder.DATASET_START_DATE.isoformat()
            }
        ),
        "monthly_event_extracts_exclude_future_dates": (
            {x["record_id"] for x in monthly_event_extracts}
            == {
                x["record_id"] for x in monthly_cohorts
                if x["event_month"] and x["event_date_is_after_snapshot"] == "0"
            }
            and all(
                x["event_month"]
                and x["event_date_is_after_snapshot"] == "0"
                and x["event_date"] <= x["snapshot_date"]
                for x in monthly_event_extracts
            )
        ),
        "planned_event_extracts_contain_only_future_plans": (
            {x["record_id"] for x in planned_event_extracts}
            == {
                x["record_id"] for x in monthly_cohorts
                if x["event_month"] and x["event_date_is_after_snapshot"] == "1"
            }
            and all(
                x["event_month"]
                and x["event_date_is_after_snapshot"] == "1"
                and x["event_date_is_planned"] == "1"
                and x["event_date_basis"] == "source_reported_plan"
                and x["event_date"] > x["snapshot_date"]
                for x in planned_event_extracts
            )
        ),
        "research_extracts_partition_dated_cohorts": (
            not ({x["record_id"] for x in monthly_event_extracts}
                 & {x["record_id"] for x in planned_event_extracts})
            and {x["record_id"] for x in monthly_event_extracts + planned_event_extracts}
            == {x["record_id"] for x in monthly_cohorts if x["event_month"]}
            and len(monthly_event_extracts) + len(planned_event_extracts)
            == sum(bool(x["event_month"]) for x in monthly_cohorts)
        ),
        "monthly_event_index_reconciles": (
            bool(monthly_events_index)
            and monthly_events_index.get("format_version") == "2.0.0"
            and monthly_events_index.get("extract_type") == "monthly_events"
            and monthly_events_index.get("dataset_start_date") == "2020-01-01"
            and monthly_events_index.get("record_count") == len(monthly_event_extracts)
            and monthly_events_index.get("month_count")
            == len(list(monthly_events_dir.glob("????-??.csv")))
        ),
        "monthly_event_scope_starts_2020": all(
            x["event_date"] >= "2020-01-01" for x in monthly_event_extracts
        ),
        "planned_event_index_reconciles": (
            bool(planned_events_index)
            and planned_events_index.get("format_version") == "2.0.0"
            and planned_events_index.get("extract_type") == "planned_events"
            and planned_events_index.get("dataset_start_date") == "2020-01-01"
            and planned_events_index.get("record_count") == len(planned_event_extracts)
            and planned_events_index.get("month_count")
            == len(list(planned_events_dir.glob("????-??.csv")))
        ),
        "legacy_monthly_records_directory_removed": not (ROOT / "data" / "monthly_records").exists(),
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
        "event_ids_unique": len(event_ids) == len(events),
        "events_reference_activities": all(x["activity_id"] in activity_ids for x in events),
        "events_reference_projects": all(x["master_project_id"] in master_ids for x in events),
        "events_reference_source_records": all(x["source_record_key"] in source_keys for x in events),
        "events_use_allowed_types": all(x["event_type"] in ground_truth.EVENT_TYPES for x in events),
        "events_have_one_observation_per_source_feature": event_source_keys == source_keys and sum(
            x["event_type"] == "source_record_observed" for x in events
        ) == len(sources),
        "events_expose_evidence_and_inference": all(
            x["evidence_strength"] in {
                "official_source_observation", "official_reported_date", "official_lifecycle_record"
            } and x["is_inferred"] in {"yes", "no"} and x["interpretation_note"].strip()
            for x in events
        ),
        "no_false_completion_events": not any(x["event_type"] in {
            "final_inspection_passed", "temporary_co_issued",
            "certificate_of_occupancy_issued", "construction_completion_reported",
        } for x in events),
        "amounts_are_positive_and_typed": all(float(x["amount_usd"]) > 0 and x["amount_type"] and x["is_final"] == "unknown" for x in amounts),
        "context_raw_snapshots_are_privacy_minimized": not context_privacy_fields,
        "context_metadata_declares_separate_scope": (
            bool(context_metadata)
            and "separate from the eight-layer bounded census" in context_metadata.get("scope_note", "")
        ),
        "capital_budget_context_record_ids_unique": (
            len({x["context_record_id"] for x in capital_budget}) == len(capital_budget)
        ),
        "capital_comparison_preserves_repeated_source_ids": all(
            int(x["budget_book_record_count"]) == len(
                [value for value in x["budget_book_context_record_ids"].split(";") if value]
            )
            for x in capital_comparison
        ),
        "capital_comparison_project_ids_unique": len({x["city_project_id"] for x in capital_comparison}) == len(capital_comparison),
        "capital_comparison_uses_exact_ids_only": all(
            x["comparison_status"] in {
                "matched_core_activity", "budget_book_only", "core_capital_only",
                "ambiguous_multiple_core_activities",
            }
            and x["match_method"] in {"exact_city_project_id", "no_exact_identifier_match"}
            for x in capital_comparison
        ),
        "finance_events_are_observations_not_spending_claims": all(
            x["event_type"] in {
                "capital_estimate_reported", "capital_actual_cost_reported", "funded_status_reported"
            }
            and x["evidence_strength"] == "official_source_observation"
            and x["is_inferred"] == "no"
            and x["interpretation_warning"].strip()
            for x in finance_events
        ),
        "parcel_context_folios_unique": len(parcel_folios) == len(parcel_context),
        "parcel_links_unique_and_resolve": (
            len({x["parcel_activity_link_id"] for x in parcel_links}) == len(parcel_links)
            and all(x["activity_id"] in activity_ids for x in parcel_links)
            and all(x["master_project_id"] in master_ids for x in parcel_links)
            and all(x["review_status"] == "pending_human_review" for x in parcel_links)
        ),
        "parcel_context_excludes_owner_and_mailing_columns": not (
            {field.lower() for field in (parcel_context[0] if parcel_context else {})}
            & context_modules.PRIVACY_BLOCKED_FIELDS
        ),
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
        "release": "0.9.0", "edition": "city_plus_optional_hcpa" if args.allow_hcpa else "source_bounded_city_arcgis_snapshot",
        "passed": all(checks.values()), "checks": checks,
        "row_counts": {
            "activities": len(activities), "source_records": len(sources), "locations": len(locations),
            "links": len(links), "activity_id_aliases": len(aliases),
            "parcel_building_matches": len(matches), "verification_queue": len(queue),
            "manual_validation_sample": len(audit),
            "manual_validation_development_sample": len(audit_development),
            "manual_validation_holdout_sample": len(audit_holdout),
            "manual_validation_second_review": len(review2),
            "manual_validation_accela_source_fidelity": len(accela_source_review),
            "manual_validation_accela_source_fidelity_second_review": len(accela_source_review2),
            "manual_validation_accela_normalization": len(accela_normalization_review),
            "manual_validation_accela_normalization_second_review": len(accela_normalization_review2),
            "manual_validation_integration_links": len(integration_review),
            "manual_validation_integration_links_second_review": len(integration_review2),
            "manual_validation_change_events": len(change_review),
            "manual_validation_change_events_second_review": len(change_review2),
            "external_verification_pilot": len(pilot),
            "activity_truth_status": len(truth), "master_projects": len(projects),
            "master_project_candidates": len(candidates), "development_events": len(events),
            "investment_amounts": len(amounts), "building_match_audit": len(match_audit),
            "capital_budget_book_projects": len(capital_budget),
            "capital_budget_book_comparison": len(capital_comparison),
            "public_finance_events": len(finance_events),
            "parcel_context": len(parcel_context), "parcel_activity_links": len(parcel_links),
            "bounded_census_records": len(census_records), "source_universes": len(universes),
            "activity_by_month": len(monthly_cohorts),
            "monthly_event_extract_rows": len(monthly_event_extracts),
            "planned_event_extract_rows": len(planned_event_extracts),
            "longitudinal_snapshots": len(tracker_snapshots),
            "longitudinal_comparisons": len(tracker_index.get("comparisons", [])),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
