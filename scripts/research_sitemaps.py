#!/usr/bin/env python3
"""Read public retailer sitemap indexes for candidate product URLs."""
import argparse
import gzip
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from import_research import https_url, normalized, write


STORE_ORIGINS = {
    'Винлаб': 'www.winelab.ru', 'Ароматный мир': 'amwine.ru', 'Vinissimo': 'vinissimo.biz',
    'Sabonis': 'sabonis.ru', 'WineStyle': 'spb.winestyle.ru', 'SimpleWine': 'simplewine.ru',
    'AST.WINE': 'ast.wine', 'Joia': 'joiastore.ru', 'Luding': 'spb.luding.ru',
}
PRODUCT_PATHS = {
    'Винлаб': r'/(?:catalog/)?product/[^/]+/?$',
    'Ароматный мир': r'/catalog/(?:product/[^/]+|vino/[^/]+_[^/]+)/?$',
    'Vinissimo': r'/catalog/wine/[^/]+-\d+/?$',
    'Sabonis': r'/productDetail/[^/]+/?$',
    'WineStyle': r'/products/[^/]+\.html$',
    'SimpleWine': r'/catalog/product/[^/]+/?$',
    'AST.WINE': r'/catalog/product/[^/]+/?$',
    'Joia': r'/product/[^/]+/?$',
    'Luding': r'/collection/item/[^/]+(?:/\d+)?/?$',
}
AGENT = 'WineAtlasResearch/1.0 (+https://github.com/dancyuser/wine-atlas)'
XLIMIT = 40000000
STOPS = frozenset(('wine wines vino vina wineatlas blanc blanco red rouge rosso white pinot noir reserva riserva '
                   'chardonnay cabernet sauvignon riesling tempranillo gran estate champagne classic '
                   'millesime vintage chateau domaine bodegas region rosado winery '
                   'napa valley russian river sonoma coast willamette chianti classico soave barolo barbaresco '
                   'docg bordeaux margaux late bottled port grand superiore doc doca aoc crianza').split())


def same_host(url, host):
    parts = https_url(url)
    return bool(parts and parts.netloc.lower() == host and not parts.query and not parts.fragment)


def sitemap_link(url, host):
    if same_host(url, host):
        return True
    parts = https_url(url)
    return bool(parts and host == parts.netloc == 'spb.winestyle.ru' and parts.path == '/sitemap.php'
                and not parts.fragment and re.fullmatch(r'data=prods&page=[1-9]\d*', parts.query))


def fetch(url, host):
    with urlopen(Request(url, headers={'User-Agent': AGENT}), timeout=20) as response:
        if not sitemap_link(response.geturl(), host):
            raise ValueError('other_host_or_parameters')
        data = response.read(XLIMIT + 1)
    if len(data) > XLIMIT:
        raise ValueError('file_too_large')
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=BytesIO(data)) as archive:
            data = archive.read(XLIMIT + 1)
        if len(data) > XLIMIT:
            raise ValueError('file_too_large_after_decompression')
    return data


def sitemap_urls(data):
    root = ET.fromstring(data)
    kind = root.tag.rsplit('}', 1)[-1]
    if kind not in ('urlset', 'sitemapindex'):
        raise ValueError('not_a_sitemap')
    return kind, [el.text.strip() for el in root.findall('./{*}*/{*}loc') if el.text]


def gather(store, max_files):
    host = STORE_ORIGINS[store]
    robot_url = f'https://{host}/robots.txt'
    try:
        rules = fetch(robot_url, host).decode('utf-8', errors='replace').splitlines()
    except (ValueError, OSError) as error:
        return {'status': 'unavailable', 'read': [], 'products': [], 'errors': [{'url': robot_url, 'reason': str(error)}]}
    robot = RobotFileParser()
    robot.parse(rules)
    declared = [line.split(':', 1)[1].strip() for line in rules if line.lower().startswith('sitemap:')]
    queue = deque(dict.fromkeys(url for url in declared if same_host(url, host) and 'image' not in url.lower()))
    crawled, read, errors, products = set(), [], [], set()
    delay = max(1, robot.crawl_delay(AGENT) or 0, robot.crawl_delay('*') or 0)
    last = time.monotonic()
    while queue and len(crawled) < max_files:
        url = queue.popleft()
        if url in crawled:
            continue
        crawled.add(url)
        if not robot.can_fetch(AGENT, url):
            errors.append({'url': url, 'reason': 'robots_disallowed'})
            continue
        try:
            time.sleep(max(0, last + delay - time.monotonic()))
            kind, urls = sitemap_urls(fetch(url, host))
            read.append(url)
            if kind == 'sitemapindex':
                queue.extend(link for link in urls if sitemap_link(link, host) and link not in crawled and 'image' not in link.lower())
            else:
                products.update(link for link in urls if same_host(link, host) and
                                re.fullmatch(PRODUCT_PATHS[store], urlsplit(link).path, re.I))
        except (ValueError, ET.ParseError, OSError) as error:
            errors.append({'url': url, 'reason': str(error)})
        finally:
            last = time.monotonic()
    status = 'limited' if queue or errors else 'read'
    return {'status': status if read else 'unavailable', 'read': read, 'products': sorted(products),
            'errors': errors, 'unread': len(set(queue) - crawled)}


def words(value):
    return {token for token in re.findall(r'[^\W\d_]{3,}', normalized(value)) if token not in STOPS}


def full_words(value):
    return set(re.findall(r'[^\W\d_]{3,}', normalized(value)))


def product_candidates(wines, index):
    result = defaultdict(list)
    named_counts = {}
    for store, store_data in index['stores'].items():
        if store not in STORE_ORIGINS:
            continue
        links, tokens = [], defaultdict(set)
        for link in store_data['products']:
            if not same_host(link, STORE_ORIGINS[store]):
                continue
            path = unquote(urlsplit(link).path)
            if not re.fullmatch(PRODUCT_PATHS[store], path, re.I):
                continue
            label = next(part for part in reversed(path.strip('/').split('/')) if not part.isdigit())
            terms = words(label)
            if not terms or (store == 'Винлаб' and path.split('/')[-1].isdigit()):
                continue
            number = len(links)
            links.append((link, terms, label, set(map(int, re.findall(r'\b(?:19|20)\d{2}\b', label)))))
            for word in terms:
                tokens[word].add(number)
        named_counts[store] = len(links)
        for wine in wines:
            terms = words(wine['title'])
            full = full_words(wine['title'])
            if not terms:
                continue
            possible = set().union(*(tokens[word] for word in terms))
            matches = []
            for number in possible:
                link, found, label, years = links[number]
                overlap = terms & found
                if len(overlap) < min(2, len(terms)) or len(overlap) / len(terms) < 0.6:
                    continue
                matches.append((len(overlap), wine['year'] in years, len(full & full_words(label)), -len(found - terms), link))
            result[wine['id'], store] = [record[-1] for record in sorted(matches, reverse=True)[:5]]
    return result, named_counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--files-per-store', type=int, default=18)
    args = parser.parse_args()
    if args.files_per_store < 1:
        parser.error('--files-per-store must be positive')
    with ThreadPoolExecutor(len(STORE_ORIGINS)) as pool:
        results = pool.map(gather, STORE_ORIGINS, [args.files_per_store] * len(STORE_ORIGINS))
        stores = dict(zip(STORE_ORIGINS, results))
    write(args.output, {'kind': 'wine_atlas_retailer_index', 'version': 1, 'stores': stores})
    for store, info in stores.items():
        print(store, info['status'], len(info['read']), len(info['products']), len(info['errors']))


if __name__ == '__main__':
    main()
