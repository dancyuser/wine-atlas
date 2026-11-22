#!/usr/bin/env python3
"""Build wine records from an exported Google Doc plain-text file.

Usage: python scripts/build_catalog.py source.txt
No external dependencies. Manual country/grape annotations can be added in data/overrides.json.
"""
import json, re, sys, hashlib
from pathlib import Path
from urllib.parse import urlsplit, unquote
ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'Портвейн','Джин','Шардоне','Пино Нуар','Рислинг','Игристое','Мерло','Примитиво','Кьянти','Каберне Совиньон','Зинфандель','Мальбек','Риоха','Сира','Санджовезе','Негроамаро','Сен-Лоран','Шираз','Темпранильо','Неббиоло','Барбера','Монастрель','Корвина','Каннонау','Тинта де торо','Альянико','Моника','Тинто Фино','Гренаш','Пино Гриджио','Грюнер','Ондарраби Сури','Совиньон Блан','Вердехо','Фурминт','Энкрузаду','Треббьяно','Турбиана','Кортезе','Алиготе','Гевюрцртамминер','Альбариньо','Мурведр','Торронтес'}
COUNTRIES={'italy':'Италия','france':'Франция','spain':'Испания','austria':'Австрия','germany':'Германия','portugal':'Португалия','russia':'Россия','usa':'США','chile':'Чили','argentina':'Аргентина','southafrica':'ЮАР','newzealand':'Новая Зеландия','australia':'Австралия','israel':'Израиль'}
GEO = [
 ('Италия',r'(?i)ital|sudtirol|alto-adige|trentino|trento-doc|sicilia|toscana|puglia|valpolicella|veneto|gavi|chianti|salento|sardegna|lugana|barbera|nebbiolo|prosecco|moscato-d-asti|piemonte|emilia|basilicata|treviso|friuli|collio|morellino|alba-doc|salice-salentino|colli-trevigiani|aglianico-del-vulture|fattoria-le-pupille'),
 ('Франция',r'(?i)bourgogne|bordeaux|alsace|medoc|cotes-de-provence|coteaux-d-aix|pays-d-oc|gascon|gascogne|cremant|listrac|chateau-ducluzeau|chateau-marjosse|miraval|chateau-la-tour'),
 ('Испания',r'(?i)rioja|ribera-del-duero|jumilla|priorat|cava-do|rias-baixas|txakoli|(?:^|-)toro(?:-|$)|tinta-de-toro|elias-mora|can-sumoi|crapula|protos|muga|bodegas-ramon|torres-vina-esmeralda'),
 ('Португалия',r'(?i)port-20|porto|graham|quinta-de-la-rosa|kopke|dow_s|dao-doc'),
 ('Венгрия',r'(?i)tokaji|pajzos'),
 ('Австрия',r'(?i)wachau|sudsteiermark|gruner|ingrid-groiss|tement|zantho|kracher|loimer|wohlmuth'),
 ('Германия',r'(?i)rudesheim|spatburgunder|weingut-j-neus|nik-weis|tesch-unplugged|von-buhl'),
 ('США',r'(?i)north-coast|wente|pyramid-scheme|long-barn|kendall[-_]jackson'),
 ('Аргентина',r'(?i)rio-negro|tupungato|mendoza|vina-cobos|felino|mi-terruno|el-esteco|amalaya|la-posta|clos-de-los-siete'),
 ('Чили',r'(?i)leyda-valley|undurraga|tabali|maule-valley|maturana-wines|lapostolle'),
 ('ЮАР',r'(?i)swartland|kleine-zalze|jordan-black-magic|badenhorst'),
 ('Новая Зеландия',r'(?i)huia-pinot|the-ned|villa-maria|marlborough'),
 ('Австралия',r'(?i)d-arenberg|church-block|frankland-estate'),
 ('Россия',r'(?i)myskhako'),
 ('Израиль',r'(?i)recanati')]
