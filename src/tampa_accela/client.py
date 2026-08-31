"""HTTP client for Tampa's verified anonymous ACA WebForms search flow."""

from __future__ import annotations

import datetime as dt
import csv
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import html as html_lib
from html.parser import HTMLParser
import json
import io
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from .config import COLLECTOR_VERSION, CollectorConfig, module_url
from .models import CollectionResult, Inspection, NormalizedRecord, SearchQuery
from .normalize import (
    apply_detail,
    clean,
    deduplicate_records,
    deduplicate_public_records,
    normalize_inspection_row,
    normalize_search_row,
    stable_record_id,
)


LOG = logging.getLogger("tampa_accela")
SEARCH_TARGET = "ctl00$PlaceHolderMain$btnNewSearch"
INSPECTION_TARGET = "ctl00$PlaceHolderMain$InspectionList$btnRefreshGridView"
EXPORT_TARGET = "ctl00$PlaceHolderMain$dgvPermitList$gdvPermitList$gdvPermitListtop4btnExport"
EXPORT_PATH = "Export2CSV.ashx?flag=collector"
GRID_ID_SUFFIX = "_dgvPermitList_gdvPermitList"
RETRY_STATUSES = {429, 500, 502, 503, 504}
SESSION_FIELD_NAMES = {"ACA_CS_FIELD", "__VIEWSTATE", "__VIEWSTATEGENERATOR", "__VIEWSTATEENCRYPTED"}
EXPORT_REQUIRED_FIELDS = {"Date", "Record Number", "Record Type", "Address", "Status"}


class CollectionError(RuntimeError):
    """The public portal response could not be collected or validated."""


class AccessRestricted(CollectionError):
    """The portal returned an access control that the collector will not bypass."""


