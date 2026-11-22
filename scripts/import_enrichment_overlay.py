#!/usr/bin/env python3
"""Apply a previously reviewed WineStyle browser-capture overlay to the live catalog.

Offline only. Dry-run by default; --apply atomically replaces data/wines.json.
Never imports redirect targets, independently asserted critic scores or raw page HTML.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from retailer_manifest import reconcile_manifest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "wines.json"
PUBLISH_EXCLUDE = {
    "all_characteristics", "sections", "excluded_conflicting_fields",
    "unparsed_rating_lines", "unparsed_price_lines", "identity_evidence"
}
ALLOWED_SCALES = {5, 10, 20, 100}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def day(value):
    require(isinstance(value, str), "missing observation date")
    try:
        parsed = dt.date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid observation date: {value!r}") from exc
    require(parsed <= dt.datetime.now(dt.timezone.utc).date(), "future observation")
    return parsed


def checked_rating(row, expected_url):
    require(isinstance(row, dict), "rating must be a mapping")
    require(row.get("reported_by") == "WineStyle" and row.get("source_url") == expected_url,
            "rating source URL/provider mismatch")
    require(isinstance(row.get("source"), str) and row["source"], "rating source absent")
    require(type(row.get("scale")) is int and row["scale"] in ALLOWED_SCALES, "invalid scale")
    require(type(row.get("score")) in (int, float) and 0 < row["score"] <= row["scale"],
            "invalid rating")
    require(isinstance(row.get("evidence"), str) and row["evidence"].strip(), "no rating evidence")


def verify_overlay(catalog, overlay):
    """Build a validated copy; reject all changes if any observation is inconsistent."""
    require(overlay.get("schema_version") == 2 and
            overlay.get("kind") == "reviewed_overlay_not_complete_catalog", "unknown overlay schema")
    source = overlay.get("source_capture_sha256")
    require(isinstance(source, str) and bool(re.fullmatch(r"[a-f0-9]{64}", source)),
            "missing source SHA256")
    require(isinstance(overlay.get("updates"), dict), "missing updates mapping")
    require(isinstance(overlay.get("skipped"), list), "missing skipped records")
    require(isinstance(overlay.get("statistics"), dict), "missing statistics")
    source_date = day(overlay.get("source_observed_at", "")[:10])
    new = copy.deepcopy(catalog)
    records = {r["id"]: r for r in new["records"]}
    require(len(records) == len(new["records"]), "duplicate catalog ids")
    skipped_urls = []
    for skipped in overlay["skipped"]:
        require(isinstance(skipped, dict) and skipped.get("status") == "identity_mismatch",
                "unreviewed skipped observation")
        url = skipped.get("url")
        require(isinstance(url, str) and any(
            url == s.get("url") for r in new["records"] for s in r.get("stores", [])
        ), "skipped URL not in current catalog")
        require(url not in skipped_urls, "duplicate skipped URL")
        skipped_urls.append(url)
    n_updated = n_prices = n_ratings = n_unchanged = 0
    for id_, update in overlay["updates"].items():
        require(isinstance(update, dict) and update.get("id") == id_, "bad overlay ID")
        record = records.get(id_)
        require(record is not None and record.get("title") == update.get("title") and
                record.get("year") == update.get("year"), f"catalog identity mismatch: {id_}")
        stores = [s for s in record["stores"] if s.get("url") == update.get("url")]
        require(len(stores) == 1 and update["url"] not in skipped_urls,
                f"exact URL mismatch or redirect substitution: {id_}")
        store = stores[0]
        d = update.get("product_details")
        require(isinstance(d, dict), f"missing product details: {id_}")
        observed = day(d.get("checked_at"))
        require(observed == source_date and d.get("source_url") == store["url"],
                f"product source/date mismatch: {id_}")
        status = update.get("enrichment_status")
        require(isinstance(status, dict) and status.get("status") == "verified" and
                status.get("checked_at") == d.get("checked_at") and
                status.get("source_url") == store["url"], f"unverified product: {id_}")
        old_date = (store.get("product_details") or {}).get("checked_at")
        require(not old_date or day(old_date) <= observed, f"newer product data: {id_}")
        source_ratings = d.get("ratings") or []
        require(isinstance(source_ratings, list), f"invalid ratings: {id_}")
        seen_sources = set()
        for rating in source_ratings:
            checked_rating(rating, store["url"])
            require(rating["source"] not in seen_sources, f"duplicate critic: {id_}")
            seen_sources.add(rating["source"])
        clean = {k: v for k, v in d.items() if k not in PUBLISH_EXCLUDE}
        current = update.get("price_rub")
        regular = update.get("regular_price_rub")
        if current is not None:
            require(type(current) is int and 100 <= current <= 1_000_000 and
                    update.get("price_checked_at") == d["checked_at"] and
                    update.get("price_source_url") == store["url"], f"invalid price: {id_}")
            require(regular is None or (type(regular) is int and current < regular <= 1_000_000),
                    f"invalid regular price: {id_}")
            previous_price_date = store.get("price_checked_at")
            require(not previous_price_date or day(previous_price_date) <= observed,
                    f"newer store price: {id_}")
            n_prices += 1
        else:
            require(regular is None, f"regular price without current: {id_}")
        status_value = dict(status, method="user_supplied_browser_capture")
        unchanged = (store.get("product_details") == clean and
                     store.get("enrichment_status") == status_value and
                     (current is None or
                      (store.get("price_rub") == current and
                       store.get("regular_price_rub") == regular and
                       store.get("price_checked_at") == d["checked_at"])))
        if not unchanged:
            require(not old_date or old_date < d["checked_at"],
                    f"conflicting same-date snapshot: {id_}")
            store["product_details"] = clean
            store["enrichment_status"] = status_value
            if current is not None:
                store.update(price_rub=current, regular_price_rub=regular,
                             price_checked_at=d["checked_at"],
                             price_source_url=store["url"])
            n_updated += 1
        else:
            n_unchanged += 1
        n_ratings += len(source_ratings)

    audit = overlay["statistics"]
    require(len(overlay["updates"]) == audit.get("verified_exact_products") and
            n_prices == audit.get("prices_with_direct_evidence") and
            n_ratings == audit.get("rating_scores_published_by_retailer") and
            len(skipped_urls) == audit.get("mismatched_variant_count"),
            "overlay counts disagree with source audit")
    # Overlay updates are partial. Recalculate statistics from all retained stores.
    if n_updated or skipped_urls:
        prior = copy.deepcopy(new.get("retailer_snapshot") or {})
        if prior:
            require(day(prior["observed_on"]) <= source_date,
                    "overlay predates original retailer provenance")
            if source != prior.get("source_export_sha256"):
                additional = list(prior.get("additional_capture_sources") or [])
                if not any(entry.get("sha256") == source for entry in additional):
                    additional.append({
                        "sha256": source,
                        "observed_on": source_date.isoformat(),
                        "submitted_matches": len(overlay["updates"]),
                        "submitted_mismatches": len(skipped_urls)
                    })
                prior["additional_capture_sources"] = additional
        else:
            prior = {
                "retailer": "WineStyle",
                "source": "user_supplied_browser_capture",
                "observed_on": source_date.isoformat(),
                "source_export_sha256": source,
                "caveat": "Archived retailer display; not live stock or independent critic verification.",
            }
        prior["mismatched_urls"] = list(dict.fromkeys(
            [*(prior.get("mismatched_urls") or []), *skipped_urls]
        ))
        new["retailer_snapshot"] = reconcile_manifest(prior, new["records"])
    return new, {
        "catalog_records": len(records), "matched": len(overlay["updates"]),
        "changed": n_updated, "unchanged": n_unchanged,
        "prices": n_prices, "ratings": n_ratings,
        "skipped_mismatches": len(skipped_urls),
        "source_export_sha256": source
    }


def atomic_write(path, content):
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8",
                                     suffix=".tmp", delete=False) as out:
        name = Path(out.name)
        try:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        finally:
            pass
    try:
        name.replace(path)
    finally:
        name.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("overlay", type=Path, help="Review overlay JSON, not raw Chrome capture")
    ap.add_argument("--apply", action="store_true", help="write data/wines.json after full validation")
    ap.add_argument("--catalog", type=Path, default=CATALOG)
    args = ap.parse_args()
    source = args.catalog.read_bytes()
    catalog = json.loads(source.decode("utf-8"))
    overlay = json.loads(args.overlay.read_text(encoding="utf-8-sig"))
    data, stats = verify_overlay(catalog, overlay)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", **stats}, ensure_ascii=False))
    if args.apply and stats["changed"]:
        backup = args.catalog.parent / "backups" / (
            "wines.before-overlay." + hashlib.sha256(source).hexdigest()[:12] + ".json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(source)
        atomic_write(args.catalog, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
