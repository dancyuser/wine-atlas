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

The historic agent reports an automated HTTP 403 response from WineStyle on 2026-11-22. A blocking marker is carried forward in `reports/winestyle-access.json`. The generic price updater skips the entire WineStyle domain, even if run through GitHub Actions. This PR makes **zero new live requests** to WineStyle. Its parser and rating fixtures were tested offline; the real WineStyle DOM and end-to-end network collection remain unverified. All 124 current catalog entries and existing Vivino ratings remain unchanged.

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

**Limitation:** no full, live WineStyle HTML snapshot is available in this PR or the agent archive. For that reason, the implementation cannot credibly be called a verified working live scraper. Real selectors must be tested on permitted source HTML, and the parsed results checked manually, before claiming that all fields and ratings have been collected.
