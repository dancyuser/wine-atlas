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
import math
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

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


def checked_rating(row, expected_url, min_day, product_day):
    require(isinstance(row, dict), "rating must be a mapping")
    require(row.get("reported_by") == "WineStyle" and row.get("source_url") == expected_url,
            "rating source URL/provider mismatch")
    require(isinstance(row.get("source"), str) and row["source"], "rating source absent")
    require(type(row.get("scale")) is int and row["scale"] in ALLOWED_SCALES, "invalid scale")
    require(type(row.get("score")) in (int, float) and 0 < row["score"] <= row["scale"],
            "invalid rating")
    require(isinstance(row.get("evidence"), str) and row["evidence"].strip(), "no rating evidence")
    observed = day(row.get("observed_on"))
    require(min_day <= observed <= product_day, "rating date outside verified observation window")


TEXT_FIELDS = {
    "full_name", "producer", "country", "region", "appellation", "grapes",
    "color", "wine_style", "sweetness", "taste", "aroma", "pairing_notes",
    "description_excerpt", "brand", "body", "aging_potential", "color_intensity",
    "availability_note", "image_url", "image_source",
}


def validate_details_schema(details, product_day):
    """Reject malformed published fields *before* changing the active catalog."""
    require(isinstance(details, dict), "product details must be a mapping")
    for key in TEXT_FIELDS:
        value = details.get(key)
        require(value is None or isinstance(value, str),
                f"published field {key} must be a string")
    for key in ("volume_l", "alcohol_percent"):
        value = details.get(key)
        require(value is None or (type(value) in (str, float, int)
                                  and not (isinstance(value, str) and not value.strip())),
                f"published field {key} has invalid type")
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            require(math.isfinite(value), f"published field {key} must be finite")
    require(details.get("ratings") is None or isinstance(details["ratings"], list),
            "ratings must be a list or null before normalization")
    availability = details.get("availability_spb")
    require(availability is None or type(availability) is bool, "invalid availability type")
    for name in ("field_sources", "field_evidence", "field_checked_at"):
        values = details.get(name)
        require(values is None or isinstance(values, dict), f"{name} must be a mapping")
        for key, value in (values or {}).items():
            require(isinstance(key, str) and isinstance(value, str) and value.strip(),
                    f"{name} must contain nonempty string keys/values")
            if name == "field_checked_at":
                require(day(value) <= product_day,
                        f"field_checked_at.{key} after product observation")


IDENTITY_STOPWORDS = {
    "wine", "вино", "port", "портвейн", "doc", "docg", "igt", "aoc",
    "aop", "do", "d", "s", "gift", "tube", "box", "в", "тубе",
    "подарочной", "упаковке", "л", "l", "ml", "мл", "бутылка",
    "игристое", "портвеин",
}
YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def identity_tokens(value):
    decomposed = unicodedata.normalize("NFKD", str(value)).casefold()
    clean = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    words = re.sub(r"[^a-zа-я0-9]+", " ", clean).split()
    return {word for word in words if word not in IDENTITY_STOPWORDS
            and not word.isdigit()}



VOLUME_PATTERN = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|cl|л|l|литр|литра|литров)?\s*$", re.I
)
NAME_VOLUME_PATTERN = re.compile(
    r"(?<![\w])(\d+(?:[.,]\d+)?)\s*(мл|ml|cl|л|l)(?![\w])", re.I
)


def parse_volume_l(value):
    if value is None or isinstance(value, bool):
        return None
    match = VOLUME_PATTERN.fullmatch(str(value))
    if not match:
        return None
    amount = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "").lower()
    if unit in ("мл", "ml"):
        amount /= 1000
    elif unit == "cl":
        amount /= 100
    return amount if math.isfinite(amount) and 0.05 <= amount <= 30 else None


