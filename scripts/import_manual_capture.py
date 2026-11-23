#!/usr/bin/env python3
"""Import explicitly reviewed observations from the Wine Atlas MV3 extension.

Default is dry-run. Reject wrong URLs/vintages/bottle sizes; never import
photos, customer ratings, scraper-derived old prices or unlicensed assets.
The immutable WineStyle snapshot and retailer audit are not rewritten.
"""
import argparse
import copy
from datetime import datetime, timezone, date
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

from verified_offers import verified_offer

ROOT = Path(__file__).resolve().parents[1]
OPTIONAL = (
    'alcohol_percent', 'aroma', 'taste', 'body', 'color', 'color_intensity',
    'aging_potential', 'pairing_notes', 'wine_style', 'producer', 'region',
)
MAX_IMPORT = 12_000_000


def canonical_url(url):
    try:
        u = urlsplit(url)
        if u.scheme != 'https' or not u.hostname or u.username or u.password:
            return None
        return (u.hostname.lower(), unquote(u.path).rstrip('/'), u.query)
    except (TypeError, ValueError):
        return None


def observation_day(value):
    if not isinstance(value, str):
        return None
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if instant.tzinfo is None or instant > datetime.now(timezone.utc):
            return None
        return instant.date().isoformat()
    except ValueError:
        return None


def volume_mls(value):
    """Find ALL candidate sizes; the presence of a conflicting size rejects identity."""
    value = str(value or '').replace(',', '.')
    values = set()
    for m in re.finditer(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(мл|ml|л|l)(?!\w)',
                         value, flags=re.I):
        number = float(m[1])
        ml = round(number * (1 if m[2].lower() in ('мл', 'ml') else 1000))
        if 50 <= ml <= 30000:
            values.add(ml)
    return values


def visible_value(payload):
    if not isinstance(payload, dict) or payload.get('method') != 'visible_product_label':
        return None
    value = payload.get('value')
    evidence = payload.get('evidence')
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        return None
    if not isinstance(evidence, str) or value.strip() not in evidence or len(evidence) > 650:
        return None
    return value.strip()


def verified_identity(target, capture):
    store = target['stores'][0]
    if not isinstance(capture, dict) or capture.get('blocked'):
        return False, 'blocked_or_empty_capture'
    if canonical_url(capture.get('source_url')) != canonical_url(store['url']):
        return False, 'redirected_or_different_url'
    if not isinstance(capture.get('h1'), str) or not capture['h1'].strip():
        return False, 'missing_main_product_title'
    year = target.get('year')
    # Undated targets may be non-vintage products. Never guess the year.
    if year is None:
        return False, 'unidentified_vintage'
    product_names = [capture['h1']]
    matched_products = []
    for product in capture.get('products') or []:
        if not isinstance(product, dict):
            continue
        if product.get('url') and canonical_url(product['url']) != canonical_url(store['url']):
            continue
        matched_products.append(product)
        product_names.append(str(product.get('name') or ''))
    years = {int(y) for y in re.findall(r'(?<!\d)(?:19\d\d|20\d\d)(?!\d)', ' '.join(product_names))}
    dedicated = visible_value((capture.get('fields') or {}).get('vintage'))
    if dedicated:
        years.update(int(y) for y in re.findall(r'(?<!\d)(?:19\d\d|20\d\d)(?!\d)', dedicated))
    if years != {year}:
        return False, 'missing_or_conflicting_vintage'
    expected_ml = round((target.get('volume_l') or 0) * 1000)
    if expected_ml < 50:
        return False, 'missing_target_bottle_size'
    measurements = set()
    for value in [
        *product_names,
        visible_value((capture.get('fields') or {}).get('volume_l')),
        *(p.get('size') for p in matched_products),
    ]:
        measurements.update(volume_mls(value))
    if measurements != {expected_ml}:
        return False, 'missing_or_conflicting_bottle_size'
    return True, 'exact_wine_vintage_and_volume'


