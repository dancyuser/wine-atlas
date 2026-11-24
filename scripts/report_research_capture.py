#!/usr/bin/env python3
"""Summarize browser research observations; never change the catalog."""
import argparse
import collections
import json
from pathlib import Path
from urllib.parse import urlsplit


def report(bundle):
    if bundle.get('kind') != 'wine_atlas_research_capture' or bundle.get('version') != 1:
        raise ValueError('unsupported capture format')
    rows = bundle.get('observations')
    if not isinstance(rows, list):
        raise ValueError('observations must be a list')
    grouped = collections.defaultdict(collections.Counter)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('observation must be an object')
        url = row.get('url') or ''
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('invalid observation URL')
        grouped[row.get('source') or parsed.hostname][row.get('status') or 'unknown'] += 1
    return {'observations': len(rows), 'sources': dict(grouped),
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
