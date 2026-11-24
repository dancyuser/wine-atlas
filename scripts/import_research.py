#!/usr/bin/env python3
"""Join structured browser observations and preview or apply catalog additions."""
import argparse
import datetime as dt
import hashlib
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RATE_URL = 'https://www.cbr.ru/scripts/XML_daily.asp'
SPB = 'Санкт-Петербург'
YEAR = r'(?:19|20)\d{2}'
CRITICS = {'wineenthusiast.com': 'Wine Enthusiast', 'falstaff.com': 'Falstaff',
           'vinous.com': 'Vinous', 'decanter.com': 'Decanter',
           'results.decanter.com': 'Decanter World Wine Awards', 'iwsc.net': 'IWSC',
           'jamessuckling.com': 'James Suckling', 'jancisrobinson.com': 'Jancis Robinson'}


def moscow_date(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(dt.timezone(dt.timedelta(hours=3))).date().isoformat()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def normalized(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in text if not unicodedata.combining(c))))


def year_in(text):
    years = set(re.findall(rf'\b{YEAR}\b', text))
    return int(years.pop()) if len(years) == 1 else None


def window(text):
    matches = set()
    for match in re.finditer(rf'\b(?:drinking window|drink(?:ing)?|best (?:enjoyed|drunk))\s*[:|]?\s*(now|{YEAR})?\s*(?:through|until|to|[-–—])\s*({YEAR})\b', text, re.I):
        start, end = match.groups()
        matches.add((int(start) if start and start.isdigit() else None, int(end)))
    return matches.pop() if len(matches) == 1 else (None, None)


def parse_rates(xml):
    root = ET.fromstring(xml)
    date = dt.datetime.strptime(root.attrib['Date'], '%d.%m.%Y').date().isoformat()
    rates = {}
    for row in root.findall('Valute'):
        rates[row.findtext('CharCode')] = Decimal(row.findtext('Value').replace(',', '.')) / int(row.findtext('Nominal'))
    return date, rates


