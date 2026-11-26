#!/usr/bin/env python3
"""Index every rated vintage and report its checks at every retailer."""
import argparse
import hashlib
import html
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from import_research import (
    RETAILERS, ROOT, RUBLES, SPB, VOLUME, capture_rows, exchange, https_url, identity, index_captures,
    load, local_stock, moscow_date, observation_time, observed_city, page_key, parse_rates, retailer_host, write, year_in,
)
from report_research_capture import simplewine_hints
from research_sitemaps import product_candidates
from stage_critic_research import browser_observations


STORES = ('Винлаб', 'Ароматный мир', 'Vinissimo', 'Sabonis', 'WineStyle', 'SimpleWine', 'AST.WINE', 'Joia', 'Luding')
RESULTS = {
    'matched': 'Точный винтаж · в наличии · до 5 000 ₽',
    'above_budget': 'Точный винтаж · в наличии · выше 5 000 ₽',
    'out_of_stock': 'Точный винтаж · нет в наличии в Петербурге',
    'exact_unconfirmed': 'Карточка того же винтажа · условия не подтверждены',
    'previously_verified': 'Цена того же винтажа подтверждена ранее',
    'other_vintage': 'Найден другой винтаж',
    'vintage_unconfirmed': 'Найдено название · винтаж не подтверждён',
    'search_unresolved': 'Поиск выполнен · совпадение не подтверждено',
    'search_unverified': 'Сайт открылся · выдача не распознана',
    'search_no_results': 'Поиск магазина вернул пустую выдачу',
    'search_error': 'Ошибка адресного поиска',
    'search_unavailable': 'Адресный поиск магазина недоступен',
    'age_gate': 'Сайт запрашивает подтверждение возраста',
    'index_candidates': 'В карте сайта есть похожие карточки',
    'not_in_index': 'В доступной карте сайта нет ссылки с совпавшим названием',
    'index_without_names': 'Карта сайта содержит артикулы · нужен запрос по названию',
    'store_unavailable': 'В этом прогоне каталог магазина недоступен',
    'not_in_sample': 'В просмотренных карточках совпадений нет',
    'not_checked': 'Поиск ещё не выполнен',
}


def candidate_id(key):
    return hashlib.sha256(repr(key).encode()).hexdigest()[:12]


def label_without_volume(title):
    return re.sub(rf'\b{VOLUME}', '', title, flags=re.I).strip(' ,')


def matrix_key(title, year):
    return identity(label_without_volume(title), year)


def qualifying(rating):
    score, scale = rating.get('score'), rating.get('scale')
    return scale in (20, 99, 100) and score is not None and 85 <= score * 100 / scale <= 100


def deduplicate(rows, fields):
    return list({tuple(row.get(field) for field in fields): row for row in rows}.values())


def collect_wines(bundles, aliases, archive=()):
    evidence, claims = defaultdict(list), defaultdict(list)
    for row in [*archive, *(row for bundle in bundles for row in browser_observations(bundle, aliases))]:
        if https_url(row.get('url')) and row.get('year') and row.get('title'):
            evidence[matrix_key(aliases.get(row['url'], row['title']), row['year'])].append(row)
    for bundle in bundles:
        for row in capture_rows(bundle):
            hint = simplewine_hints(row)
            if hint:
                key = matrix_key(aliases.get(hint['retailer_url'], hint['title']), hint['year'])
                claims[key].append(hint)

    wines = []
    for key in evidence.keys() | claims.keys():
        notes = deduplicate(evidence[key], ('source', 'url', 'year', 'score', 'scale', 'amount',
                                            'currency', 'price_kind', 'start', 'end', 'method'))
        published = [row for row in notes if qualifying(row)]
        hints = deduplicate(claims[key], ('retailer_url', 'year'))
        if not published and not hints:
            continue
        title = published[0]['title'] if published else hints[0]['title']
        title = aliases.get(published[0]['url'] if published else hints[0]['retailer_url'], title)
        title = re.sub(r'^(?:Игристое )?Вино\s+', '', title, flags=re.I)
        title = ' '.join(re.sub(rf'\b{key[1]}\b', '', label_without_volume(title)).split()).strip(' ,–-')
        wines.append({'id': candidate_id(key), 'title': title, 'year': key[1], 'key': key,
                      'published_ratings': deduplicate(published, ('source', 'url', 'score', 'scale')),
                      'retailer_claims': hints, 'evidence': notes,
                      'publisher_pages': [{'source': row['source'], 'url': row['url']} for row in notes
                                          if row.get('method') == 'publisher_page_lookup']})
    return sorted(wines, key=lambda wine: (not wine['published_ratings'], wine['title'].casefold(), wine['year']))


