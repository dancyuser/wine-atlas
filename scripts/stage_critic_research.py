#!/usr/bin/env python3
"""Build an exact-vintage queue for retailer searches from public critic evidence."""
import argparse
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from import_research import ROOT, exchange, identity, load, parse_rates, parse_reviews, write


def botti_observations(row):
    yield from parse_reviews(row, 'botti.no')


def browser_observations(bundle, aliases):
    if bundle.get('kind') != 'wine_atlas_research_capture' or bundle.get('version') != 1:
        raise ValueError('unsupported browser capture format')
    for row in bundle['observations']:
        url = urlsplit(row.get('url') or '')
        requested = urlsplit(row.get('requested_url') or row.get('url') or '')
        host = (url.hostname or '').removeprefix('www.')
        if (row.get('status') != 'needs_review' or url.scheme != 'https' or
                (url.netloc, url.path.rstrip('/')) != (requested.netloc, requested.path.rstrip('/'))):
            continue
        if host == 'falstaff.com':
            review = row.get('blocks', {}).get('review', '')
            if re.search(r'\b(?:Apfel Frizzante|Entalkoholisierter Schaumwein)\b', review, re.I):
                continue
        for record in parse_reviews(row, host):
            if any(record[field] is not None for field in ('score', 'end', 'amount')):
                record['title'] = aliases.get(record['url'], record['title'])
                record['method'] = 'browser_extract'
                yield record


def stage(evidence, rate_date, rates):
    coverage = {row['source']: dict(row, records=0, scored_records=0, window_records=0,
                                  queue_records=0) for row in evidence['sources']}
    groups = defaultdict(list)
    seen = set()
    for record in evidence['observations']:
        url = urlsplit(record['url'])
        key = (record['source'], record['url'].rstrip('/'), record['title'], record['year'],
               record.get('score'), record.get('end'))
        if key in seen:
            continue
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError(f'Invalid source URL: {record["url"]}')
        seen.add(key)
        groups[identity(record['title'], record['year'])].append(record)
        source = coverage[record['source']]
        source['records'] += 1
        source['scored_records'] += record.get('score') is not None
        source['window_records'] += record.get('end') is not None

    queue = []
    for (_, year), rows in groups.items():
        ratings, windows, prices = [], [], []
        for row in rows:
            score, scale = row.get('score'), row.get('scale')
            if score is not None and scale in {20, 99, 100} and 0 < score <= scale:
                ratings.append(dict(row, score_100=float(Decimal(str(score)) * 100 / scale)))
            end, start = row.get('end'), row.get('start')
            if end is not None and year <= end and (start is None or year <= start <= end):
                windows.append(row)
            currency, amount = row.get('currency'), row.get('amount')
            if (currency in rates and amount and Decimal(str(amount)) > 0 and
                    row.get('price_kind') in {'exact', 'upper_bound'}):
                rub, rounded = exchange(amount, currency, rates)
                prices.append(dict(row, price_rub=rounded, within_budget=rub <= 6000))
        passing = [rating for rating in ratings if rating['score_100'] >= 85]
        long_lived = [window for window in windows if window['end'] >= 2027]
        affordable = [price for price in prices if price['within_budget']]
        issues = []
        if not passing:
            issues.append('below_score' if ratings else 'missing_score')
        if not long_lived:
            issues.append('window_ends_before_2027' if windows else 'missing_window')
        if not affordable:
            issues.append('over_budget' if any(p['price_kind'] == 'exact' for p in prices)
                          else 'missing_qualifying_price')
        if not issues:
            for source in {row['source'] for row in passing + long_lived + affordable}:
                coverage[source]['queue_records'] += 1
        queue.append({
            'title': rows[0]['title'], 'year': year, 'status': 'pending_evidence' if issues else 'ready_for_retailer_search',
            'issues': issues, 'ratings': sorted(ratings, key=lambda row: -row['score_100']),
            'windows': sorted(windows, key=lambda row: (row['end'], row['url'])),
            'prices': sorted(prices, key=lambda row: row['price_rub']), 'evidence': rows,
        })
    queue.sort(key=lambda row: (row['status'] != 'ready_for_retailer_search', row['title'].casefold(), row['year']))
    return {
        'kind': 'wine_atlas_critic_queue', 'version': 1,
        'observed_on': evidence['observed_on'], 'rate_date': rate_date,
        'rate_source_url': 'https://www.cbr.ru/currency_base/daily/',
        'sources': list(coverage.values()), 'vintages_total': len(queue),
        'status_counts': dict(Counter(row['status'] for row in queue)),
        'issue_counts': dict(Counter(issue for row in queue for issue in row['issues'])),
        'vintages': queue,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--rates', type=Path, required=True, help='Bank of Russia daily XML')
    parser.add_argument('--capture', type=Path, action='append', default=[])
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    evidence = load(args.evidence)
    aliases = load(ROOT / 'data/research-aliases.json')
    for path in args.capture:
        evidence['observations'].extend(browser_observations(load(path), aliases))
    rate_date, rates = parse_rates(args.rates.read_bytes())
    if rate_date > evidence['observed_on']:
        parser.error('exchange rate was not effective on the observation date')
    report = stage(evidence, rate_date, rates)
    write(args.report, report)
    print(report['status_counts'])


if __name__ == '__main__':
    main()
