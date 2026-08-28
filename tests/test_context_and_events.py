from __future__ import annotations

import json
import unittest

from scripts import context_modules, ground_truth


class ContextAndEventTests(unittest.TestCase):
    def test_context_whitelist_drops_owner_and_contact_fields(self) -> None:
        collection = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"FOLIO": "123.0000", "SITE_ADDR": "1 Main St", "OWNER": "Person"},
                "geometry": None,
            }],
        }
        clean = context_modules.whitelist_collection(collection, context_modules.PARCEL_FIELDS)
        self.assertEqual(clean["features"][0]["properties"]["FOLIO"], "123.0000")
        self.assertNotIn("OWNER", clean["features"][0]["properties"])

    def test_budget_book_context_uses_exact_project_id_and_typed_observations(self) -> None:
        activities = [{"activity_id": "a1", "status": "Construction", "project_name": "Core"}]
        source_records = [{
            "source_name": "capital_improvements", "source_record_id": "P-1", "activity_id": "a1"
        }]
        links = [{"activity_id": "a1", "master_project_id": "m1"}]
        collection = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {
                    "OBJECTID": 1, "projid": "P-1", "projname": "Budget",
                    "estcost": 1000, "actcost": 900, "funded": "Yes",
                }, "geometry": None},
                {"type": "Feature", "properties": {
                    "OBJECTID": 2, "projid": "P-2", "projname": "Historical",
                    "estcost": 2000, "funded": "No",
                }, "geometry": None},
            ],
        }
        rows, comparison, events = context_modules.build_capital_context(
            collection, "2026-08-28T00:00:00+00:00", activities, source_records, links
        )
        self.assertEqual(len(rows), 2)
        statuses = {row["city_project_id"]: row["comparison_status"] for row in comparison}
        self.assertEqual(statuses, {"P-1": "matched_core_activity", "P-2": "budget_book_only"})
        self.assertEqual(
            {row["event_type"] for row in events},
            {"capital_estimate_reported", "capital_actual_cost_reported", "funded_status_reported"},
        )
        self.assertTrue(all(row["is_inferred"] == "no" for row in events))

    def test_parcel_links_are_pending_and_do_not_imply_legal_match(self) -> None:
        collection = {"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {"OBJECTID": 1, "FOLIO": "123.0000", "PIN": "A-1", "SITE_ADDR": "1 Main Street"},
            "geometry": {"type": "Polygon", "coordinates": []},
        }]}
        matches = [{
            "activity_id": "a1", "folio": "123.0000", "match_method": "point_in_building_footprint",
            "match_confidence": "high", "building_source_endpoint": "https://example.test/buildings",
        }]
        parcels, links = context_modules.build_parcel_context(
            collection, "2026-08-28T00:00:00+00:00", matches,
            [{"activity_id": "a1", "master_project_id": "m1"}],
        )
        self.assertEqual(parcels[0]["site_address_normalized"], "1 MAIN ST")
        self.assertEqual(links[0]["review_status"], "pending_human_review")
        self.assertEqual(links[0]["link_method"], "building_footprint_folio")

    def test_event_model_preserves_source_observations_without_completion_claims(self) -> None:
        activities = [{
            "activity_id": "a1", "status": "Issued", "activity_stage": "permit_or_funding_approved",
            "source_url": "https://example.test/permit",
        }]
        links = [{"activity_id": "a1", "master_project_id": "m1"}]
        sources = [{
            "source_record_key": "s1", "activity_id": "a1", "source_name": "construction_inspections",
            "source_record_id": "BLD-1", "source_endpoint": "https://example.test/layer",
            "retrieved_at_utc": "2026-08-23T00:00:00+00:00",
            "properties_json": json.dumps({"PROJECTSTATUS": "Issued", "CREATEDDATE": 1704067200000}),
        }]
        events = ground_truth.build_events(activities, links, sources)
        types = {row["event_type"] for row in events}
        self.assertEqual(types, {"source_record_observed", "application_filed", "permit_issued_reported"})
        self.assertFalse(types & {
            "final_inspection_passed", "temporary_co_issued",
            "certificate_of_occupancy_issued", "construction_completion_reported",
        })
        self.assertTrue(all(row["activity_id"] == "a1" and row["source_record_key"] == "s1" for row in events))


if __name__ == "__main__":
    unittest.main()