def price_evidence(wine, rates):
    prices = []
    for row in wine['evidence']:
        amount, currency = row.get('amount'), row.get('currency')
        if amount and currency in rates and row.get('price_kind') in ('exact', 'upper_bound'):
            value, rounded = exchange(amount, currency, rates)
            if value > 0:
                prices.append({'rub': rounded, 'within_budget': value <= 6000, 'url': row['url'],
                               'amount': amount, 'currency': currency, 'kind': row['price_kind']})
    return min(prices, key=lambda price: price['rub'], default=None)


def observed_product(row, host, aliases):
    """Keep a partial card separate from a reliably parsed offer."""
    blocks = row.get('blocks', {})
    if not any(blocks.get(key) for key in ('product', 'offer_price', 'price_stock')):
        return None
    title = row.get('title', '').strip()
    if not title:
        return None
    variant = blocks.get('selected_variant', '')
    label = re.findall(r'(?mi)^\s*(?:Год урожая|Винтаж)\s*:?\s*\n?\s*((?:19|20)\d{2})\s*$',
                       blocks.get('product', ''))
    years = {y for y in [year_in(variant.splitlines()[0]) if variant else None, *map(int, label),
                        year_in(title) if host != 'joiastore.ru' else None] if y}
    shown_year = next(iter(years)) if len(years) == 1 else None
    canonical = aliases.get(row['url'], title)
    names = matrix_key(canonical, shown_year or year_in(canonical))[0]
    # These dedicated fields describe the current card, not its recommendations.
    price_text = blocks.get('offer_price') or blocks.get('price_stock', '')
    city = observed_city(row)
    unavailable = False
    if host == 'simplewine.ru' and shown_year is not None:
        variants = set(re.findall(
            rf'(?mi)^[ \t]*{shown_year}[ \t]+г\.[ \t]*[—–-][ \t]*{RUBLES}[ \t]*\n[ \t]*(в наличии|нет в наличии)[ \t]*$',
            blocks.get('product', '')))
        if len(variants) == 1:
            amount, stock = variants.pop()
            price_text = amount + ' ₽'
            unavailable = city == SPB and stock.casefold() == 'нет в наличии'
    elif host == 'spb.winestyle.ru':
        unavailable = bool(re.search(r'нет в наличии|ожидаем поступление', price_text, re.I))
    prices = {float(re.sub(r'\s', '', amount).replace(',', '.'))
              for amount in re.findall(RUBLES, price_text, re.I)}
    price = next(iter(prices)) if len(prices) == 1 else None
    return names, {'url': row['url'], 'title': title, 'year': shown_year, 'price': price,
                   'unavailable_in_spb': unavailable, 'city': city, 'observed_at': row['observed_at']}


def index_retailers(rows, aliases):
    state = {store: Counter() for store in STORES}
    cards, attempts = defaultdict(list), defaultdict(list)
    latest = {}
    for row in rows:
        host = retailer_host(row)
        store = RETAILERS.get(host)
        if not store:
            continue
        state[store][row.get('status', 'unknown')] += 1
        lookup = row.get('lookup')
        if isinstance(lookup, dict) and isinstance(lookup.get('id'), str):
            attempts[lookup['id'], store].append(row)
        requested = https_url(row.get('requested_url') or row.get('url'))
        actual = https_url(row.get('url'))
        if row.get('status') == 'needs_review' and requested and actual and page_key(requested) == page_key(actual):
            key = (store, page_key(actual))
            if key not in latest or observation_time(latest[key][1]['observed_at']) <= observation_time(row['observed_at']):
                latest[key] = (host, row)
    for (store, _), (host, row) in latest.items():
        product = observed_product(row, host, aliases)
        if product:
            names, card = product
            cards[names, store].append(card)
    return state, cards, attempts


