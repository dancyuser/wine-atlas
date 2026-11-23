# WineStyle HTML parser with retailer-reported ratings

This feature ports the non-invasive HTML extractor from historic agent commit `9e9985b` to the current 124-wine wishlist without merging its outdated 163-wine catalog.

## Capabilities

- Strict match of product name, producer, year and known bottle volume before accepting product-related values.
- Parse Product JSON-LD and labelled product DOM: name, producer, country, region, appellation, grapes, color, style, sweetness, ABV, volume, tasting notes, aroma, pairings, description, explicit offer price / previous price, source date, and availability only when the Saint Petersburg region is explicit.
- Parse `Product.aggregateRating` (WineStyle user score, count, scale); structured expert reviews with named authors, or explicit labelled rating sections (e.g. Wine Enthusiast 94/100, Jancis Robinson 16.5/20). Reject unlabelled scores, unrecognized critics, invalid scales, conflicts and recommendation widgets.
- Keep all WineStyle-reported scores in `stores[].product_details.ratings`, each with source, original score and scale, count if present, date, URL and extraction method.
- Do **not** copy retailer-reported scores into the authoritative `data/ratings.json`. They are displayed with a retailer-provenance warning and never affect Vivino or the computed index.
- Atomic file writes, local backup, imported field-level timestamps, safe repeat imports; original manual edits and archival prices retained. No unauthorized images displayed.

## Current access status

The historic agent reports an automated HTTP 403 response from WineStyle on 2026-11-22. A blocking marker is carried forward in `reports/winestyle-access.json`. The generic price updater skips the entire WineStyle domain, even if run through GitHub Actions. This PR makes **zero new live requests** to WineStyle. Its parser and rating fixtures were tested offline; the real WineStyle DOM and end-to-end network collection remain unverified. The active catalog retains 124 entries. From the supplied browser export, 118 exact products were enriched with 88 observed prices and 246 retailer-reported scores; independently verified Vivino data remain unchanged.

Do not remove the blocked-state marker to work around QRATOR, CAPTCHA or other site access controls. Before any future automated collection, establish permission under applicable site terms, verify robots.txt and ordinary automated access, and only then review the block with an audit trail.

## Offline HTML import from normal, authorized browsing

Install the parser:

~~~powershell
python -m pip install -r scripts/requirements-enrichment.txt
~~~

Create local `manual/` containing `manifest.json` and a *manually obtained* page snapshot. The snapshot must be for the exact same active wishlist URL and be saved as UTF-8 HTML. Synthetic example of a manifest:

~~~json
[
  {
    "url": "https://spb.winestyle.ru/products/Graham-s-Late-Bottled-Vintage-LBV-2019-gift-tube.html",
    "file": "graham-2019.html",
    "checked_at": "2026-11-22"
  }
]
~~~

Run a read-only preview first:

~~~powershell
python scripts/enrich_winestyle.py --input-dir manual --dry-run --limit 3
python scripts/enrich_winestyle.py --input-dir manual --limit 3
python scripts/validate_catalog.py
python scripts/validate_ratings.py
python -m unittest discover -s scripts -p "test_winestyle_parser.py" -v
node --check app.js
~~~

The offline parser neither contacts WineStyle nor automatically clears a previously recorded 403. Its output only applies to exact URLs present in the current catalogue. Add the resulting reviewed `data/wines.json` changes to a separate draft PR. Do not commit source HTML or personal browsing data. Confirm each extracted price and rating against the saved page before review.

## Reviewed browser export import (2026-11-22)

The user supplied a captured JSON archive of 121 target WineStyle URLs. Of these, 118 exact product/vintage matches passed the offline validation process, while three redirects were excluded. The resulting 118 `product_details` snapshots, 88 prices and 182 retailer-published ratings have been added to `data/wines.json`. All prices and scores carry an observation date and source provenance. The original complete capture is held by the user; the public repository contains the compact product details plus SHA256 and the audit at `data/archive/winestyle-import-audit-2026-11-22.json`.

A repeatable offline importer is provided. To verify an overlay without writes:

~~~powershell
python scripts/import_enrichment_overlay.py path/to/winestyle-enrichment-overlay-2026-11-22.json
~~~

Add `--apply` only after reviewing the dry-run output. It enforces identity, vintage, URL, date, rating provenance and audit counts, preserving archived prices and manually curated values. If run on an already imported identical snapshot, it reports no changes.

The site shows short excerpts, specific wine details and source-labelled ratings. Country, grape and food-pairing filters use verified details when the existing metadata lacks those values; pre-existing curated grapes take precedence.

**Limitations:** the actual browser DOM/live network scraper is not independently validated within GitHub Actions, because the submitted export contains extracted text, not replayable HTML. The 246 ratings are WineStyle's reported values, not independently sourced reviews. No new live network request to WineStyle was made by this PR. Changes to QRATOR behavior and retailer stock are not assumed.

## Post-capture score recovery, 23 Nov 2026

The original authorized browser export contained `raw_product_text` for exact-matched products. The first extraction missed score-first headers such as `93 /100 Wine Enthusiast`, while its initial parser had only collected 182 ratings. The offline recovery extracted and source-checked 64 additional entries across 27 verified products (246 total) without any new retailer requests. The original capture must match the catalog's recorded SHA256; URL, catalog ID, canonical URL and vintage also must match. No redirected products are imported.

~~~bash
python scripts/recover_capture_ratings.py 'winestyle-capture-2026-11-22 (1).json'
python scripts/recover_capture_ratings.py 'winestyle-capture-2026-11-22 (1).json' --apply
python scripts/validate_enrichment.py
python -m unittest discover -s scripts -p 'test_recover_capture_ratings.py' -v
~~~

The current WineStyle HTML rating extractor also recognizes this score-first header convention under strict product-region constraints. Live HTML parsing remains unverified: the saved user export is text, not a replayable DOM snapshot. Price-before-discount remains unsupported by the reviewed export; do not infer it from old prices. Three exact vintage-specific photos have source attribution; other cards intentionally use a neutral placeholder rather than another product's bottle.
