#!/usr/bin/env python3
"""Check the actually served GitHub Pages bytes after deployment.

The static checkout must match what GitHub Pages serves. A successful Pages
deployment action alone is not a browser/network availability check.
"""
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "index.html", "app.js", "styles.css", "editorial.css", "responsive.css",
    "data/wines.json", "data/ratings.json",
    "data/verified-snapshot-2026-11-23.json",
    "data/researched-photos-2026-11-23.json",
)


def fetch(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "WineAtlasPagesSmoke/1.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("HTTP status %d" % response.status)
        return response.read(2_500_001)


def check(base):
    if urlsplit(base).scheme != "https" or urlsplit(base).hostname != "dancyuser.github.io":
        raise ValueError("Unexpected Pages host: " + base)
    base = base.rstrip("/") + "/"
    for filename in FILES:
        expected = (ROOT / filename).read_bytes()
        observed = fetch(urljoin(base, filename))
        if len(observed) > 2_500_000:
            raise ValueError(filename + " unexpectedly large")
        if hashlib.sha256(observed).digest() != hashlib.sha256(expected).digest():
            raise ValueError(filename + " differs from deployed commit")
        print("OK", filename, len(observed), "bytes")
    catalog = json.loads((ROOT / "data/wines.json").read_text(encoding="utf-8"))
    assert len(catalog["records"]) >= 110
    assert "<script src=\"./app.js\" defer></script>" in (ROOT / "index.html").read_text(encoding="utf-8")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/smoke_pages.py https://dancyuser.github.io/wine-atlas/")
    url = sys.argv[1]
    last_error = None
    for attempt in range(1, 9):
        try:
            check(url)
            print("PUBLISHED_SITE_VERIFIED")
            return
        except (OSError, ValueError, AssertionError) as exc:
            last_error = exc
            print("PENDING", attempt, str(exc), file=sys.stderr)
            if attempt < 8:
                time.sleep(10)
    raise SystemExit("Published site verification failed: " + str(last_error))


if __name__ == "__main__":
    main()
