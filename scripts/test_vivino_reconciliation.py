#!/usr/bin/env python3
"""Offline regression of Vivino alias resolution and seller-reported fallback."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
catalog=json.loads((ROOT/'data/wines.json').read_text(encoding='utf-8'))
obj=json.loads((ROOT/'data/ratings.json').read_text(encoding='utf-8'))
audit=json.loads((ROOT/'data/archive/vivino-reconciliation-2026-11-23.json').read_text(encoding='utf-8'))
wines={w['id']:w for w in catalog['records']}
assert len(wines)==123
assert all(id_ in obj['records'] for id_ in wines) and not any(id_ in obj['unrated'] for id_ in wines),'All four old gaps must be researched'
for match in audit['matched_unrated']:
    id_=match['id']
    assert id_ in wines
    scores=[x for x in obj['records'][id_] if x['source']=='Vivino']
    assert len(scores)==1,(id_,scores)
    score=scores[0]
    assert score['score']==match['score']
    assert score['scope']==match['scope']
    assert score['source_url']==match['source']
    assert score['source_kind']=='vivino_primary_alias_verified'
    assert score['vintage']==wines[id_]['year'] if score['scope']=='vintage' else score['vintage'] is None
assert len(audit['matched_unrated'])==4
quoted=[]
for wine in wines.values():
    values=[x for s in wine['stores'] for x in (s.get('product_details',{}).get('ratings') or [])
            if x.get('source')=='Vivino' and x.get('reported_by')=='WineStyle']
    if values:
        assert len(values)==1
        quoted.append((wine,values[0]))
assert audit['wineStyle_vivino_display_observations']==33, 'The archived 124-item snapshot must remain immutable'
assert len(quoted)==32, 'Removing Myskhako reduces current retailer Vivino quotations by one'
matches=differences=0
for wine,v in quoted:
    direct=next(x for x in obj['records'][wine['id']] if x['source']=='Vivino')
    if abs(direct['score']-v['score'])<=.15:
        matches+=1
    else:
        differences+=1
        assert wine['id']=='f0c33d420f2f' and direct['score']==3.5 and v['score']==3.8
assert matches==31 and differences==1
print('VIVINO AUDIT VALIDATED: 123/123 resolved, 32 seller comparisons, 1 archived conflict')
