#!/usr/bin/env python3
"""Refresh only manually reviewed, exact identified public JSON-LD offers.

The immutable archive stays in data/verified-snapshot-2026-11-23.json.
New observations are stored separately as stores[].live_offer and may not
overwrite an archived price, historical inventory audit or old price.
"""
import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

from verified_offers import verified_offer

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "PersonalWineAtlasCatalog/1.0 (respectful metadata fetch)"


def robots_allowed(url, cache):
    parsed = urlsplit(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in cache:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(base + "/robots.txt")
        try:
            request = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=10) as response:
                lines = response.read(200000).decode("utf-8", "replace").splitlines()
            parser.parse(lines)
            cache[base] = parser
        except urllib.error.HTTPError as exc:
            cache[base] = exc.code == 404
        except (urllib.error.URLError, TimeoutError):
            cache[base] = False
    permission = cache[base]
    return permission.can_fetch(USER_AGENT, url) if isinstance(permission, urllib.robotparser.RobotFileParser) else permission


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    catalog_path = ROOT / "data" / "wines.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    counters = {"verified": 0, "changed": 0, "blocked": 0, "unreviewed": 0,
                "skipped_winestyle": 0, "rejected": 0, "failed": 0}
    cache = {}
    today = datetime.date.today().isoformat()
    attempted = 0
    for record in catalog["records"]:
        for store in record["stores"]:
            url = store["url"]
            host = (urlsplit(url).hostname or "").lower()
            if host == "winestyle.ru" or host.endswith(".winestyle.ru"):
                counters["skipped_winestyle"] += 1
                continue
            if record.get("publication_review", {}).get("status") != "verified":
                counters["unreviewed"] += 1
                continue
            if args.limit and attempted >= args.limit:
                break
            if not robots_allowed(url, cache):
                counters["blocked"] += 1
                continue
            attempted += 1
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                                "Accept": "text/html"})
                with urllib.request.urlopen(request, timeout=18) as response:
                    if response.status != 200 or "text/html" not in response.headers.get("Content-Type", ""):
                        raise ValueError("Non-HTML response")
                    final_url = response.geturl()
                    body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ValueError("Oversized page")
                observation, reason = verified_offer(body.decode("utf-8", "replace"),
                                                      record, url, final_url)
                if not observation:
                    counters["rejected"] += 1
                    print("REJECT", reason, url)
                    continue
                counters["verified"] += 1
                observation["observed_on"] = today
                previous = store.get("live_offer")
                print("VERIFIED", observation["price_rub"], observation["availability"], url)
                if previous != observation:
                    counters["changed"] += 1
                    if not args.dry_run:
                        store["live_offer"] = observation
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                counters["failed"] += 1
                print("SKIP", url, str(exc)[:120], file=sys.stderr)
                if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429, 503):
                    base = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
                    cache[base] = False
            finally:
                time.sleep(max(args.delay, 1))
        if args.limit and attempted >= args.limit:
            break
    if counters["changed"] and not args.dry_run:
        temp = catalog_path.with_suffix(".tmp")
        temp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(catalog_path)
    print(" ".join(f"{k.upper()}={v}" for k, v in counters.items()))


if __name__ == "__main__":
    main()
