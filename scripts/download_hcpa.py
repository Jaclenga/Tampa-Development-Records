#!/usr/bin/env python3
"""Download a named file from HCPA's ASP.NET public-download portal."""

from __future__ import annotations

import argparse
import http.cookiejar
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class HiddenFields(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("type") == "hidden" and values.get("name"):
            self.values[str(values["name"])] = str(values.get("value") or "")


def download(filename_pattern: str, output: Path, subfolder: str = "") -> tuple[str, int]:
    url = "https://downloads.hcpafl.org/Default.aspx?" + urllib.parse.urlencode({"subfolder": subfolder})
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    headers = {"User-Agent": "tampa-development-dataset/0.2"}
    with opener.open(urllib.request.Request(url, headers=headers), timeout=120) as response:
        html = response.read().decode("utf-8")

    # Each file row contains the postback target followed by the visible filename.
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S)
    chosen: tuple[str, str] | None = None
    for row in rows:
        target = re.search(r"__doPostBack\(&#39;([^&]+)&#39;", row)
        visible = re.sub(r"<[^>]+>", " ", row)
        visible = re.sub(r"\s+", " ", visible).strip()
        if target and re.search(filename_pattern, visible, flags=re.I):
            match = re.search(r"([\w .-]+\.(?:zip|xls|xlsx|doc|docx|pdf))", visible, flags=re.I)
            chosen = (target.group(1), match.group(1).strip() if match else visible.split()[0])
            break
    if not chosen:
        raise RuntimeError(f"No HCPA file matched {filename_pattern!r} in {subfolder!r}")

    parser = HiddenFields()
    parser.feed(html)
    form = {k: v for k, v in parser.values.items() if k.startswith("__") or k == "grdFiles_ClientState"}
    form["__EVENTTARGET"] = chosen[0]
    form["__EVENTARGUMENT"] = ""
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Referer": url},
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with opener.open(request, timeout=600) as response, output.open("wb") as handle:
        total = 0
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
            total += len(chunk)
    return chosen[1], total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", help="Case-insensitive regular expression matching a visible filename")
    parser.add_argument("output", type=Path)
    parser.add_argument("--subfolder", default="")
    args = parser.parse_args()
    filename, size = download(args.pattern, args.output, args.subfolder)
    print(f"Downloaded {filename}: {size} bytes -> {args.output}")


if __name__ == "__main__":
    main()