def retailer_result(wine, store_state, exact_offers, cards, attempts, date, indexed, index_coverage):
    fresh = [row for row in exact_offers if row['date'] == date]
    local = [row for row in fresh if local_stock(row)]
    primary = min(local or fresh, key=lambda row: row['price'], default=None)
    earlier = [row for row in exact_offers if row['date'] < date]
    previous = max(earlier, key=lambda row: (row['date'], -row['price']), default=None)
    exact_cards = [card for card in cards if card['year'] == wine['year']]
    current_cards = [card for card in exact_cards if moscow_date(card['observed_at']) == date]
    current_named = [card for card in cards if moscow_date(card['observed_at']) == date]
    unavailable = bool(current_cards) and all(card['unavailable_in_spb'] for card in current_cards)
    attempts = sorted(attempts, key=lambda row: row['observed_at'])
    search = [{'url': row.get('requested_url') or row.get('url'), 'status': row['status'],
               'role': row['lookup'].get('role'), 'error': row.get('error'),
               'access_reason': row.get('access_reason'),
               'query_text': row['lookup'].get('term'),
               'observed_at': row['observed_at'], 'observed_url': row.get('url'), 'title': row.get('title'),
               'search_coverage': row.get('search_coverage')} for row in attempts]
    if local:
        status = 'matched' if primary['price'] <= 5000 else 'above_budget'
    elif unavailable:
        status = 'out_of_stock'
    elif primary or current_cards:
        status = 'exact_unconfirmed'
    elif any(card['year'] is None for card in current_named):
        status = 'vintage_unconfirmed'
    elif current_named:
        status = 'other_vintage'
    elif previous:
        status = 'previously_verified'
    elif exact_cards:
        status = 'exact_unconfirmed'
    elif any(card['year'] is None for card in cards):
        status = 'vintage_unconfirmed'
    elif cards:
        status = 'other_vintage'
    elif search:
        relevant = [item for item in search if moscow_date(item['observed_at']) == date] or search
        queries = [item['status'] for item in relevant if item['role'] == 'query']
        outcomes = {item['access_reason'] or item['status'] for item in relevant}
        if 'needs_review' in outcomes:
            status = 'search_unresolved'
        elif 'age_gate' in outcomes:
            status = 'age_gate'
        elif outcomes <= {'blocked', 'search_unavailable'}:
            status = 'search_unavailable'
        elif queries and set(queries) == {'no_results'}:
            status = 'search_no_results'
        elif 'search_unverified' in outcomes:
            status = 'search_unverified'
        else:
            status = 'search_error'
    elif indexed:
        status = 'index_candidates'
    elif index_coverage.get('products'):
        status = 'not_in_index' if index_coverage['named_products'] else 'index_without_names'
    elif store_state:
        status = 'not_in_sample' if store_state['needs_review'] else 'store_unavailable'
    else:
        status = 'not_checked'

    partial = max(current_cards or exact_cards, key=lambda card: observation_time(card['observed_at']), default=None)
    displayed = primary or (previous if status == 'previously_verified' else None) or partial
    price = (displayed or {}).get('price')
    price_date = (displayed.get('date') or moscow_date(displayed['observed_at'])) if displayed and price is not None else None
    return {'status': status, 'price_rub': price, 'price_within_budget': 0 < price <= 5000 if price is not None else None,
            'volume_l': (displayed or {}).get('volume_l'),
            'spb_stock': True if local else False if unavailable else None,
            'availability': primary['stock'] if primary and primary in fresh else 'out_of_stock' if unavailable else None,
            'url': (displayed or {}).get('url'), 'price_date': price_date,
            'previous_offer': {k: v for k, v in previous.items() if k != 'text'} if previous else None,
            'cards': cards, 'offers': [{k: v for k, v in row.items() if k != 'text'} for row in exact_offers],
            'targeted_checks': search, 'indexed_product_urls': indexed}