class FormParser(HTMLParser):
    """Capture successful controls from ACA's aspnetForm for a postback."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_form = False
        self.controls: dict[str, str] = {}
        self._select: str | None = None
        self._options: list[tuple[str, bool]] = []
        self._textarea: str | None = None
        self._textarea_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value if value is not None else "" for key, value in attrs}
        flags = {key for key, _ in attrs}
        if tag == "form" and values.get("id") == "aspnetForm":
            self.in_form = True
            return
        if not self.in_form:
            return
        if tag == "input":
            name = values.get("name")
            kind = values.get("type", "text").lower()
            if not name or "disabled" in flags or kind in {"button", "submit", "image", "file"}:
                return
            if kind in {"checkbox", "radio"} and "checked" not in flags:
                return
            self.controls[name] = values.get("value", "")
        elif tag == "select" and values.get("name") and "disabled" not in flags:
            self._select = values["name"]
            self._options = []
        elif tag == "option" and self._select is not None:
            self._options.append((values.get("value", ""), "selected" in flags))
        elif tag == "textarea" and values.get("name") and "disabled" not in flags:
            self._textarea = values["name"]
            self._textarea_text = []

    def handle_data(self, data: str) -> None:
        if self._textarea is not None:
            self._textarea_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._select is not None:
            selected = next((value for value, chosen in self._options if chosen), None)
            if selected is None and self._options:
                selected = self._options[0][0]
            self.controls[self._select] = selected or ""
            self._select = None
            self._options = []
        elif tag == "textarea" and self._textarea is not None:
            self.controls[self._textarea] = "".join(self._textarea_text)
            self._textarea = None
            self._textarea_text = []
        elif tag == "form" and self.in_form:
            self.in_form = False


class TableParser(HTMLParser):
    """Extract one or more ACA HTML tables without external parser dependencies."""

    def __init__(self, id_predicate: Callable[[str], bool]) -> None:
        super().__init__(convert_charrefs=True)
        self.id_predicate = id_predicate
        self.tables: list[list[list[str]]] = []
        self.table_links: list[list[list[str]]] = []
        self._active_depth = 0
        self._rows: list[list[str]] | None = None
        self._links: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._row_links: list[str] | None = None
        self._cell: list[str] | None = None
        self._cell_links: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "table":
            if self._active_depth:
                self._active_depth += 1
            elif self.id_predicate(values.get("id") or ""):
                self._active_depth = 1
                self._rows = []
                self._links = []
            return
        if not self._active_depth:
            return
        if tag == "tr" and self._active_depth == 1:
            self._row = []
            self._row_links = []
        elif tag in {"td", "th"} and self._active_depth == 1 and self._row is not None:
            self._cell = []
            self._cell_links = []
        elif tag == "a" and self._cell is not None and values.get("href"):
            self._cell_links.append(values["href"] or "")
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._active_depth:
            return
        if tag in {"td", "th"} and self._active_depth == 1 and self._cell is not None:
            self._row.append(clean(" ".join(self._cell)) or "")
            self._row_links.append("|".join(self._cell_links or []))
            self._cell = None
            self._cell_links = None
        elif tag == "tr" and self._active_depth == 1 and self._row is not None:
            if any(self._row):
                self._rows.append(self._row)
                self._links.append(self._row_links or [])
            self._row = None
            self._row_links = None
        elif tag == "table":
            self._active_depth -= 1
            if self._active_depth == 0 and self._rows is not None:
                self.tables.append(self._rows)
                self.table_links.append(self._links or [])
                self._rows = None
                self._links = None


class PostbackParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self._target: tuple[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        match = re.search(r"__doPostBack\(['\"]([^'\"]+)['\"],['\"]([^'\"]*)['\"]\)", href)
        if match:
            self._target = (match.group(1), match.group(2))
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._target:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._target:
            self.links.append((*self._target, clean(" ".join(self._text)) or ""))
            self._target = None
            self._text = []


def form_controls(source: str) -> dict[str, str]:
    parser = FormParser()
    parser.feed(source)
    if "ACA_CS_FIELD" not in parser.controls or "__VIEWSTATE" not in parser.controls:
        raise CollectionError("ACA form response is missing expected CSRF/view-state controls")
    return parser.controls


def _cap_parts(url: str) -> tuple[str, str, str] | None:
    query = parse_qs(urlparse(html_lib.unescape(url)).query)
    values = tuple((query.get(name) or [""])[0] for name in ("capID1", "capID2", "capID3"))
    return values if all(values) else None


def parse_result_rows(source: str, base_url: str) -> list[dict[str, Any]]:
    parser = TableParser(lambda table_id: table_id.endswith(GRID_ID_SUFFIX))
    parser.feed(source)
    if not parser.tables:
        return []
    rows = parser.tables[0]
    links = parser.table_links[0]
    if len(rows) < 2:
        return []
    header_index = next(
        (
            index for index, candidate in enumerate(rows)
            if "record number" in {str(value).strip().lower() for value in candidate}
        ),
        None,
    )
    if header_index is None:
        return []
    headers = [clean(value) or f"column_{index}" for index, value in enumerate(rows[header_index])]
    output: list[dict[str, Any]] = []
    for cells, cell_links in zip(rows[header_index + 1 :], links[header_index + 1 :]):
        if len(cells) != len(headers):
            continue
        row: dict[str, Any] = dict(zip(headers, cells))
        detail = next(
            (href for href in cell_links if "CapDetail.aspx" in html_lib.unescape(href)),
            None,
        )
        if not detail:
            continue
        source_url = urljoin(base_url, html_lib.unescape(detail))
        row["_source_url"] = source_url
        row["_cap_id_parts"] = _cap_parts(source_url)
        output.append(row)
    return output


def next_page_target(source: str) -> str | None:
    parser = PostbackParser()
    parser.feed(source)
    candidates = [
        target
        for target, _argument, label in parser.links
        if "dgvPermitList" in target and html_lib.unescape(label).strip().lower().startswith("next")
    ]
    return candidates[0] if candidates else None


def next_inspection_page_target(source: str, section: str) -> str | None:
    """Return the public pager target for completed or upcoming inspections."""
    if section not in {"completed", "upcoming"}:
        raise ValueError("inspection section must be completed or upcoming")
    parser = PostbackParser()
    parser.feed(source)
    marker = f"InspectionList$gvList{section.title()}"
    candidates = [
        target
        for target, _argument, label in parser.links
        if marker in target and html_lib.unescape(label).strip().lower().startswith("next")
    ]
    return candidates[0] if candidates else None


def _element_text(source: str, element_id: str) -> str | None:
    pattern = re.compile(
        rf"(?is)<(?P<tag>span|div|td|table)[^>]+id=['\"]{re.escape(element_id)}['\"][^>]*>"
        rf"(?P<body>.*?)</(?P=tag)>"
    )
    match = pattern.search(source)
    return _plain_text(match.group("body")) if match else None


def _plain_text(fragment: str) -> str | None:
    fragment = re.sub(r"(?is)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", fragment)
    fragment = re.sub(r"(?s)<[^>]+>", " ", fragment)
    lines = [clean(html_lib.unescape(line)) for line in fragment.splitlines()]
    return "\n".join(line for line in lines if line) or None


def _validation_excerpt(source: str) -> str | None:
    """Return a short, visible portal validation message for safe diagnostics."""
    text = _plain_text(source) or ""
    candidates = [
        line for line in text.splitlines()
        if re.search(r"(?i)\b(error|invalid|required|enter|unable|no records?)\b", line)
        and len(line) <= 300
    ]
    return candidates[-1] if candidates else None


def _label_block_value(source: str, label_pattern: str) -> str | None:
    match = re.search(
        rf"(?is)id=['\"][^'\"]*{label_pattern}[^'\"]*['\"][^>]*>.*?</h1>"
        rf".*?<table[^>]*class=['\"]table_child['\"][^>]*>(.*?)</table>",
        source,
    )
    return _plain_text(match.group(1)) if match else None


def parse_detail(source: str) -> dict[str, object]:
    details: dict[str, object] = {
        "record number": _element_text(source, "ctl00_PlaceHolderMain_lblPermitNumber"),
        "record type": _element_text(source, "ctl00_PlaceHolderMain_lblPermitType"),
        "record status": _element_text(source, "ctl00_PlaceHolderMain_lblRecordStatus"),
        "expiration date": _element_text(source, "ctl00_PlaceHolderMain_lblExpirtionDate"),
        "address": _element_text(source, "tbl_worklocation"),
        "project description": _label_block_value(source, r"label_project"),
        "owner": _label_block_value(source, r"label_owner"),
    }
    applicant_first = re.search(r"(?is)class=['\"]contactinfo_firstname['\"]>(.*?)</span>", source)
    applicant_last = re.search(r"(?is)class=['\"]contactinfo_lastname['\"]>(.*?)</span>", source)
    details["applicant"] = clean(
        " ".join(
            _plain_text(match.group(1)) or ""
            for match in (applicant_first, applicant_last)
            if match
        )
    )
    licensed = _element_text(source, "tbl_licensedps")
    if licensed:
        lines = [clean(re.sub(r"\b[^\s@]+@[^\s@]+\b", "", line)) for line in licensed.splitlines()]
        lines = [line for line in lines if line]
        details["licensed professional"] = lines[1] if len(lines) > 1 else lines[0]
        license_match = re.search(
            r"(?i)(?:General Contractor|Building Contractor|Contractor)\s+([A-Z]{1,5}\d{4,})",
            licensed,
        )
        if license_match:
            details["contractor license"] = license_match.group(1)
    parcel_match = re.search(r"(?is)Parcel Number:\s*</?[^>]*>*\s*([A-Za-z0-9.-]+)", source)
    if not parcel_match:
        plain = _plain_text(source) or ""
        parcel_match = re.search(r"Parcel Number:\s*([A-Za-z0-9.-]+)", plain)
    if parcel_match:
        details["parcel number"] = parcel_match.group(1)
    plain = _plain_text(source) or ""
    parent_match = re.search(
        r"(?i)\b(?:Parent Record|Parent Application)\s*:?\s*([A-Z][A-Z0-9-]{5,})\b",
        plain,
    )
    if parent_match:
        details["parent record number"] = parent_match.group(1)
    related: set[str] = set()
    for match in re.finditer(r"(?is)<a[^>]+CapDetail\.aspx[^>]*>(.*?)</a>", source):
        context = source[max(0, match.start() - 500) : match.start()]
        label = clean(_plain_text(match.group(1)))
        if re.search(r"(?i)\b(related|parent|child)\b", context) and label and re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{5,}", label):
            related.add(label)
    if related:
        details["related record numbers"] = "|".join(sorted(related))
    for label, value in re.findall(
        r"(?is)<div[^>]+MoreDetail_ItemCol1[^>]*>\s*<span[^>]*>(.*?)</span>\s*</div>\s*"
        r"<div[^>]+MoreDetail_ItemCol2[^>]*>\s*<span[^>]*>(.*?)</span>",
        source,
    ):
        key = (clean(_plain_text(label)) or "").rstrip(":").lower()
        if key in {
            "job value", "valuation", "estimated cost", "work description", "property id",
            "filed date", "application date", "issued date", "issue date", "completed date",
            "completion date", "closed date", "updated date", "last updated", "record category",
            "category", "record subtype", "subtype",
        }:
            details[key] = _plain_text(value)
    return {key: value for key, value in details.items() if clean(value)}


def parse_inspection_rows(source: str, section: str | None = None) -> list[dict[str, str]]:
    """Parse ACA's headerless, nested presentation-style inspection rows."""
    if section not in {None, "completed", "upcoming"}:
        raise ValueError("inspection section must be completed, upcoming, or None")
    output: list[dict[str, str]] = []
    starts = list(re.finditer(r"(?is)<tr[^>]+class=['\"][^'\"]*\bInspectionListRow\b[^'\"]*['\"][^>]*>", source))
    for index, start in enumerate(starts):
        prior = source[: start.start()]
        completed_at = prior.rfind("InspectionList_gvListCompleted")
        upcoming_at = prior.rfind("InspectionList_gvListUpcoming")
        row_section = "completed" if completed_at > upcoming_at else "upcoming"
        if section is not None and row_section != section:
            continue
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        fragment = source[start.start() : end]
        spans = [
            clean(_plain_text(value))
            for value in re.findall(r"(?is)<span\b[^>]*>(.*?)</span>", fragment)
        ]
        spans = [value for value in spans if value and value.lower() != "view details"]
        if len(spans) < 2:
            continue
        details_match = re.search(r"(?is)InspectionDetails\.aspx\?([^'\"]+)", html_lib.unescape(fragment))
        source_id = None
        if details_match:
            source_id = (parse_qs(details_match.group(1)).get("ID") or [None])[0]
        descriptor = next(
            (value for value in spans[2:] if re.search(r"(?i)\b(?:result by|scheduled|requested)\b", value)),
            "",
        )
        row: dict[str, str] = {"Inspection Type": spans[1], "Status": spans[0]}
        if source_id:
            row["Inspection ID"] = source_id
        completed = re.search(r"(?i)^Result by:\s*(.*?)\s+on\s+(\d{1,2}/\d{1,2}/\d{4})\s*$", descriptor)
        if completed:
            row.update({
                "Result": spans[0],
                "Inspector": clean(completed.group(1)) or "",
                "Result Date": completed.group(2),
            })
        else:
            scheduled = re.search(r"(?i)(\d{1,2}/\d{1,2}/\d{4})", descriptor)
            if scheduled:
                row["Scheduled Date"] = scheduled.group(1)
        if source_id or row.get("Inspection Type"):
            output.append(row)
    return output