def validate_product_identity(record, store, details):
    """Validate the imported *product*, not only its external record wrapper.

    Slug/name concordance follows the conservative HTML extractor. Year
    assertions are independent of the catalog title and cannot be fabricated
    by leaving the product's vintage unconfirmed.
    """
    name = details.get("full_name")
    producer = details.get("producer")
    require(isinstance(name, str) and name.strip() and
            isinstance(producer, str) and producer.strip(),
            f"verified product identity missing: {record['id']}")
    slug = unquote(urlsplit(store["url"]).path.rsplit("/", 1)[-1])
    if slug.lower().endswith(".html"):
        slug = slug[:-5]
    expected_tokens = identity_tokens(slug)
    if not expected_tokens:
        expected_tokens = identity_tokens(record["title"])
    actual_tokens = identity_tokens(name)
    require(expected_tokens and
            len(expected_tokens.intersection(actual_tokens)) / len(expected_tokens) >= 0.9,
            f"product_details name does not match original URL: {record['id']}")
    # One-way slug coverage is not sufficient: "Riserva", "Reserve" and
    # other extra cuvee names can refer to a different wine from the same estate.
    extra = actual_tokens - expected_tokens - identity_tokens(record["title"])
    previous_name = (store.get("product_details") or {}).get("full_name")
    if extra and previous_name != name:
        require(False, f"unexpected cuvee qualifiers in product_details: {sorted(extra)}")
    visible_years = {int(y) for y in YEAR_PATTERN.findall(name)}
    vintage = details.get("vintage")
    explicit_year = None
    if vintage is not None and str(vintage).strip():
        require(isinstance(vintage, (str, int)) and type(vintage) is not bool
                and bool(re.fullmatch(r"(?:19|20)\d{2}", str(vintage))),
                f"invalid explicit product vintage: {record['id']}")
        explicit_year = int(vintage)
    target_year = record.get("year")
    if target_year is not None:
        require(type(target_year) is int, "catalog year must be an integer or null")
        require((not visible_years or visible_years == {target_year}) and
                (explicit_year is None or explicit_year == target_year) and
                (visible_years or explicit_year is not None),
                f"product_details vintage mismatches or unconfirmed: {record['id']}")
    else:
        require(not visible_years and explicit_year is None,
                f"unexpected vintage for non-vintage catalog wine: {record['id']}")
    # A bottle size printed in the product title, in the overlay fields or
    # in a previously verified snapshot must not contradict a known variant.
    observed_volumes = []
    if details.get("volume_l") is not None:
        incoming_volume = parse_volume_l(details["volume_l"])
        require(incoming_volume is not None, f"invalid product volume: {record['id']}")
        observed_volumes.append(incoming_volume)
    for match in NAME_VOLUME_PATTERN.finditer(name):
        volume_from_name = parse_volume_l(" ".join(match.groups()))
        if volume_from_name is not None:
            observed_volumes.append(volume_from_name)
    source_volume = record.get("volume_l")
    previous = store.get("product_details") or {}
    if source_volume is None and previous.get("source_url") == store["url"]:
        source_volume = parse_volume_l(previous.get("volume_l"))
    if source_volume is not None:
        expected_volume = parse_volume_l(source_volume)
        require(expected_volume is not None, f"invalid reference volume: {record['id']}")
        require(all(abs(volume - expected_volume) <= 0.001 for volume in observed_volumes),
                f"product_details volume mismatches catalog bottle: {record['id']}")
    require(not observed_volumes or max(observed_volumes) - min(observed_volumes) <= 0.001,
            f"conflicting volume in product_details: {record['id']}")


