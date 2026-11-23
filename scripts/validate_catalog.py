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
 assert not re.search(r'(?<!\d)\d{5,}(?!\d)',r['title']), 'SKU/EAN in title: '+r['title']
 assert not re.search(r'(?:^|\s)(?:075|375|750|1500)$',r['title']), 'Bottle volume in title: '+r['title']
 assert r['title']!=r['title'].lower(), 'Title must use proper capitalization: '+r['title']
 assert r['year'] is None or not re.search(r'(?<!\d)'+str(r['year'])+r'(?!\d)',r['title']), 'Vintage duplicated in title: '+r['title']
 assert isinstance(r['pairings'],list)
 assert isinstance(r['grapes'],list)
 photo=r.get('photo')
 if photo:
  assert r['year'] is not None and photo.get('matched_year')==r['year'],('Photo vintage mismatch',r['id'])
  assert photo.get('url','').startswith('https://'),('Invalid photo URL',r['id'])
  assert photo.get('source_url','').startswith('https://'),('Invalid photo source',r['id'])
  assert photo.get('source') and photo.get('verified_on'),('Missing photo provenance',r['id'])
 stock=r.get('availability')
 if stock is not None:
  assert stock['status'] in ('in_stock','out_of_stock'), (r['id'],stock)
  assert stock.get('source_url') in {s['url'] for s in r['stores']},r['id']
  assert re.fullmatch(r'\d{4}-\d{2}-\d{2}',stock['observed_on']),r['id']
  assert stock.get('evidence') and stock.get('snapshot_source'),r['id']
 review=r.get('publication_review')
 if review:
  assert review['status'] in ('verified','excluded'),(r['id'],review)
  assert review['checked_at'] and re.fullmatch(r'\d{4}-\d{2}-\d{2}',review['checked_at'])
  assert review['source_url'].split('#')[0].rstrip('/') in {s['url'].split('#')[0].rstrip('/') for s in r['stores']}, (r['id'],review['source_url'])
  assert re.fullmatch(r'[0-9a-f]{64}',review['source_snapshot_sha256'])
  assert review['reason'] and review['evidence'] and review['final_url'],r['id']
  assert review['year']==r['year'],r['id']
  if review['status']=='excluded':
   assert review['reason'] in ('out_of_stock','redirect_vintage_mismatch','redirect_vintage_and_volume_mismatch')

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
snapshot=d.get('inventory_snapshot')
if snapshot:
 assert re.fullmatch(r'[0-9a-f]{64}',snapshot['archive_sha256'])
 assert re.fullmatch(r'\d{4}-\d{2}-\d{2}',snapshot['observed_on'])
 in_stock=sum(r.get('availability',{}).get('status')=='in_stock' for r in records)
 unavailable=sum(r.get('availability',{}).get('status')=='out_of_stock' for r in records)
 unknown=sum(r.get('availability') is None for r in records)
 assert snapshot['targets']==len(records)
 assert (in_stock,unavailable,unknown)==(snapshot['in_stock'],snapshot['out_of_stock'],snapshot['unconfirmed_identity'])
 assert in_stock+unavailable==snapshot['exact_matches']
 assert all(r['availability']['observed_on']==snapshot['observed_on']
            for r in records if r.get('availability'))
publication=d.get('publication_review_snapshot')
if publication:
 assert re.fullmatch(r'\d{4}-\d{2}-\d{2}',publication['checked_at'])
 assert publication['reviewed']==sum(bool(r.get('publication_review')) for r in records)
 assert publication['verified_for_order']==sum(r.get('publication_review',{}).get('status')=='verified' for r in records)
 assert publication['excluded']==sum(r.get('publication_review',{}).get('status')=='excluded' for r in records)
 assert publication['original_available_count']==sum(r.get('availability',{}).get('status')!='out_of_stock' for r in records)
 assert publication['visible_after_review']==sum(r.get('availability',{}).get('status')!='out_of_stock' and r.get('publication_review',{}).get('status')!='excluded' for r in records)
 assert publication['reviewed']==publication['verified_for_order']+publication['excluded']
 assert publication['visible_after_review']==110

assert len(records)==d['source']['unique_wine_urls'], 'Catalog size differs from source snapshot'
assert all(r['wishlist'] and not r['research'] for r in records), 'Archived research cannot appear in active catalog'
assert not any(r['section']=='Джин' for r in records)
assert len(records)>0
print('VALIDATED',len(records),'unique wine entries',len(urls),'retailer links', 'countries=',len({r['country'] for r in records if r['country']}))
