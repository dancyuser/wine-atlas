#!/usr/bin/env python3
"""Validate the catalog contract and preservation against the frozen input."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]


def date(value):
    assert isinstance(value,str) and dt.date.fromisoformat(value).isoformat()==value, value
    assert value <= dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date().isoformat(), value


def validate(data, baseline=None):
    assert data['region']=='Санкт-Петербург'
    date(data['updated_at'])
    records=data['records']
    assert records and len(records)==len({r['id'] for r in records}), 'Duplicate/missing IDs'
    urls=set()
    for r in records:
        assert r['type'] in ('Красное','Белое','Розовое','Игристое','Оранжевое','Портвейн','Не установлен')
        assert isinstance(r['title'],str) and 0<len(r['title'])<230
        assert isinstance(r['description'],str)
        for field in ('grapes','pairings'):
            assert isinstance(r[field],list) and all(isinstance(x,str) and x for x in r[field])
            assert len(r[field])==len(set(r[field]))
        assert r['year'] is None or type(r['year']) is int and 1900<=r['year']<=2100
        assert r['volume_l'] is None or type(r['volume_l']) in (int,float) and math.isfinite(r['volume_l']) and 0<r['volume_l']<=30
        assert type(r['wishlist']) is bool and type(r['research']) is bool
        assert r['stores'] and r['section']!='Джин'
        for store in r['stores']:
            url=store['url']
            p=urlsplit(url)
            assert p.scheme=='https' and p.hostname,url
            key=(p.hostname.lower(),p.path.rstrip('/').lower(),p.query)
            assert key not in urls,'Duplicate retailer URL: '+url
            urls.add(key)
            for f,tf in (('price_rub','price_checked_at'),('reference_price_rub','reference_date')):
                value=store[f]
                if value is not None:
                    assert type(value) is int and 100<=value<=1000000,(r['id'],f,value)
                    date(store[tf])
            for f,pf in (('regular_price_rub','price_rub'),('reference_regular_price_rub','reference_price_rub')):
                value=store[f]
                if value is not None:
                    assert type(value) is int and store[pf] is not None and store[pf]<value<=1000000
            details=store.get('product_details')
            if details:
                assert details['source_url']==url
                date(details['checked_at'])
                assert details['full_name'] and details['producer'] and details['identity_evidence']
                if r['year'] is not None:assert details['vintage']==r['year']
                if r['volume_l'] is not None:assert details['volume_l']==r['volume_l']
                assert details['availability_spb'] is None or type(details['availability_spb']) is bool
                for field in ('alcohol_percent','volume_l'):
                    value=details.get(field)
                    assert value is None or type(value) in (int,float) and math.isfinite(value) and value>0
                if details.get('image_usage_allowed'):
                    assert details.get('image_permission_source') and details.get('image_url')
                if store['price_rub'] is not None:assert store.get('price_source_url')==url
    if baseline:
        before={r['id']:r for r in baseline['records']}
        after={r['id']:r for r in records}
        assert len(after)>=len(before) and before.keys()<=after.keys(),'Wine entries lost'
        for ident,old in before.items():
            new=after[ident]
            for field in ('title','year','section','type','grapes','pairings','description','wishlist','research'):
                assert new[field]==old[field],(ident,'source annotation changed',field)
            for field in ('country','volume_l'):
                if old[field] is not None: assert new[field]==old[field],(ident,field)
            old_stores={s['url']:s for s in old['stores']}
            new_stores={s['url']:s for s in new['stores']}
            assert old_stores.keys()<=new_stores.keys(),(ident,'store URL lost')
            for url,store in old_stores.items():
                for f in ('reference_price_rub','reference_regular_price_rub','reference_date'):
                    assert new_stores[url][f]==store[f],(ident,'historical data changed',f)
    return len(records),len(urls)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--catalog',type=Path,default=ROOT/'data/wines.json')
    ap.add_argument('--baseline',type=Path,default=ROOT/'data/backups/wines.before-winestyle-2026-11-22.json')
    args=ap.parse_args()
    baseline=json.loads(args.baseline.read_text(encoding='utf-8')) if args.baseline.exists() else None
    counts=validate(json.loads(args.catalog.read_text(encoding='utf-8')),baseline)
    print('VALIDATED',counts[0],'unique wines;',counts[1],'retailer links; baseline preservation:',bool(baseline))


if __name__=='__main__':main()
