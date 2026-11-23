#!/usr/bin/env python3
"""Recover overlooked exact-product prices from the saved WineStyle browser export.

Offline only. The WineStyle HTTP 403 must not be bypassed. A timestamped price
is not asserted to be a current, in-stock offer; no crossed-out/regular price
is guessed from nearby recommended products.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICE = re.compile(r"(?:^|\s)Цена\s+([\d\s\u00a0\u202f]{3,19})\s*₽")
DIGITS = re.compile(r"\D")


def first_exact_product_price(text):
    if not isinstance(text, str):
        return None
    first = text.find(" Все товары ")
    last = text.find(" Условия для бизнеса", first + 1) if first >= 0 else -1
    if first < 0 or last <= first:
        return None
    # Source header, before any related item / cross-sell.
    match = PRICE.search(text, first, last)
    if not match:
        return None
    value = int(DIGITS.sub("", match.group(1)))
    if not (100 <= value <= 1_000_000):
        return None
    return value, match.group(0).strip()


def recover_prices(catalog, export, export_sha256):
    snapshot = catalog["retailer_snapshot"]
    if snapshot["source_export_sha256"] != export_sha256:
        raise ValueError("Price export is not the catalog's verified source capture")
    index = {(s["url"], r["id"]): (r, s)
             for r in catalog["records"] for s in r["stores"]}
    added = 0
    for captured in export["captures"]:
        if captured.get("status") != "captured":
            continue
        identity = captured.get("identity") or {}
        url, key = captured.get("url"), identity.get("target_id")
        pair = index.get((url, key))
        if pair is None:
            continue
        record, store = pair
        if (store.get("enrichment_status") or {}).get("status") != "verified":
            continue
        details = store.get("product_details") or {}
        if details.get("source_url") != url or identity.get("canonical_url") != url:
            continue
        if identity.get("target_year") != record.get("year"):
            continue
        price = first_exact_product_price(captured.get("raw_product_text"))
        if price is None:
            continue
        value, evidence = price
        original_structured = captured.get("price")
        if original_structured and original_structured.get("value_rub") != value:
            raise ValueError(f"Structured price conflicts with text: {url}")
        if store.get("price_rub") is not None:
            if store["price_rub"] != value:
                raise ValueError(f"Saved price conflict: {url}")
            continue
        date = dt.date.fromisoformat(details["checked_at"])
        store["price_rub"] = value
        store["price_checked_at"] = date.isoformat()
        store["price_source_url"] = url
        store["price_evidence"] = {
            "method": "saved_exact_product_primary_price_text",
            "source_capture_sha256": export_sha256,
            "observed_on": date.isoformat(),
            "value_rub": value,
            "verified_against_original_capture": True,
            "text": evidence,
        }
        added += 1
    snapshot["direct_price_observations"] = sum(
        1 for r in catalog["records"] for s in r["stores"]
        if (s.get("enrichment_status") or {}).get("status") == "verified"
        and s.get("price_rub") is not None
    )
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--catalog", type=Path, default=ROOT/"data"/"wines.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raw = args.capture.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    count = recover_prices(catalog, json.loads(raw), digest)
    print(f"Recovered {count} new prices; now "
          f"{catalog['retailer_snapshot']['direct_price_observations']} exact observations")
    if args.apply and count:
        import os
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         suffix=".tmp", dir=args.catalog.parent,
                                         delete=False) as handle:
            json.dump(catalog, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp = handle.name
        os.replace(temp, args.catalog)
    elif not args.apply:
        print("Dry-run: no file changes")


if __name__ == "__main__":
    main()