def build_matrix(bundles, aliases, rates, date, archive=(), index=None):
    aliases = {**{row['url']: row['title'] for row in archive if row.get('method') == 'publisher_page_lookup'}, **aliases}
    rows = [row for bundle in bundles for row in capture_rows(bundle)]
    wines = collect_wines(bundles, aliases, archive)
    _, indexed_offers, _, _ = index_captures(rows, aliases, date)
    previous_rows = [row for row in rows if retailer_host(row) in RETAILERS and moscow_date(row['observed_at']) < date]
    _, previous_offers, _, _ = index_captures(previous_rows, aliases, date)
    offers = defaultdict(list)
    candidates = deduplicate((row for collection in (previous_offers, indexed_offers)
                              for group in collection.values() for row in group),
                             ('source', 'url', 'year', 'date'))
    for row in candidates:
        offers[matrix_key(aliases.get(row['url'], row['title']), row['year']), row['source']].append(row)
    coverage, cards, attempts = index_retailers(rows, aliases)
    candidate_links, named_counts = product_candidates(wines, index) if index else ({}, {})
    index_coverage = {store: {'status': item['status'], 'documents': item['read'],
                             'products': len(item['products']), 'errors': item['errors'],
                             'named_products': named_counts.get(store, 0),
                             'unread': item.get('unread', 0)} for store, item in index['stores'].items()} if index else {}
    for wine in wines:
        key = wine.pop('key')
        price = price_evidence(wine, rates)
        windows = [row for row in wine.pop('evidence') if row.get('end') and row['end'] >= max(date_year(date), wine['year'])]
        wine['foreign_price'] = price
        wine['drink_until'] = min((row['end'] for row in windows), default=None)
        wine['window_urls'] = sorted({row['url'] for row in windows})
        wine['stores'] = {store: retailer_result(wine, coverage[store],
                         offers[key, store],
                         cards[key[0], store], attempts[wine['id'], store], date,
                         candidate_links.get((wine['id'], store), []), index_coverage.get(store, {})) for store in STORES}
        requirements = {'primary_score': bool(wine['published_ratings']), 'drinking_window': bool(windows),
                        'foreign_price': bool(price and price['within_budget']),
                        'spb_offer': any(item['status'] == 'matched' for item in wine['stores'].values())}
        wine['missing_requirements'] = [key for key, passed in requirements.items() if not passed]
    totals = Counter(result['status'] for wine in wines for result in wine['stores'].values())
    return {'kind': 'wine_atlas_retailer_matrix', 'version': 1, 'checked_on': date,
            'observations': len(rows), 'stores': list(STORES), 'wines': wines,
            'source_rows': dict(Counter(row.get('source') for row in rows if row.get('source'))),
            'retailer_coverage': {store: dict(stats) for store, stats in coverage.items()},
            'public_index_coverage': index_coverage,
            'pair_status_counts': dict(totals)}


def search_plan(matrix):
    wines = []
    for wine in matrix['wines']:
        target = {key: wine[key] for key in ('id', 'title', 'year')}
        products = {store: result['indexed_product_urls'][:2] for store, result in wine['stores'].items()
                    if result['indexed_product_urls']}
        if products:
            target['products'] = products
        if wine['publisher_pages']:
            target['publisher_pages'] = wine['publisher_pages']
        wines.append(target)
    return {'kind': 'wine_atlas_store_search_plan', 'version': 1, 'wines': wines}


def date_year(date):
    return max(2027, int(date[:4]))