GRAPES = [('Шардоне',r'(?i)chardonnay|shardone|шардоне'),('Пино Нуар',r'(?i)pinot-noir|spatburgunder|пино нуар'),('Рислинг',r'(?i)riesling|risling|рислинг'),('Совиньон Блан',r'(?i)sauvignon-blanc|sovinon_blan|совиньон блан'),('Грюнер Вельтлинер',r'(?i)gruner-veltliner|gruner_veltl|грюнер'),('Мальбек',r'(?i)malbec|мальбек'),('Мерло',r'(?i)merlot|мерло'),('Каберне Совиньон',r'(?i)cabernet-sauvignon|kaberne_sovinon|каберне совиньон'),('Каберне Фран',r'(?i)cabernet-franc|каберне фран'),('Темпранильо',r'(?i)tempranillo|tinto-fino|тинто фино'),('Примитиво',r'(?i)primitivo'),('Сира / Шираз',r'(?i)syrah|shiraz'),('Зинфандель',r'(?i)zinfandel'),('Алиготе',r'(?i)aligote|алиготе'),('Неббиоло',r'(?i)nebbiolo'),('Барбера',r'(?i)barbera'),('Монастрель',r'(?i)monastrell'),('Корвина',r'(?i)corvina'),('Каннонау',r'(?i)cannonau'),('Альянико',r'(?i)aglianico'),('Вердехо',r'(?i)verdejo'),('Фурминт',r'(?i)furmint'),('Пино Гриджио',r'(?i)pinot-grigio'),('Гевюрцтраминер',r'(?i)gewurztraminer'),('Альбариньо',r'(?i)albarino'),('Турбиана',r'(?i)turbiana'),('Кортезе',r'(?i)cortese'),('Москато',r'(?i)moscato'),('Ркацители',r'(?i)rkaciteli|ркацители'),('Вионье',r'(?i)vione|вионье'),('Мальвазия',r'(?i)malvaziya|мальвазия'),('Блауфранкиш',r'(?i)blaufrankisch'),('Сен-Лоран',r'(?i)st-laurent'),('Торронтес',r'(?i)torrontes'),('Торонтель',r'(?i)torontel')]
PAIRINGS={'Красное':['Красное мясо','Сыры','Паста'],'Белое':['Рыба','Морепродукты','Птица'],'Розовое':['Салаты','Рыба','Птица'],'Игристое':['Закуски','Сыры','Морепродукты'],'Оранжевое':['Пряные блюда','Сыры','Птица'],'Портвейн':['Десерты','Выдержанные сыры']}

def parse_type(s, category=''):
 t=s.lower(); cat=category.lower()
 if 'портвейн' in t or cat=='портвейн' or 'port-' in t or 'lbv' in t: return 'Портвейн'
 if 'оранжев' in t or 'naranjo' in t or 'orange' in t: return 'Оранжевое'
 if 'игрист' in t or cat=='игристое' or re.search(r'(?i)prosecco|brut|cremant|cava-do|spumante|moscato.d.asti|ancestral',t):return 'Игристое'
 if 'розов' in t or 'rosé' in t or 'rose' in t or 'rosato' in t or 'rosado' in t: return 'Розовое'
 if 'белое' in t or re.search(r'(?i)white|blanc|blanco|bianco|chardonnay|riesling|gruner|pinot-grigio|verdejo|furmint|aligote|lugana|gavi|albarino|gewurztraminer|sauvignon|gluegglich',t):return 'Белое'
 if 'красн' in t or re.search(r'(?i)red|rosso|rouge|merlot|pinot-noir|spatburgunder|syrah|shiraz|cabernet|malbec|primitivo|nebbiolo|barbera|zinfandel|chianti|rioja|valpolicella|monastrell|grenache|cannonau|sangiovese|tempranillo|sainte-laurent|tinto|blaufrankisch|aglianico',t): return 'Красное'
 if category in {'Шардоне','Рислинг','Пино Гриджио','Грюнер','Совиньон Блан','Вердехо','Фурминт','Энкрузаду','Треббьяно','Турбиана','Кортезе','Алиготе','Гевюрцртамминер','Альбариньо','Ондарраби Сури'}: return 'Белое'
 if category in {'Пино Нуар','Мерло','Примитиво','Кьянти','Каберне Совиньон','Зинфандель','Мальбек','Риоха','Сира','Санджовезе','Негроамаро','Сен-Лоран','Шираз','Темпранильо','Неббиоло','Барбера','Монастрель','Корвина','Каннонау','Тинта де торо','Альянико','Моника','Тинто Фино'}:return 'Красное'
 return 'Не установлен'

