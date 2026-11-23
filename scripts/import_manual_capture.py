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

from verified_offers import verified_offer, words

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


def strict_automatic_name(target, h1):
    """Reject same-producer substitutions: producer overlap alone is not wine identity.

    Accept only when *every* distinctive product token from the curated
    wishlist name OR previously SHA-verified exact retailer name appears in
    the visible main heading. This deliberately sends ambiguous products to
    review rather than inventing new verified observations.
    """
    generic={'aoc','aop','doc','docg','doca','igt','igp','doq','ava','wo'}
    shown=words(h1)
    store=target['stores'][0]
    candidates=[target.get('title')]
    details=store.get('product_details') or {}
    if (store.get('enrichment_status',{}).get('status')=='verified'
            and canonical_url(details.get('source_url'))==canonical_url(store['url'])
            and isinstance(details.get('full_name'),str)):
        candidates.append(details['full_name'])
    for candidate in candidates:
        expected=words(candidate)-generic
        if len(expected)>=2 and expected<=shown:
            return True
    return False


def verified_identity(target, capture, automated=False):
    store = target['stores'][0]
    if not isinstance(capture, dict) or capture.get('blocked'):
        return False, 'blocked_or_empty_capture'
    if canonical_url(capture.get('source_url')) != canonical_url(store['url']):
        return False, 'redirected_or_different_url'
    if not isinstance(capture.get('h1'), str) or not capture['h1'].strip():
        return False, 'missing_main_product_title'
    # Year + volume alone are not product identity: a replaced listing may
    # contain another bottle of the same vintage and size at the original URL.
    title_words = words(target.get('title'))
    if not title_words or len(title_words & words(capture['h1'])) < min(2, len(title_words)):
        return False, 'main_product_name_mismatch'
    if automated and not strict_automatic_name(target,capture['h1']):
        return False, 'strict_main_product_name_mismatch'
    year = target.get('year')
    # In a manually reviewed capture, undated vintages need a user decision.
    # In an automated capture, a title that has no vintage on either source
    # can still be the exact undated catalog product without inventing a year.
    if year is None and not automated:
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
    years.update(int(y) for y in re.findall(r'(?<!\d)(?:19\d\d|20\d\d)(?!\d)',
                                           str(capture.get('page_title') or '')))
    if year is None:
        if years:
            return False, 'unexpected_vintage_on_undated_product'
    elif years != {year}:
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
    return True, 'exact_undated_product_and_volume' if year is None else 'exact_wine_vintage_and_volume'


def numeric_displayed_rubles(text):
    """Match one literal, visible RUB amount; not a range or inferred MSRP."""
    if not isinstance(text, str) or len(text)>90:
        return None
    m=re.fullmatch(r'\s*(\d[\d \u00a0\u202f]*)\s*(?:₽|руб\.?)\s*',text,re.I)
    if not m:
        return None
    amount=int(re.sub(r'[\s\u00a0\u202f]','',m.group(1)))
    return amount if 100<=amount<=1000000 else None


def verified_visible_main_offer(target, capture):
    """Use only explicitly observed WineStyle main-product price and stock.

    Browser capture must already pass independently verified full name, URL,
    vintage, and bottle size. This provenance is separate from Product JSON-LD.
    """
    source=canonical_url(capture.get('source_url'))
    store=target['stores'][0]
    if source is None or source[0]!='spb.winestyle.ru' or source!=canonical_url(store['url']):
        return None
    v=capture.get('visible_offer')
    if not isinstance(v,dict) or (v.get('method')!='visible_main_product_price'
        or v.get('scope')!='winestyle_primary_product_panel'
        or v.get('price_currency')!='RUB'
        or capture.get('offer_evidence_complete') is not True):
        return None
    # Never silently privilege a visible price if conflicting or unparseable
    # Product/Offer JSON-LD also appeared on the same page.
    if any(isinstance(p,dict) and p.get('offers') for p in capture.get('products') or []):
        return None
    price=numeric_displayed_rubles(v.get('price_evidence'))
    if price is None or type(v.get('price_rub')) is not int or v['price_rub']!=price:
        return None
    availability=v.get('availability')
    evidence=v.get('availability_evidence')
    if not isinstance(evidence,str) or len(evidence)>180:
        return None
    if availability=='in_stock':
        if not re.match(r'^в наличии(?:\s|$)',evidence.strip(),re.I):
            return None
    elif availability=='out_of_stock':
        if not re.match(r'^(?:ожидаем поступление|нет в наличии|товар отсутствует)(?:\s|$)',evidence.strip(),re.I):
            return None
    else:
        return None
    regular=None
    if v.get('regular_price_rub') is not None or v.get('regular_price_evidence') is not None:
        regular=numeric_displayed_rubles(v.get('regular_price_evidence'))
        if regular is None or type(v.get('regular_price_rub')) is not int or (
            regular!=v['regular_price_rub'] or regular<=price):
            return None
    return {'price_rub':price,'regular_price_rub':regular,
            'availability':availability,'product_name':capture['h1'],
            'source_url':capture['source_url'],
            'verification_method':'exact_main_product_visible_price',
            'price_evidence':v['price_evidence'],
            'availability_evidence':evidence.strip(),
            'regular_price_evidence':v.get('regular_price_evidence') if regular is not None else None}