def exchange(amount, currency, rates):
    rub = Decimal(str(amount)) * rates[currency]
    return rub, float(rub.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def parse_review(row, host):
    text = row.get('blocks', {}).get('review', '')
    if not text or host not in CRITICS:
        return None
    title = row.get('title', '')
    year = year_in(title)
    if not year:
        return None
    start, end = window(text)
    score = price = currency = None
    scale = 100
    price_kind = 'exact'
    if host == 'wineenthusiast.com':
        mark = re.search(r'\bRating\s+(\d{2,3})(?![\d.])', text, re.I)
        amount = re.search(r'\bPrice\s+\$\s*(\d+(?:\.\d{1,2})?)(?![\d,.])', text, re.I)
        score = int(mark[1]) if mark else None
        price, currency = (amount[1], 'USD') if amount else (None, None)
    elif host == 'falstaff.com':
        marks = set(re.findall(r'\b(\d{2,3})\s+(?:Falstaff points|Falstaff.Punkte)\b', text, re.I))
        score = int(marks.pop()) if len(marks) == 1 else None
        producer = row.get('blocks', {}).get('producer')
        if producer and normalized(producer) not in normalized(title):
            title = producer + ' ' + title
        ranges = set(re.findall(r'\b(?:Price|Preis)\s*:\s*(?:\d+\s*[-–]\s*|bis\s+|up to\s+)(\d+)\s*€', text, re.I))
        if len(ranges) == 1:
            price, currency, price_kind = ranges.pop(), 'EUR', 'upper_bound'
    elif host not in {'vinous.com'}:
        marks = set(re.findall(r'\b(?:score|rating|points)\s*[:|]?\s*(\d{1,3}(?:\.\d+)?)\s*/\s*(100|20)\b', text, re.I))
        if host == 'decanter.com' and not marks:
            marks = {(value, '100') for value in re.findall(r'(?m)^\s*(\d{2,3})\s*\n\s*Tasted by\s*:', text)}
        if len(marks) == 1:
            value, divisor = marks.pop()
            score, scale = float(value), int(divisor)
    return {'title': title, 'year': year, 'score': score, 'source': CRITICS[host],
            'scale': scale,
            'start': start, 'end': end, 'amount': price, 'currency': currency, 'price_kind': price_kind,
            'url': row['url'], 'date': moscow_date(row['observed_at'])}


def parse_offer(row, host):
    blocks = row.get('blocks', {})
    text = blocks.get('product', '')
    title = row.get('title', '')
    hint = blocks.get('document_title', '')
    year = year_in(title) or year_in(re.sub(r'\b(?:руб|₽).*$', '', hint, flags=re.I))
    volume_matches = re.findall(r'(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l)(?=\W|$)', hint, re.I)
    if not volume_matches and host == 'vinissimo.biz':
        volume_matches = re.findall(r'(?:Объем|Объём)\s*[:|]?\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l)(?=\W|$)', text, re.I)
    volumes = {Decimal(n.replace(',', '.')) / (1000 if unit.lower() in {'мл', 'ml'} else 1)
               for n, unit in volume_matches}
    if not year or len(volumes) != 1:
        return None
    stock = amount = None
    if host == 'sabonis.ru':
        # Match the price on the selected variant, then require a nonzero count
        # on at least one of the known local shop addresses in the stock block.
        stock_line = re.search(r'Наличие\s*:([^\n]*(?:\n[^\n]{1,100}){0,5})', text, re.I)
        price_line = re.search(r'цена\s+([\d\s\u00a0]+)\s*₽\s+в\s+СПб', hint, re.I)
        addresses = r'(?:Петроградская наб\.,\s*8|Жуковского,\s*10|Казанская,\s*8-10)\s*[-–]\s*[1-9]\d*\s*шт'
        selected_year = re.search(rf'\bВинтаж\s*:\s*({YEAR})\b', text, re.I)
        confirmed_year = not selected_year or int(selected_year[1]) == year
        if confirmed_year and stock_line and price_line and re.search(addresses, stock_line[1], re.I):
            amount = price_line[1]
            displayed = re.findall(r'(?<!\d)(\d[\d\u00a0\u202f ]*)\s*₽', text)
            if re.sub(r'\s', '', amount) not in {re.sub(r'\s', '', value) for value in displayed}:
                amount = None
            stock = 'in_stock'
            title = re.sub(r'^.*?Вино\s+', '', hint, flags=re.I).split(str(year), 1)[0].strip()
    elif host == 'spb.winestyle.ru':
        text = blocks.get('price_stock', '')
        price = {re.sub(r'\s', '', value) for value in re.findall(r'(?<!\d)(\d[\d\u00a0\u202f ]*)\s*₽', text)}
        if len(price) == 1 and not re.search(r'нет в наличии|ожидаем поступление', text, re.I):
            amount = price.pop()
            stock = 'in_stock' if re.search(r'в наличии в\s+[1-9]', text, re.I) else None
            if not stock and re.search(r'доступно\s+под заказ', text, re.I):
                stock = 'orderable'
    elif host == 'vinissimo.biz' and blocks.get('city') == SPB:
        options = set(re.findall(rf'\b{year}\s*г\.\s*[-–]\s*(\d[\d\u00a0 ]*)\s*руб\.?\s*(?:\n\s*){{0,2}}(в наличии|нет в наличии)', text, re.I))
        if len(options) == 1 and (match := options.pop())[1].lower() == 'в наличии':
            amount, stock = match[0], 'in_stock'
            latin = next((line for line in text.splitlines()[1:5]
                          if re.search(r'[A-Za-z]{3,}.*[A-Za-z]{3,}', line) and not re.search(r'[А-Яа-я]', line)), None)
            title = latin or title
    elif host in {'luding.ru', 'spb.luding.ru'} and blocks.get('city') == SPB:
        price = {re.sub(r'\s', '', value) for value in re.findall(r'(?<!\d)(\d[\d\u00a0\u202f ]*)\s*₽', text)}
        if len(price) == 1 and not re.search(r'нет в наличии|ожидаем поступление', text, re.I):
            amount = price.pop()
            if re.search(r'в наличии у\s+поставщика', text, re.I):
                stock = 'supplier_stock'
            elif re.search(r'в наличии в\s+винотек', text, re.I):
                stock = 'in_stock'
    if not stock or not amount:
        return None
    return {'title': title, 'year': year, 'volume_l': float(volumes.pop()),
            'price': int(re.sub(r'\s', '', amount)), 'stock': stock, 'text': text[:1000],
            'url': row['url'], 'source': row.get('source') or host, 'date': moscow_date(row['observed_at'])}


def identity(title, year):
    # Keep distinguishing cuvée terms. Unmatched aliases require review.
    words = [s for s in normalized(title).split() if s not in {'вино', 'doc', 'doca', 'aoc', 'bodegas', str(year)}]
    return tuple(sorted(words)), year


def join(bundle, rate_date, rates, aliases=None, checked_on=None):
    if bundle.get('kind') != 'wine_atlas_research_capture' or bundle.get('version') != 1:
        raise ValueError('unsupported capture format')
    aliases = aliases or {}
    checked_on = checked_on or rate_date
    if rate_date > checked_on:
        raise ValueError('the exchange rate was not effective on the observation date')
    reviews, offers, unresolved = {}, {}, []
    for row in bundle['observations']:
        url = urlsplit(row.get('url') or '')
        if url.scheme != 'https' or url.username or url.password or row.get('status') != 'needs_review':
            continue
        requested = urlsplit(row.get('requested_url') or row['url'])
        if (requested.netloc, requested.path.rstrip('/')) != (url.netloc, url.path.rstrip('/')):
            unresolved.append({'url': row['url'], 'reason': 'redirect'})
            continue
        host = (url.hostname or '').removeprefix('www.')
        review, offer = parse_review(row, host), parse_offer(row, host)
        for observation, index in [(review, reviews), (offer, offers)]:
            if observation:
                label = aliases.get(observation['url'], observation['title'])
                index.setdefault(identity(label, observation['year']), []).append(observation)
        if not review and not offer and row.get('blocks'):
            reason = 'review_requires_review' if host in CRITICS else 'offer_requires_review'
            unresolved.append({'url': row['url'], 'reason': reason})
    accepted = []
    for key, observations in reviews.items():
        rated = [r for r in observations if r['score'] is not None and 85 <= r['score'] * 100 / r['scale'] <= 100]
        windows = [r for r in observations if r['end'] and r['end'] >= max(2027, key[1]) and
                   (r['start'] is None or key[1] <= r['start'] <= r['end'])]
        priced = [r for r in observations if r['amount'] and r['currency'] in rates and
                  r['date'] == checked_on and 0 < exchange(r['amount'], r['currency'], rates)[0] <= 6000]
        local = [o for o in offers.get(key, []) if 0 < o['price'] <= 5000 and o['date'] == checked_on]
        missing = [flag for flag, rows in [('score', rated), ('window', windows), ('foreign_price', priced), ('spb_offer', local)] if not rows]
        if missing:
            unresolved.append({'title': observations[0]['title'], 'year': key[1], 'missing': missing})
            continue
        offer = min(local, key=lambda o: (o['price'], o['url']))
        score = max(rated, key=lambda r: r['score'] * 100 / r['scale'])
        end = min(windows, key=lambda r: r['end'])
        price = priced[0]
        title = aliases.get(score['url'], score['title'])
        if str(key[1]) in title:
            title = re.sub(rf'\b{key[1]}\b', '', title)
            title = ' '.join(title.split())
        record_id = hashlib.sha256(repr(key).encode()).hexdigest()[:12]
        accepted.append({'id': record_id, 'title': title, 'year': key[1], 'research': True,
                         'wishlist': False, 'volume_l': offer['volume_l'], 'grapes': [], 'pairings': [],
                         'stores': [{'name': offer['source'], 'url': offer['url'], 'price_rub': offer['price'],
                                     'price_checked_at': offer['date']}],
                         'availability': {'status': 'in_stock', 'stock_kind': offer['stock'], 'region': SPB,
                                          'source_url': offer['url'], 'observed_on': offer['date'], 'evidence': offer['text']},
                         'drinking_window': {'kind': 'window', 'scope': 'vintage', 'min': end['start'],
                                             'max': end['end'], 'source': end['source'], 'source_url': end['url']},
                         'critic_ratings': [{'source': score['source'], 'score': score['score'], 'scale': score['scale'],
                                             'scope': 'vintage', 'vintage': key[1], 'source_url': score['url'],
                                             'observed_on': score['date']}],
                         'foreign_reference': {'amount': float(price['amount']), 'currency': price['currency'], 'kind': price['price_kind'],
                                               'price_source_url': price['url'], 'exchange_rate_rub': float(rates[price['currency']]),
                                               'rate_source': {'source': 'Банк России', 'date': rate_date, 'source_url': RATE_URL},
                                               'amount_rub': exchange(price['amount'], price['currency'], rates)[1]}})
    return accepted, unresolved


def merge(existing, new, catalog, exclusions):
    seen_ids = {r.get('id') for r in existing + catalog} | set(exclusions)
    seen_names = {identity(r['title'], r.get('year')) for r in existing + catalog + list(exclusions.values()) if r.get('title')}
    seen_urls = {s['url'].rstrip('/') for r in existing + catalog for s in r.get('stores', []) if s.get('url')}
    seen_urls.update(r['url'].rstrip('/') for r in exclusions.values() if r.get('url'))
    additions = []
    for r in new:
        key, url = identity(r['title'], r['year']), r['stores'][0]['url'].rstrip('/')
        if r['id'] in seen_ids or key in seen_names or url in seen_urls:
            continue
        additions.append(r)
        seen_ids.add(r['id']); seen_names.add(key); seen_urls.add(url)
    return additions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--rates', type=Path, help='Saved CBR XML for replay; otherwise fetch today’s rates')
    parser.add_argument('--aliases', type=Path, help='Reviewed URL → canonical wine name mapping; does not override vintage')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    bundle = load(args.capture)
    checked_on = max(moscow_date(row['observed_at']) for row in bundle['observations']) if bundle['observations'] else None
    if not checked_on:
        parser.error('capture has no observations')
    if args.rates:
        xml = args.rates.read_bytes()
    else:
        requested = dt.date.fromisoformat(checked_on).strftime('%d/%m/%Y')
        with urllib.request.urlopen(RATE_URL + '?date_req=' + requested, timeout=20) as response:
            xml = response.read(1_000_000)
    date, rates = parse_rates(xml)
    aliases = load(ROOT / 'data/research-aliases.json')
    if args.aliases:
        aliases.update(load(args.aliases))
    accepted, unresolved = join(bundle, date, rates, aliases, checked_on=checked_on)
    path = ROOT / 'data/discovered-wines.json'
    overlay = load(path)
    additions = merge(overlay['records'], accepted, load(ROOT / 'data/wines.json')['records'],
                      load(ROOT / 'data/owner-exclusions.json')['records'])
    report = {'rate_date': date, 'eligible': accepted, 'candidates': unresolved, 'new_catalog_records': additions}
    if args.report:
        write(args.report, report)
    if args.apply and additions:
        overlay['records'].extend(additions)
        overlay['checked_at'] = max(checked_on, overlay.get('checked_at', checked_on))
        write(path, overlay)
    print(f'eligible={len(accepted)} unresolved={len(unresolved)} new={len(additions)} applied={len(additions) if args.apply else 0}')


if __name__ == '__main__':
    main()
