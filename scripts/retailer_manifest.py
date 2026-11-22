"""Reconcile the WineStyle capture manifest with the catalog currently being published.

The manifest references the original browser export by hash; counts reflect only
still-present *exact* product snapshots, not every URL in a newer wishlist.
No network access. No source data is generated or inferred.
"""
from urllib.parse import urlsplit


def is_winestyle(url):
    host = (urlsplit(url).hostname or "").lower()
    return host == "winestyle.ru" or host.endswith(".winestyle.ru")


def reconcile_manifest(previous_manifest, records):
    """Recount retained captures, prices, scores and redirected variants.

    Keep the original source SHA and observation date: these identify where the
    historic observations originated, not a claim of live availability.
    """
    if not previous_manifest:
        return None
    manifest = dict(previous_manifest)
    stores = {store["url"]: store
              for record in records for store in record.get("stores", [])
              if is_winestyle(store.get("url", ""))}
    verified = []
    for url, store in stores.items():
        state = store.get("enrichment_status") or {}
        data = store.get("product_details") or {}
        if (state.get("status") == "verified" and state.get("source_url") == url
                and isinstance(data, dict) and data.get("source_url") == url):
            verified.append(store)
    mismatched_urls = [
        url for url in manifest.get("mismatched_urls", [])
        if url in stores and all(s["url"] != url for s in verified)
    ]
    manifest.update(
        mismatched_urls=mismatched_urls,
        matched_exact_products=len(verified),
        mismatched_variants=len(mismatched_urls),
        collected_target_urls=len(verified) + len(mismatched_urls),
        direct_price_observations=sum(store.get("price_rub") is not None for store in verified),
        retailer_reported_ratings=sum(len((store.get("product_details") or {}).get("ratings") or [])
                                      for store in verified),
        regular_prices_confirmed=sum(store.get("regular_price_rub") is not None for store in verified),
    )
    dates = [(store.get("product_details") or {}).get("checked_at") for store in verified]
    dates = [day for day in dates if isinstance(day, str)]
    if dates:
        manifest["latest_observed_on"] = max(dates)
    else:
        manifest.pop("latest_observed_on", None)
    return manifest