def render_html(matrix):
    escape = html.escape

    def link(url, text):
        return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>' if https_url(url) else escape(text)

    def cell(result):
        status = result['status']
        description = RESULTS[status]
        price = (f" · {result['price_rub']:g} ₽"
                 + (' (до 5 000 ₽)' if result['price_within_budget'] else ' (выше 5 000 ₽)')) if result['price_rub'] is not None else ''
        if result['volume_l'] is not None:
            price += f" · {result['volume_l']:g} л"
        if result['price_date'] and result['price_date'] != matrix['checked_on']:
            price += ' · ' + result['price_date']
        if status == 'other_vintage':
            years = sorted({card['year'] for card in result['cards'] if card['year'] is not None})
            description += ' · ' + ', '.join(map(str, years))
        reference = result['url'] or next((card['url'] for card in result['cards']), None)
        if not reference:
            reference = next((item['observed_url'] or item['url'] for item in result['targeted_checks']
                              if item['role'] == 'detail'), None)
            reference = reference or next((item['observed_url'] or item['url'] for item in result['targeted_checks']), None)
        checks = result['targeted_checks']
        details = ''
        if checks:
            queries = sum(item['role'] == 'query' for item in checks)
            targets = [item for item in checks if item['role'] == 'detail']
            if targets:
                details = '<br><small>' + ' · '.join(link(item['observed_url'] or item['url'],
                    item['title'] or 'Карточка') for item in targets[:5]) + '</small>'
            details = f'<br><small>Страниц поиска: {queries}. Карточек: {len(targets)}.</small>' + details
            current = [item for item in checks if moscow_date(item['observed_at']) == matrix['checked_on']]
            blocked = any(item['status'] == 'blocked' or item['access_reason'] == 'blocked' for item in current)
            gated = any(item['status'] == 'age_gate' or item['access_reason'] == 'age_gate' for item in current)
            if blocked or gated:
                reason = 'подтверждение возраста' if gated else 'сайт ограничил доступ'
                errors = sorted({item['error'] for item in current if item['status'] == 'blocked' and item['error']})
                if errors:
                    reason += ' · ' + ', '.join(errors)
                details += '<br><small>В текущем обходе · ' + escape(reason) + '</small>'
            skipped = sum(item['role'] == 'skipped' for item in current)
            if skipped:
                details += f'<br><small>Пропущено после ограничения: {skipped}.</small>'
        if result['indexed_product_urls'] and status != 'matched':
            details += '<br><small>Карта сайта: ' + ' · '.join(link(url, str(i))
                for i, url in enumerate(result['indexed_product_urls'], 1)) + '</small>'
        if result['previous_offer'] and status not in ('matched', 'previously_verified'):
            earlier = result['previous_offer']
            details += '<br><small>' + link(earlier['url'], f"Ранее: {earlier['price']:g} ₽ · {earlier['date']}") + '</small>'
        return f'<td class="{status}">{link(reference, description + price)}{details}</td>'

    def row(wine):
        published = wine['published_ratings']
        ratings = [link(r['url'], f"{r['source']} {r['score']:g}/{r['scale']}") for r in published]
        ratings += [link(h['retailer_url'], 'SimpleWine сообщает ' + ', '.join(
            f"{r['source']} {r['score']:g}/{r['scale']}" for r in h['reported_ratings']))
            for h in wine['retailer_claims']]
        ratings += [link(p['url'], f"{p['source']} · открытая часть карточки без балла")
                    for p in wine['publisher_pages'] if p['url'] not in {r['url'] for r in published}]
        foreign = wine['foreign_price']
        foreign_label = link(foreign['url'], f"{foreign['rub']:g} ₽") if foreign else '—'
        windows = wine['window_urls']
        window_label = link(windows[0], str(wine['drink_until'])) if windows else '—'
        qualifies = 'yes' if not wine['missing_requirements'] else 'no'
        return (f"<tr data-qualifies='{qualifies}'><th scope='row'>{escape(wine['title'])}</th><td>{wine['year']}</td>"
                f"<td>{'<br>'.join(ratings)}</td><td>{window_label}<br>{foreign_label}</td>"
                + ''.join(cell(wine['stores'][store]) for store in matrix['stores']) + '</tr>')

    count = len(matrix['wines'])
    confirmed = sum(bool(wine['published_ratings']) for wine in matrix['wines'])
    qualified = sum(not wine['missing_requirements'] for wine in matrix['wines'])
    queried = sum(any(check['role'] == 'query' for check in item['targeted_checks'])
                  for wine in matrix['wines'] for item in wine['stores'].values())
    maps = matrix['public_index_coverage']
    mapped = sum(info['products'] > 0 for info in maps.values())
    urls = sum(info['products'] for info in maps.values())
    current_checks = []
    for store in matrix['stores']:
        checks = [check for wine in matrix['wines'] for check in wine['stores'][store]['targeted_checks']
                  if moscow_date(check['observed_at']) == matrix['checked_on']]
        pages = sum(check['role'] == 'query' for check in checks)
        products = sum(check['role'] == 'detail' for check in checks)
        skipped = sum(check['role'] == 'skipped' for check in checks)
        current_checks.append(f'<li>{escape(store)} · страниц поиска {pages} · проверок карточек {products} · пропущено {skipped}</li>')
    headers = ['Вино', 'Урожай', 'Оценки и источники', 'Пить по / цена за рубежом', *matrix['stores']]
    return f"""<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wine Atlas — матрица поиска</title>
<style>
body{{font:15px/1.45 system-ui,sans-serif;margin:24px;color:#211d20;background:#fbf9f8}}
table{{border-collapse:collapse;background:white;width:100%;font-size:13px}}
td,th{{padding:8px;vertical-align:top;text-align:left;border:1px solid #ddd;min-width:94px}}
th:first-child{{position:sticky;left:0;background:#f5edf0;min-width:170px}}
thead th{{background:#f5edf0}}.scroll{{overflow-x:auto}}a{{color:#702544}}
.matched{{background:#e1f2e5}}.above_budget,.exact_unconfirmed,.vintage_unconfirmed,.previously_verified{{background:#fff1d6}}
.store_unavailable,.search_error,.search_unavailable,.out_of_stock,.age_gate{{background:#fae6e7}}
</style>
<h1>Wine Atlas — матрица поиска</h1>
<p>{escape(matrix['checked_on'])} · {count} винтажей · {confirmed} с баллом первоисточника · {count * len(matrix['stores'])} пар «вино × магазин».</p>
<p>Карты сайтов: {mapped} магазинов, {urls:,} товарных адресов. Адресные запросы: {queried} пар. Все условия каталога выполнили {qualified} винтажа.</p>
<details><summary>Попытки доступа по магазинам за {escape(matrix['checked_on'])}</summary><ul>{''.join(current_checks)}</ul></details>
<p>Совпадение в карте сайта означает похожий адрес карточки. Цена, наличие и винтаж подтверждаются при чтении товара. Пустая выдача относится к конкретному запросу. Оценки с сайта магазина отмечены отдельно.</p>
<p><label for="filter">Фильтр по вину, году или критику</label> <input id="filter" type="search">
<label><input id="qualified" type="checkbox"> Только прошедшие все условия</label></p>
<div class="scroll"><table><thead><tr>{''.join(f'<th scope="col">{escape(h)}</th>' for h in headers)}</tr></thead>
<tbody>{''.join(row(wine) for wine in matrix['wines'])}</tbody></table></div>
<script>
const filter = document.getElementById('filter');
const qualified = document.getElementById('qualified');
const rows = [...document.querySelectorAll('tbody tr')];
function update() {{
  const query = filter.value.trim().toLocaleLowerCase();
  for (const row of rows) {{
    const key = [...row.cells].slice(0, 3).map(cell => cell.textContent.toLocaleLowerCase()).join(' ');
    row.hidden = !key.includes(query) || (qualified.checked && row.dataset.qualifies !== 'yes');
  }}
}}
filter.addEventListener('input', update);
qualified.addEventListener('change', update);
</script>
</html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path, nargs='+')
    parser.add_argument('--archive', type=Path, action='append', default=[], help='Reviewed critic evidence JSON (repeatable)')
    parser.add_argument('--indexes', type=Path, help='Public sitemap output from research_sitemaps.py')
    parser.add_argument('--rates', type=Path, required=True, help='CBR daily XML')
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--html', type=Path)
    parser.add_argument('--plan', type=Path, help='Write a package for Chrome to search every listed wine')
    args = parser.parse_args()
    bundles = [load(path) for path in args.captures]
    rate_date, rates = parse_rates(args.rates.read_bytes())
    date = max((moscow_date(row['observed_at']) for b in bundles for row in capture_rows(b)
                if retailer_host(row) in RETAILERS), default=rate_date)
    if rate_date > date:
        parser.error('the exchange rate was not effective on the observation date')
    archive = [row for path in args.archive for row in load(path)['observations']]
    index = load(args.indexes) if args.indexes else None
    if index and (index.get('kind'), index.get('version')) != ('wine_atlas_retailer_index', 1):
        parser.error('unsupported retailer index format')
    matrix = build_matrix(bundles, load(ROOT / 'data/research-aliases.json'), rates, date, archive, index)
    write(args.json, matrix)
    if args.html:
        args.html.write_text(render_html(matrix), encoding='utf-8')
    if args.plan:
        write(args.plan, search_plan(matrix))
    print(f"Wines: {len(matrix['wines'])}. Pair statuses: {matrix['pair_status_counts']}")


if __name__ == '__main__':
    main()