def merge_details(previous, incoming):
    """Merge partial published retailer fields without erasing independent older observations."""
    if previous is None:
        previous = {}
    require(isinstance(previous, dict), "previous details must be a mapping")
    if not previous or previous == incoming:
        return copy.deepcopy(incoming)
    require(previous.get("source_url") in (None, incoming["source_url"]),
            "existing product details belong to another URL")
    combined = copy.deepcopy(previous)
    sources = dict(previous.get("field_sources") or {})
    dates = dict(previous.get("field_checked_at") or {})
    evidence = dict(previous.get("field_evidence") or {})
    meta = {"checked_at", "source_url", "field_sources", "field_checked_at", "field_evidence"}
    for key, value in previous.items():
        if key not in meta and value is not None and key not in dates and previous.get("checked_at"):
            dates[key] = previous["checked_at"]
    for key, value in incoming.items():
        if key in meta or value is None or value == "" or value == []:
            continue
        old = combined.get(key)
        incoming_day = day((incoming.get("field_checked_at") or {}).get(key, incoming["checked_at"]))
        saved_date = dates.get(key, previous.get("checked_at"))
        if key != "ratings" and old is not None and saved_date and day(saved_date) > incoming_day:
            # A newer snapshot can still carry an older independently observed field.
            continue
        if key == "ratings":
            by_source = {r["source"]: r for r in (old or [])
                         if isinstance(r, dict) and isinstance(r.get("source"), str)}
            for rating in value:
                prior = by_source.get(rating["source"])
                if prior and prior.get("observed_on") and day(prior["observed_on"]) > day(rating["observed_on"]):
                    continue
                by_source[rating["source"]] = rating
            combined["ratings"] = list(by_source.values())
        else:
            combined[key] = value
        supplied_source = (incoming.get("field_sources") or {}).get(key)
        if supplied_source:
            sources[key] = supplied_source
        elif old != combined.get(key):
            # Never reuse provenance of the replaced value.
            sources[key] = "user_supplied_browser_capture"
        else:
            sources[key] = sources.get(key, "user_supplied_browser_capture")
        dates[key] = incoming_day.isoformat()
        new_evidence = (incoming.get("field_evidence") or {}).get(key)
        if new_evidence:
            evidence[key] = new_evidence
        elif old != combined.get(key):
            evidence.pop(key, None)
    if incoming.get("availability_spb") is not None and (
        combined.get("availability_spb") == incoming["availability_spb"]
    ):
        newer_stock_day = day(dates.get("availability_spb", incoming["checked_at"]))
        note_date = dates.get("availability_note", previous.get("checked_at"))
        if not note_date or newer_stock_day >= day(note_date):
            combined.pop("availability_note", None)
            sources.pop("availability_note", None)
            dates.pop("availability_note", None)
            evidence.pop("availability_note", None)
    combined.update(source_url=incoming["source_url"], checked_at=incoming["checked_at"])
    combined["field_sources"] = sources
    combined["field_checked_at"] = dates
    combined["field_evidence"] = evidence
    return combined


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
            checked_rating(rating, store["url"], source_date, observed)
            require(rating["source"] not in seen_sources, f"duplicate critic: {id_}")
            seen_sources.add(rating["source"])
        incoming = {k: v for k, v in d.items() if k not in PUBLISH_EXCLUDE}
        # Normalize before comparing against an already published snapshot:
        # absence or null of ratings means an empty observation, not a new shape.
        incoming["ratings"] = source_ratings
        validate_details_schema(incoming, observed)
        clean = merge_details(store.get("product_details"), incoming)
        # The published snapshot contract uses a list, including when no ratings exist.
        if clean.get("ratings") is None:
            clean["ratings"] = []
        validate_details_schema(clean, observed)
        validate_product_identity(record, store, incoming)
        validate_product_identity(record, store, clean)
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
            # Preserve original source date and hash. Older independent captures
            # are permitted for other wines, subject to per-record freshness gates.
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
    # Validate the complete JSON output before atomic replacement; Python's default
    # json.dumps would otherwise encode Infinity/NaN, invalid in browsers.
    json.dumps(new, ensure_ascii=False, allow_nan=False)
    manifest_changed = new.get("retailer_snapshot") != catalog.get("retailer_snapshot")
    return new, {
        "manifest_changed": manifest_changed,
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
    if args.apply and data != catalog:
        backup = args.catalog.parent / "backups" / (
            "wines.before-overlay." + hashlib.sha256(source).hexdigest()[:12] + ".json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(source)
        atomic_write(args.catalog, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
