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
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit
from critic_publications import publication_kind, publication_entries

ROOT = Path(__file__).resolve().parents[1]
RATE_URL = 'https://www.cbr.ru/scripts/XML_daily.asp'
SPB = 'Санкт-Петербург'
YEAR = r'(?:19|20)\d{2}'
CRITICS = {'wineenthusiast.com': 'Wine Enthusiast', 'falstaff.com': 'Falstaff',
           'vinous.com': 'Vinous', 'decanter.com': 'Decanter',
           'results.decanter.com': 'Decanter World Wine Awards', 'iwsc.net': 'IWSC',
           'jamessuckling.com': 'James Suckling', 'jancisrobinson.com': 'Jancis Robinson',
           'top100.winespectator.com': 'Wine Spectator', 'lucamaroni.it': 'Luca Maroni',
           'kenswineguide.com': "Ken's Wine Guide"}
RETAILERS = {
    'winelab.ru': 'Винлаб', 'amwine.ru': 'Ароматный мир', 'vinissimo.biz': 'Vinissimo',
    'sabonis.ru': 'Sabonis', 'spb.winestyle.ru': 'WineStyle', 'simplewine.ru': 'SimpleWine',
    'ast.wine': 'AST.WINE', 'joia.ru': 'Joia', 'joiastore.ru': 'Joia', 'luding.ru': 'Luding', 'spb.luding.ru': 'Luding',
}
LABELED_RETAILERS = {'winelab.ru', 'amwine.ru', 'simplewine.ru', 'ast.wine', 'joia.ru', 'joiastore.ru'}
RUBLES = r'(\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{2})?)\s*(?:₽|руб\.?)'
VOLUME = r'(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l)(?=\W|$)'


def moscow_date(value):
    return observation_time(value).astimezone(dt.timezone(dt.timedelta(hours=3))).date().isoformat()


