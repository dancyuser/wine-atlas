#!/usr/bin/env python3
"""Conservative WineStyle enrichment. No private APIs or access-control workarounds.

BeautifulSoup: pip install -r scripts/requirements-enrichment.txt
Playwright is optional, and only used with --headed on otherwise permitted pages.
Offline imports use a manifest of user-saved public HTML; see README.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import unquote, urlsplit, urljoin
from winestyle_ratings import extract_ratings, is_recommendation
from retailer_manifest import reconcile_manifest

ROOT = Path(__file__).resolve().parents[1]
AGENT = 'PersonalWineAtlasCatalog/1.0 (respectful metadata fetch)'
LOG = logging.getLogger('winestyle')
DETAIL_FIELDS = ('full_name', 'producer', 'vintage', 'country', 'region',
                 'appellation', 'grapes', 'color', 'wine_type', 'sweetness',
                 'alcohol_percent', 'volume_l', 'taste', 'aroma', 'food_pairings',
                 'description', 'image_url', 'image_source', 'availability_spb', 'ratings')


def today():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date().isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         delete=False, suffix='.tmp') as f:
            name = f.name
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def backup(path):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:12]
    dest = path.parent / 'backups' / f'{path.stem}.{today()}.{digest}.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(raw)
    return dest


def is_winestyle(url):
    host = (urlsplit(url).hostname or '').lower()
    return host == 'winestyle.ru' or host.endswith('.winestyle.ru')


def url_key(url):
    p = urlsplit(url)
    return ((p.hostname or '').lower(), unquote(p.path).rstrip('/').lower())


def normalized(value):
    return re.sub(r'[^a-zа-я0-9]+', ' ', unicodedata.normalize('NFKD', str(value)).lower()).strip()


def tokens(value):
    return set(normalized(value).split()) - {
        'wine', 'вино', 'doc', 'docg', 'igt', 'aoc', 'aop', 'do', 'd', 's',
        'gift', 'tube', 'box', 'в', 'тубе', 'подарочной', 'упаковке', 'л', 'l', 'ml',
    }


def price(value):
    if isinstance(value, bool) or value is None:
        return None
    text = re.sub(r'[\s\u00a0\u202f]', '', str(value)).replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', text):
        return None
    number = float(text)
    # Catalog contract uses integer RUB: do not silently round kopecks.
    return int(number) if math.isfinite(number) and number.is_integer() and 100 <= number <= 1000000 else None


def measure(value, unit):
    text = str(value or '').lower().replace(',', '.')
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(л|l|мл|ml|cl|%|об\.?)?\s*', text)
    if not match:
        return None
    number = float(match[1])
    if unit == 'volume':
        if match[2] in ('мл', 'ml'): number /= 1000
        if match[2] == 'cl': number /= 100
        return number if 0.05 <= number <= 30 else None
    return number if 0 < number <= 100 else None


def text_value(value):
    if isinstance(value, dict): value = value.get('name') or value.get('value')
    if isinstance(value, (str, int, float)):
        return re.sub(r'\s+', ' ', str(value)).strip() or None
    return None


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from nodes(child)
    elif isinstance(value, list):
        for child in value: yield from nodes(child)


def schema_type(node, kind):
    types = node.get('@type', [])
    return any(str(t).rsplit('/', 1)[-1] == kind for t in (types if isinstance(types, list) else [types]))


def blocked_html(body):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, 'html.parser')
    heading = ' '.join(x.get_text(' ', strip=True) for x in soup.select('title,h1'))
    return bool(re.search(r'captcha|access denied|forbidden|доступ ограничен|проверка.*(?:браузера|человек)|just a moment', heading, re.I)
                or soup.select('iframe[src*="captcha"],form[action*="captcha"],#captcha'))


def extract(body, record, source_url, checked_at):
    from bs4 import BeautifulSoup
    if blocked_html(body): raise ValueError('access_challenge')
    soup = BeautifulSoup(body, 'html.parser')
    products = []
    for script in soup.select('script[type="application/ld+json"]'):
        try: products.extend(n for n in nodes(json.loads(script.get_text())) if schema_type(n, 'Product'))
        except (ValueError, TypeError): continue
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and url_key(urljoin(source_url, canonical.get('href', ''))) != url_key(source_url):
        raise ValueError('canonical_product_mismatch')
    # DOM fallback is confined to the main product, never recommendation cards.
    if not products:
        root = soup.select_one('[itemscope][itemtype$="/Product"]')
        if root:
            def item(prop):
                el = root.select_one(f'[itemprop="{prop}"]')
                return el.get('content') or el.get_text(' ', strip=True) if el else None
            products = [{'@type': 'Product', 'name': item('name'), 'brand': item('brand'),
                         'description': item('description'), 'offers': {'@type': 'Offer',
                         'price': item('price'), 'priceCurrency': item('priceCurrency')}}]
    expected_year = record.get('year')
    expected_tokens = tokens(unquote(urlsplit(source_url).path).split('/')[-1].removesuffix('.html'))
    expected_tokens = {t for t in expected_tokens if not t.isdigit()}
    candidates = []
    for product in products:
        name = text_value(product.get('name'))
        producer = text_value(product.get('manufacturer')) or text_value(product.get('brand'))
        if not name or not producer: continue
        if product.get('url') and url_key(urljoin(source_url, str(product['url']))) != url_key(source_url): continue
        candidate_tokens = tokens(name + ' ' + producer)
        if not expected_tokens or len(expected_tokens & candidate_tokens) / len(expected_tokens) < .9: continue
        # Producer must also occur in the original name or URL, not just a related Product.
        original_tokens = tokens(record['title']) | expected_tokens
        if not tokens(producer) or not tokens(producer) <= original_tokens: continue
        years = {int(v) for v in re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', name)}
        vintage = product.get('vintage') or product.get('productionDate')
        if vintage and re.fullmatch(r'(?:19|20)\d{2}', str(vintage)): years.add(int(vintage))
        if expected_year is not None and years != {expected_year}: continue
        if expected_year is None and len(years) > 1: continue
        candidates.append((product, name, producer, next(iter(years), None)))
    if len(candidates) != 1: raise ValueError('product_identity_unconfirmed_or_ambiguous')
    product, name, producer, vintage = candidates[0]
    details = dict.fromkeys(DETAIL_FIELDS)
    details.update(full_name=name, producer=producer, vintage=vintage,
                   source_url=source_url, checked_at=checked_at,
                   identity_evidence='URL/name tokens >=90%, producer, exact vintage; known volume checked',
                   image_usage_allowed=False, image_permission_source=None,
                   field_sources={'full_name':'JSON-LD/structured Product','producer':'JSON-LD/structured Product'})
    # Extract characteristics only from the matched product's main body.
    # Exclude recommendation/comparison subtrees and never let a later
    # unrelated table silently overwrite an earlier labelled value.
    primary = soup.select_one('main') or soup.select_one('[itemscope][itemtype$="/Product"]')
    candidates = {}
    if primary:
        for row in primary.select('tr'):
            if is_recommendation(row):
                continue
            cells = row.find_all(['th', 'td'], recursive=False)
            if len(cells) == 2:
                label = normalized(cells[0].get_text(' ', strip=True))
                value = cells[1].get_text(' ', strip=True)
                if label and value:
                    candidates.setdefault(label, set()).add(value)
        for term in primary.select('dt'):
            if is_recommendation(term):
                continue
            value = term.find_next_sibling('dd')
            if value and not is_recommendation(value):
                label = normalized(term.get_text(' ', strip=True))
                content = value.get_text(' ', strip=True)
                if label and content:
                    candidates.setdefault(label, set()).add(content)
    # If the same DOM label contains conflicting values, none are accepted.
    labels = {label: next(iter(values)) for label, values in candidates.items() if len(values) == 1}
    structured_labels = {}
    for prop in product.get('additionalProperty', []) if isinstance(product.get('additionalProperty'), list) else []:
        if isinstance(prop, dict) and text_value(prop.get('name')):
            label = normalized(prop['name'])
            value = text_value(prop.get('value'))
            if value:
                structured_labels.setdefault(label, set()).add(value)
    structured_labels = {label: next(iter(values)) for label, values in structured_labels.items()
                         if len(values) == 1}
    mapping = {
        'country':('Страна','Страна происхождения','Country'), 'region':('Регион','Region'),
        'appellation':('Апелласьон','Аппелласьон','Appellation'), 'grapes':('Сорт винограда','Сорта винограда','Grape varieties'),
        'color':('Цвет','Цвет вина','Color'), 'wine_type':('Тип вина','Wine type'),
        'sweetness':('Сахар','Содержание сахара','Сладость','Sweetness'),
        'volume_l':('Объем','Объём','Volume'), 'alcohol_percent':('Крепость','Алкоголь','Alcohol'),
        'taste':('Вкус','Taste'), 'aroma':('Аромат','Aroma'), 'food_pairings':('Гастрономические сочетания','Food pairing'),
    }
    for field, aliases in mapping.items():
        value = next((structured_labels[normalized(k)] for k in aliases
                      if structured_labels.get(normalized(k))), None)
        source = 'Product.additionalProperty' if value else 'labelled main-product DOM'
        if not value:
            value = next((labels[normalized(k)] for k in aliases
                          if labels.get(normalized(k))), None)
        if value:
            details[field] = value
            details['field_sources'][field] = source
    volume = measure(product.get('size') or details['volume_l'], 'volume')
    if volume is None:
        match = re.search(r'(\d+[.,]\d+)\s*(?:л\b|l\b)', name, re.I)
        if match: volume = measure(match[1], 'volume')
    if record.get('volume_l') is not None and (volume is None or abs(volume-record['volume_l']) > .001):
        raise ValueError('volume_mismatch_or_unconfirmed')
    details['volume_l'] = volume
    details['alcohol_percent'] = measure(details['alcohol_percent'], 'alcohol')
    for field, prop in (('country','countryOfOrigin'),('color','color')):
        value = text_value(product.get(prop))
        if value:
            details[field] = value
            details['field_sources'][field] = 'JSON-LD Product.'+prop
    details['description'] = text_value(product.get('description'))
    if details['description']:
        details['description'] = BeautifulSoup(details['description'], 'html.parser').get_text(' ', strip=True)
        details['field_sources']['description'] = 'JSON-LD/structured Product'
    image = product.get('image')
    if isinstance(image, list): image = image[0] if image else None
    if isinstance(image, dict): image = image.get('contentUrl') or image.get('url')
    if isinstance(image, str) and urlsplit(urljoin(source_url, image)).scheme == 'https':
        details.update(image_url=urljoin(source_url, image), image_source=source_url)
    offers = product.get('offers', [])
    offers = offers if isinstance(offers, list) else [offers]
    verified_prices = []
    regional_stock = []
    for offer in offers:
        if not isinstance(offer, dict) or schema_type(offer, 'AggregateOffer'):
            continue
        if offer.get('url') and url_key(urljoin(source_url, str(offer['url']))) != url_key(source_url):
            continue
        region = text_value(offer.get('eligibleRegion'))
        local_region = bool(region and normalized(region) in
                            ('санкт петербург', 'saint petersburg', 'st petersburg'))
        if local_region:
            availability = str(offer.get('availability', '')).rsplit('/', 1)[-1]
            value = {'InStock': True, 'OutOfStock': False, 'SoldOut': False}.get(availability)
            if value is not None:
                # Availability does not depend on an offer exposing a price.
                regional_stock.append(value)
        # An explicitly non-SPb offer is never evidence of an SPb price.
        if region and not local_region:
            continue
        if offer.get('priceCurrency') not in ('RUB', 'RUR'):
            continue
        current = price(offer.get('price'))
        if current is None:
            continue
        regular = next((p for k in ('oldPrice','previousPrice','originalPrice')
                        if (p := price(offer.get(k))) and p > current), None)
        verified_prices.append((current, regular))
    current = regular = None
    if verified_prices and len(set(verified_prices)) == 1:
        current, regular = verified_prices[0]
    if regional_stock and len(set(regional_stock)) == 1:
        details['availability_spb'] = regional_stock[0]
        details['field_sources']['availability_spb'] = 'Product Offer eligibleRegion/availability'
    details['ratings'] = extract_ratings(soup, product, source_url, checked_at)
    if details['ratings']:
        details['field_sources']['ratings'] = 'Product ratings JSON-LD or labelled DOM'
    return details, current, regular


# Map independent extractor field names onto the published browser-capture schema.
PUBLISHED_FIELDS = {
    'wine_type': 'wine_style',
    'food_pairings': 'pairing_notes',
    'description': 'description_excerpt',
}


def apply_result(record, store, details, current, regular, overrides):
    """Overlay new verified observations without discarding unrelated old fields."""
    previous = store.get('product_details') or {}
    if not isinstance(previous, dict):
        raise ValueError('product_details must be a mapping when present')
    if previous.get('source_url') and url_key(previous['source_url']) != url_key(store['url']):
        raise ValueError('previous_product_details_url_mismatch')
    if url_key(details['source_url']) != url_key(store['url']):
        raise ValueError('incoming_product_details_url_mismatch')
    old_date = previous.get('checked_at')
    if old_date and old_date > details['checked_at']:
        raise ValueError('older_observation_would_replace_newer_snapshot')
    if current is not None and store.get('price_checked_at') and store['price_checked_at'] > details['checked_at']:
        raise ValueError('older_price_would_replace_newer_price')

    merged = copy.deepcopy(previous)
    sources = dict(previous.get('field_sources') or {})
    sources_checked = dict(previous.get('field_checked_at') or {})
    for field, old_value in previous.items():
        if (field not in ('field_sources', 'field_checked_at', 'field_evidence',
                          'checked_at', 'source_url') and old_value is not None
                and field not in sources_checked and previous.get('checked_at')):
            sources_checked[field] = previous['checked_at']
    evidence = dict(previous.get('field_evidence') or {})
    for field, value in details.items():
        if field in ('checked_at', 'source_url', 'field_sources', 'field_evidence',
                     'field_checked_at', 'identity_evidence'):
            continue
        if field in ('image_url', 'image_source'):
            # Images are recorded as source-only data; never imply usage permission.
            if value is not None:
                merged[field] = value
            continue
        if value is None or value == '' or value == []:
            continue
        canonical = PUBLISHED_FIELDS.get(field, field)
        if canonical == 'ratings':
            # A saved HTML page may contain fewer critic entries than a prior
            # browser capture. Update those named in the new page only.
            existing = {row['source']: row for row in (merged.get('ratings') or [])
                        if isinstance(row, dict) and isinstance(row.get('source'), str)}
            for row in value:
                existing[row['source']] = row
            merged['ratings'] = list(existing.values())
        else:
            merged[canonical] = value
        sources[canonical] = (details.get('field_sources') or {}).get(field, 'matched product HTML')
        sources_checked[canonical] = details['checked_at']
        if (details.get('field_evidence') or {}).get(field):
            evidence[canonical] = details['field_evidence'][field]
        else:
            # The old evidence refers to a different value, not the new one.
            evidence.pop(canonical, None)

    # A new explicit availability assertion supersedes an older textual note.
    if details.get('availability_spb') is not None:
        merged.pop('availability_note', None)
        sources.pop('availability_note', None)
        sources_checked.pop('availability_note', None)
        evidence.pop('availability_note', None)
    merged.update(source_url=store['url'], checked_at=details['checked_at'])
    merged['field_sources'] = sources
    merged['field_checked_at'] = sources_checked
    # A stale previous value must never keep an unrelated evidence string.
    merged['field_evidence'] = evidence
    merged['image_usage_allowed'] = False
    merged['image_permission_source'] = None
    merged.setdefault('ratings', [])
    store['product_details'] = merged
    if current is not None:
        store.update(price_rub=current, regular_price_rub=regular,
                     price_checked_at=details['checked_at'], price_source_url=store['url'])
    # Existing top-level attributes and overrides take precedence.
    manual = overrides.get(record['id'], {})
    if record.get('country') is None and 'country' not in manual and merged.get('country'):
        record['country'] = str(merged['country']).split(',')[0].strip()
    if record.get('volume_l') is None and 'volume_l' not in manual and merged.get('volume_l') is not None:
        # Browser snapshots use strings such as "0.75 л", but the catalog
        # contract requires a numeric volume for comparisons and card rendering.
        parsed_volume = measure(merged['volume_l'], 'volume')
        if parsed_volume is not None:
            record['volume_l'] = parsed_volume
    store['enrichment_status'] = {
        'status': 'verified', 'checked_at': details['checked_at'],
        'source_url': store['url'], 'method': 'offline_html'
    }

class DomainBlocked(RuntimeError): pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent':AGENT,'Accept':'text/html,text/plain'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=25) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise ValueError('response_too_large')
            return raw.decode(response.headers.get_content_charset() or 'utf-8', 'replace')
    except urllib.error.HTTPError as error:
        if error.code in (401,403,429,503): raise DomainBlocked(f'HTTP {error.code}: {url}') from error
        raise


def selected(data):
    return [(r,s) for r in data['records'] for s in r['stores'] if is_winestyle(s['url'])]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--limit',type=int,default=0)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--headed',action='store_true')
    ap.add_argument('--delay',type=float,default=3)
    ap.add_argument('--domain',choices=['winestyle.ru'],default='winestyle.ru')
    ap.add_argument('--catalog',type=Path,default=ROOT/'data/wines.json')
    ap.add_argument('--access-state',type=Path,default=ROOT/'reports/winestyle-access.json')
    ap.add_argument('--report',type=Path,default=ROOT/'reports/winestyle-run.json')
    ap.add_argument('--input-dir',type=Path,help='Offline folder with manifest.json and manually saved HTML')
    ap.add_argument('--policy-file',type=Path,help='Local terms review: allowed=true, terms_url, reviewed_at, note')
    args = ap.parse_args(argv)
    if args.limit < 0 or not math.isfinite(args.delay) or args.delay < 1: ap.error('limit >= 0, finite delay >= 1 required')
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    data = json.loads(args.catalog.read_text(encoding='utf-8'))
    overrides = json.loads((ROOT/'data/overrides.json').read_text(encoding='utf-8'))
    all_targets = selected(data)
    targets = all_targets[:args.limit or None]
    report = dict(checked_at=today(), domain=args.domain, discovered=len(all_targets), selected=len(targets),
                  attempted=0, successful=0, current_prices=0, discounts=0, characteristics=0,
                  errors=0, blocked=0, skipped=0, entries=[])
    access = json.loads(args.access_state.read_text(encoding='utf-8')) if args.access_state.exists() else {}
    manifest = {}
    if args.input_dir:
        for entry in json.loads((args.input_dir/'manifest.json').read_text(encoding='utf-8')):
            if entry['url'] in manifest: raise ValueError('duplicate_manifest_URL')
            dt.date.fromisoformat(entry['checked_at'])
            if entry['checked_at'] > today(): raise ValueError('future_manifest_date')
            manifest[entry['url']] = entry
    reason = None
    if not args.input_dir:
        if access.get('blocked'): reason = 'domain_block_recorded: '+str(access.get('reason'))
        else:
            policy = json.loads(args.policy_file.read_text(encoding='utf-8')) if args.policy_file else {}
            if not (policy.get('allowed') is True and policy.get('terms_url') and policy.get('reviewed_at') and policy.get('note')):
                reason = 'terms_not_reviewed: review site terms before live collection'
    if reason:
        report.update(skipped=len(targets), stop_reason=reason, blocked=int(bool(access.get('blocked'))))
        LOG.warning(reason)
        if not args.dry_run: atomic_json(args.report,report)
        print(json.dumps(report,ensure_ascii=False))
        return 2
    if not args.dry_run: backup(args.catalog)
    robots = {}
    browser = context = playwright = None
    try:
        for index,(record,store) in enumerate(targets):
            url = store['url']
            entry = {'id':record['id'],'url':url,'checked_at':today()}
            try:
                if args.input_dir:
                    saved = manifest.get(url)
                    if not saved:
                        report['skipped'] += 1
                        entry['status'] = 'no_offline_file'
                        report['entries'].append(entry)
                        continue
                    report['attempted'] += 1
                    file = (args.input_dir/saved['file']).resolve()
                    if not file.is_relative_to(args.input_dir.resolve()): raise ValueError('offline_path_outside_input_dir')
                    body = file.read_text(encoding='utf-8-sig')
                    entry['checked_at'] = saved['checked_at']
                else:
                    host = urlsplit(url).netloc
                    if host not in robots:
                        try:
                            robots_text = fetch(f'https://{host}/robots.txt')
                        except DomainBlocked:
                            raise
                        except (OSError,ValueError) as error:
                            raise DomainBlocked('robots_unavailable: '+str(error)) from error
                        parser = urllib.robotparser.RobotFileParser()
                        parser.parse(robots_text.splitlines())
                        robots[host] = parser
                        time.sleep(args.delay)
                    if not robots[host].can_fetch(AGENT,url): raise DomainBlocked('robots_denied: '+url)
                    report['attempted'] += 1
                    body = fetch(url)
                    if blocked_html(body): raise DomainBlocked('access_challenge: '+url)
                    if args.headed:
                        # Only public navigation after successful HTTP and policy checks.
                        if browser is None:
                            from playwright.sync_api import sync_playwright
                            playwright = sync_playwright().start()
                            browser = playwright.chromium.launch(headless=False)
                            context = browser.new_context()
                            def permitted(route):
                                request = route.request
                                if request.resource_type in ('image','media','font'):
                                    return route.abort()
                                if request.is_navigation_request() and request.url != url:
                                    return route.abort()
                                return route.continue_()
                            context.route('**/*',permitted)
                        page = context.new_page()
                        response = page.goto(url,wait_until='domcontentloaded',timeout=30000)
                        if response and response.status in (401,403,429,503): raise DomainBlocked(f'HTTP {response.status}: {url}')
                        body = page.content()
                        page.close()
                        if blocked_html(body): raise DomainBlocked('browser_access_challenge: '+url)
                details,current,regular = extract(body,record,url,entry['checked_at'])
                apply_result(record,store,details,current,regular,overrides)
                report['successful'] += 1
                report['current_prices'] += int(current is not None)
                report['discounts'] += int(regular is not None)
                report['characteristics'] += int(any(details.get(f) is not None for f in ('country','grapes','region','taste','aroma')))
                entry.update(status='verified',price_rub=current,regular_price_rub=regular)
            except DomainBlocked as error:
                report['blocked'] += 1
                report['stop_reason'] = str(error)
                entry.update(status='blocked',reason=str(error))
                report['skipped'] += len(targets)-index-1
                if not args.dry_run:
                    atomic_json(args.access_state,dict(blocked=True,checked_at=today(),reason=str(error),url=url))
                report['entries'].append(entry)
                break
            except Exception as error:
                report['errors'] += 1
                entry.update(status='error',reason=str(error))
                LOG.warning('%s: %s',url,error)
            report['entries'].append(entry)
            if not args.dry_run:
                if entry['status'] == 'verified':
                    data['updated_at'] = today()
                    snapshot_manifest = reconcile_manifest(data.get('retailer_snapshot'), data['records'])
                    if snapshot_manifest is not None:
                        data['retailer_snapshot'] = snapshot_manifest
                    atomic_json(args.catalog,data)
                atomic_json(args.report,report)
            if not args.input_dir and index+1 < len(targets):
                time.sleep(max(args.delay,(robots[urlsplit(url).netloc].crawl_delay(AGENT) or 0) if urlsplit(url).netloc in robots else 0))
    finally:
        if browser: browser.close()
        if playwright: playwright.stop()
        if not args.dry_run: atomic_json(args.report,report)
    print(json.dumps(report,ensure_ascii=False))
    return 2 if report['blocked'] else (1 if report['errors'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