def maybe_country(slug):
 hits=[country for country,pat in GEO if re.search(pat,slug)]
 return hits[0] if len(hits)==1 else None

def maybe_grapes(text, category):
 hits=[]
 for grape,pattern in GRAPES:
  if re.search(pattern,text) and grape not in hits:hits.append(grape)
 # Only use the section as secondary classification. It is not proof of varietal content.
 if not hits and category in {'Шардоне','Пино Нуар','Рислинг','Мерло','Примитиво','Каберне Совиньон','Зинфандель','Мальбек','Сира','Санджовезе','Негроамаро','Сен-Лоран','Шираз','Темпранильо','Неббиоло','Барбера','Монастрель','Корвина','Каннонау','Альянико','Гренаш','Пино Гриджио','Грюнер','Совиньон Блан','Вердехо','Фурминт','Треббьяно','Турбиана','Кортезе','Алиготе','Альбариньо','Мурведр','Торронтес'}: return []
 return hits

def wine_title(url):
 slug=unquote(urlsplit(url).path).rstrip('/').split('/')[-1].removesuffix('.html')
 slug=re.sub(r'(?i)-id\d+$','',slug)
 slug=re.sub(r'(?i)_?0?75_\d+$','',slug)
 return re.sub(r'[-_]+',' ',slug).strip()

def key(url):
 u=urlsplit(url);return (u.netloc.lower()+u.path.rstrip('/').lower()).removesuffix('.html')

def make_record(url,category,curated=False):
 slug=unquote(urlsplit(url).path).rstrip('/').split('/')[-1].removesuffix('.html')
 year=re.search(r'(?<!\d)(20\d\d|19\d\d)(?!\d)',slug)
 typ=parse_type(slug,category)
 g=maybe_grapes(slug,category)
 return {'id':hashlib.sha1(key(url).encode()).hexdigest()[:12], 'title':wine_title(url), 'year':int(year[0]) if year else None,'country':maybe_country(slug),'grapes':g,'type':typ,'pairings':PAIRINGS.get(typ,[]),'description':f'{typ} вино. Сочетания указаны как ориентиры для категории, а не персональные дегустационные характеристики.', 'section':category, 'wishlist':True, 'research':False,'stores':[{'name':urlsplit(url).netloc.removeprefix('spb.'),'url':url,'price_rub':None,'regular_price_rub':None,'price_checked_at':None,'reference_price_rub':None,'reference_regular_price_rub':None,'reference_date':None}], 'volume_l':None, 'scores':[], 'review_note':None}

