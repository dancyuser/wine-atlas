#!/usr/bin/env python3
"""Check the November vendor identity review, exact prices and critic coverage."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
wine=json.loads((root/'data/wines.json').read_text(encoding='utf-8'))
ratings=json.loads((root/'data/ratings.json').read_text(encoding='utf-8'))
snap=json.loads((root/'data/verified-snapshot-2026-11-23.json').read_text(encoding='utf-8'))['records']
review=json.loads((root/'data/archive/catalog-quality-audit-2026-11-23.json').read_text(encoding='utf-8'))
rows=wine['records']
by_id={r['id']:r for r in rows}
available=[r for r in rows if r.get('availability',{}).get('status')!='out_of_stock'
           and r.get('publication_review',{}).get('status')!='excluded']
assert len(rows)==124 and len(available)==110
assert len(review['reviewed_records'])==8
assert sum(r.get('publication_review',{}).get('status')=='verified' for r in rows)==2
assert sum(r.get('publication_review',{}).get('status')=='excluded' for r in rows)==6
assert not [r for r in available if r.get('type')=='Не установлен'], 'Unknown wine type still visible'
assert not [r for r in available if not r.get('country')], 'Missing country still visible'
prices=[]
for r in available:
 s=r['stores'][0]
 assert r['id'] in snap or s.get('price_rub') is not None or s.get('reference_price_rub') is not None,r['id']
 prices.append(r['id'])
assert len(prices)==110
for id_,price in [('c9f63273980c',3579),('060e3c866e44',6348)]:
 r=by_id[id_]
 assert r['publication_review']['status']=='verified'
 assert r['stores'][0]['price_rub']==price
 assert r['stores'][0]['price_checked_at']=='2026-11-23'
assert by_id['8433dbc66ae6']['publication_review']['reason']=='out_of_stock'
for id_ in ['d9a5af8ef749','28bf2f843af7','e3e9c91e71bc','ce214c07863d','3684c27c6d62']:
 assert by_id[id_]['publication_review']['status']=='excluded'
m=next(x for x in ratings['records']['6b16a51f5c8c'] if x['source']=='Vivino')
assert '/w/9317032' in m['source_url'] and m['score']==4.1
assert '10522915' not in m['source_url']
covered={}
for r in available:
 s=r['stores'][0]
 retail=s.get('enrichment_status',{}).get('status')=='verified' and s.get('product_details',{}).get('source_url')==s['url'] and any(
 x.get('source')!='Vivino' and x.get('scale') in (20,100) for x in s.get('product_details',{}).get('ratings',[]))
 independent=any(x.get('source')!='Vivino' and x.get('scale') in (20,100)
       and 'winestyle.ru' not in (x.get('source_url') or '') for x in ratings['records'][r['id']])
 covered[r['id']]=retail or independent
unrated={r['id'] for r in available if not covered[r['id']]}
assert unrated=={'5e980b14c4d5','6b16a51f5c8c'},unrated
print('PUBLICATION REVIEW VALIDATED: 110 visible, 110 priced, 6 excluded, 2 available ports, 108 with critic scores, 2 genuine gaps')
