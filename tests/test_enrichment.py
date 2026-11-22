"""Synthetic fixtures test rejection paths; they are NOT real WineStyle evidence."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
TEST_TMP=ROOT/'tests/.tmp'
TEST_TMP.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts'))
import enrich_winestyle as e
from validate_catalog import validate

URL='https://spb.winestyle.ru/products/Peter-Zemmer-Chardonnay-Alto-Adige-DOC-2023.html'
BASE=json.loads((ROOT/'data/backups/wines.before-winestyle-2026-11-22.json').read_text(encoding='utf-8'))
RECORD=next(r for r in BASE['records'] if any(s['url']==URL for s in r['stores']))


def product():
    return {'@type':'Product','name':'Peter Zemmer Chardonnay Alto Adige DOC 2023, 0.75 l',
            'brand':{'name':'Peter Zemmer'},'url':URL,'size':'0.75 l',
            'description':'Synthetic example: apple aroma; NOT scraped evidence.',
            'image':'https://example.com/test-bottle.jpg',
            'additionalProperty':[{'name':'Страна','value':'Италия'},
                                  {'name':'Сорт винограда','value':'Шардоне: 100%'},
                                  {'name':'Крепость','value':'13.5%'}],
            'offers':{'@type':'Offer','price':'2 500','priceCurrency':'RUB',
                      'availability':'https://schema.org/InStock','url':URL}}


def page(p=None, extra=''):
    return '<html><title>Wine fixture</title><link rel="canonical" href="'+URL+'"><script type="application/ld+json">'+json.dumps(p or product())+'</script>'+extra+'</html>'


class ParserTests(unittest.TestCase):
    def parse(self,p=None,record=None,extra=''):
        return e.extract(page(p,extra),record or RECORD,URL,'2026-11-22')

    def test_fields_and_regional_uncertainty(self):
        d,p,old=self.parse()
        self.assertEqual(p,2500)
        self.assertIsNone(old)
        self.assertEqual(d['producer'],'Peter Zemmer')
        self.assertEqual(d['alcohol_percent'],13.5)
        self.assertEqual(d['country'],'Италия')
        self.assertIsNone(d['availability_spb'])
        self.assertFalse(d['image_usage_allowed'])

    def test_explicit_discount_only(self):
        p=product();p['offers']['highPrice']=4000
        self.assertIsNone(self.parse(p)[2])
        p['offers']['oldPrice']='3 200'
        self.assertEqual(self.parse(p)[2],3200)

    def test_invalid_prices(self):
        for value in (True,False,0,-1,'NaN','Infinity','2 500-3 000','от 2500','2500.50',99,1000001):
            with self.subTest(value=value): self.assertIsNone(e.price(value))
        self.assertEqual(e.price('2\u202f500,00'),2500)

    def test_currency_and_aggregate_rejected(self):
        p=product();p['offers']['priceCurrency']='EUR'
        self.assertIsNone(self.parse(p)[1])
        p['offers'].update(priceCurrency='RUB',**{'@type':'AggregateOffer'})
        self.assertIsNone(self.parse(p)[1])

    def test_wrong_year_name_and_producer_rejected(self):
        for field,value in [('name','Peter Zemmer Chardonnay Alto Adige DOC 2022, 0.75 l'),
                            ('name','Peter Zemmer Pinot Noir 2023, 0.75 l'),
                            ('brand',{'name':'Different Winery'})]:
            p=product();p[field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):self.parse(p)

    def test_wrong_volume_rejected(self):
        record=copy.deepcopy(RECORD);record['volume_l']=.75
        p=product();p['size']='1.5 l'
        with self.assertRaises(ValueError):self.parse(p,record)

    def test_offer_url_mismatch_rejected(self):
        p=product();p['offers']['url']='https://spb.winestyle.ru/products/other.html'
        self.assertIsNone(self.parse(p)[1])

    def test_ambiguous_offers_rejected(self):
        p=product();o=copy.deepcopy(p['offers']);o['price']=2600;p['offers']=[p['offers'],o]
        self.assertIsNone(self.parse(p)[1])

    def test_recommendation_product_rejected(self):
        p=product();p['name']='Other Winery Merlot 2023';p['url']='https://spb.winestyle.ru/products/other.html'
        with self.assertRaises(ValueError):self.parse({'@graph':[p]})

    def test_graph_and_duplicate_products(self):
        self.assertEqual(self.parse({'@graph':[product()]})[1],2500)
        with self.assertRaises(ValueError):self.parse([product(),product()])

    def test_block_page(self):
        with self.assertRaisesRegex(ValueError,'access_challenge'):
            e.extract('<title>Access denied</title>',RECORD,URL,'2026-11-22')

    def test_dom_microdata(self):
        html='''<main itemscope itemtype="https://schema.org/Product">
        <h1 itemprop="name">Peter Zemmer Chardonnay Alto Adige DOC 2023, 0.75 l</h1>
        <span itemprop="brand">Peter Zemmer</span><meta itemprop="price" content="2500">
        <meta itemprop="priceCurrency" content="RUB"><dl><dt>Объем</dt><dd>0.75 л</dd>
        <dt>Аромат</dt><dd>Тестовый аромат.</dd></dl></main>'''
        details,current,_=e.extract(html,RECORD,URL,'2026-11-22')
        self.assertEqual(current,2500)
        self.assertEqual(details['aroma'],'Тестовый аромат.')

    def test_availability_requires_explicit_region(self):
        p=product();p['offers']['eligibleRegion']={'name':'Санкт-Петербург'}
        self.assertIs(self.parse(p)[0]['availability_spb'],True)

    def test_apply_preserves_history_manual_and_missing_price(self):
        r=copy.deepcopy(RECORD);s=r['stores'][0]
        s.update(price_rub=3100,regular_price_rub=3500,price_checked_at='2026-11-14')
        original=copy.deepcopy(s)
        d,_,_=self.parse();r['country']='Ручная страна'
        e.apply_result(r,s,d,None,None,{r['id']:{'country':'Ручная страна'}})
        self.assertEqual(r['country'],'Ручная страна')
        for k in ('reference_price_rub','reference_regular_price_rub','reference_date','price_rub','price_checked_at'):
            self.assertEqual(s[k],original[k])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        output=patch('sys.stdout',new_callable=io.StringIO)
        output.start()
        self.addCleanup(output.stop)

    def test_actual_catalog_preserved(self):
        data=json.loads((ROOT/'data/wines.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(data,BASE),(163,163))

    def test_validator_detects_lost_history_duplicate_and_nan(self):
        for mutate in (lambda d:d['records'].append(d['records'][0]),
                       lambda d:d['records'][0]['stores'][0].update(reference_price_rub=999),
                       lambda d:d['records'][0].update(volume_l=float('nan'))):
            data=copy.deepcopy(BASE);mutate(data)
            with self.assertRaises(AssertionError):validate(data,BASE)

    def test_persistent_block_and_dry_run_no_writes(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            root=Path(tmp);catalog=root/'wines.json';state=root/'access.json';report=root/'report.json'
            e.atomic_json(catalog,BASE);e.atomic_json(state,{'blocked':True,'reason':'HTTP 403'})
            before={p.name:p.read_bytes() for p in root.iterdir()}
            with patch.object(e,'fetch',side_effect=AssertionError('must not request domain')):
                code=e.main(['--catalog',str(catalog),'--access-state',str(state),'--report',str(report),'--limit','3','--dry-run','--headed'])
            self.assertEqual(code,2)
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})

    def test_offline_run_and_repeat(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            root=Path(tmp);catalog=root/'wines.json';report=root/'report.json'
            data=copy.deepcopy(BASE);e.atomic_json(catalog,data)
            (root/'wine.html').write_text(page(),encoding='utf-8')
            e.atomic_json(root/'manifest.json',[{'url':URL,'file':'wine.html','checked_at':'2026-11-22'}])
            args=['--catalog',str(catalog),'--input-dir',str(root),'--report',str(report)]
            with patch.object(e,'fetch',side_effect=AssertionError('offline means no HTTP')):
                self.assertEqual(e.main(args),0)
                first=catalog.read_bytes()
                self.assertEqual(e.main(args),0)
                self.assertEqual(catalog.read_bytes(),first)
            after=json.loads(first)
            self.assertEqual(validate(after,BASE),(163,163))
            self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['successful'],1)

    def test_block_stops_subsequent_requests(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            root=Path(tmp);catalog=root/'wines.json'
            e.atomic_json(catalog,BASE)
            e.atomic_json(root/'policy.json',dict(allowed=True,terms_url='https://example.com/test-terms',reviewed_at='2026-11-22',note='Synthetic test policy only'))
            calls=[]
            def fetch(url):
                calls.append(url)
                if url.endswith('/robots.txt'):return 'User-agent: *\nAllow: /\n'
                raise e.DomainBlocked('HTTP 403 synthetic fixture')
            with patch.object(e,'fetch',side_effect=fetch),patch.object(e.time,'sleep'):
                code=e.main(['--catalog',str(catalog),'--policy-file',str(root/'policy.json'),
                             '--access-state',str(root/'access.json'),'--report',str(root/'report.json')])
            self.assertEqual(code,2)
            self.assertEqual(len(calls),2)
            self.assertTrue(json.loads((root/'access.json').read_text(encoding='utf-8'))['blocked'])
            self.assertEqual(json.loads(catalog.read_text(encoding='utf-8')),BASE)

    def test_builder_retains_enrichment_and_history(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            root=Path(tmp);(root/'data').mkdir()
            spec=importlib.util.spec_from_file_location('builder',ROOT/'scripts/build_catalog.py')
            builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder);builder.ROOT=root
            rec=copy.deepcopy(RECORD);s=rec['stores'][0]
            d,p,old=e.extract(page(),rec,URL,'2026-11-22');e.apply_result(rec,s,d,p,old,{})
            s.update(reference_price_rub=1800,reference_date='2026-11-14')
            e.atomic_json(root/'data/wines.json',dict(records=[rec]))
            e.atomic_json(root/'data/overrides.json',{rec['id']:{'country':'Италия'}})
            source=root/'source.txt';source.write_text('Шардоне\n'+URL+'\n',encoding='utf-8')
            with patch.object(sys,'argv',['build_catalog.py',str(source)]):builder.main()
            built=json.loads((root/'data/wines.json').read_text(encoding='utf-8'))['records'][0]
            self.assertEqual(built['stores'][0],s)
            self.assertEqual(built['country'],'Италия')


if __name__=='__main__':unittest.main()