def main():
 src=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'source.txt'
 lines=src.read_text(encoding='utf-8-sig').splitlines()
 recs={}; cat=None; research=False; num_research=0; extra_gin=0
 for i,ln in enumerate(lines):
  s=ln.strip()
  if s.startswith('ВИНА ДЛЯ ПОКУПКИ'):research=True;continue
  if not research:
   if s in CATEGORIES:cat=s;continue
   if s.startswith('https://') and cat:
    if cat=='Джин':extra_gin+=1;continue
    k=key(s)
    if k not in recs:recs[k]=make_record(s,cat)
  else:
   match=re.match(r'^(\d+)\.\s+(.*)',s)
   if not match:continue
   num_research+=1
   description=match.group(2)
   url=next((x.strip() for x in lines[i+1:i+6] if x.strip().startswith('http') and 'docs.google' not in x.strip()),None)
   if not url:continue
   k=key(url)
   if k in recs:r=recs[k]
   else:
    r=make_record(url,'Подборка СПб');r['wishlist']=False;recs[k]=r
   r['research']=True
   title=description.split(' — ',1)[0]
   # A researched exact title is generally more informative than the URL slug.
   title=re.sub(r'^[\s\d]+\.\s*','',title).strip()
   r['title']=title
   r['description']=description.split(' — ',1)[1].split(' ₽.',1)[-1].strip()[:240] if ' — ' in description else r['description']
   info=description.split(' — ',1)[-1]
   country=next((c for c in COUNTRIES.values() if re.search(r'(?<!\w)'+re.escape(c)+r'(?!\w)',info)),None)
   if country:r['country']=country
   typ=parse_type(info.split(' ₽')[0],r['section'])
   if typ!='Не установлен':r['type']=typ;r['pairings']=PAIRINGS.get(typ,[])
   grams=maybe_grapes(title+' '+wine_title(url),r['section'])
   if grams:r['grapes']=grams
   price_m=re.search(r'(?<!\d)(\d[\d\s]{2,6})\s*(?:\([^)]*\)\s*)?₽',info)
   if price_m:
    r['stores'][0]['reference_price_rub']=int(price_m.group(1).replace(' ',''))
    r['stores'][0]['reference_date']='2026-11-14'
   if 'Семисам Красное' in title:
    r['stores'][0]['reference_price_rub']=743
    r['stores'][0]['reference_regular_price_rub']=990
   if 'Вторая Линия Солист' in title:
    r['stores'][0]['reference_price_rub']=1300
    r['stores'][0]['reference_regular_price_rub']=1733
   year=re.search(r'(?<!\d)(20\d\d|19\d\d)(?!\d)',title)
   if year:r['year']=int(year.group())
   vol=re.search(r'(\d[,\.]\d+)\s*л',info)
   if vol:r['volume_l']=float(vol.group(1).replace(',','.'))
   r['scores']=re.findall(r'(?:Decanter|Wine Enthusiast|Wine Spectator|Tim Atkin|James Suckling|Falstaff|Top100Wines|Simple Wine News)[^.;]{0,65}',info,re.I)[:3]
   r['review_note']='Данные подборки от 14.11.2026; текущие цены и наличие не подтверждены.'
 overrides=ROOT/'data'/'overrides.json'
 if overrides.exists():
  custom=json.loads(overrides.read_text(encoding='utf-8'))
  for r in recs.values():
   if r['id'] in custom:
    r.update({k:v for k,v in custom[r['id']].items() if k not in ['id','stores']})
 # Entries in the Saint Petersburg research tab are exclusive to that tab,
 # even if their URL was also present in the original wishlist or overrides.
 for record in recs.values():
  if record['research']:
   record['wishlist']=False
 # Keep current verified store snapshots across re-imports of the source list.
 target=ROOT/'data'/'wines.json'
 if target.exists():
  try: previous={r['id']:r for r in json.loads(target.read_text(encoding='utf-8'))['records']}
  except (KeyError,ValueError):previous={}
  for record in recs.values():
   prev=previous.get(record['id'])
   if not prev:continue
   old_stores={key(s['url']):s for s in prev.get('stores',[])}
   for store in record['stores']:
    was=old_stores.get(key(store['url']))
    if was:
     for f in ('price_rub','regular_price_rub','price_checked_at'):
      store[f]=was.get(f)
 out={'updated_at':'2026-11-22','region':'Санкт-Петербург','historical_as_of':'2026-11-14','records':sorted(recs.values(),key=lambda r:(not r['research'],r['title'].casefold()))}
 (ROOT/'data'/'wines.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f'wishlist URLs excluding gin and duplicates: {sum(r["wishlist"] for r in recs.values())}; research: {num_research}; total unique: {len(recs)}; gin excluded: {extra_gin}')
if __name__=='__main__':main()
