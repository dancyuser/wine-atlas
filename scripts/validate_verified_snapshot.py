#!/usr/bin/env python3
"""Check the compact photo/price overlay against the active wishlist."""
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / 'data/wines.json').read_text(encoding='utf-8'))
snapshot = json.loads((ROOT / 'data/verified-snapshot-2026-11-23.json').read_text(encoding='utf-8'))
assert snapshot['version'] == 1
assert re.fullmatch(r'[0-9a-f]{64}', snapshot['source_archive_sha256'])
assert snapshot['source_archive_sha256'] == '6a25aaf5b393b0e19c909cef7f44532b6bd6b65972c2c1bfa052bf78fe53f26e'
assert date.fromisoformat(snapshot['as_of']) <= date.today()
index = {r['id']: r for r in catalog['records']}
rows = snapshot['records']
assert len(rows) == 116, len(rows)
for id_, observation in rows.items():
    assert id_ in index
    wine = index[id_]
    assert len(observation) == 2
    price, image_id = observation
    assert type(price) is int and 100 <= price <= 1_000_000, (id_, price)
    assert isinstance(image_id, str) and re.fullmatch(r'[0-9]{4,6}', image_id), (id_, image_id)
    assert wine['stores'][0]['url'].startswith('https://spb.winestyle.ru/products/'), id_
    assert wine.get('year') is None or isinstance(wine['year'], int), id_

available = [r for r in catalog['records']
             if r.get('availability', {}).get('status') != 'out_of_stock']
matched = sum(r['id'] in rows for r in available)
assert matched == 108 and len(available) == 116, (matched, len(available))
print('VERIFIED SNAPSHOT:', len(rows), 'photo/price pairs,', matched, 'visible exact matches')