def parse_export_rows(source: str) -> list[dict[str, str]]:
    """Parse the portal's official Download results CSV with strict headers."""
    reader = csv.DictReader(io.StringIO(source.lstrip("\ufeff")))
    headers = {clean(value) or "" for value in (reader.fieldnames or [])}
    missing = EXPORT_REQUIRED_FIELDS - headers
    if missing:
        raise CollectionError(f"Accela export is missing required columns: {sorted(missing)}")
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {clean(key) or "": clean(value) or "" for key, value in raw.items() if key is not None}
        if not row.get("Record Number"):
            if any(row.values()):
                raise CollectionError("Accela export contained a populated row without a record number")
            continue
        rows.append(row)
    return rows


def _redact_session_fields(source: str) -> str:
    for name in SESSION_FIELD_NAMES:
        source = re.sub(
            rf"(?is)(<input[^>]+name=['\"]{re.escape(name)}['\"][^>]+value=['\"])[^'\"]*(['\"])",
            r"\1[REDACTED]\2",
            source,
        )
    return source


def _atomic_text(path: Path, value: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (2**attempt))
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _atomic_bytes(path: Path, value: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (2**attempt))
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, value: object) -> None:
    _atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


class RawStore:
    """Write immutable, token-redacted public payloads and safe provenance."""

    def __init__(self, root: Path, module: str, run_id: str, *, compress_html: bool = False) -> None:
        self.root = root / module.lower() / run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.compress_html = compress_html

    def write(
        self,
        *,
        kind: str,
        sequence: int,
        response: requests.Response,
        semantic_request: dict[str, object],
        record_count: int | None = None,
        extension: str = ".html",
    ) -> Path:
        redacted = _redact_session_fields(response.text)
        digest = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
        stem = f"{sequence:05d}-{kind}-{digest[:12]}"
        if extension not in {".html", ".csv"}:
            raise ValueError("raw payload extension must be .html or .csv")
        stored_extension = ".html.gz" if extension == ".html" and self.compress_html else extension
        payload = self.root / f"{stem}{stored_extension}"
        metadata = self.root / f"{stem}.metadata.json"
        if not payload.exists():
            if stored_extension == ".html.gz":
                _atomic_bytes(payload, gzip.compress(redacted.encode("utf-8"), compresslevel=6))
            else:
                _atomic_text(payload, redacted)
        provenance = {
            "collector_version": COLLECTOR_VERSION,
            "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "request_url": response.request.url if response.request else response.url,
            "request_method": response.request.method if response.request else None,
            "semantic_request": semantic_request,
            "http_status": response.status_code,
            "module": semantic_request.get("module"),
            "page": semantic_request.get("page"),
            "record_count": record_count,
            "response_sha256": digest,
            "stored_content_encoding": "gzip" if stored_extension == ".html.gz" else "identity",
            "redactions": sorted(SESSION_FIELD_NAMES),
            "note": "Cookies, request headers, WebForms view state, and anti-CSRF values are not retained.",
        }
        if not metadata.exists():
            _atomic_json(metadata, provenance)
        return payload


