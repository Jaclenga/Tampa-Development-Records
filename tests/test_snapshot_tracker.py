from __future__ import annotations

import csv
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_release, snapshot_tracker


def record(
    source: str,
    native_id: str,
    properties: dict,
    observed: str,
    *,
    object_id: str = "1",
    global_id: str = "g-1",
) -> dict[str, str]:
    return {
        "source_name": source,
        "source_record_id": native_id,
        "source_object_id": object_id,
        "source_global_id": global_id,
        "source_endpoint": f"https://example.test/{source}",
        "retrieved_at_utc": observed,
        "properties_json": json.dumps(properties, separators=(",", ":")),
    }


class SnapshotTrackerTests(unittest.TestCase):
    def test_live_collection_uses_eight_layers_and_privacy_whitelist(self) -> None:
        core = {
            "construction_inspections": {"url": "https://example.test/construction"},
            "development_coordination": {"url": "https://example.test/planning"},
            "single_family_permits": {"url": "https://example.test/single-family"},
            "historic_preservation": {"url": "https://example.test/preservation"},
            "capital_improvements": {"url": "https://example.test/capital"},
        }
        extra = {
            "capital_locations_point": ("https://example.test/capital-point", "Points"),
            "capital_locations_line": ("https://example.test/capital-line", "Lines"),
            "capital_locations_polygon": ("https://example.test/capital-polygon", "Polygons"),
        }
        source_by_url = {config["url"]: source for source, config in core.items()}
        source_by_url.update({value[0]: source for source, value in extra.items()})

        geometry_requests = []

        def fake_layer(url: str, *, return_geometry: bool = True) -> dict:
            geometry_requests.append(return_geometry)
            source = source_by_url[url]
            features = []
            for number in range(375):
                props = {
                    "OBJECTID": number + 1,
                    "GlobalID": f"{source}-{number}",
                    "POCEMAIL": "must-not-survive@example.test",
                }
                if source in {"construction_inspections", "single_family_permits"}:
                    props["RECORD_ID"] = f"P-{number}"
                elif source in {"development_coordination", "historic_preservation"}:
                    props["RECORDID"] = f"A-{number}"
                else:
                    props["projid"] = f"C-{number}"
                features.append({"properties": props})
            return {"type": "FeatureCollection", "features": features}

        with (
            mock.patch("scripts.build_release.load_legacy_module", return_value=types.SimpleNamespace(SOURCES=core)),
            mock.patch("scripts.build_release.EXTRA_CIP", extra),
            mock.patch("scripts.build_release.fetch_arcgis_layer", side_effect=fake_layer),
        ):
            rows = snapshot_tracker.collect_live_rows()
        self.assertEqual(len(rows), 3000)
        self.assertEqual({row["source_name"] for row in rows}, set(core) | set(extra))
        self.assertEqual(geometry_requests, [False] * 8)
        self.assertTrue(all("POCEMAIL" not in json.loads(row["properties_json"]) for row in rows))

    def test_attribute_only_arcgis_fetch_normalizes_json_attributes(self) -> None:
        responses = [
            {"count": 1},
            {"count": 1},
            {"objectIdFieldName": "OBJECTID", "objectIds": [1]},
            {"features": [{"attributes": {"OBJECTID": 1, "NAME": "Project"}}]},
            {"count": 1},
        ]
        with mock.patch("scripts.build_release.get_json", side_effect=responses) as get_json:
            collection = build_release.fetch_arcgis_layer(
                "https://example.test/FeatureServer/0", return_geometry=False,
            )
        self.assertEqual(collection["features"][0]["properties"]["NAME"], "Project")
        params = get_json.call_args_list[3].args[1]
        self.assertEqual(params["returnGeometry"], "false")
        self.assertEqual(params["f"], "json")
        self.assertEqual(collection["collection_integrity"]["count_only"], 1)

    def test_arcgis_fetch_rejects_count_inventory_mismatch(self) -> None:
        responses = [
            {"count": 2},
            {"count": 2},
            {"objectIdFieldName": "OBJECTID", "objectIds": [1]},
        ]
        with mock.patch("scripts.build_release.get_json", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "count-only=2, ID-only=1"):
                build_release.fetch_arcgis_layer("https://example.test/FeatureServer/0")

    def test_arcgis_fetch_rejects_nonempty_partial_feature_page(self) -> None:
        responses = [
            {"count": 2},
            {"count": 2},
            {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2]},
            {"features": [{"attributes": {"OBJECTID": 1, "NAME": "Only one"}}]},
        ]
        with mock.patch("scripts.build_release.get_json", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "fetched feature inventory differs"):
                build_release.fetch_arcgis_layer(
                    "https://example.test/FeatureServer/0", return_geometry=False,
                )

    def test_arcgis_fetch_rejects_duplicate_inventory_ids(self) -> None:
        responses = [
            {"count": 2},
            {"count": 2},
            {"objectIdFieldName": "OBJECTID", "objectIds": [1, 1]},
        ]
        with mock.patch("scripts.build_release.get_json", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "duplicate object IDs"):
                build_release.fetch_arcgis_layer("https://example.test/FeatureServer/0")

    def test_live_collection_retries_empty_source_response(self) -> None:
        core = {
            f"source_{number}": {"url": f"https://example.test/source-{number}"}
            for number in range(8)
        }
        calls: dict[str, int] = {}

        def fake_layer(url: str, *, return_geometry: bool = True) -> dict[str, object]:
            calls[url] = calls.get(url, 0) + 1
            if url.endswith("source-0") and calls[url] == 1:
                return {"type": "FeatureCollection", "features": []}
            return {
                "type": "FeatureCollection",
                "features": [
                    {"properties": {"OBJECTID": number}}
                    for number in range(375)
                ],
            }

        with (
            mock.patch("scripts.build_release.load_legacy_module", return_value=types.SimpleNamespace(SOURCES=core)),
            mock.patch("scripts.build_release.EXTRA_CIP", {}),
            mock.patch("scripts.build_release.fetch_arcgis_layer", side_effect=fake_layer) as fetch,
            mock.patch("scripts.snapshot_tracker.time.sleep") as sleep,
        ):
            rows = snapshot_tracker.collect_live_rows()
        self.assertEqual(len(rows), 3000)
        self.assertEqual(fetch.call_count, 9)
        sleep.assert_called_once_with(15)

    def test_native_identity_survives_objectid_change(self) -> None:
        before = record("construction_inspections", "BLD-1", {}, "2026-08-23T00:00:00Z", object_id="1")
        after = record("construction_inspections", "BLD-1", {}, "2026-09-01T00:00:00Z", object_id="99")
        self.assertEqual(snapshot_tracker.record_identity(before), snapshot_tracker.record_identity(after))

    def test_duplicate_native_ids_use_global_ids_across_snapshots(self) -> None:
        before = [
            record("construction_inspections", "BLD-DUP", {"PROJECTSTATUS": "Pending"}, "2026-08-23T00:00:00Z", object_id="1", global_id="g-a"),
            record("construction_inspections", "BLD-DUP", {"PROJECTSTATUS": "Pending"}, "2026-08-23T00:00:00Z", object_id="2", global_id="g-b"),
        ]
        after = [
            record("construction_inspections", "BLD-DUP", {"PROJECTSTATUS": "Issued"}, "2026-09-01T00:00:00Z", object_id="22", global_id="g-b"),
            record("construction_inspections", "BLD-DUP", {"PROJECTSTATUS": "Pending"}, "2026-09-01T00:00:00Z", object_id="11", global_id="g-a"),
        ]
        changes = snapshot_tracker.compare_records(before, after, "2026-08-23", "2026-09-01")
        self.assertEqual([row["change_type"] for row in changes], ["status_changed"])
        self.assertEqual(changes[0]["semantic_type"], "permit_issued")

    def test_change_types_and_semantics(self) -> None:
        before = [
            record(
                "construction_inspections",
                "BLD-1",
                {"PROJECTSTATUS": "Pending", "PROJECTDESCRIPTION": "Old", "URL": "https://example.test/permit"},
                "2026-08-23T00:00:00Z",
            ),
            record(
                "capital_improvements",
                "CIP-1",
                {"projphase": "Design", "estcost": 100, "planend": 1770000000000, "projname": "Project"},
                "2026-08-23T00:00:00Z",
                global_id="g-2",
            ),
            record("historic_preservation", "HP-OLD", {"APPSTATUS": "Open"}, "2026-08-23T00:00:00Z", global_id="g-3"),
        ]
        after = [
            record(
                "construction_inspections",
                "BLD-1",
                {"PROJECTSTATUS": "Issued", "PROJECTDESCRIPTION": "New", "URL": "https://example.test/permit"},
                "2026-09-01T00:00:00Z",
                object_id="88",
            ),
            record(
                "capital_improvements",
                "CIP-1",
                {"projphase": "Construction", "estcost": 125, "planend": 1775000000000, "projname": "Project"},
                "2026-09-01T00:00:00Z",
                object_id="42",
                global_id="g-2",
            ),
            record(
                "development_coordination",
                "DEV-NEW",
                {"APPSTATUS": "Open", "URL": "https://example.test/planning"},
                "2026-09-01T00:00:00Z",
                global_id="g-4",
            ),
        ]
        changes = snapshot_tracker.compare_records(before, after, "2026-08-23", "2026-09-01")
        types = {row["change_type"] for row in changes}
        semantics = {row["semantic_type"] for row in changes}
        self.assertTrue({
            "new_record",
            "record_disappeared",
            "status_changed",
            "description_changed",
            "capital_project_phase_changed",
            "estimated_cost_changed",
            "planned_date_changed",
        }.issubset(types))
        self.assertIn("permit_issued", semantics)
        self.assertIn("planning_application_added", semantics)
        self.assertIn("expected_completion_changed", semantics)

    def test_archive_is_immutable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source_records.csv"
            snapshots = root / "snapshots"
            row = record(
                "construction_inspections",
                "BLD-1",
                {"PROJECTSTATUS": "Issued"},
                "2026-08-23T00:00:00Z",
            )

            def write(value: dict[str, str]) -> None:
                with source.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=snapshot_tracker.SNAPSHOT_FIELDS)
                    writer.writeheader()
                    writer.writerow(value)

            write(row)
            first = snapshot_tracker.archive_snapshot(source, snapshots)
            second = snapshot_tracker.archive_snapshot(source, snapshots)
            self.assertEqual(first["source_records_content_sha256"], second["source_records_content_sha256"])
            same_state_later = dict(row)
            same_state_later["retrieved_at_utc"] = "2026-08-23T12:00:00Z"
            write(same_state_later)
            third = snapshot_tracker.archive_snapshot(source, snapshots)
            self.assertEqual(first["retrieved_at_utc"], third["retrieved_at_utc"])
            changed = dict(row)
            changed["properties_json"] = json.dumps({"PROJECTSTATUS": "Revision"})
            write(changed)
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite immutable snapshot"):
                snapshot_tracker.archive_snapshot(source, snapshots)

    def test_update_creates_monthly_machine_and_human_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshots = root / "snapshots"
            changes = root / "changes"
            reports = root / "reports"
            source = root / "source_records.csv"

            def write(observed: str, status: str) -> None:
                row = record(
                    "construction_inspections",
                    "BLD-1",
                    {"PROJECTSTATUS": status},
                    observed,
                )
                with source.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=snapshot_tracker.SNAPSHOT_FIELDS)
                    writer.writeheader()
                    writer.writerow(row)

            write("2026-08-23T00:00:00Z", "Pending")
            baseline = snapshot_tracker.update_tracker(
                source,
                snapshots_dir=snapshots,
                changes_dir=changes,
                reports_dir=reports,
            )
            self.assertEqual(baseline["index"]["status"], "baseline_only")
            write("2026-09-01T00:00:00Z", "Issued")
            result = snapshot_tracker.update_tracker(
                source,
                snapshots_dir=snapshots,
                changes_dir=changes,
                reports_dir=reports,
            )
            self.assertEqual(result["index"]["status"], "longitudinal")
            self.assertTrue((changes / "2026-09.csv").exists())
            self.assertTrue((changes / "2026-09.json").exists())
            self.assertTrue((reports / "2026-09.md").exists())
            self.assertEqual(result["comparison"]["semantic_type_counts"]["permit_issued"], 1)


if __name__ == "__main__":
    unittest.main()