def apply_observations(catalog, observations, automated=False):
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
        if automated:
            # No per-bottle clicks. Revalidate *every* source field independently
            # below; do not equate browser navigation with human review.
            verification=obs.get('verification') or {}
            trusted_exact=verification.get('status')=='exact'
            # Backward-compatible revalidation for the first one-click run:
            # its undated, otherwise exact products were marked needs_review.
            undated_legacy=(verification.get('status')=='needs_review'
                           and verification.get('reason')=='catalog_vintage_unspecified'
                           and r.get('year') is None)
            if obs.get('capture_method') != 'automated_browser_batch' or not (trusted_exact or undated_legacy):
                summary['rejected'].append([id_, 'automated_identity_not_verified'])
                continue
        elif not obs.get('reviewer_confirmed'):
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
        ok, reason = verified_identity(r, captured, automated=automated)
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
        # Keep verified product_details as an immutable source snapshot.
        # Newly observed characteristics are separately attributed to a
        # manual capture, and only fill fields absent from both sources.
        archive = store.get('product_details')
        if not (store.get('enrichment_status', {}).get('status') == 'verified'
                and isinstance(archive, dict)
                and canonical_url(archive.get('source_url')) == canonical_url(store['url'])):
            archive = {}
        manual = store.get('research_details')
        if not (isinstance(manual, dict)
                and manual.get('source_kind') in
                    ('primary_retailer_product_description', 'manual_verified_original_seller',
                     'automated_verified_original_seller')
                and canonical_url(manual.get('source_url')) == canonical_url(store['url'])):
            manual = None
        additions = {}
        for key in OPTIONAL:
            value = visible_value((captured.get('fields') or {}).get(key))
            if value and not archive.get(key) and not (manual or {}).get(key):
                additions[key] = value
        if additions:
            if manual is None:
                manual = {'checked_at': observed_on,
                          'source_url': store['url'].split('#')[0],
                          'source_kind': ('automated_verified_original_seller' if automated
                                          else 'manual_verified_original_seller'),
                          'full_name': captured['h1']}
                store['research_details'] = manual
            field_dates = manual.setdefault('field_checked_at', {})
            for key, value in additions.items():
                manual[key] = value
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
            # Two simultaneous sources on the same WineStyle page must agree.
            # Do not publish a JSON-LD offer when the primary visible product
            # panel explicitly shows a different price or stock status.
            if (offer and canonical_url(store['url'])[0]=='spb.winestyle.ru'
                    and captured.get('visible_offer') is not None):
                panel=verified_visible_main_offer(r,captured)
                if (not panel or panel['price_rub']!=offer['price_rub'] or
                        (offer['availability']!='unknown' and
                         panel['availability']!=offer['availability'])):
                    offer=None
            if offer and observed_on >= (review.get('checked_at') or store.get('enrichment_status', {}).get('checked_at', '9999-12-31')):
                previous = store.get('live_offer') or {}
                if previous.get('observed_on', '') <= observed_on:
                    offer['observed_on'] = observed_on
                    offer['capture_method'] = ('automated_browser_batch' if automated
                                               else 'user_confirmed_active_browser_tab')
                    if previous != offer:
                        store['live_offer'] = offer
                        summary['live_offers_updated'] += 1
        # WineStyle usually publishes its offer only as visible main-page HTML.
        # In that case, a strictly identified browser capture provides a
        # separate documented offer without inventing JSON-LD or discount.
        if (automated and not any(isinstance(p,dict) and p.get('offers')
                                  for p in captured.get('products') or [])):
            visible=verified_visible_main_offer(r,captured)
            if visible and observed_on >= (review.get('checked_at') or
                   store.get('enrichment_status',{}).get('checked_at','9999-12-31')):
                previous=store.get('live_offer') or {}
                if previous.get('observed_on','')<=observed_on:
                    visible['observed_on']=observed_on
                    visible['capture_method']='automated_browser_batch'
                    if visible!=previous:
                        store['live_offer']=visible
                        summary['live_offers_updated']+=1
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
    legacy = (imported.get('schema_version') == 1
              and imported.get('source') == 'wine_atlas_manual_extension')
    automated = (imported.get('schema_version') == 2
                 and imported.get('source') == 'wine_atlas_automated_browser_extension')
    if not (legacy or automated):
        raise SystemExit('Unexpected capture schema or source')
    observations = imported.get('observations')
    if not isinstance(observations, list) or len(observations) > 1000:
        raise SystemExit('Invalid observation count')
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    revised, summary = apply_observations(catalog, observations, automated=automated)
    if args.apply and revised != catalog:
        output = args.catalog.with_suffix('.new')
        output.write_text(json.dumps(revised,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        output.replace(args.catalog)
    print(json.dumps({'mode':'apply' if args.apply else 'dry_run',**summary},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
