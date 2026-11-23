"""Evidence-gated, offline-only manual extension import regressions."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_manual_capture import apply_observations, verified_identity

URL = 'https://spb.winestyle.ru/products/Kopke-LBV-2018.html'
RECORD = {
    'id':'kopke', 'title':'Kopke Late Bottled Vintage Port (LBV)',
    'year':2018,'volume_l':0.75,'availability':{'status':'in_stock'},
    'stores':[{'url':URL,'price_rub':7000,'price_checked_at':'2026-11-22',
               'enrichment_status':{'status':'verified','source_url':URL,
                                    'checked_at':'2026-11-22'},
               'product_details':{'source_url':URL,'checked_at':'2026-11-22',
                                  'full_name':'Kopke LBV 2018','producer':'Kopke'}}]
}
CAPTURE = {
    'source_url':URL, 'captured_at':'2026-11-23T11:00:00+00:00',
    'h1':'Kopke LBV Port 2018, 750 ml','blocked':False,
    'fields':{'color':{'method':'visible_product_label','value':'Глубокий рубиновый',
                      'evidence':'Цвет: Глубокий рубиновый'}},
    'products':[{'@context':'https://schema.org','@type':'Product',
       'name':'Kopke Late Bottled Vintage Port 2018, 750 ml','url':URL,
       'description':'Kopke LBV 2018 bottle, 750 ml',
       'offers':[{'@type':'Offer','url':URL,'priceCurrency':'RUB',
                  'price':'6348','availability':'https://schema.org/InStock'}]}],
    'image_candidate':{'url':'https://images.example/bottle.jpg','rights':'unverified_not_for_publication'},
}
OBS = {'target_id':'kopke','target_url':URL,'capture':CAPTURE,'reviewer_confirmed':True}


class ManualImportTests(unittest.TestCase):
    def run_import(self, record=None, observation=None):
        return apply_observations(
            {'records':[copy.deepcopy(record or RECORD)]},
            [copy.deepcopy(observation or OBS)]
        )

    def test_verified_metadata_and_price_separate(self):
        catalog, report = self.run_import()
        r = catalog['records'][0]
        s = r['stores'][0]
        self.assertEqual(report['accepted_identity'],1)
        self.assertEqual(s['product_details']['color'],'Глубокий рубиновый')
        self.assertEqual(s['product_details']['field_checked_at']['color'],'2026-11-23')
        self.assertEqual(s['live_offer']['price_rub'],6348)
        self.assertEqual(s['live_offer']['regular_price_rub'],None)
        self.assertEqual(s['live_offer']['capture_method'],'user_confirmed_active_browser_tab')
        self.assertEqual(s['price_rub'],7000,'Historical value must not be mutated')
        self.assertNotIn('photo',r,'No permission to copy external image')
        self.assertNotIn('ratings',s['product_details'],'Do not trust retailer customer ratings')
        self.assertEqual(report['photos_imported'],0)
        self.assertEqual(report['ratings_imported'],0)

    def test_never_overwrite_existing_qualitative_value(self):
        r=copy.deepcopy(RECORD)
        r['stores'][0]['product_details']['color']='Проверенный старый цвет'
        c,report=self.run_import(record=r)
        self.assertEqual(c['records'][0]['stores'][0]['product_details']['color'],'Проверенный старый цвет')
        self.assertEqual(report['details_added'],0)

    def test_unreviewed_observation_is_rejected(self):
        o=copy.deepcopy(OBS);o['reviewer_confirmed']=False
        c,report=self.run_import(observation=o)
        self.assertEqual(report['accepted_identity'],0)
        self.assertEqual(c['records'][0]['stores'][0]['price_rub'],7000)

    def test_redirect_rejected(self):
        o=copy.deepcopy(OBS)
        o['capture']['source_url']='https://spb.winestyle.ru/products/Kopke-LBV-2025.html'
        c,report=self.run_import(observation=o)
        self.assertEqual(report['rejected'][0][1],'redirected_or_different_url')
        self.assertNotIn('live_offer',c['records'][0]['stores'][0])

    def test_different_year_rejected(self):
        o=copy.deepcopy(OBS);o['capture']['h1']='Kopke LBV Port 2025, 750 ml'
        o['capture']['products']=[]
        self.assertEqual(self.run_import(observation=o)[1]['rejected'][0][1],
                         'missing_or_conflicting_vintage')

    def test_different_size_rejected(self):
        o=copy.deepcopy(OBS);o['capture']['h1']='Kopke LBV Port 2018, 1.5 l'
        o['capture']['products']=[]
        self.assertEqual(self.run_import(observation=o)[1]['rejected'][0][1],
                         'missing_or_conflicting_bottle_size')

    def test_ambiguous_bottle_size_rejected(self):
        o=copy.deepcopy(OBS);o['capture']['h1']='Kopke LBV Port 2018, 750 ml and 1.5 l'
        self.assertEqual(self.run_import(observation=o)[1]['rejected'][0][1],
                         'missing_or_conflicting_bottle_size')

    def test_unknown_vintage_remains_unknown(self):
        r=copy.deepcopy(RECORD);r['year']=None
        self.assertEqual(self.run_import(record=r)[1]['rejected'][0][1],'unidentified_vintage')

    def test_unverified_merchant_rejected(self):
        r=copy.deepcopy(RECORD);r['stores'][0].pop('enrichment_status')
        self.assertEqual(self.run_import(record=r)[1]['rejected'][0][1],
                         'not_approved_for_publication')

    def test_no_price_when_jsonld_missing_identity(self):
        o=copy.deepcopy(OBS)
        o['capture']['products'][0]['name']='Kopke LBV Port 2025, 750 ml'
        c,report=self.run_import(observation=o)
        self.assertEqual(report['accepted_identity'],0)

    def test_no_price_when_offer_ambiguous_or_missing_size(self):
        o=copy.deepcopy(OBS)
        o['capture']['products'][0]['name']='Kopke LBV Port 2018'
        o['capture']['products'][0]['description']='Only 2018'
        o['capture']['products'][0]['size']=''
        c,report=self.run_import(observation=o)
        self.assertEqual(report['accepted_identity'],1)
        self.assertEqual(report['live_offers_updated'],0)
        self.assertEqual(c['records'][0]['stores'][0]['price_rub'],7000)

    def test_manual_port_research_without_wine_style_manifest(self):
        r=copy.deepcopy(RECORD)
        r['stores'][0].pop('enrichment_status')
        r['stores'][0].pop('product_details')
        r['publication_review']={'status':'verified','checked_at':'2026-11-22',
                                 'final_url':URL}
        catalog,report=self.run_import(record=r)
        self.assertEqual(report['accepted_identity'],1)
        self.assertEqual(catalog['records'][0]['stores'][0]['research_details']['color'],
                         'Глубокий рубиновый')

    def test_rejected_page_never_changes_catalog(self):
        o=copy.deepcopy(OBS);o['capture']['blocked']=True
        c,report=self.run_import(observation=o)
        self.assertEqual(c['records'][0],RECORD)
        self.assertEqual(report['accepted_identity'],0)

    def test_extension_does_not_store_raw_html(self):
        self.assertNotIn('raw_html',CAPTURE)
        self.assertNotIn('cookies',CAPTURE)
        self.assertNotIn('headers',CAPTURE)


if __name__=='__main__':
    unittest.main()