class AccelaClient:
    def __init__(
        self,
        config: CollectorConfig | None = None,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or CollectorConfig()
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent, "Accept": "text/html,application/xhtml+xml"})
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self.request_count = 0
        self.last_initial_response: requests.Response | None = None

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "AccelaClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _rate_limit(self) -> None:
        minimum = 1.0 / self.config.requests_per_second
        if self._last_request_at is not None:
            remaining = minimum - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)

    def _validate_request_url(self, url: str) -> None:
        """Fail closed unless a request stays on the configured HTTPS ACA origin."""
        expected = urlparse(self.config.base_url)
        candidate = urlparse(url)
        try:
            candidate_port = candidate.port
            expected_port = expected.port or 443
        except ValueError as exc:
            raise AccessRestricted(f"Refusing malformed request URL: {url!r}") from exc
        expected_path = expected.path.rstrip("/") + "/"
        if (
            candidate.scheme.lower() != "https"
            or candidate.hostname != expected.hostname
            or (candidate_port or 443) != expected_port
            or candidate.username is not None
            or candidate.password is not None
            or not (candidate.path or "/").startswith(expected_path)
        ):
            raise AccessRestricted(
                f"Refusing request outside configured ACA HTTPS origin/path: {url!r}"
            )

    def _consume_bounded_response(self, response: requests.Response) -> None:
        """Buffer a response while enforcing wire and decoded byte ceilings."""
        declared = response.headers.get("Content-Length")
        if declared:
            try:
                if int(declared) > self.config.max_wire_bytes:
                    raise CollectionError(
                        f"Response Content-Length exceeds {self.config.max_wire_bytes} bytes: "
                        f"{response.url}"
                    )
            except ValueError:
                raise CollectionError(f"Response has invalid Content-Length: {response.url}")
        chunks: list[bytes] = []
        decoded = 0
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                decoded += len(chunk)
                if decoded > self.config.max_decoded_bytes:
                    raise CollectionError(
                        f"Decoded response exceeds {self.config.max_decoded_bytes} bytes: "
                        f"{response.url}"
                    )
                chunks.append(chunk)
                raw = getattr(response, "raw", None)
                try:
                    wire = raw.tell() if raw is not None else decoded
                except (AttributeError, OSError, ValueError):
                    wire = decoded
                if wire > self.config.max_wire_bytes:
                    raise CollectionError(
                        f"Wire response exceeds {self.config.max_wire_bytes} bytes: {response.url}"
                    )
        except Exception:
            response.close()
            raise
        response._content = b"".join(chunks)
        response._content_consumed = True

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (self.config.connect_timeout, self.config.read_timeout))
        follow_redirects = bool(kwargs.pop("allow_redirects", True))
        error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            request_method = method.upper()
            request_url = url
            request_kwargs = dict(kwargs)
            try:
                redirects = 0
                while True:
                    self._validate_request_url(request_url)
                    self._rate_limit()
                    response = self.session.request(
                        request_method,
                        request_url,
                        timeout=timeout,
                        allow_redirects=False,
                        stream=True,
                        **request_kwargs,
                    )
                    self.request_count += 1
                    self._last_request_at = self._clock()
                    is_redirect = response.status_code in {301, 302, 303, 307, 308}
                    if is_redirect and follow_redirects:
                        location = response.headers.get("Location")
                        if not location:
                            response.close()
                            raise CollectionError(f"Redirect response omitted Location: {response.url}")
                        redirects += 1
                        if redirects > self.config.max_redirects:
                            response.close()
                            raise CollectionError(
                                f"Redirects exceeded safeguard of {self.config.max_redirects}: {url}"
                            )
                        target = urljoin(response.url, location)
                        self._validate_request_url(target)
                        status = response.status_code
                        response.close()
                        if status == 303 or status in {301, 302} and request_method not in {"GET", "HEAD"}:
                            request_method = "GET"
                            request_kwargs.pop("data", None)
                            request_kwargs.pop("json", None)
                        request_url = target
                        continue
                    self._consume_bounded_response(response)
                    break
            except requests.RequestException as exc:
                error = exc
                LOG.warning("request failure method=%s url=%s attempt=%s error=%s", method, url, attempt + 1, exc)
                if attempt >= self.config.max_retries:
                    raise CollectionError(f"Request failed after {attempt + 1} attempts: {method} {url}: {exc}") from exc
                self._sleep(self.config.backoff_seconds * (2**attempt))
                continue
            LOG.info("request method=%s status=%s url=%s", method, response.status_code, response.url)
            if response.status_code in {401, 403}:
                raise AccessRestricted(f"Portal returned HTTP {response.status_code}; collection stopped")
            if response.status_code in RETRY_STATUSES:
                if attempt >= self.config.max_retries:
                    raise CollectionError(
                        f"Portal returned HTTP {response.status_code} after {attempt + 1} attempts: {response.url}"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = self.config.backoff_seconds * (2**attempt)
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            retry_at = parsedate_to_datetime(retry_after)
                            if retry_at.tzinfo is None:
                                retry_at = retry_at.replace(tzinfo=dt.timezone.utc)
                            delay = max(delay, (retry_at - dt.datetime.now(dt.timezone.utc)).total_seconds())
                        except (TypeError, ValueError, OverflowError):
                            pass
                self._sleep(delay)
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise CollectionError(f"Portal returned HTTP {response.status_code}: {response.url}") from exc
            lowered = response.text.lower()
            if "potential cross-site request forgery attacks" in lowered:
                raise CollectionError("ACA rejected the WebForms POST because CSRF headers/state were invalid")
            if re.search(r"(?i)(class|id)=['\"][^'\"]*(?:g-recaptcha|recaptcha)", response.text):
                raise AccessRestricted("Portal presented a CAPTCHA; collection stopped without bypassing it")
            return response
        raise CollectionError(f"Request failed: {method} {url}: {error}")

    @staticmethod
    def _post_headers(url: str) -> dict[str, str]:
        parsed = urlparse(url)
        return {"Referer": url, "Origin": f"{parsed.scheme}://{parsed.netloc}"}

    def _postback(self, url: str, source: str, target: str, updates: dict[str, str] | None = None) -> requests.Response:
        data = form_controls(source)
        data["__EVENTTARGET"] = target
        data["__EVENTARGUMENT"] = ""
        if updates:
            data.update(updates)
        return self.request("POST", url, data=data, headers=self._post_headers(url), allow_redirects=True)

    def search(self, query: SearchQuery) -> Iterable[tuple[int, requests.Response, list[dict[str, Any]]]]:
        query.validate()
        url = module_url(query.module, self.config.base_url)
        initial = self.request("GET", url)
        self.last_initial_response = initial
        updates = {
            "ctl00$PlaceHolderMain$generalSearchForm$txtGSPermitNumber": query.record_number or "",
            "ctl00$PlaceHolderMain$generalSearchForm$txtGSStartDate": query.from_date.strftime("%m/%d/%Y") if query.from_date else "",
            "ctl00$PlaceHolderMain$generalSearchForm$txtGSEndDate": query.to_date.strftime("%m/%d/%Y") if query.to_date else "",
        }
        response = self._postback(url, initial.text, SEARCH_TARGET, updates)
        if "CapDetail.aspx" in response.url:
            parts = _cap_parts(response.url)
            detail = parse_detail(response.text)
            row: dict[str, Any] = {
                "Record Number": detail.get("record number"),
                "Record Type": detail.get("record type"),
                "Status": detail.get("record status"),
                "Expiration Date": detail.get("expiration date"),
                "Address": detail.get("address"),
                "Short Notes": detail.get("project description"),
                "_source_url": response.url,
                "_cap_id_parts": parts,
                "_detail_html": response.text,
            }
            yield 1, response, [row]
            return
        seen_signatures: set[str] = set()
        for page in range(1, self.config.max_pages + 1):
            rows = parse_result_rows(response.text, self.config.base_url)
            if not rows:
                lowered = _plain_text(response.text) or ""
                if "no records found" in lowered.lower() or "no record" in lowered.lower():
                    yield page, response, []
                    return
                excerpt = _validation_excerpt(response.text)
                suffix = f": {excerpt}" if excerpt else ""
                raise CollectionError(
                    f"Search page {page} contained neither a result grid nor a recognized empty result{suffix}"
                )
            signature = hashlib.sha256(
                "|".join(str(row.get("_source_url") or "") for row in rows).encode("utf-8")
            ).hexdigest()
            if signature in seen_signatures:
                raise CollectionError(f"Pagination repeated page content at page {page}; refusing an infinite loop")
            seen_signatures.add(signature)
            yield page, response, rows
            target = next_page_target(response.text)
            if target is None:
                return
            response = self._postback(url, response.text, target)
        raise CollectionError(f"Pagination exceeded the configured safeguard of {self.config.max_pages} pages")

    def export_search(self, query: SearchQuery) -> tuple[list[dict[str, str]], list[requests.Response]]:
        """Download all rows for one bounded query through ACA's public export control."""
        search = self.search(query)
        try:
            _page, result_page, visible_rows = next(iter(search))
        except StopIteration:
            raise CollectionError("Accela search ended without returning a result page")
        responses = [response for response in (self.last_initial_response, result_page) if response is not None]
        if not visible_rows:
            return [], responses
        if "CapDetail.aspx" in result_page.url:
            raise CollectionError("Download results is unavailable for an exact-record redirect")
        prepared = self._postback(result_page.url, result_page.text, EXPORT_TARGET)
        download = self.request(
            "GET",
            urljoin(self.config.base_url, EXPORT_PATH),
            headers={"Accept": "text/csv,*/*"},
        )
        content_type = (download.headers.get("Content-Type") or "").lower()
        if "text/csv" not in content_type:
            raise CollectionError(f"Accela export returned unexpected Content-Type {content_type!r}")
        rows = parse_export_rows(download.content.decode("utf-8-sig", "replace"))
        for row in rows:
            event_date = dt.datetime.strptime(row["Date"], "%m/%d/%Y").date()
            if query.from_date and event_date < query.from_date or query.to_date and event_date > query.to_date:
                raise CollectionError(
                    f"Accela export row {row['Record Number']} falls outside the bounded opened-date query"
                )
        return rows, [*responses, prepared, download]

    def collect(
        self,
        query: SearchQuery,
        *,
        raw_store: RawStore,
        checkpoint_path: Path,
        include_addresses: bool = False,
        include_parcels: bool = False,
        include_inspections: bool = False,
        max_records: int | None = None,
        use_export: bool = False,
        checkpoint_every: int = 1,
    ) -> CollectionResult:
        query.validate()
        checkpoint = self._read_checkpoint(checkpoint_path, query)
        result = CollectionResult(
            records=[NormalizedRecord(**row) for row in checkpoint.get("records", [])],
            inspections=[Inspection(**row) for row in checkpoint.get("inspections", [])],
            checkpoint_path=str(checkpoint_path),
        )
        completed_records = set(checkpoint.get("completed_record_ids", []))
        sequence = int(checkpoint.get("raw_sequence", 0))
        retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            if use_export:
                if include_addresses or include_parcels or include_inspections:
                    raise CollectionError("--use-export is list-only and cannot be combined with detail enrichment")
                if max_records is not None:
                    raise CollectionError("--use-export cannot be combined with --max-records")
                exported_rows, responses = self.export_search(query)
                for response_index, response in enumerate(responses, start=1):
                    sequence += 1
                    is_csv = "text/csv" in (response.headers.get("Content-Type") or "").lower()
                    raw_path = raw_store.write(
                        kind="search-export" if is_csv else "search-export-handshake",
                        sequence=sequence,
                        response=response,
                        semantic_request={
                            "module": query.module,
                            "operation": "download_results" if is_csv else "prepare_download_results",
                            "from_date": query.from_date.isoformat() if query.from_date else None,
                            "to_date": query.to_date.isoformat() if query.to_date else None,
                            "response_index": response_index,
                        },
                        record_count=len(exported_rows) if is_csv else None,
                        extension=".csv" if is_csv else ".html",
                    )
                    if is_csv:
                        export_path = raw_path
                result.records.extend(
                    normalize_search_row(
                        row,
                        module=query.module,
                        retrieved_at=retrieved_at,
                        raw_source_file=export_path.as_posix(),
                    )
                    for row in exported_rows
                )
                result.pages = 1
                completed_records.update(record.record_id for record in result.records if record.record_id)
                self._write_checkpoint(
                    checkpoint_path, query, completed_records, result.records, result.inspections,
                    result.pages, sequence, complete=True,
                )
            else:
                sequence = self._collect_paginated(
                    query, raw_store, checkpoint_path, result, completed_records, sequence,
                    retrieved_at, include_addresses, include_parcels, include_inspections, max_records,
                    checkpoint_every,
                )
        except CollectionError as exc:
            result.gaps.append({"type": "collection_failed", "message": str(exc)})
            self._write_checkpoint(
                checkpoint_path, query, completed_records, result.records, result.inspections,
                result.pages, sequence, complete=False,
            )
        result.records = deduplicate_public_records(deduplicate_records(result.records))
        result.requests = self.request_count
        self._write_checkpoint(
            checkpoint_path,
            query,
            completed_records,
            result.records,
            result.inspections,
            result.pages,
            sequence,
            complete=not result.gaps,
        )
        return result

    def _collect_paginated(
        self,
        query: SearchQuery,
        raw_store: RawStore,
        checkpoint_path: Path,
        result: CollectionResult,
        completed_records: set[str],
        sequence: int,
        retrieved_at: str,
        include_addresses: bool,
        include_parcels: bool,
        include_inspections: bool,
        max_records: int | None,
        checkpoint_every: int,
    ) -> int:
        """Run the original page-wise path, including optional detail enrichment."""
        try:
            for page, response, rows in self.search(query):
                if page == 1 and self.last_initial_response is not None:
                    sequence += 1
                    raw_store.write(
                        kind="search-form",
                        sequence=sequence,
                        response=self.last_initial_response,
                        semantic_request={"module": query.module, "page": 0, "operation": "initialize_search"},
                    )
                sequence += 1
                raw_page = raw_store.write(
                    kind="search-page",
                    sequence=sequence,
                    response=response,
                    semantic_request={
                        "module": query.module,
                        "page": page,
                        "from_date": query.from_date.isoformat() if query.from_date else None,
                        "to_date": query.to_date.isoformat() if query.to_date else None,
                        "record_number": query.record_number,
                    },
                    record_count=len(rows),
                )
                result.pages += 1
                selected = rows
                if max_records is not None:
                    remaining = max_records - len(result.records)
                    if remaining <= 0:
                        result.truncated = True
                        break
                    if len(selected) > remaining:
                        selected = selected[:remaining]
                        result.truncated = True
                for row in selected:
                    record = normalize_search_row(
                        row,
                        module=query.module,
                        retrieved_at=retrieved_at,
                        raw_source_file=raw_page.as_posix(),
                    )
                    detail_response: requests.Response | None = None
                    detail_html = row.get("_detail_html")
                    enrichment_complete = True
                    if detail_html and record.record_id not in completed_records:
                        detail_response = response
                    elif record.record_id in completed_records:
                        detail_html = None
                    if include_addresses or include_parcels or include_inspections:
                        if record.record_id not in completed_records and detail_response is None:
                            if not record.source_url:
                                result.gaps.append({
                                    "type": "missing_detail_url",
                                    "record_id": record.record_id,
                                    "record_number": record.record_number,
                                    "message": "Result row did not expose a public detail URL",
                                })
                                result.records.append(record)
                                continue
                            try:
                                detail_response = self.request("GET", record.source_url)
                                detail_html = detail_response.text
                            except CollectionError as exc:
                                enrichment_complete = False
                                LOG.error("detail gap record=%s error=%s", record.record_number, exc)
                                result.gaps.append({
                                    "type": "detail_request_failed",
                                    "record_id": record.record_id,
                                    "record_number": record.record_number,
                                    "message": str(exc),
                                })
                        if detail_response is not None and detail_html:
                            if include_addresses or include_parcels:
                                sequence += 1
                                detail_path = raw_store.write(
                                    kind=f"record-{record.record_id}",
                                    sequence=sequence,
                                    response=detail_response,
                                    semantic_request={"module": query.module, "record_number": record.record_number, "page": page},
                                    record_count=1,
                                )
                                record.raw_source_file = detail_path.as_posix()
                                record = apply_detail(record, parse_detail(detail_html))
                            if include_inspections:
                                try:
                                    inspection_response = self._postback(record.source_url, detail_html, INSPECTION_TARGET)
                                    sequence += 1
                                    inspection_rows = parse_inspection_rows(inspection_response.text)
                                    inspection_path = raw_store.write(
                                        kind=f"inspections-{record.record_id}-p1",
                                        sequence=sequence,
                                        response=inspection_response,
                                        semantic_request={
                                            "module": query.module,
                                            "record_number": record.record_number,
                                            "enrichment": "inspections",
                                        },
                                        record_count=len(inspection_rows),
                                    )
                                    result.inspections.extend(
                                        normalize_inspection_row(
                                            item,
                                            record=record,
                                            retrieved_at=retrieved_at,
                                            raw_source_file=inspection_path.as_posix(),
                                        )
                                        for item in inspection_rows
                                    )
                                    current_inspection_response = inspection_response
                                    for section in ("completed", "upcoming"):
                                        inspection_page = 1
                                        initial_section_rows = parse_inspection_rows(
                                            current_inspection_response.text, section=section
                                        )
                                        seen_signatures = {
                                            hashlib.sha256(
                                                json.dumps(initial_section_rows, sort_keys=True).encode("utf-8")
                                            ).hexdigest()
                                        }
                                        while target := next_inspection_page_target(
                                            current_inspection_response.text, section
                                        ):
                                            inspection_page += 1
                                            if inspection_page > self.config.max_pages:
                                                raise CollectionError(
                                                    f"Inspection pagination exceeded {self.config.max_pages} pages "
                                                    f"for {record.record_number}"
                                                )
                                            current_inspection_response = self._postback(
                                                record.source_url,
                                                current_inspection_response.text,
                                                target,
                                            )
                                            sequence += 1
                                            page_rows = parse_inspection_rows(
                                                current_inspection_response.text, section=section
                                            )
                                            signature = hashlib.sha256(
                                                json.dumps(page_rows, sort_keys=True).encode("utf-8")
                                            ).hexdigest()
                                            if signature in seen_signatures:
                                                raise CollectionError(
                                                    f"Inspection pagination repeated {section} content for "
                                                    f"{record.record_number}"
                                                )
                                            seen_signatures.add(signature)
                                            page_path = raw_store.write(
                                                kind=(
                                                    f"inspections-{record.record_id}-{section}-"
                                                    f"p{inspection_page}"
                                                ),
                                                sequence=sequence,
                                                response=current_inspection_response,
                                                semantic_request={
                                                    "module": query.module,
                                                    "record_number": record.record_number,
                                                    "enrichment": "inspections",
                                                    "inspection_section": section,
                                                    "inspection_page": inspection_page,
                                                },
                                                record_count=len(page_rows),
                                            )
                                            result.inspections.extend(
                                                normalize_inspection_row(
                                                    item,
                                                    record=record,
                                                    retrieved_at=retrieved_at,
                                                    raw_source_file=page_path.as_posix(),
                                                )
                                                for item in page_rows
                                            )
                                except CollectionError as exc:
                                    enrichment_complete = False
                                    result.gaps.append({
                                        "type": "inspection_request_failed",
                                        "record_id": record.record_id,
                                        "record_number": record.record_number,
                                        "message": str(exc),
                                    })
                    result.records.append(record)
                    if enrichment_complete:
                        completed_records.add(record.record_id)
                    if len(completed_records) % checkpoint_every == 0:
                        self._write_checkpoint(
                            checkpoint_path,
                            query,
                            completed_records,
                            result.records,
                            result.inspections,
                            page,
                            sequence,
                            complete=False,
                        )
                if result.truncated:
                    result.gaps.append({
                        "type": "intentional_limit",
                        "page": page,
                        "message": f"Collection stopped at max_records={max_records}",
                    })
                    break
        except CollectionError as exc:
            result.gaps.append({"type": "collection_failed", "message": str(exc)})
            self._write_checkpoint(
                checkpoint_path, query, completed_records, result.records, result.inspections,
                result.pages, sequence, complete=False,
            )
        return sequence

    @staticmethod
    def _query_dict(query: SearchQuery) -> dict[str, object]:
        return {
            "module": query.module,
            "from_date": query.from_date.isoformat() if query.from_date else None,
            "to_date": query.to_date.isoformat() if query.to_date else None,
            "record_number": query.record_number,
            "updated_since": query.updated_since.isoformat() if query.updated_since else None,
        }

    def _read_checkpoint(self, path: Path, query: SearchQuery) -> dict[str, object]:
        if not path.exists():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("query") != self._query_dict(query):
            raise CollectionError(f"Checkpoint query does not match this run: {path}")
        return value

    def _write_checkpoint(
        self,
        path: Path,
        query: SearchQuery,
        completed_records: set[str],
        records: list[NormalizedRecord],
        inspections: list[Inspection],
        page: int,
        sequence: int,
        *,
        complete: bool,
    ) -> None:
        _atomic_json(
            path,
            {
                "format_version": "1.0.0",
                "collector_version": COLLECTOR_VERSION,
                "query": self._query_dict(query),
                "last_traversed_page": page,
                "completed_record_ids": sorted(completed_records),
                "records": [record.as_row() for record in deduplicate_records(records)],
                "inspections": [inspection.as_row() for inspection in inspections],
                "raw_sequence": sequence,
                "complete": complete,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "resume_note": "ACA pagination is session-bound; resume safely replays earlier pages and skips completed enrichment.",
            },
        )
