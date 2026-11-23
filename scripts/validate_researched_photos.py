#!/usr/bin/env python3
"""Check sourced fallback photos are safe and cover only exact-capture gaps."""
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
wines=json.loads((ROOT/'data/wines.json').read_text(encoding='utf-8'))
main=json.loads((ROOT/'data/verified-snapshot-2026-11-23.json').read_text(encoding='utf-8'))
photos=json.loads((ROOT/'data/researched-photos-2026-11-23.json').read_text(encoding='utf-8'))
assert photos['version']==1
ids={r['id']:r for r in wines['records']}
assert len(photos['records'])==8
for id_,p in photos['records'].items():
    assert id_ in ids
    assert id_ not in main['records'], ('Unnecessary photo override',id_)
    assert ids[id_]['availability']['status']!='out_of_stock' if ids[id_].get('availability') else True
    assert p['year']==ids[id_]['year'], ('Wrong vintage',id_)
    assert p.get('source') and len(p.get('evidence',''))>=20
    for field in ('url','source_url'):
        u=urlsplit(p[field])
        assert u.scheme=='https' and u.hostname and not u.username and not u.password
print('PHOTO SOURCES VALIDATED',len(photos['records']))
