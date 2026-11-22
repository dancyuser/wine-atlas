#!/usr/bin/env python3
"""Static data contract checks (no network required)."""
import json,re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
p=Path(__file__).resolve().parents[1]/'data'/'wines.json'
d=json.loads(p.read_text(encoding='utf-8'))
assert d['region']=='Санкт-Петербург'
records=d['records']
assert records and len(records)==len({r['id'] for r in records})
assert all(r['type'] in ('Красное','Белое','Розовое','Игристое','Оранжевое','Портвейн','Не установлен') for r in records)
urls=[]
for r in records:
 assert r['title'] and len(r['title'])<230,r
 assert not re.search(r'(?<!\\d)\\d{5,}(?!\\d)',r['title']), 'SKU/EAN in title: '+r['title']
 assert not re.search(r'(?:^|\\s)(?:075|375|750|1500)
 assert isinstance(r['pairings'],list)
 assert isinstance(r['grapes'],list)
 assert r['stores']
 assert not (r['section']=='Джин')
 for store in r['stores']:
  url=store['url']
  assert urlsplit(url).scheme=='https' and urlsplit(url).hostname,url
  assert not url.split('#')[0] in urls, 'Duplicate store URL: '+url
  urls.append(url.split('#')[0])
  for f,tf in (('price_rub','price_checked_at'),('reference_price_rub','reference_date')):
   if store[f] is not None:
    assert isinstance(store[f],int) and store[f]>0
    assert store[tf] and re.fullmatch(r'\d{4}-\d{2}-\d{2}',store[tf])
  if store['regular_price_rub'] is not None:
   assert store['price_rub'] is not None and store['regular_price_rub']>store['price_rub']
  if store['reference_regular_price_rub'] is not None:
   assert store['reference_price_rub'] is not None and store['reference_regular_price_rub']>store['reference_price_rub']
assert len(records)==d['source']['unique_wine_urls'], 'Catalog size differs from source snapshot'
assert all(r['wishlist'] and not r['research'] for r in records), 'Archived research cannot appear in active catalog'
assert not any(r['section']=='Джин' for r in records)
assert len(records)>0
print('VALIDATED',len(records),'unique wine entries',len(urls),'retailer links', 'countries=',len({r['country'] for r in records if r['country']}))
,r['title']), 'Bottle volume in title: '+r['title']
 assert r['title']!=r['title'].lower(), 'Title must use proper capitalization: '+r['title']
 assert r['year'] is None or not re.search(r'(?<!\\d)'+str(r['year'])+r'(?!\\d)',r['title']), 'Vintage duplicated in title: '+r['title']
 assert isinstance(r['pairings'],list)
 assert isinstance(r['grapes'],list)
 assert r['stores']
 assert not (r['section']=='Джин')
 for store in r['stores']:
  url=store['url']
  assert urlsplit(url).scheme=='https' and urlsplit(url).hostname,url
  assert not url.split('#')[0] in urls, 'Duplicate store URL: '+url
  urls.append(url.split('#')[0])
  for f,tf in (('price_rub','price_checked_at'),('reference_price_rub','reference_date')):
   if store[f] is not None:
    assert isinstance(store[f],int) and store[f]>0
    assert store[tf] and re.fullmatch(r'\d{4}-\d{2}-\d{2}',store[tf])
  if store['regular_price_rub'] is not None:
   assert store['price_rub'] is not None and store['regular_price_rub']>store['price_rub']
  if store['reference_regular_price_rub'] is not None:
   assert store['reference_price_rub'] is not None and store['reference_regular_price_rub']>store['reference_price_rub']
assert len(records)==d['source']['unique_wine_urls'], 'Catalog size differs from source snapshot'
assert all(r['wishlist'] and not r['research'] for r in records), 'Archived research cannot appear in active catalog'
assert not any(r['section']=='Джин' for r in records)
assert len(records)>0
print('VALIDATED',len(records),'unique wine entries',len(urls),'retailer links', 'countries=',len({r['country'] for r in records if r['country']}))
