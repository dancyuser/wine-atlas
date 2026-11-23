#!/usr/bin/env python3
"""Recover source-labelled WineStyle scores missed by the first browser extractor.

Offline only: no WineStyle requests and no bypass of the recorded HTTP 403.
By default read-only. The capture SHA256, exact product URL and record ID are
required before an extracted score can be attached to a wine.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "wines.json"
SOURCES = (
    "Wine Spectator", "Wine Enthusiast", "James Suckling", "Robert Parker",
    "Jancis Robinson", "Vinous", "Decanter | 100", "Decanter",
    "Tim Atkin", "Falstaff Magazine", "Falstaff", "Vivino", "Luca Maroni",
)
SOURCE_ALIASES = {"Decanter | 100": "Decanter", "Falstaff Magazine": "Falstaff"}
SCORE = re.compile(
    r"(?<!\d)(\d{1,3}(?:[.,]\d+)?)\s*/\s*(5|10|20|100)\s+("
    + "|".join(re.escape(source) for source in SOURCES)
    + r")(?![\w])"
)


def score_rows(text):
    """Parse only the current product's first score strip, before related items."""
    if not isinstance(text, str):
        return []
    start = text.find(" О товаре ")
    end = text.find(" Все товары ", start + 1) if start >= 0 else -1
    # A missing boundary is unsafe: related-product ratings might be present.
    if start < 0 or end <= start:
        return []
    strip = text[start + len(" О товаре "):end]
    unique = {}
    conflicts = set()
    for match in SCORE.finditer(strip):
        value, scale = float(match.group(1).replace(",", ".")), int(match.group(2))
        if not (0 < value <= scale):
            continue
        source = SOURCE_ALIASES.get(match.group(3), match.group(3))
        row = {
            "source": source, "score": int(value) if value.is_integer() else value,
            "scale": scale, "ratings_count": None, "scope": "unspecified",
            "reported_by": "WineStyle", "evidence": match.group(0),
            "method": "visible_primary_rating_text_recovered_from_saved_capture",
        }
        if source in unique and (
            unique[source]["score"], unique[source]["scale"]
        ) != (row["score"], row["scale"]):
            conflicts.add(source)
        else:
            unique[source] = row
    return [row for source, row in unique.items() if source not in conflicts]


def recover(catalog, capture, sha256):
    snapshot = catalog["retailer_snapshot"]
    if sha256 != snapshot["source_export_sha256"]:
        raise ValueError("Export SHA256 differs from the catalog's recorded source")
    index = {
        (s["url"], r["id"]): (r, s)
        for r in catalog["records"] for s in r.get("stores", [])
    }
    changed, added = 0, 0
    for observation in capture["captures"]:
        if observation.get("status") != "captured":
            continue
        ident = observation.get("identity") or {}
        url, wine_id = observation.get("url"), ident.get("target_id")
        match = index.get((url, wine_id))
        if match is None:
            continue
        record, store = match
        details = store.get("product_details") or {}
        if (store.get("enrichment_status") or {}).get("status") != "verified":
            continue
        if details.get("source_url") != url or ident.get("canonical_url") != url:
            continue
        if ident.get("target_year") != record.get("year"):
            continue
        observed = dt.date.fromisoformat(details["checked_at"])
        candidates = score_rows(observation.get("raw_product_text"))
        current = details.get("ratings", [])
        by_source = {row["source"]: row for row in current}
        new_count = 0
        for row in candidates:
            source = row["source"]
            existing = by_source.get(source)
            if existing is not None:
                if (existing["score"], existing["scale"]) != (row["score"], row["scale"]):
                    raise ValueError("Conflicting score for " + str((url, source)))
                continue
            # Do not make a date claim newer than the product's verified snapshot.
            row["source_url"] = url
            row["observed_on"] = observed.isoformat()
            current.append(row)
            by_source[source] = row
            added += 1
            new_count += 1
        if new_count:
            details["ratings"] = current
            changed += 1
    # Manifest reflects all published scores, rather than just the old 182.
    snapshot["retailer_reported_ratings"] = sum(
        len(s.get("product_details", {}).get("ratings", []))
        for r in catalog["records"] for s in r["stores"]
    )
    return changed, added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Original saved WineStyle JSON")
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--apply", action="store_true", help="Write after validation")
    args = parser.parse_args()
    original = args.capture.read_bytes()
    sha256 = hashlib.sha256(original).hexdigest()
    capture = json.loads(original)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    changed, added = recover(catalog, capture, sha256)
    print(f"Matched: {changed} wines; new scores: {added}; total: "
          f"{catalog['retailer_snapshot']['retailer_reported_ratings']}")
    if args.apply and added:
        import os
        import tempfile
        with tempfile.NamedTemporaryFile("w", dir=args.catalog.parent,
                                         suffix=".tmp", encoding="utf-8",
                                         delete=False) as fp:
            try:
                json.dump(catalog, fp, ensure_ascii=False, indent=2)
                fp.write("\n")
                fp.flush()
                os.fsync(fp.fileno())
                temp_path = fp.name
            except BaseException:
                Path(fp.name).unlink(missing_ok=True)
                raise
        os.replace(temp_path, args.catalog)
        print("Catalog updated; run scripts/validate_enrichment.py")
    elif not args.apply:
        print("Dry run only. Add --apply after reviewing recovered values.")


if __name__ == "__main__":
    main()
