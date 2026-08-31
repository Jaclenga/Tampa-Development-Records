import datetime as dt
import unittest
from pathlib import Path

import requests

from tampa_accela.client import (
    AccessRestricted, AccelaClient, CollectionError, RawStore, _redact_session_fields, parse_export_rows,
)
from tampa_accela.config import CollectorConfig
from tampa_accela.models import SearchQuery


def response(status=200, text="ok", url="https://example.test"):
    item = requests.Response()
    item.status_code = status
    item._content = text.encode()
    item._content_consumed = True
    item.url = url
    item.headers = {}
    item.request = requests.Request("GET", url).prepare()
    return item


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}

    def request(self, *_args, **_kwargs):
        return self.responses.pop(0)

    def close(self):
        pass


class ScriptedClient(AccelaClient):
    def __init__(self, pages):
        super().__init__(CollectorConfig(requests_per_second=1), session=FakeSession([]), sleep=lambda _: None)
        self.pages = pages

    def search(self, _query):
        yield from self.pages


class FailingClient(ScriptedClient):
    def search(self, _query):
        raise CollectionError("changed schema")
        yield


class AccelaClientTests(unittest.TestCase):
    def test_parses_official_export_and_rejects_schema_drift(self):
        rows = parse_export_rows(
            "Date,Record Number,Record Type,Address,Status,Expiration Date,Short Notes,\n"
            "08/13/2026,BLD-1,Building Permit,1 MAIN ST,Open,,,\n"
        )
        self.assertEqual(rows[0]["Record Number"], "BLD-1")
        with self.assertRaises(CollectionError):
            parse_export_rows("Date,Record Number\n08/13/2026,BLD-1\n")

    def test_retries_429_and_500(self):
        sleeps = []
        first, second, third = response(429), response(500), response(200)
        first.headers["Retry-After"] = "2"
        client = AccelaClient(
            CollectorConfig(base_url="https://example.test/", max_retries=2, requests_per_second=1),
            session=FakeSession([first, second, third]), sleep=sleeps.append, clock=lambda: 0,
        )
        self.assertEqual(client.request("GET", "https://example.test").status_code, 200)
        self.assertIn(2.0, sleeps)

    def test_stops_on_access_restriction_and_captcha(self):
        with self.assertRaises(AccessRestricted):
            AccelaClient(
                CollectorConfig(base_url="https://example.test/"),
                session=FakeSession([response(403)]), sleep=lambda _: None,
            ).request("GET", "https://example.test/")
        captcha = '<div class="g-recaptcha"></div>'
        with self.assertRaises(AccessRestricted):
            AccelaClient(
                CollectorConfig(base_url="https://example.test/"),
                session=FakeSession([response(200, captcha)]), sleep=lambda _: None,
            ).request("GET", "https://example.test/")

    def test_non_retry_http_error_is_wrapped(self):
        with self.assertRaises(CollectionError):
            AccelaClient(
                CollectorConfig(base_url="https://example.test/"),
                session=FakeSession([response(404)]), sleep=lambda _: None,
            ).request("GET", "https://example.test/")

    def test_rejects_cross_origin_links_and_redirects(self):
        config = CollectorConfig(base_url="https://example.test/TAMPA/")
        with self.assertRaises(AccessRestricted):
            AccelaClient(config, session=FakeSession([]), sleep=lambda _: None).request(
                "GET", "https://evil.test/TAMPA/detail"
            )
        redirect = response(302, url="https://example.test/TAMPA/start")
        redirect.headers["Location"] = "https://evil.test/TAMPA/detail"
        with self.assertRaises(AccessRestricted):
            AccelaClient(config, session=FakeSession([redirect]), sleep=lambda _: None).request(
                "GET", "https://example.test/TAMPA/start"
            )

    def test_follows_only_bounded_same_origin_redirects(self):
        config = CollectorConfig(base_url="https://example.test/TAMPA/")
        redirect = response(302, url="https://example.test/TAMPA/start")
        redirect.headers["Location"] = "/TAMPA/detail"
        final = response(200, "safe", "https://example.test/TAMPA/detail")
        client = AccelaClient(config, session=FakeSession([redirect, final]), sleep=lambda _: None)
        self.assertEqual(client.request("GET", "https://example.test/TAMPA/start").text, "safe")
        self.assertEqual(client.request_count, 2)

    def test_rejects_oversized_response_before_buffering(self):
        config = CollectorConfig(
            base_url="https://example.test/", max_wire_bytes=100, max_decoded_bytes=200
        )
        oversized = response(200, "small", "https://example.test/")
        oversized.headers["Content-Length"] = "101"
        with self.assertRaises(CollectionError):
            AccelaClient(config, session=FakeSession([oversized]), sleep=lambda _: None).request(
                "GET", "https://example.test/"
            )

    def test_rejects_response_that_exceeds_decoded_limit(self):
        config = CollectorConfig(
            base_url="https://example.test/", max_wire_bytes=100, max_decoded_bytes=100
        )
        oversized = response(200, "x" * 101, "https://example.test/")
        with self.assertRaises(CollectionError):
            AccelaClient(config, session=FakeSession([oversized]), sleep=lambda _: None).request(
                "GET", "https://example.test/"
            )

    def test_raw_redaction_and_checkpoint_resume(self):
        html = '<input name="ACA_CS_FIELD" value="secret"><input name="__VIEWSTATE" value="state">'
        self.assertNotIn("secret", _redact_session_fields(html))
        detail = "https://example.test/detail?capID1=A&capID2=B&capID3=C"
        rows = [{"Record Number": "A", "Status": "Open", "Date": "08/13/2026", "_source_url": detail, "_cap_id_parts": ("A", "B", "C")}]
        query = SearchQuery("Building", dt.date(2026, 8, 13), dt.date(2026, 8, 13))
        root = Path("tests/.tmp_accela_client")
        root.mkdir(exist_ok=True)
        result = ScriptedClient([(1, response(text="grid"), rows)]).collect(
            query, raw_store=RawStore(root / "raw", "Building", "run"), checkpoint_path=root / "checkpoint.json"
        )
        self.assertEqual(len(result.records), 1)
        resumed = ScriptedClient([(1, response(text="grid"), rows)]).collect(
            query, raw_store=RawStore(root / "raw", "Building", "run2"), checkpoint_path=root / "checkpoint.json"
        )
        self.assertEqual(len(resumed.records), 1)

    def test_collection_failure_returns_explicit_gap(self):
        root = Path("tests/.tmp_accela_client")
        query = SearchQuery("Building", dt.date(2026, 8, 13), dt.date(2026, 8, 13))
        result = FailingClient([]).collect(
            query,
            raw_store=RawStore(root / "raw", "Building", "failed"),
            checkpoint_path=root / "failed-checkpoint.json",
        )
        self.assertEqual(result.gaps[0]["type"], "collection_failed")
        self.assertIn("changed schema", result.gaps[0]["message"])


if __name__ == "__main__":
    unittest.main()
