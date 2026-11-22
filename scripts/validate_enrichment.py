#!/usr/bin/env python3
"""Audit retailer snapshot integrity separately from independent Vivino ratings."""
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / "data" / "wines.json").read_text(encoding="utf-8"))
snapshot = catalog.get("retailer_snapshot")
assert isinstance(snapshot, dict), "Missing retailer snapshot manifest"
assert snapshot["retailer"] == "WineStyle"
assert snapshot["source"] == "user_supplied_browser_capture"
assert re.fullmatch(r"[0-9a-f]{64}", snapshot["source_export_sha256"])
observation_day = dt.date.fromisoformat(snapshot["observed_on"])
assert observation_day <= dt.date.today()
assert snapshot["regular_prices_confirmed"] >= 0
assert snapshot["matched_exact_products"] <= snapshot["collected_target_urls"]

records = catalog["records"]
assert len(records) == len({r["id"] for r in records}), "Duplicate wine IDs"
index = {s["url"]: (r, s) for r in records for s in r["stores"]}
assert len(index) == sum(len(r["stores"]) for r in records)
skipped = snapshot["mismatched_urls"]
assert isinstance(skipped, list) and len(set(skipped)) == len(skipped)
assert len(skipped) == snapshot["mismatched_variants"]
for url in skipped:
    assert url in index, "Skipped URL absent from source catalog"
    assert index[url][1].get("enrichment_status", {}).get("status") != "verified", (
        "A redirected variant was improperly attached to the original wishlist wine")

enriched = priced = ratings = scored_wines = 0
for record in records:
    for store in record["stores"]:
        status = store.get("enrichment_status")
        if status is None:
            continue
        assert status.get("status") == "verified"
        assert status.get("source_url") == store["url"]
        d = store.get("product_details")
        assert isinstance(d, dict), "Verified retailer observation without details"
        assert d.get("checked_at") == status.get("checked_at"), "Snapshot/status date mismatch"
        date = dt.date.fromisoformat(d["checked_at"])
        assert observation_day <= date <= dt.date.today(), "Snapshot outside permitted observation range"
        assert d.get("source_url") == store["url"]
        assert d.get("producer") and d.get("grapes") and d.get("region"), record["id"]
        assert d.get("aroma") and d.get("taste") and d.get("description_excerpt"), record["id"]
        assert d.get("full_name") and d.get("volume_l"), record["id"]
        # Do not ship raw/recommended-item captures to the publicly displayed catalog.
        for key in ("all_characteristics", "sections", "unparsed_rating_lines",
                    "excluded_conflicting_fields", "identity_evidence"):
            assert key not in d, (record["id"], key)
        enriched += 1
        if store.get("price_rub") is not None:
            assert isinstance(store["price_rub"], int) and 100 <= store["price_rub"] <= 1_000_000
            assert store.get("price_checked_at") == d["checked_at"]
            assert store.get("price_source_url") == store["url"]
            old = store.get("regular_price_rub")
            assert old is None or old > store["price_rub"]
            priced += 1
        local_ratings = d.get("ratings", [])
        if local_ratings:
            scored_wines += 1
        sources = set()
        for rating in local_ratings:
            assert rating.get("reported_by") == "WineStyle"
            assert rating.get("source_url") == store["url"]
            rating_day = dt.date.fromisoformat(rating["observed_on"])
            assert observation_day <= rating_day <= date, "Retailer score date out of range"
            assert rating.get("source") not in sources, "Duplicate rating source"
            assert rating.get("scale") in (5, 10, 20, 100)
            assert isinstance(rating.get("score"), (float, int)) and 0 < rating["score"] <= rating["scale"]
            assert rating.get("evidence"), "Missing score provenance"
            sources.add(rating["source"])
            ratings += 1

assert enriched == snapshot["matched_exact_products"], (enriched, snapshot)
assert priced == snapshot["direct_price_observations"], (priced, snapshot)
assert ratings == snapshot["retailer_reported_ratings"], (ratings, snapshot)
assert snapshot["regular_prices_confirmed"] == sum(
    1 for record in records for store in record["stores"]
    if (store.get("enrichment_status") or {}).get("status") == "verified"
    and store.get("regular_price_rub") is not None
), "Verified regular price count does not match manifest"
print("WINESTYLE SNAPSHOT VALIDATED", enriched, "exact products,", priced,
      "retailer prices,", ratings, "retailer-reported scores,", scored_wines, "scored products")
