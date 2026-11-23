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
  live=store.get('live_offer')
  if live is not None:
   assert (r.get('publication_review',{}).get('status')=='verified' or (
    r.get('publication_review',{}).get('status')!='excluded'
    and live.get('capture_method') in ('user_confirmed_active_browser_tab','automated_browser_batch')
    and store.get('enrichment_status',{}).get('status')=='verified'
    and store.get('product_details',{}).get('source_url')==store['url']
   )),('Unreviewed offer',r['id'])
   assert live.get('verification_method') in ('exact_jsonld_product','exact_main_product_visible_price'),('Offer method',r['id'])
   assert live.get('availability') in ('in_stock','out_of_stock','unknown'),('Offer status',r['id'])
   assert re.fullmatch(r'\d{4}-\d{2}-\d{2}',live.get('observed_on','')),('Offer date',r['id'])
   assert live['observed_on']>=((r.get('publication_review') or {}).get('checked_at') or store.get('enrichment_status',{}).get('checked_at','9999-12-31')),('Stale offer',r['id'])
   assert live.get('price_rub') is not None and type(live['price_rub']) is int and 100<=live['price_rub']<=1000000,('Offer price',r['id'])
   regular=live.get('regular_price_rub')
   assert regular is None or (type(regular) is int and live['price_rub']<regular<=1000000),('Offer old price',r['id'])
   def source_id(u):
    p=urlsplit(u)
    return (p.scheme,p.hostname,p.path.rstrip('/'))
   assert source_id(live.get('source_url',''))==source_id(store['url'])==source_id((r.get('publication_review') or {}).get('final_url') or store.get('enrichment_status',{}).get('source_url')),('Offer redirect',r['id'])
   assert live.get('product_name') and isinstance(live['product_name'],str),('Offer product',r['id'])
   if live['verification_method']=='exact_main_product_visible_price':
    assert urlsplit(store['url']).hostname=='spb.winestyle.ru',('Visible offer vendor',r['id'])
    assert live.get('capture_method')=='automated_browser_batch',('Visible offer source',r['id'])
    from import_manual_capture import numeric_displayed_rubles
    assert numeric_displayed_rubles(live.get('price_evidence'))==live['price_rub'],('Visible offer price evidence',r['id'])
    if regular is not None:
     assert numeric_displayed_rubles(live.get('regular_price_evidence'))==regular,('Visible offer regular price proof',r['id'])
    stock=live.get('availability_evidence')
    assert isinstance(stock,str) and stock,('Visible offer stock proof',r['id'])
    if live['availability']=='in_stock':
     assert re.match(r'^в наличии(?:\s|$)',stock,re.I),('Visible offer availability',r['id'])
    elif live['availability']=='out_of_stock':
     assert re.match(r'^(?:ожидаем поступление|нет в наличии|товар отсутствует)(?:\s|$)',stock,re.I),('Visible unavailable stock proof',r['id'])
    else: raise AssertionError(('Unconfirmed visible-stock offer',r['id']))

 # Vendor-sourced manual research is separate from the immutable WineStyle archive.
  manual=store.get('research_details')
  if manual is not None:
   assert manual.get('source_kind') in ('primary_retailer_product_description','manual_verified_original_seller','automated_verified_original_seller','producer_style_profile'),('Research kind',r['id'])
   assert manual.get('checked_at') and re.fullmatch(r'\d{4}-\d{2}-\d{2}',manual['checked_at']),('Research date',r['id'])
   if manual['source_kind']=='producer_style_profile':
    assert manual.get('scope')=='all_vintages' and manual.get('producer'),('Producer scope',r['id'])
    assert urlsplit(manual.get('source_url','')).scheme=='https' and urlsplit(manual['source_url']).hostname,('Producer URL',r['id'])
    assert store.get('product_details') is None and store.get('enrichment_status') is None,('Producer profile is not retailer capture',r['id'])
   else:
    assert manual.get('source_url','').split('#')[0].rstrip('/')==store['url'].split('#')[0].rstrip('/'),('Research URL',r['id'])
   assert manual.get('full_name') or manual.get('producer'),('Research identity',r['id'])

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
 assert publication['visible_after_review']==109

visible=[r for r in records if r.get('availability',{}).get('status')!='out_of_stock' and
         r.get('publication_review',{}).get('status')!='excluded']
assert len(visible)==109
assert all(type(r.get('volume_l')) in (float,int) and r['volume_l']>0 for r in visible), 'Missing published bottle volume'
assert all(isinstance(r.get('grapes'),list) and r['grapes'] for r in visible), 'Missing published grape identity'
assert all(any((r['stores'][0].get(kind) or {}).get('color') for kind in ('product_details','research_details'))
           for r in visible), 'Missing published source color description'
assert all(any((r['stores'][0].get(kind) or {}).get('wine_style') for kind in ('product_details','research_details'))
           for r in visible), 'Missing verified wine style for published bottle'
assert all(any((r['stores'][0].get(kind) or {}).get('pairing_notes') for kind in ('product_details','research_details'))
           for r in visible), 'Missing verified food pairings for published bottle'

assert len(records)==d['source']['unique_wine_urls'], 'Catalog size differs from source snapshot'
assert all(r['wishlist'] and not r['research'] for r in records), 'Archived research cannot appear in active catalog'
assert not any(r['section']=='Джин' for r in records)
assert len(records)>0
print('VALIDATED',len(records),'unique wine entries',len(urls),'retailer links', 'countries=',len({r['country'] for r in records if r['country']}))
