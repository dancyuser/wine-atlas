#!/usr/bin/env python3
"""Conservative updater using publicly accessible JSON-LD Product offers only.

Unverified values remain null; historical values are never overwritten. Observe robots.txt,
never bypass anti-bot controls, never infer an undiscounted price from MSRP/priceHigh.
"""
import argparse,json,datetime,html,re,sys,time,urllib.request,urllib.error,urllib.robotparser
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
USER_AGENT='PersonalWineAtlasCatalog/1.0 (respectful metadata fetch)'
class ProductSchemaParser(HTMLParser):
 def __init__(self):super().__init__();self.capture=False;self.blocks=[];self.buf=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='script' and attrs.get('type','').lower()=='application/ld+json':self.capture=True;self.buf=[]
 def handle_data(self,data):
  if self.capture:self.buf.append(data)
 def handle_endtag(self,tag):
  if tag=='script' and self.capture:self.blocks.append(''.join(self.buf));self.capture=False;self.buf=[]

def find_price(html_text):
 p=ProductSchemaParser();p.feed(html_text)
 for block in p.blocks:
  try: obj=json.loads(html.unescape(block))
  except (ValueError,TypeError):continue
  nodes=obj if isinstance(obj,list) else [obj]
  for node in nodes:
   if not isinstance(node,dict):continue
   nodes2=node.get('@graph',[]) if '@graph' in node else [node]
   for item in nodes2:
    if not isinstance(item,dict):continue
    kind=item.get('@type','');kind=[kind] if isinstance(kind,str) else kind
    if not isinstance(kind,list) or not any(str(t).lower().endswith('product') for t in kind):continue
    offers=item.get('offers');offers=offers if isinstance(offers,list) else [offers]
    for offer in offers:
     if not isinstance(offer,dict):continue
     if offer.get('priceCurrency') not in ('RUB','RUR'):continue
     val=offer.get('price')
     # When a price specification exists, pick an explicit current price only.
     if val is None:
      spec=offer.get('priceSpecification')
      if isinstance(spec,dict):val=spec.get('price')
     if val is None:continue
     try: price=round(float(str(val).replace(' ', '').replace(',','.')))
     except (TypeError,ValueError):continue
     if not 100 <= price <= 1000000:continue
     regular=None
     # Explicit previous price fields only; do not equate highPrice to oldPrice.
     for k in ('oldPrice','previousPrice','originalPrice'):
      if k in offer:
       try:
        z=round(float(str(offer[k]).replace(' ', '').replace(',','.')))
        if price<z<=1000000:regular=z;break
       except (ValueError,TypeError):pass
     return price,regular
 return None

def robots_allowed(url,cache):
 p=urlsplit(url);base=f'{p.scheme}://{p.netloc}'
 if base not in cache:
  rf=urllib.robotparser.RobotFileParser();rf.set_url(base+'/robots.txt')
  try:
   with urllib.request.urlopen(urllib.request.Request(base+'/robots.txt',headers={'User-Agent':USER_AGENT}),timeout=10) as response:
    data=response.read(200000).decode('utf-8','replace').splitlines()
   rf.parse(data);cache[base]=rf
  except urllib.error.HTTPError as e:
   cache[base]=(e.code==404)
  except (urllib.error.URLError,TimeoutError):cache[base]=False
 v=cache[base]
 return v.can_fetch(USER_AGENT,url) if isinstance(v,urllib.robotparser.RobotFileParser) else v

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=0);ap.add_argument('--delay',type=float,default=3.0);ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
 path=ROOT/'data'/'wines.json';data=json.loads(path.read_text(encoding='utf-8'))
 cache={};seen=set();updated=0;attempted=0;blocked=0;failed=0
 for r in data['records']:
  for store in r['stores']:
   url=store['url']
   if (urlsplit(url).hostname or '').lower().removeprefix('spb.')=='winestyle.ru':
    # The identity-aware WineStyle pipeline owns this domain and its stop state.
    blocked+=1;continue
   if url in seen:continue
   seen.add(url)
   if args.limit and attempted>=args.limit:break
   if not robots_allowed(url,cache):blocked+=1;continue
   attempted+=1
   try:
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=18) as res:
     if res.status!=200 or 'text/html' not in res.headers.get('Content-Type',''):raise ValueError('Non-HTML response')
     body=res.read(2_000_001)
    if len(body)>2_000_000:raise ValueError('Oversized page')
    parsed=find_price(body.decode('utf-8','replace'))
    if parsed:
     price,regular=parsed
     print(f'OK {urlsplit(url).netloc}: {price} RUB (regular {regular})')
     if not args.dry_run:
      store.update(price_rub=price,regular_price_rub=regular,price_checked_at=datetime.date.today().isoformat())
      updated+=1
    else: print('NO_PRICE',url)
   except (urllib.error.URLError,TimeoutError,ValueError) as e:
    failed+=1;print('SKIP',url,str(e)[:100],file=sys.stderr)
    if isinstance(e,urllib.error.HTTPError) and e.code in (403,429,503):
     # A blocked retailer must not be hammered after access refusal.
     cache[f'{urlsplit(url).scheme}://{urlsplit(url).netloc}']=False
   time.sleep(max(args.delay,1.0))
  if args.limit and attempted>=args.limit:break
 if updated and not args.dry_run:
  data['updated_at']=datetime.date.today().isoformat()
  tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)
 print(f'PROCESSED={attempted} UPDATED={updated} ROBOTS_DENIED={blocked} ERRORS={failed}')
if __name__=='__main__':main()