def observation_time(value):
    stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('observation timestamp requires a time zone')
    return stamp


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
    for match in re.finditer(rf'\b(?:drinking window|drink(?:ing)?|best(?: enjoyed| drunk)?)(?:\s+from)?\s*[:|]?\s*(now|{YEAR})?\s*(?:through|until|to|[-–—])\s*({YEAR}|\d{{2}})\b', text, re.I):
        start, end = match.groups()
        start = int(start) if start and start.isdigit() else None
        if len(end) == 2:
            if start is None:
                continue
            end = str(start // 100) + end
        matches.add((start, int(end)))
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
    if host == 'kenswineguide.com':
        heading = re.search(r"^Ken['’]s wine review of (.+)$", row.get('blocks', {}).get('document_title', ''), re.I)
        if heading:
            title = heading[1]
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
    elif host == 'top100.winespectator.com':
        mark = re.search(r'(?mi)^[ \t]*Score\s*:?\s*(\d{2,3})[ \t]*$', text)
        amount = re.search(r'(?mi)^[ \t]*Price\s*:?\s*\$\s*(\d+(?:\.\d{1,2})?)[ \t]*$', text)
        score = int(mark[1]) if mark else None
        price, currency = (amount[1], 'USD') if amount else (None, None)
    elif host == 'lucamaroni.it':
        producer = re.search(r'(?mi)^Produttore[ :\t]*\s*([^\n]+)', text)
        mark = re.search(r'(?mi)^\s*(\d{2})\s*\n\s*Indice di Piacevolezza\s*$', text)
        if not producer or not mark:
            return None
        title = producer[1].strip() + ' ' + title
        score, scale = int(mark[1]), 99
    elif host == 'kenswineguide.com':
        mark = re.search(r"(?mi)^Ken['’]s Wine Rating:[^(]*\((\d{2,3}(?:\.\d+)?)\)", text)
        amount = re.search(r'(?mi)^Price:\s*\$\s*(\d+(?:\.\d{1,2})?)', text)
        score = float(mark[1]) if mark else None
        price, currency = (amount[1], 'USD') if amount else (None, None)
    elif host == 'falstaff.com':
        # The German tasting summary uses the inflected form "Punkten".
        marks = set(re.findall(r'\b(\d{2,3})(?:\s*[-–]\s*\d{2,3}|\+)?\s+Falstaff(?: points|[- ]Punkten?)\b', text, re.I))
        score = int(marks.pop()) if len(marks) == 1 else None
        producer = row.get('blocks', {}).get('producer')
        if producer and normalized(producer) not in normalized(title):
            title = producer + ' ' + title
        ranges = set(re.findall(r'\b(?:Price|Preis)\s*:\s*(?:\d+\s*[-–]\s*|bis\s+|up to\s+)(\d+)\s*€', text, re.I))
        if len(ranges) == 1:
            price, currency, price_kind = ranges.pop(), 'EUR', 'upper_bound'
    elif host not in {'vinous.com'}:
        marks = set(re.findall(r'\b(?:score|rating|points)\s*[:|]?\s*(\d{1,3}(?:\.\d+)?)\s*/\s*(100|20)\b', text, re.I))
        if host == 'jamessuckling.com' and not marks and urlsplit(row['url']).path.startswith('/tasting-notes/'):
            marks = {(mark, '100') for mark in re.findall(
                r'(?mi)^[ \t]*Score(?:[ \t]*:[ \t]*|[ \t]*\n[ \t]*)([1-9]\d|100)[ \t]*$', text)}
        if host == 'decanter.com' and not marks:
            marks = {(value, '100') for value in re.findall(r'(?m)^\s*(\d{2,3})\s*\n\s*Tasted by\s*:', text)}
        if len(marks) == 1:
            value, divisor = marks.pop()
            score, scale = float(value), int(divisor)
    return {'title': title, 'year': year, 'score': score, 'source': CRITICS[host],
            'scale': scale,
            'start': start, 'end': end, 'amount': price, 'currency': currency, 'price_kind': price_kind,
            'url': row['url'], 'date': moscow_date(row['observed_at'])}


def parse_reviews(row, host):
    kind = publication_kind(host, urlsplit(row['url']).path)
    text = row.get('blocks', {}).get('review')
    if kind and text:
        reviews = publication_entries(kind, row.get('title', ''), text)
        for review in reviews:
            review['start'], review['end'] = window(review.pop('window_text'))
            review.update(url=row['url'], date=moscow_date(row['observed_at']))
        return reviews
    review = parse_review(row, host)
    return [review] if review else []


def parse_offer(row, host):
    if host in LABELED_RETAILERS:
        return parse_labeled_offer(row, host)
    blocks = row.get('blocks', {})
    text = blocks.get('product', '')
    title = row.get('title', '')
    hint = blocks.get('document_title', '')
    year = year_in(title) or year_in(re.sub(r'\b(?:руб|₽).*$', '', hint, flags=re.I))
    volume_matches = re.findall(VOLUME, hint, re.I)
    if not volume_matches and host == 'vinissimo.biz':
        volume_matches = re.findall(r'(?:Объ[её]м(?:ы)?)\s*[:|]?\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l)(?=\W|$)', text, re.I)
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
            stores = '\n'.join(match[0] for match in re.finditer(addresses + r'\.?', stock_line[1], re.I))
            text = f'{SPB}\n{price_line[1].strip()} ₽\nНаличие:\n{stores}'
    elif host == 'spb.winestyle.ru':
        text = blocks.get('price_stock', '')
        price = {re.sub(r'\s', '', value) for value in re.findall(r'(?<!\d)(\d[\d\u00a0\u202f ]*)\s*₽', text)}
        if len(price) == 1 and not re.search(r'нет в наличии|ожидаем поступление', text, re.I):
            amount = price.pop()
            stock = 'in_stock' if re.search(r'в наличии в\s+[1-9]', text, re.I) else None
            if not stock and re.search(r'доступно\s+под заказ', text, re.I):
                stock = 'orderable'
    elif host == 'vinissimo.biz' and blocks.get('city') == SPB:
        selected_year = re.search(rf'\bГод урожая\s*:?\s*({YEAR})\b', text, re.I)
        if selected_year and int(selected_year[1]) != year:
            return None
        options = set(re.findall(rf'\b{year}\s*г\.\s*[-–]\s*(\d[\d\u00a0 ]*)\s*руб\.?\s*(?:\n\s*){{0,2}}(в наличии|нет в наличии)', text, re.I))
        if len(options) == 1 and (match := options.pop())[1].lower() == 'в наличии':
            amount, stock = match[0], 'in_stock'
            latin = next((line for line in text.splitlines()[1:5]
                          if re.search(r'[A-Za-z]{3,}.*[A-Za-z]{3,}', line) and not re.search(r'[А-Яа-я]', line)), None)
            title = latin or title
            text = f'{SPB}\n{year} г. — {amount} ₽\n{match[1]}'
    elif host in {'luding.ru', 'spb.luding.ru'} and blocks.get('city') == SPB:
        if year_in(title) != year:
            return None
        # The block contains the main offer followed by legal text and reviews.
        # A discounted offer can show two prices. Require the localized title
        # to confirm which of those visible values is the current price.
        offer = re.split(r'(?mi)^[ \t]*(?:Отзывы|Легенда)[ \t]*$', text, maxsplit=1)[0]
        marks = set(re.findall(r'(?m)^[ \t]*(\d[\d \u00a0\u202f]*)[ \t\u00a0\u202f]*₽[ \t]*$', offer))
        prices = {re.sub(r'\s', '', value) for value in marks}
        advertised = re.search(r'в Санкт-Петербурге по цене\s+(\d[\d \u00a0\u202f]*)\s*₽', hint, re.I)
        if advertised:
            advertised_amount = re.sub(r'\s', '', advertised[1])
            amount = advertised_amount if advertised_amount in prices else None
        elif len(prices) == 1:
            amount = prices.pop()
        if not re.search(r'нет в наличии|ожидаем поступление', offer, re.I):
            availability = re.search(r'(?mi)^[ \t]*(в наличии(?:[ \t]+у[ \t]+поставщика|[ \t]+в[ \t]+винотек[^\n]*)?)[ \t]*$', offer)
            if availability:
                label = availability[1]
                stock = 'supplier_stock' if 'поставщика' in label.casefold() else 'in_stock'
                text = f'{title}\n{SPB}\n{amount} ₽\n{label}'
    if not stock or not amount:
        return None
    return {'title': title, 'year': year, 'volume_l': float(volumes.pop()),
            'price': int(re.sub(r'\s', '', amount)), 'stock': stock, 'text': text[:1000],
            'url': row['url'], 'source': RETAILERS[host], 'date': moscow_date(row['observed_at'])}


def parse_labeled_offer(row, host):
    blocks = row.get('blocks', {})
    if blocks.get('city') != SPB or not blocks.get('product'):
        return None
    text = blocks['product']
    title = row.get('title', '')
    # The JOIA storefront has bottle names such as “El Coto 1970”.
    displayed_year = None if host == 'joiastore.ru' else year_in(title)
    years = set(re.findall(rf'(?mi)^[ \t]*(?:Год урожая|Выбранный винтаж|Винтаж)\s*:\s*({YEAR})[ \t]*$', text))
    selected = blocks.get('selected_variant', '')
    if selected and host == 'ast.wine':
        selected, *suffix = selected.splitlines()
        # Some AST variants include their own price on a second line.
        if suffix and (len(suffix) != 1 or not re.fullmatch(RUBLES, suffix[0].strip(), re.I)):
            return None
    if selected:
        selected_year = re.fullmatch(rf'({YEAR})(?:,\s*{VOLUME})?', selected, re.I)
        if not selected_year:
            return None
        years.add(selected_year[1])
    if host == 'ast.wine' and not years and displayed_year is None:
        options = re.findall(rf'(?:^|\n)({YEAR}),[ \t]+{VOLUME}', text)
        title_year = year_in(blocks.get('document_title', ''))
        if len(options) == 1 and title_year == int(options[0][0]):
            years.add(options[0][0])
    if displayed_year is not None:
        years.add(str(displayed_year))
    if len(years) != 1:
        return None
    year = int(years.pop())
    sizes = re.findall(rf'(?mi)^[ \t]*Объ[её]м\s*:?\s*{VOLUME}', text)
    sizes.extend(re.findall(VOLUME, title, re.I))
    sizes.extend(re.findall(VOLUME, selected, re.I))
    volumes = {Decimal(n.replace(',', '.')) / (1000 if unit.casefold() in {'мл', 'ml'} else 1)
               for n, unit in sizes}
    if len(volumes) != 1 or next(iter(volumes)) <= 0:
        return None

    if host == 'simplewine.ru':
        # The price and stock token must belong to the selected year's row.
        variants = set(re.findall(rf'(?mi)^[ \t]*{year}[ \t]+г\.[ \t]*[—–-][ \t]*{RUBLES}[ \t]*\n[ \t]*(в наличии|нет в наличии)[ \t]*$', text))
        if len(variants) != 1 or not re.search(r'(?mi)^[ \t]*Забрать сегодня из [1-9]\d* винотек', text):
            return None
        amount, label = variants.pop()
        if label.casefold() != 'в наличии':
            return None
    else:
        prices = set(re.findall(rf'(?mi)^[ \t]*(?:(?:Текущая )?Цена[ \t]*:[ \t]*)?{RUBLES}[ \t]*$',
                                blocks.get('offer_price') or text))
        if len(prices) != 1:
            return None
        if host == 'ast.wine':
            # "В наличии в магазинах" is also the name of a general button.
            addresses = r'(?:ул\.\s*Жуковского,\s*22|ул\.\s*Марата,\s*43)'
            _, marker, tail = text.partition('\nНаличие\n')
            stock_block = '\n'.join(tail.splitlines()[:22]) if marker else ''
            local_shops = blocks.get('local_shops')
            if local_shops:
                stock = re.search(rf'(?mi)^{addresses}[ \t]*\|[ \t]*(В наличии|Мало|Много)[ \t]*$', local_shops)
            else:
                stock = re.search(rf'(?mi)^{addresses}[ \t]*$(?:\n[^\n]*){{0,2}}\n[ \t]*(В наличии|Мало|Много)[ \t]*$',
                                  stock_block)
        else:
            stock = re.search(r'(?mi)^[ \t]*(В наличии(?: в (?:(?:вашем )?магазине|винотеке|[1-9]\d* магазин(?:е|ах)))?)[ \t]*$', text)
        if not stock or re.search(r'(?mi)^[ \t]*(Нет в наличии|Ожидаем поступление)[ \t]*$', text):
            return None
        amount, label = prices.pop(), stock[1]
    price = Decimal(re.sub(r'\s', '', amount).replace(',', '.'))
    if price <= 0:
        return None
    return {'title': title, 'year': year, 'volume_l': float(volumes.pop()), 'price': float(price),
            'stock': 'in_stock', 'text': f'{title}\n{SPB}\n{amount} ₽\n{label}',
            'url': row['url'], 'source': RETAILERS[host], 'date': moscow_date(row['observed_at'])}


def identity(title, year):
    # Keep distinguishing cuvée terms. Unmatched aliases require review.
    words = [s for s in normalized(title).split() if s not in {'вино', 'doc', 'doca', 'aoc', 'bodegas', str(year)}]
    return tuple(sorted(words)), year


def capture_rows(bundle):
    if bundle.get('kind') != 'wine_atlas_research_capture' or bundle.get('version') != 1:
        raise ValueError('unsupported capture format')
    return bundle['observations']


def https_url(value):
    url = urlsplit(value or '')
    return url if url.scheme == 'https' and url.hostname and not (url.username or url.password) else None


def page_key(url):
    return url.netloc.lower(), url.path.rstrip('/'), url.query


def retailer_host(row):
    url = https_url(row.get('requested_url') or row.get('url'))
    return (url.hostname or '').removeprefix('www.') if url else None


def wine_key(row, aliases):
    return identity(aliases.get(row['url'], row['title']), row['year'])


def queue_reviews(queue, aliases):
    if not isinstance(queue.get('vintages'), list) or (
            'kind' in queue and (queue['kind'], queue.get('version')) != ('wine_atlas_critic_queue', 1)):
        raise ValueError('unsupported critic queue format')
    for vintage in queue['vintages']:
        key = identity(vintage['title'], vintage['year'])
        for review in vintage['evidence']:
            if https_url(review.get('url')) and wine_key(review, aliases) == key:
                yield review


def local_stock(offer):
    return offer['stock'] == 'in_stock' or (offer['source'], offer['stock']) == ('Luding', 'supplier_stock')


def observed_city(row):
    city = row.get('blocks', {}).get('city')
    if city:
        return city
    # Earlier captures kept the city switcher in the first header excerpt.
    header = row.get('excerpts', [])[:2]
    cities = {line.split(' | ', 1)[0].strip() for line in header} & {SPB, 'Москва'}
    return cities.pop() if len(cities) == 1 else None


def index_captures(rows, aliases, checked_on):
    reviews, latest, counters, unresolved = [], {}, {}, []
    for row in rows:
        host = retailer_host(row)
        requested = https_url(row.get('requested_url') or row.get('url'))
        url = https_url(row.get('url'))
        if host in RETAILERS:
            seller = RETAILERS[host]
            stats = counters.setdefault(seller, dict(pages=0, offers=0, in_stock_in_budget=0))
            stats['pages'] += 1
            key = page_key(requested)
            stamp = observation_time(row['observed_at'])
            if key not in latest or latest[key][0] <= stamp:
                latest[key] = (stamp, host, row)
        elif url and page_key(requested) == page_key(url) and row.get('status') == 'needs_review':
            found = parse_reviews(row, host)
            if found:
                reviews.extend(found)
            elif host in CRITICS and row.get('blocks'):
                unresolved.append({'url': row['url'], 'reason': 'review_requires_review'})

    offers = defaultdict(list)
    for _, host, row in latest.values():
        url = https_url(row.get('url'))
        requested = https_url(row.get('requested_url') or row.get('url'))
        reason = row.get('status') if row.get('status') != 'needs_review' else None
        if not url or page_key(requested) != page_key(url):
            reason = 'redirect'
        offer = None if reason else parse_offer(row, host)
        if offer:
            offers[wine_key(offer, aliases)].append(offer)
            stats = counters[offer['source']]
            stats['offers'] += 1
            stats['in_stock_in_budget'] += (offer['date'] == checked_on and local_stock(offer)
                                             and 0 < offer['price'] <= 5000)
        elif reason or row.get('blocks') or '/product/' in requested.path or '/productDetail/' in requested.path:
            if not reason and observed_city(row) not in {None, SPB}:
                reason = 'other_city'
            unresolved.append({'url': row.get('url'), 'retailer': RETAILERS[host],
                               'reason': reason or 'offer_requires_review'})
    return reviews, offers, counters, unresolved


def catalog_record(key, title, offer, ratings, end, price, rate_date, rates):
    year = key[1]
    title = ' '.join(re.sub(rf'\b{year}\b', '', title).split())
    record_id = hashlib.sha256(repr(key).encode()).hexdigest()[:12]
    return {'id': record_id, 'title': title, 'year': year, 'research': True,
            'wishlist': False, 'volume_l': offer['volume_l'], 'grapes': [], 'pairings': [],
            'stores': [{'name': offer['source'], 'url': offer['url'], 'price_rub': offer['price'],
                        'price_checked_at': offer['date']}],
            'availability': {'status': 'in_stock', 'stock_kind': offer['stock'], 'region': SPB,
                             'source_url': offer['url'], 'observed_on': offer['date'], 'evidence': offer['text'],
                             'snapshot_source': 'browser_observation'},
            'drinking_window': {'kind': 'window', 'scope': 'vintage', 'min': end.get('start'),
                                'max': end['end'], 'source': end['source'], 'source_url': end['url']},
            'critic_ratings': [{'source': score['source'], 'score': score['score'], 'scale': score['scale'],
                               'scope': 'vintage', 'vintage': year, 'source_url': score['url'],
                               'observed_on': score['date']} for score in ratings],
            'foreign_reference': {'amount': float(price['amount']), 'currency': price['currency'], 'kind': price['price_kind'],
                                  'price_source_url': price['url'], 'exchange_rate_rub': float(rates[price['currency']]),
                                  'rate_source': {'source': 'Банк России', 'date': rate_date, 'source_url': RATE_URL},
                                  'amount_rub': exchange(price['amount'], price['currency'], rates)[1]}}


def reconcile(rows, rate_date, rates, aliases, checked_on, queue=None):
    if rate_date > checked_on:
        raise ValueError('the exchange rate was not effective on the observation date')
    extracted, offers, counters, unresolved = index_captures(rows, aliases, checked_on)
    reviews = defaultdict(list)
    for review in queue_reviews(queue, aliases) if queue is not None else ():
        if review['date'] <= checked_on:
            reviews[wine_key(review, aliases)].append(review)
    for review in extracted:
        if review['date'] <= checked_on:
            reviews[wine_key(review, aliases)].append(review)

    accepted, candidates = [], []
    cutoff_year = max(2027, dt.date.fromisoformat(checked_on).year)
    for key, observations in reviews.items():
        year = key[1]
        rated, windows, priced = {}, [], []
        for r in observations:
            score, scale = r.get('score'), r.get('scale')
            if scale in {20, 99, 100} and score is not None and 85 <= score * 100 / scale <= 100:
                previous = rated.get(r['source'])
                if previous is None or score / scale > previous['score'] / previous['scale']:
                    rated[r['source']] = r
            end, start = r.get('end'), r.get('start')
            if end and end >= max(cutoff_year, year) and (start is None or year <= start <= end):
                windows.append(r)
            amount, currency = r.get('amount'), r.get('currency')
            if (amount and currency in rates and r.get('price_kind') in {'exact', 'upper_bound'} and
                    (queue is not None or r['date'] == checked_on) and 0 < exchange(amount, currency, rates)[0] <= 6000):
                priced.append(r)

        matched = offers.get(key, [])
        fresh = [o for o in matched if o['date'] == checked_on]
        local = [o for o in fresh if 0 < o['price'] <= 5000 and local_stock(o)]
        requirements = [('score', rated), ('window', windows), ('foreign_price', priced)]
        missing = [flag for flag, evidence in requirements if not evidence]
        title = aliases.get(observations[0]['url'], observations[0]['title'])
        if not missing:
            if local:
                result = 'matched'
            elif any(local_stock(o) for o in fresh):
                result = 'above_budget'
            elif fresh:
                result = 'local_stock_unconfirmed'
            else:
                result = 'stale_offer' if matched else 'no_exact_offer'
            candidates.append({'title': title, 'year': year, 'result': result,
                               'offers': [{k: v for k, v in o.items() if k != 'text'} for o in matched]})
        if missing or not local:
            unresolved.append({'title': title, 'year': year, 'missing': missing + ([] if local else ['spb_offer'])})
            continue
        offer = min(local, key=lambda o: (o['price'], o['url']))
        end = min(windows, key=lambda r: r['end'])
        price = min(priced, key=lambda r: exchange(r['amount'], r['currency'], rates)[0])
        accepted.append(catalog_record(key, title, offer, rated.values(), end, price, rate_date, rates))
    return {'eligible': accepted, 'candidates': unresolved, 'retailer_matches': candidates, 'retailers': counters}


def join(bundle, rate_date, rates, aliases=None, checked_on=None):
    report = reconcile(capture_rows(bundle), rate_date, rates, aliases or {}, checked_on or rate_date)
    return report['eligible'], report['candidates']


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
    parser.add_argument('capture', type=Path, nargs='+', help='One or more browser exports')
    parser.add_argument('--critic-queue', type=Path, help='Output of stage_critic_research.py')
    parser.add_argument('--rates', type=Path, help='Saved CBR XML for replay; otherwise fetch today’s rates')
    parser.add_argument('--aliases', type=Path, help='Reviewed mapping from URL to canonical wine name; does not override vintage')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    rows = [row for path in args.capture for row in capture_rows(load(path))]
    market_rows = [row for row in rows if retailer_host(row) in RETAILERS]
    checked_on = max((moscow_date(row['observed_at']) for row in market_rows or rows), default=None)
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
    queue = load(args.critic_queue) if args.critic_queue else None
    report = reconcile(rows, date, rates, aliases, checked_on, queue)
    accepted, unresolved = report['eligible'], report['candidates']
    path = ROOT / 'data/discovered-wines.json'
    if args.report and args.report.resolve() == path.resolve():
        parser.error('the report path may not overwrite the catalog')
    overlay = load(path)
    additions = merge(overlay['records'], accepted, load(ROOT / 'data/wines.json')['records'],
                      load(ROOT / 'data/owner-exclusions.json')['records'])
    report.update(rate_date=date, checked_on=checked_on, new_catalog_records=additions)
    if args.report:
        write(args.report, report)
    if args.apply and additions:
        overlay['records'].extend(additions)
        overlay['checked_at'] = max(checked_on, overlay.get('checked_at', checked_on))
        write(path, overlay)
    print(f'eligible={len(accepted)} unresolved={len(unresolved)} new={len(additions)} applied={len(additions) if args.apply else 0}')


if __name__ == '__main__':
    main()
