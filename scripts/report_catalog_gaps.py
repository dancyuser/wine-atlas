#!/usr/bin/env python3
"""Report all visible catalog gaps after merging verified page snapshots.

Usage: python scripts/report_catalog_gaps.py [--output /tmp/wine-gaps.json]
Unknown identity and missing observations remain gaps: never infer availability
or copy prices/photos from redirected products.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report():
    c = json.loads((ROOT / 'data/wines.json').read_text(encoding='utf-8'))
    independent = json.loads((ROOT / 'data/ratings.json').read_text(encoding='utf-8'))
    snapshot = json.loads((ROOT / 'data/verified-snapshot-2026-11-23.json').read_text(encoding='utf-8'))
    verified = snapshot['records']
    researched = json.loads((ROOT / 'data/researched-photos-2026-11-23.json').read_text(encoding='utf-8'))['records']
    visible = [r for r in c['records'] if r.get('availability', {}).get('status') != 'out_of_stock']
    missing = []
    totals = {'visible': len(visible), 'snapshot_price_and_photo': 0,
              'missing_price': 0, 'missing_photo': 0,
              'missing_vivino': 0, 'missing_critic': 0}
    for r in visible:
        s = r['stores'][0]
        x = verified.get(r['id'])
        if x:
            totals['snapshot_price_and_photo'] += 1
        has_price = bool(x or s.get('price_rub') is not None or s.get('reference_price_rub') is not None)
        has_photo = bool(x or researched.get(r['id'], {}).get('url') or r.get('photo', {}).get('url'))
        has_vivino = any(y.get('source') == 'Vivino'
                         for y in independent['records'].get(r['id'], []))
        has_critic = any(y.get('scale') in (20, 100) and y.get('source') != 'Vivino'
                         for y in s.get('product_details', {}).get('ratings', [])) or any(
                         y.get('scale') == 100 and y.get('source') != 'Vivino'
                         for y in independent['records'].get(r['id'], []))
        gaps = [name for name, exists in [('price', has_price),
                  ('photo', has_photo), ('vivino', has_vivino), ('critic', has_critic)]
                if not exists]
        for key in gaps:
            totals['missing_' + key] += 1
        if gaps:
            missing.append({'id': r['id'], 'title': r['title'], 'vintage': r.get('year'),
                            'source_url': s['url'], 'gaps': gaps,
                            'identity_verified_in_archive': r['id'] in verified})
    return {'as_of': snapshot['as_of'], 'totals': totals, 'gaps': missing}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    o = report()
    output = json.dumps(o, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
