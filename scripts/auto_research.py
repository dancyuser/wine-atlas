#!/usr/bin/env python3
"""Collect vintage-specific Wine Enthusiast reviews and search SPb retailers.

Read-only crawler. It writes observations and an explicit error report, never a
catalog change. Example: python scripts/auto_research.py --limit 50 --output research.json
"""
import argparse
import datetime as dt
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

AGENT = 'WineAtlasResearch/1.0 (+https://github.com/dancyuser/wine-atlas)'
CRITIC = 'www.wineenthusiast.com'
SEEDS = ['https://www.wineenthusiast.com/wine-ratings/']
RETAILER_SEEDS = {
    'winelab.ru':'https://www.winelab.ru/catalog/vino',
    'amwine.ru':'https://amwine.ru/catalog/vino/',
    'vinissimo.biz':'https://vinissimo.biz/catalog/wine/',
    'sabonis.ru':'https://sabonis.ru/catalog/vino',
    'spb.winestyle.ru':'https://spb.winestyle.ru/wine/',
    'simplewine.ru':'https://simplewine.ru/catalog/vino/',
    'ast.wine':'https://ast.wine/catalog/vino/',
    'joia.ru':'https://joia.ru/catalog/vino/',
    'spb.luding.ru':'https://spb.luding.ru/collection/wine/',
}
STOP = {'wine','wines','vino','bodegas','bodega','winery','red','white',
        'tempranillo','garnacha','merlot','cabernet','sauvignon','chardonnay',
        'pinot','rioja','spain','france','italy','doc','doca','the','and','de','la'}


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))


def tokens(text):
    return {w for w in re.findall(r'[a-z0-9]+', normalized(text))
            if len(w) >= 3 and not w.isdigit() and w not in STOP}


