#!/usr/bin/env python3
"""Check the actually served GitHub Pages bytes after deployment.

The static checkout must match what GitHub Pages serves. A successful Pages
deployment action alone is not a browser/network availability check.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "index.html", "app.js", "styles.css", "editorial.css", "responsive.css",
    "data/wines.json", "data/simplewine-catalog.json", "data/ratings.json", "data/full-descriptions.json", "data/source-pairings.json", "data/owner-exclusions.json",
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


def probe_url(url):
    """Bypass stale negative/error CDN entries while preserving the exact path."""
    parts = urlsplit(url)
    query = parts.query + ("&" if parts.query else "") + "pages-smoke=" + str(time.time_ns())
    return urlunsplit(parts._replace(query=query))


def check_forbidden(url, attempts=4):
    """Only 403/404 prove the forbidden path is not publicly readable.
    Transient CDN errors are retried; never accepted as proof of absence.
    """
    for attempt in range(attempts):
        try:
            fetch(probe_url(url))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                return
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise ValueError(f"Unexpected HTTP status for {url}: {exc.code}") from exc
        except (OSError, TimeoutError):
            if attempt == attempts - 1:
                raise
        else:
            raise ValueError("Internal repository file publicly accessible: " + url)
        time.sleep(min(2 ** attempt, 8))


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
    for forbidden in ("README.md", "scripts/update_prices.py",
                      "data/archive/spb-research-2026-11-14.json"):
        check_forbidden(urljoin(base, forbidden))
    print("INTERNAL_FILES_NOT_PUBLISHED")
    catalog = json.loads((ROOT / "data/wines.json").read_text(encoding="utf-8"))
    assert catalog["records"] and isinstance(catalog["records"], list)
    simple = json.loads((ROOT / "data/simplewine-catalog.json").read_text(encoding="utf-8"))
    catalog["records"].extend(simple["records"])
    assert "<script src=\"./app.js\" defer></script>" in (ROOT / "index.html").read_text(encoding="utf-8")
    # Chromium exercises real network fetches, initialization and DOM rendering.
    browser = next((shutil.which(x) for x in ("google-chrome-stable", "google-chrome",
                                             "chromium", "chromium-browser") if shutil.which(x)), None)
    if not browser:
        raise RuntimeError("Chromium required for deployed-site UI smoke test")
    command = [browser, "--headless", "--no-sandbox", "--disable-gpu",
               "--disable-dev-shm-usage", "--disable-extensions",
               "--blink-settings=imagesEnabled=false",
               "--virtual-time-budget=12000", "--dump-dom", base]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if completed.returncode:
        raise ValueError("Chromium failed: " + completed.stderr[-1000:])
    dom = completed.stdout
    rendered = len(re.findall(r'<article class="wine-card"', dom))
    excluded = json.loads((ROOT / "data/owner-exclusions.json").read_text(encoding="utf-8"))["records"]
    expected = sum(
        r["id"] not in excluded
        and type(r.get("year")) is int and r["year"] > 0
        and r.get("availability", {}).get("status") != "out_of_stock"
        and r.get("publication_review", {}).get("status") != "excluded"
        and not (
            r.get("publication_review", {}).get("status") == "verified"
            and r.get("stores", [{}])[0].get("live_offer", {}).get("verification_method") == "exact_jsonld_product"
            and r["stores"][0]["live_offer"].get("availability") == "out_of_stock"
            and r["stores"][0]["live_offer"].get("observed_on", "") >= r["publication_review"]["checked_at"]
        )
        for r in catalog["records"]
    )
    rendered_ids = set(re.findall(r'data-wine-id="([^"]+)"', dom))
    undated_ids = {r["id"] for r in catalog["records"] if type(r.get("year")) is not int or r["year"] <= 0}
    if not {r["id"] for r in simple["records"] if r["id"] not in excluded}.issubset(rendered_ids):
        raise ValueError("SimpleWine card missing from live site")
    if rendered_ids.intersection(set(excluded) | undated_ids):
        raise ValueError("Owner-excluded wine rendered")
    if rendered != expected or expected == 0:
        raise ValueError(f"Rendered cards {rendered}, expected {expected}")
    # The application filters unavailable wines before populating both the header and card grid.
    if not re.search(r'id="stat-total"[^>]*>' + str(expected) + r'<', dom):
        raise ValueError("Catalog total was not populated by app.js")
    if 'id="result-count"' not in dom or 'Ошибка загрузки' in dom:
        raise ValueError("Catalog initialization failed")
    print("RENDERED_CARDS_VERIFIED", rendered)


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
        except (OSError, ValueError, AssertionError, RuntimeError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            print("PENDING", attempt, str(exc), file=sys.stderr)
            if attempt < 8:
                time.sleep(10)
    raise SystemExit("Published site verification failed: " + str(last_error))


if __name__ == "__main__":
    main()
