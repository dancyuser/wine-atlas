#!/usr/bin/env python3
"""Summarize browser research observations; never change the catalog."""
import argparse
import collections
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from import_research import parse_offer, year_in
from stage_critic_research import browser_observations


SIMPLEWINE_CRITICS = {
    'JS': ('James Suckling', 'jamessuckling.com', 100),
    'RP': ('Robert Parker Wine Advocate', 'robertparker.com', 100),
    'WS': ('Wine Spectator', 'winespectator.com', 100),
    'WE': ('Wine Enthusiast', 'wineenthusiast.com', 100),
    'DECANTER': ('Decanter', 'decanter.com', 100),
    'FALSTAFF': ('Falstaff', 'falstaff.com', 100),
    'VINOUS': ('Vinous', 'vinous.com', 100),
    'JANCIS ROBINSON': ('Jancis Robinson', 'jancisrobinson.com', 20),
}
EXPERT_RATING = re.compile(r'\b(' + '|'.join(map(re.escape, SIMPLEWINE_CRITICS))
                          + r')\s+(\d{2,3}(?:[.,]\d+)?)(?![\d.,])', re.I)


def simplewine_hints(row):
    """Return storefront claims for publisher lookup, without promoting them to ratings."""
    url = urlsplit(row.get('url') or '')
    if ((url.hostname or '').removeprefix('www.') != 'simplewine.ru' or
            not url.path.startswith('/catalog/product/') or row.get('status') != 'needs_review'):
        return None
    requested = urlsplit(row.get('requested_url') or row['url'])
    if (requested.netloc, requested.path.rstrip('/')) != (url.netloc, url.path.rstrip('/')):
        return None
    title = row.get('title', '')
    year = year_in(title)
    if not year:
        return None
    blocks = row.get('blocks', {})
    text = blocks.get('critic_hints')
    if not text:
        _, _, tail = blocks.get('product', '').partition('Рейтинги экспертов\n')
        text = re.split(r'(?mi)^(?:Особенности|Мнение эксперта|Отзывы|Характеристики|Гастрономия)\s*$',
                        '\n'.join(tail.splitlines()[:24]), maxsplit=1)[0]
    claims = {}
    lookup_title = re.sub(r'^(?:Игристое )?Вино\s+', '', title, flags=re.I)
    for label, mark in EXPERT_RATING.findall(text):
        source, domain, scale = SIMPLEWINE_CRITICS[label.upper()]
        score = float(mark.replace(',', '.'))
        if 85 <= score * 100 / scale <= 100:
            lookup = f'{lookup_title} site:{domain}'
            claims[source, score] = {'source': source, 'score': score, 'scale': scale, 'primary_query': lookup}
    if not claims:
        return None
    offer = parse_offer(row, 'simplewine.ru')
    return {'title': title, 'year': year, 'retailer_url': row['url'],
            'selected_city': blocks.get('city'), 'local_price_rub': offer['price'] if offer else None,
            'status': 'needs_primary_review', 'reported_ratings': list(claims.values())}


def report(bundle):
    if bundle.get('kind') != 'wine_atlas_research_capture' or bundle.get('version') != 1:
        raise ValueError('unsupported capture format')
    rows = bundle.get('observations')
    if not isinstance(rows, list):
        raise ValueError('observations must be a list')
    grouped = collections.defaultdict(collections.Counter)
    coverage = collections.defaultdict(collections.Counter)
    hints = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('observation must be an object')
        url = row.get('url') or ''
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('invalid observation URL')
        source = row.get('source') or parsed.hostname
        grouped[source][row.get('status') or 'unknown'] += 1
        if row.get('blocks', {}).get('review'):
            coverage[source]['pages_with_review_block'] += 1
        if limits := row.get('discovery'):
            counts = coverage[source]
            counts['catalog_pages_with_link_counts'] += 1
            counts['visible_detail_links'] += limits['visible_details']
            counts['detail_links_queued'] += limits['queued_details']
            counts['next_pages_queued'] += int(limits['next_queued'])
            counts['catalog_pages_hitting_detail_limit'] += int(limits['eligible_details'] > limits['detail_limit'])
            counts['catalog_pages_hitting_pagination_limit'] += int(limits['next_found'] and not limits['next_queued'])
        if hint := simplewine_hints(row):
            hints[(hint['retailer_url'], hint['year'])] = hint
    for row in browser_observations(bundle, {}):
        counts = coverage[row['source']]
        counts['parsed_numeric_ratings'] += int(row.get('score') is not None and 0 < row['score'] <= row['scale'])
        counts['parsed_drinking_windows'] += int(row.get('end') is not None)
    return {'observations': len(rows), 'sources': dict(grouped),
            'coverage': {source: dict(coverage[source]) for source in grouped},
            'retailer_rating_leads': list(hints.values()),
            'catalog_updates': 0,
            'note': 'Unverified browser excerpts are candidates, not validated wine, price, stock or drinking windows.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    data = json.loads(args.capture.read_text(encoding='utf-8'))
    print(json.dumps(report(data), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