def apply_observations(catalog, observations):
    catalog = copy.deepcopy(catalog)
    index = {r['id']: r for r in catalog['records']}
    summary = {'observations': 0, 'accepted_identity': 0, 'rejected': [],
               'details_added': 0, 'live_offers_updated': 0,
               'photos_imported': 0, 'ratings_imported': 0}
    for obs in observations:
        summary['observations'] += 1
        id_ = obs.get('target_id') if isinstance(obs, dict) else None
        r = index.get(id_)
        if not r:
            summary['rejected'].append([id_, 'unknown_target'])
            continue
        if not obs.get('reviewer_confirmed'):
            summary['rejected'].append([id_, 'not_reviewed_by_user'])
            continue
        store = r['stores'][0]
        if canonical_url(obs.get('target_url')) != canonical_url(store['url']):
            summary['rejected'].append([id_, 'catalog_url_mismatch'])
            continue
        captured = obs.get('capture') or {}
        observed_on = observation_day(captured.get('captured_at'))
        if not observed_on:
            summary['rejected'].append([id_, 'invalid_capture_date'])
            continue
        ok, reason = verified_identity(r, captured)
        if not ok:
            summary['rejected'].append([id_, reason])
            continue
        review = r.get('publication_review') or {}
        verified_archive = (store.get('enrichment_status', {}).get('status') == 'verified'
                            and canonical_url(store.get('enrichment_status', {}).get('source_url')) ==
                                canonical_url(store['url'])
                            and store.get('product_details', {}).get('source_url') == store['url'])
        if review.get('status') == 'excluded' or not (review.get('status') == 'verified' or verified_archive):
            summary['rejected'].append([id_, 'not_approved_for_publication'])
            continue
        summary['accepted_identity'] += 1
        d = store.get('product_details') if store.get('enrichment_status', {}).get('status') == 'verified' else None
        if d is not None and canonical_url(d.get('source_url')) != canonical_url(store['url']):
            d = None
        if d is None:
            d = store.get('research_details')
            if d is not None and canonical_url(d.get('source_url')) != canonical_url(store['url']):
                d = None
        if d is None:
            # This is new, separately labelled manual provenance, not a WineStyle
            # snapshot and not part of the immutable retailer ingestion manifest.
            d = {'checked_at': observed_on, 'source_url': store['url'].split('#')[0],
                 'source_kind': 'manual_verified_original_seller'}
            store['research_details'] = d
        field_dates = d.setdefault('field_checked_at', {})
        for key in OPTIONAL:
            value = visible_value((captured.get('fields') or {}).get(key))
            if value and not d.get(key):
                d[key] = value
                field_dates[key] = observed_on
                summary['details_added'] += 1
        # Offer import is independent from labels. Never accept a price based
        # on a generic price element, an AggregateOffer or browser text alone.
        # Verify every matching Product together. Conflicting offers must be
        # rejected as a group, independently of JSON-LD node ordering.
        products = [p for p in (captured.get('products') or [])
                    if isinstance(p,dict) and
                    (not p.get('url') or canonical_url(p['url']) == canonical_url(store['url']))]
        if products and captured.get('offer_evidence_complete') is True:
            synthetic = '<script type="application/ld+json">' + json.dumps(
                products, ensure_ascii=False
            ) + '</script>'
            verified_record = r if review.get('status') == 'verified' else {
                **r, 'publication_review': {'status':'verified','final_url':store['url'].split('#')[0]}
            }
            offer, _ = verified_offer(synthetic, verified_record, store['url'].split('#')[0],
                                      captured['source_url'].split('#')[0])
            if offer and observed_on >= (review.get('checked_at') or store.get('enrichment_status', {}).get('checked_at', '9999-12-31')):
                previous = store.get('live_offer') or {}
                if previous.get('observed_on', '') <= observed_on:
                    offer['observed_on'] = observed_on
                    offer['capture_method'] = 'user_confirmed_active_browser_tab'
                    if previous != offer:
                        store['live_offer'] = offer
                        summary['live_offers_updated'] += 1
    return catalog, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path, help='Exported JSON from extension, NOT the raw HTML archive')
    p.add_argument('--catalog', type=Path, default=ROOT/'data'/'wines.json')
    p.add_argument('--apply', action='store_true', help='Write validated updates to catalog')
    args = p.parse_args()
    if args.capture.stat().st_size > MAX_IMPORT:
        raise SystemExit('Capture file exceeds safe size limit')
    imported = json.loads(args.capture.read_text(encoding='utf-8'))
    if imported.get('schema_version') != 1 or imported.get('source') != 'wine_atlas_manual_extension':
        raise SystemExit('Unexpected capture schema or source')
    observations = imported.get('observations')
    if not isinstance(observations, list) or len(observations) > 1000:
        raise SystemExit('Invalid observation count')
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    revised, summary = apply_observations(catalog, observations)
    if args.apply and revised != catalog:
        output = args.catalog.with_suffix('.new')
        output.write_text(json.dumps(revised,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        output.replace(args.catalog)
    print(json.dumps({'mode':'apply' if args.apply else 'dry_run',**summary},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