def parse_review(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.select('script,style,nav,footer,aside'):
        tag.decompose()
    heading = soup.find('h1')
    if not heading:
        return None
    name = heading.get_text(' ', strip=True)
    year = re.search(r'(?<!\d)((?:19|20)\d{2})(?!\d)', name)
    text = soup.get_text('\n', strip=True).split('What Is Blind Tasting?')[0]
    rating = re.search(r'\bRating\s+(\d{2,3})\b', text, re.I)
    price = re.search(r'\bPrice\s+\$\s*(\d+(?:\.\d{1,2})?)', text, re.I)
    end = re.search(r'\b(?:drink|drinking|enjoy|best)[^.!?\n]{0,70}?(?:through|until|to|[-–—])\s*((?:20)\d{2})\b', text, re.I)
    if not (year and rating and price and end):
        return None
    score, year, end_year = int(rating.group(1)), int(year.group(1)), int(end.group(1))
    if not 85 <= score <= 100 or end_year < 2027:
        return None
    return {'name': name, 'year': year, 'score': score, 'scale': 100,
            'critic': 'Wine Enthusiast', 'critic_url': url,
            'foreign_price': float(price.group(1)), 'currency': 'USD',
            'drink_until': end_year, 'window_url': url}


def extract_links(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    found = []
    for a in soup.select('a[href]'):
        url = urllib.parse.urljoin(base, a.get('href'))
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname == CRITIC and parsed.path.startswith('/buying-guide/'):
            found.append(urllib.parse.urlunsplit(('https', parsed.netloc, parsed.path, '', '')))
    return list(dict.fromkeys(found))


def parse_search_rss(xml, domain):
    root = ET.fromstring(xml)
    result = []
    for item in root.findall('.//item'):
        url = item.findtext('link', '')
        host = urllib.parse.urlsplit(url).hostname or ''
        if host == domain or host.endswith('.' + domain):
            result.append(url)
    return list(dict.fromkeys(result))


def retailer_page_links(html, base):
    """Extract only visible catalog anchors; pagination and products separately."""
    soup = BeautifulSoup(html, 'html.parser')
    products, pages = {}, []
    original = urllib.parse.urlsplit(base)
    for a in soup.select('a[href]'):
        url = urllib.parse.urljoin(base, a.get('href'))
        p = urllib.parse.urlsplit(url)
        if p.scheme != 'https' or p.hostname != original.hostname:
            continue
        label = a.get_text(' ', strip=True)
        if not label:
            label = ' '.join((img.get('alt') or '') for img in a.select('img'))
        if re.search(r'/(?:product|products|productDetail)/', p.path, re.I) or (
                'vinissimo.biz' in p.hostname and '/catalog/wine/' in p.path and re.search(r'-\d+/?$', p.path)):
            products[url] = label + ' ' + urllib.parse.unquote(p.path).replace('_', ' ').replace('-', ' ')
        elif re.search(r'(?:page|pagen_\d+)=\d+', p.query, re.I):
            pages.append(url)
    return products, list(dict.fromkeys(pages))


def inspect_offer(html, url, review):
    soup = BeautifulSoup(html, 'html.parser')
    for t in soup.select('script,style,nav,footer,aside'):
        t.decompose()
    h = soup.find('h1')
    if not h:
        return None, 'no_product_heading'
    title_tag = soup.find('title')
    title = h.get_text(' ', strip=True) + ' ' + (title_tag.get_text(' ', strip=True) if title_tag else '')
    text = soup.get_text(' ', strip=True)
    text = re.split(r'Рекомендованные товары|Похожие товары|Вина в похожем стиле', text, flags=re.I)[0]
    # Year must belong to the main heading/title, not the recommendations.
    if not re.search(r'(?<!\d)' + str(review['year']) + r'(?!\d)', title):
        return None, 'vintage_not_in_heading'
    expected = tokens(review['name'])
    observed = tokens(title + ' ' + text[:1500])
    common = expected & observed
    # Multiple distinctive identity tokens required; do not assign generic varietal scores.
    if len(common) < 3 or len(common) / max(1, len(expected)) < 0.6:
        return None, 'identity_not_confirmed'
    if not re.search(r'(?:0[,.]75\s*(?:л|l)|750\s*(?:мл|ml))', title + ' ' + text[:1800], re.I):
        return None, 'volume_not_confirmed'
    host = urllib.parse.urlsplit(url).hostname or ''
    if 'sabonis.ru' not in host and not re.search(r'Санкт-Петербург|Санкт.Петербург|\bСПб\b', text[:2500], re.I) and not host.startswith('spb.'):
        return None, 'spb_not_confirmed'
    if re.search(r'нет в наличии|товар отсутствует|ожидаем поступление', text[:2500], re.I):
        return None, 'stock_unknown_or_unavailable'
    # Luding supplier inventory is eligible when the site explicitly shows SPb.
    # It is kept as a candidate until a source-specific price and identity check.
    supplier = ('luding.ru' in host and
                re.search(r'в\s+наличии\s+у\s+поставщика', text[:2500], re.I) and
                re.search(r'Санкт-Петербург|Санкт.Петербург|\bСПб\b', text[:2500], re.I))
    if ('luding.ru' in host and re.search(r'в\s+наличии\s+у\s+поставщика', text[:2500], re.I)
            and not supplier):
        return None, 'spb_not_confirmed'
    if not supplier and not re.search(r'\bв наличии\b|забрать сегодня|наличие\s*:', text[:2500], re.I):
        return None, 'stock_not_confirmed'
    # A conditional/ambiguous price is a research result, not an offer.
    return {'url': url, 'matched_tokens': sorted(common), 'year': review['year'],
            'status': 'needs_price_and_stock_verification'}, 'candidate'


class Fetcher:
    def __init__(self):
        self.robots = {}
        self.last = defaultdict(float)
        self.errors = []

    def get(self, url):
        p = urllib.parse.urlsplit(url)
        origin = p.scheme + '://' + p.netloc
        if p.scheme != 'https' or p.username or p.password:
            raise ValueError('unsafe URL')
        if origin not in self.robots:
            robots = urllib.robotparser.RobotFileParser(origin + '/robots.txt')
            try:
                req = urllib.request.Request(origin + '/robots.txt', headers={'User-Agent': AGENT})
                with urllib.request.urlopen(req, timeout=20) as res:
                    robots.parse(res.read(500000).decode('utf-8', 'replace').splitlines())
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    robots.parse([])
                else:
                    raise RuntimeError('robots_unavailable: ' + str(exc)) from exc
            except Exception as exc:
                raise RuntimeError('robots_unavailable: ' + str(exc)) from exc
            self.robots[origin] = robots
        robots = self.robots[origin]
        if not robots.can_fetch(AGENT, url):
            raise RuntimeError('robots_disallowed')
        delay = max(5, robots.crawl_delay(AGENT) or robots.crawl_delay('*') or 0)
        time.sleep(max(0, self.last[origin] + delay - time.monotonic()))
        req = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept':'text/html,application/xml,text/xml,*/*'})
        try:
            with urllib.request.urlopen(req, timeout=25) as res:
                final = urllib.parse.urlsplit(res.geturl())
                if final.hostname != p.hostname:
                    raise RuntimeError('cross_host_redirect')
                data = res.read(12_000_001)
                if len(data) > 12_000_000:
                    raise RuntimeError('response_too_large')
                return data.decode('utf-8', 'replace')
        finally:
            self.last[origin] = time.monotonic()

    def safe_get(self, url):
        try:
            return self.get(url)
        except Exception as exc:
            self.errors.append({'url':url, 'error':str(exc)})
            return None


def research_retailer(seed, limit, reviews):
    fetch = Fetcher()
    queue, visited, products = [seed], set(), {}
    while queue and len(visited) < limit:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        page = fetch.safe_get(url)
        if page:
            found, next_pages = retailer_page_links(page, url)
            products.update(found)
            queue.extend(page_url for page_url in next_pages if page_url not in visited)

    results = []
    for review in reviews:
        expected = tokens(review['name'])
        for url, label in products.items():
            if len(expected & tokens(label)) < 2:
                continue
            page = fetch.safe_get(url)
            if not page:
                continue
            candidate, reason = inspect_offer(page, url, review)
            if candidate:
                results.append({'review': review, 'offer': candidate})
            elif reason not in ('identity_not_confirmed', 'vintage_not_in_heading'):
                fetch.errors.append({'url': url, 'error': reason})
    return len(products), results, fetch.errors


def research_retailers(reviews, limit):
    with ThreadPoolExecutor(max_workers=len(RETAILER_SEEDS)) as pool:
        jobs = {domain: pool.submit(research_retailer, seed, limit, reviews)
                for domain, seed in RETAILER_SEEDS.items()}
        return {domain: job.result() for domain, job in jobs.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--limit', type=int, default=50, help='maximum critic review pages')
    p.add_argument('--retailer-pages', type=int, default=5, help='maximum catalog pages per retailer')
    p.add_argument('--output', default='wine-research.json')
    args = p.parse_args()
    if args.limit < 1 or args.retailer_pages < 1:
        p.error('--limit and --retailer-pages must be positive')
    fetch = Fetcher()
    reviews, links, results = [], [], []
    for seed in SEEDS:
        html = fetch.safe_get(seed)
        if html:
            links.extend(extract_links(html, seed))
    # Follow review-to-review links as a bounded queue. The initial page itself
    # supplies recent reviews; no model or manually supplied wine list needed.
    seen = set()
    while links and len(seen) < args.limit:
        url = links.pop(0)
        if url in seen:
            continue
        seen.add(url)
        html = fetch.safe_get(url)
        if not html:
            continue
        links.extend(x for x in extract_links(html, url) if x not in seen)
        review = parse_review(html, url)
        if review:
            reviews.append(review)
    # Currency rates are tied to a date and denomination, not a hard-coded rate.
    rate_xml = fetch.safe_get('https://www.cbr.ru/scripts/XML_daily.asp')
    rate = None
    if rate_xml:
        try:
            root = ET.fromstring(rate_xml)
            usd = next(n for n in root.findall('Valute') if n.findtext('CharCode') == 'USD')
            rate = float(usd.findtext('Value').replace(',', '.')) / int(usd.findtext('Nominal'))
            rate_date = dt.datetime.strptime(root.attrib['Date'], '%d.%m.%Y').date().isoformat()
        except Exception as exc:
            fetch.errors.append({'url':'https://www.cbr.ru/scripts/XML_daily.asp','error':'invalid_rate: '+str(exc)})
    priced_reviews = []
    for review in reviews:
        if rate is None or review['foreign_price'] * rate > 6000:
            continue
        review['rate_rub'], review['rate_date'] = rate, rate_date
        priced_reviews.append(review)
    indexed = {}
    for domain, (products, candidates, errors) in research_retailers(priced_reviews, args.retailer_pages).items():
        indexed[domain] = products
        results.extend(candidates)
        fetch.errors.extend(errors)
    output = {'version':1, 'run_at':dt.datetime.now(dt.timezone.utc).isoformat(),
              'review_pages_attempted':len(seen), 'qualifying_reviews':len(reviews),
              'retailer_products_indexed':indexed,
              'candidates':results, 'errors':fetch.errors,
              'note':'Candidates require current exact price, SPb inventory and catalog validation before publication.'}
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print('review_pages=', len(seen), 'qualifying=', len(reviews), 'candidates=', len(results), 'errors=', len(fetch.errors))
    return 0 if seen else 2


if __name__ == '__main__':
    raise SystemExit(main())
