"""Offline-only synthetic tests; they do NOT establish live WineStyle DOM support."""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_winestyle as parser
from winestyle_ratings import extract_ratings

URL = 'https://spb.winestyle.ru/products/Peter-Zemmer-Chardonnay-Alto-Adige-DOC-2023.html'
DATE = '2026-11-22'
RECORD = {
    'id': 'synthetic-1', 'title': 'Peter Zemmer Chardonnay Alto Adige DOC',
    'year': 2023, 'country': 'Италия', 'volume_l': 0.75,
    'stores': [{'url': URL, 'price_rub': None, 'regular_price_rub': None,
                'price_checked_at': None, 'reference_price_rub': 4790,
                'reference_regular_price_rub': None, 'reference_date': '2026-11-14'}]
}


def product():
    return {
        '@type': 'Product', 'name': 'Peter Zemmer Chardonnay Alto Adige DOC 2023 0.75 l',
        'brand': {'name': 'Peter Zemmer'}, 'url': URL, 'size': '0.75 l',
        'description': 'Synthetic test description', 'additionalProperty': [
            {'name': 'Аромат', 'value': 'Яблоко'}, {'name': 'Страна', 'value': 'Италия'}],
        'offers': {'@type': 'Offer', 'url': URL, 'price': '2 500',
                   'priceCurrency': 'RUB', 'oldPrice': '3 200'},
        'aggregateRating': {'ratingValue': 5, 'bestRating': 5, 'ratingCount': 12},
        'review': [
            {'author': 'Wine Enthusiast',
             'reviewRating': {'ratingValue': 94, 'bestRating': 100}},
            {'author': 'Jancis Robinson',
             'reviewRating': {'ratingValue': 16.5, 'bestRating': 20}}]
    }


def html(item=None, suffix=''):
    return '<html><title>Wine fixture</title><link rel="canonical" href="'+URL+'">' + \
        '<main><script type="application/ld+json">'+json.dumps(item or product())+'</script>'+ \
        suffix+'</main></html>'


class ExtractionTests(unittest.TestCase):
    def test_all_ratings_with_scales_count_provenance(self):
        details, current, regular = parser.extract(html(), RECORD, URL, DATE)
        self.assertEqual((current, regular), (2500, 3200))
        self.assertEqual(details['aroma'], 'Яблоко')
        self.assertEqual(details['volume_l'], 0.75)
        self.assertEqual([(r['source'], r['score'], r['scale']) for r in details['ratings']],
                         [('WineStyle users', 5, 5), ('Wine Enthusiast', 94, 100),
                          ('Jancis Robinson', 16.5, 20)])
        self.assertEqual(details['ratings'][0]['ratings_count'], 12)
        self.assertEqual(details['ratings'][0]['scope'], 'unspecified')
        self.assertEqual(details['ratings'][0]['source_url'], URL)

    def test_dom_scores_without_unrelated_recommendations(self):
        markup = '<aside><section class="ratings"><p>Wine Enthusiast 100/100</p></section></aside>' + \
            '<main><section class="ratings"><h2>Рейтинги</h2><p>Wine Enthusiast 94/100</p>' + \
            '<p>Jancis Robinson 16,5/20</p><p>Оценка покупателей: 5/5 - 12 оценок</p></section>' + \
            '<section class="recommended-ratings"><p>Wine Spectator 99/100</p></section></main>'
        got = extract_ratings(BeautifulSoup(markup, 'html.parser'), {}, URL, DATE)
        self.assertEqual({r['source']: r['score'] for r in got},
                         {'Wine Enthusiast': 94, 'Jancis Robinson': 16.5, 'WineStyle users': 5})

    def test_recommendation_nested_rating_not_included(self):
        markup = ('<main><section class="ratings"><h2>Рейтинги</h2>'
                  '<p>Wine Enthusiast 94/100</p>'
                  '<section class="recommended"><div class="ratings">'
                  '<p>Wine Enthusiast 99/100</p>'
                  '<p>Wine Spectator 98/100</p></div></section>'
                  '</section></main>')
        scores = extract_ratings(BeautifulSoup(markup, 'html.parser'), {}, URL, DATE)
        self.assertEqual([(r['source'], r['score']) for r in scores],
                         [('Wine Enthusiast', 94)])

    def test_recommendation_ancestor_not_included(self):
        markup = ('<main><section class="similar"><div class="ratings">'
                  '<p>Wine Spectator 99/100</p></div></section>'
                  '<section class="ratings"><p>Jancis Robinson 16.5/20</p>'
                  '</section></main>')
        scores = extract_ratings(BeautifulSoup(markup, 'html.parser'), {}, URL, DATE)
        self.assertEqual([(r['source'], r['score']) for r in scores],
                         [('Jancis Robinson', 16.5)])

    def test_main_product_attributes_exclude_recommendations(self):
        markup = html(suffix=(
            '<table class="product-specifications">'
            '<tr><th>Сорта винограда</th><td>Шардоне</td></tr>'
            '<tr><th>Регион</th><td>Альто-Адидже</td></tr></table>'
            '<section class="recommended-products"><div class="product-ratings">'
            '<table><tr><th>Сорта винограда</th><td>Сира</td></tr>'
            '<tr><th>Регион</th><td>Риоха</td></tr></table></div></section>'
            '<section class="comparison-table">'
            '<dl><dt>Сорта винограда</dt><dd>Темпранильо</dd></dl></section>'
        ))
        details, _, _ = parser.extract(markup, RECORD, URL, DATE)
        self.assertEqual(details['grapes'], 'Шардоне')
        self.assertEqual(details['region'], 'Альто-Адидже')

    def test_ambiguous_main_product_label_not_accepted(self):
        markup = html(suffix=(
            '<table><tr><th>Сорта винограда</th><td>Шардоне</td></tr>'
            '<tr><th>Сорта винограда</th><td>Сира</td></tr></table>'
        ))
        details, _, _ = parser.extract(markup, RECORD, URL, DATE)
        self.assertIsNone(details['grapes'])

    def test_unlabelled_ratings_not_accepted(self):
        markup = '<main><p>94/100</p><p>5/5</p><aside>Wine Enthusiast 94/100</aside></main>'
        self.assertEqual(extract_ratings(BeautifulSoup(markup, 'html.parser'), {}, URL, DATE), [])

    def test_conflicting_critic_ratings_dropped(self):
        item = product()
        item['review'].append({'author': 'Wine Enthusiast',
                               'reviewRating': {'ratingValue': 93, 'bestRating': 100}})
        got = parser.extract(html(item), RECORD, URL, DATE)[0]['ratings']
        self.assertNotIn('Wine Enthusiast', [r['source'] for r in got])

    def test_wrong_year_and_product_rejected(self):
        for name in ('Peter Zemmer Chardonnay Alto Adige DOC 2022 0.75 l',
                     'Peter Zemmer Pinot Noir 2023 0.75 l'):
            item = product()
            item['name'] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                parser.extract(html(item), RECORD, URL, DATE)

    def test_wrong_volume_rejected(self):
        item = product()
        item['size'] = '1.5 l'
        with self.assertRaises(ValueError):
            parser.extract(html(item), RECORD, URL, DATE)

    def test_unverified_discount_not_inferred(self):
        item = product()
        del item['offers']['oldPrice']
        item['offers']['highPrice'] = 4200
        self.assertEqual(parser.extract(html(item), RECORD, URL, DATE)[1:], (2500, None))

    def test_html_import_preserves_published_overlay_schema(self):
        record = copy.deepcopy(RECORD)
        store = record['stores'][0]
        store['product_details'] = {
            'source_url': URL, 'checked_at': '2026-11-21',
            'wine_style': 'Белое, Сухое',
            'pairing_notes': 'рыба, морепродукты',
            'description_excerpt': 'Older description.',
            'brand': 'Zemmer', 'availability_note': 'Ожидаем поступление',
            'field_evidence': {'pairing_notes': 'Подходит к: рыба'},
            'field_sources': {'pairing_notes': 'primary_product_table'},
            'ratings': [{
                'source': 'Wine Spectator', 'score': 88, 'scale': 100,
                'reported_by': 'WineStyle', 'source_url': URL,
                'observed_on': '2026-11-21', 'evidence': 'Wine Spectator 88/100'
            }]
        }
        details, current, regular = parser.extract(html(), record, URL, DATE)
        parser.apply_result(record, store, details, current, regular, {})
        result = store['product_details']
        self.assertEqual(result['description_excerpt'], 'Synthetic test description')
        self.assertEqual(result['pairing_notes'], 'рыба, морепродукты')
        self.assertEqual(result['wine_style'], 'Белое, Сухое')
        self.assertEqual(result['brand'], 'Zemmer')
        self.assertEqual(result['availability_note'], 'Ожидаем поступление')
        self.assertIn('Wine Spectator', [r['source'] for r in result['ratings']])
        self.assertIn('Jancis Robinson', [r['source'] for r in result['ratings']])
        self.assertEqual(result['field_checked_at']['pairing_notes'], '2026-11-21')
        self.assertEqual(result['field_checked_at']['description_excerpt'], DATE)
        self.assertEqual(result['field_evidence']['pairing_notes'], 'Подходит к: рыба')
        self.assertEqual(store['enrichment_status']['method'], 'offline_html')

    def test_stale_field_evidence_cleared_after_replacement(self):
        record = copy.deepcopy(RECORD)
        store = record['stores'][0]
        store['product_details'] = {
            'source_url': URL, 'checked_at': '2026-11-21',
            'description_excerpt': 'old',
            'field_evidence': {'description_excerpt': 'old literal text'}
        }
        details, current, regular = parser.extract(html(), record, URL, DATE)
        parser.apply_result(record, store, details, current, regular, {})
        result = store['product_details']
        self.assertEqual(result['description_excerpt'], 'Synthetic test description')
        self.assertEqual(result['field_evidence'], {})

    def test_retain_older_price_if_latest_html_has_no_offer(self):
        record = copy.deepcopy(RECORD)
        store = record['stores'][0]
        store.update(price_rub=3490, price_checked_at='2026-11-21',
                     price_source_url=URL, regular_price_rub=None)
        item = product()
        item['offers'] = []
        details, current, regular = parser.extract(html(item), record, URL, DATE)
        self.assertIsNone(current)
        parser.apply_result(record, store, details, current, regular, {})
        self.assertEqual(store['price_rub'], 3490)
        self.assertEqual(store['price_checked_at'], '2026-11-21')
        self.assertEqual(store['product_details']['checked_at'], DATE)

    def test_out_of_stock_without_price_still_supersedes_old_stock(self):
        record = copy.deepcopy(RECORD)
        store = record['stores'][0]
        store['product_details'] = {
            'source_url': URL, 'checked_at': '2026-11-21',
            'availability_spb': True,
            'availability_note': 'В наличии'
        }
        item = product()
        item['offers'] = {
            '@type': 'Offer', 'url': URL, 'eligibleRegion': 'Saint Petersburg',
            'availability': 'https://schema.org/OutOfStock'
        }
        details, current, regular = parser.extract(html(item), record, URL, DATE)
        self.assertIs(details['availability_spb'], False)
        self.assertIsNone(current)
        parser.apply_result(record, store, details, current, regular, {})
        self.assertIs(store['product_details']['availability_spb'], False)
        self.assertNotIn('availability_note', store['product_details'])

    def test_non_spb_offer_price_is_not_accepted(self):
        item = product()
        item['offers'] = {
            '@type': 'Offer', 'url': URL, 'eligibleRegion': 'Moscow',
            'priceCurrency': 'RUB', 'price': '3000',
            'availability': 'https://schema.org/InStock'
        }
        details, current, regular = parser.extract(html(item), RECORD, URL, DATE)
        self.assertIsNone(current)
        self.assertIsNone(details['availability_spb'])
        self.assertIsNone(regular)

    def test_regional_price_ignores_moscow_when_spb_price_is_valid(self):
        item = product()
        item['offers'] = [
            {'@type': 'Offer', 'url': URL, 'eligibleRegion': 'Moscow',
             'priceCurrency': 'RUB', 'price': '3000'},
            {'@type': 'Offer', 'url': URL, 'eligibleRegion': 'Saint Petersburg',
             'priceCurrency': 'RUB', 'price': '2500',
             'availability': 'https://schema.org/InStock'}
        ]
        details, current, regular = parser.extract(html(item), RECORD, URL, DATE)
        self.assertEqual(current, 2500)
        self.assertIsNone(regular)
        self.assertIs(details['availability_spb'], True)

    def test_conflicting_stock_offers_are_not_accepted(self):
        item = product()
        item['offers'] = [
            {'@type': 'Offer', 'url': URL, 'eligibleRegion': 'Saint Petersburg',
             'availability': 'https://schema.org/InStock'},
            {'@type': 'Offer', 'url': URL, 'eligibleRegion': 'Saint Petersburg',
             'availability': 'https://schema.org/OutOfStock'}
        ]
        details, price, _ = parser.extract(html(item), RECORD, URL, DATE)
        self.assertIsNone(details['availability_spb'])
        self.assertIsNone(price)

    def test_new_explicit_stock_status_replaces_older_waiting_note(self):
        record = copy.deepcopy(RECORD)
        store = record['stores'][0]
        store['product_details'] = {
            'source_url': URL, 'checked_at': '2026-11-21',
            'availability_note': 'Ожидаем поступление',
            'field_sources': {'availability_note': 'older retail capture'},
            'field_evidence': {'availability_note': 'Ожидаем поступление'},
            'field_checked_at': {'availability_note': '2026-11-21'}
        }
        item = product()
        item['offers']['eligibleRegion'] = 'Санкт-Петербург'
        item['offers']['availability'] = 'https://schema.org/InStock'
        details, current, regular = parser.extract(html(item), record, URL, DATE)
        self.assertIs(details['availability_spb'], True)
        parser.apply_result(record, store, details, current, regular, {})
        merged = store['product_details']
        self.assertNotIn('availability_note', merged)
        self.assertNotIn('availability_note', merged['field_sources'])
        self.assertNotIn('availability_note', merged['field_checked_at'])
        self.assertNotIn('availability_note', merged['field_evidence'])
        self.assertIs(merged['availability_spb'], True)

    def test_retained_text_volume_promoted_as_numeric_litres(self):
        record = copy.deepcopy(RECORD)
        record["volume_l"] = None
        store = record["stores"][0]
        store["product_details"] = {
            "source_url": URL, "checked_at": "2026-11-21",
            "volume_l": "0.75 л"
        }
        item = product()
        del item["size"]
        item["name"] = item["name"].replace(" 0.75 l", "")
        details, current, regular = parser.extract(html(item), record, URL, DATE)
        self.assertIsNone(details["volume_l"])
        parser.apply_result(record, store, details, current, regular, {})
        self.assertEqual(record["volume_l"], 0.75)
        self.assertIsInstance(record["volume_l"], float)

    def test_newer_snapshot_is_not_downgraded(self):
        record = copy.deepcopy(RECORD)
        store = record['stores'][0]
        store['product_details'] = {'source_url': URL, 'checked_at': '2026-11-23'}
        details, current, regular = parser.extract(html(), record, URL, DATE)
        with self.assertRaisesRegex(ValueError, 'older_observation'):
            parser.apply_result(record, store, details, current, regular, {})

    def test_null_previous_enrichment_is_accepted(self):
        record = copy.deepcopy(RECORD)
        store = record['stores'][0]
        store['product_details'] = None
        details, current, regular = parser.extract(html(), record, URL, DATE)
        parser.apply_result(record, store, details, current, regular, {})
        self.assertEqual(store['product_details']['producer'], 'Peter Zemmer')
        self.assertEqual(store['price_rub'], 2500)

    def test_retain_original_values_and_archive(self):
        record = copy.deepcopy(RECORD)
        before = copy.deepcopy(record['stores'][0])
        details, price, regular = parser.extract(html(), record, URL, DATE)
        parser.apply_result(record, record['stores'][0], details, price, regular, {})
        self.assertEqual(record['stores'][0]['reference_price_rub'], before['reference_price_rub'])
        self.assertEqual(record['stores'][0]['product_details']['ratings'][1]['score'], 94)
        self.assertEqual(record['country'], RECORD['country'])


class OfflineWorkflowTests(unittest.TestCase):
    def test_saved_page_import_uses_no_http_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            catalog, report, access = path/'catalog.json', path/'run.json', path/'access.json'
            parser.atomic_json(catalog, {'records': [copy.deepcopy(RECORD)]})
            (path/'wine.html').write_text(html(), encoding='utf-8')
            parser.atomic_json(path/'manifest.json',
                               [{'url': URL, 'file': 'wine.html', 'checked_at': DATE}])
            args = ['--catalog', str(catalog), '--report', str(report),
                    '--access-state', str(access), '--input-dir', str(path)]
            with patch.object(parser, 'fetch', side_effect=AssertionError('network forbidden')):
                with patch('sys.stdout', new_callable=io.StringIO):
                    self.assertEqual(parser.main(args), 0)
                    first = catalog.read_bytes()
                    self.assertEqual(parser.main(args), 0)
                    self.assertEqual(first, catalog.read_bytes())
            self.assertEqual(json.loads(first)['records'][0]['stores'][0]['product_details']['ratings'][1]['score'], 94)

    def test_first_saved_html_creates_manifest_for_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            catalog, report, access = path/'catalog.json', path/'run.json', path/'access.json'
            parser.atomic_json(catalog, {'records': [copy.deepcopy(RECORD)]})
            (path/'wine.html').write_text(html(), encoding='utf-8')
            parser.atomic_json(path/'manifest.json', [
                {'url': URL, 'file': 'wine.html', 'checked_at': DATE}
            ])
            with patch.object(parser, 'fetch', side_effect=AssertionError('network forbidden')):
                with patch('sys.stdout', new_callable=io.StringIO):
                    status = parser.main([
                        '--catalog',str(catalog),'--report',str(report),
                        '--access-state',str(access),'--input-dir',str(path)
                    ])
            self.assertEqual(status, 0)
            result = json.loads(catalog.read_text(encoding='utf-8'))
            manifest = result['retailer_snapshot']
            self.assertEqual(manifest['source_capture_kind'], 'offline_saved_html')
            self.assertEqual(manifest['matched_exact_products'], 1)
            self.assertEqual(manifest['direct_price_observations'], 1)
            self.assertEqual(manifest['retailer_reported_ratings'], 3)
            self.assertEqual(manifest['observed_on'], DATE)
            self.assertEqual(len(manifest['source_export_sha256']), 64)

    def test_older_separate_html_does_not_relabel_existing_capture_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            url2 = URL.replace('2023', '2022')
            old = copy.deepcopy(RECORD)
            old_store = old['stores'][0]
            old_store.update(
                product_details={'source_url': URL, 'checked_at': DATE,
                                 'full_name': 'Peter Zemmer Chardonnay Alto Adige DOC 2023',
                                 'producer': 'Peter Zemmer', 'ratings': []},
                enrichment_status={'status': 'verified', 'source_url': URL,
                                   'checked_at': DATE}
            )
            rec2 = copy.deepcopy(RECORD)
            rec2.update(id='another-wine', year=2022)
            rec2['stores'][0]['url'] = url2
            catalog = path/'catalog.json'
            report = path/'report.json'
            access = path/'access.json'
            parser.atomic_json(catalog, {
                'records': [old, rec2],
                'retailer_snapshot': {
                    'retailer': 'WineStyle', 'source': 'user_supplied_browser_capture',
                    'source_export_sha256': 'a'*64, 'observed_on': DATE,
                    'mismatched_urls': []
                }
            })
            product2 = product()
            product2['url'] = url2
            product2['name'] = product2['name'].replace('2023', '2022')
            body = ('<html><link rel="canonical" href="' + url2 +
                    '"><main><script type="application/ld+json">' +
                    json.dumps(product2) + '</script></main></html>')
            (path/'older.html').write_text(body, encoding='utf-8')
            parser.atomic_json(path/'manifest.json', [{
                'url': url2, 'file': 'older.html', 'checked_at': '2026-11-21'
            }])
            with patch.object(parser, 'fetch', side_effect=AssertionError('no network')):
                with patch('sys.stdout', new_callable=io.StringIO):
                    status = parser.main([
                        '--catalog', str(catalog), '--report', str(report),
                        '--access-state', str(access), '--input-dir', str(path)
                    ])
            self.assertEqual(status, 0)
            snapshot = json.loads(catalog.read_text(encoding='utf-8'))['retailer_snapshot']
            self.assertEqual(snapshot['observed_on'], DATE)
            self.assertEqual(snapshot['source_export_sha256'], 'a'*64)
            self.assertEqual(snapshot['earliest_observed_on'], '2026-11-21')
            self.assertEqual(snapshot['latest_observed_on'], DATE)
            self.assertEqual(snapshot['additional_capture_sources'][0]['observed_on'],
                             '2026-11-21')

    def test_two_saved_pages_import_without_manifest_shadowing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            url2 = URL.replace('2023', '2022')
            rec2 = copy.deepcopy(RECORD)
            rec2.update(id='synthetic-2', year=2022)
            rec2['stores'][0]['url'] = url2
            catalog, report, access = path/'catalog.json', path/'run.json', path/'access.json'
            parser.atomic_json(catalog, {'records': [copy.deepcopy(RECORD), rec2]})
            (path/'one.html').write_text(html(), encoding='utf-8')
            p2 = product()
            p2['url'] = url2
            p2['name'] = p2['name'].replace('2023', '2022')
            body2 = ('<html><link rel="canonical" href="' + url2 +
                     '"><main><script type="application/ld+json">' +
                     json.dumps(p2) + '</script></main></html>')
            (path/'two.html').write_text(body2, encoding='utf-8')
            parser.atomic_json(path/'manifest.json', [
                {'url': URL, 'file': 'one.html', 'checked_at': DATE},
                {'url': url2, 'file': 'two.html', 'checked_at': DATE}
            ])
            with patch.object(parser, 'fetch', side_effect=AssertionError('network forbidden')):
                with patch('sys.stdout', new_callable=io.StringIO):
                    status = parser.main(['--catalog',str(catalog),'--report',str(report),
                                          '--access-state',str(access),
                                          '--input-dir',str(path)])
            self.assertEqual(status, 0)
            run = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(run['successful'], 2)
            self.assertEqual(run['skipped'], 0)
            records = json.loads(catalog.read_text(encoding='utf-8'))['records']
            self.assertTrue(all(r['stores'][0]['product_details']['producer'] == 'Peter Zemmer'
                                for r in records))

    def test_persisted_403_blocks_all_network_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            catalog, report, access = path/'catalog.json', path/'run.json', path/'access.json'
            parser.atomic_json(catalog, {'records': [copy.deepcopy(RECORD)]})
            parser.atomic_json(access, {'blocked': True, 'reason': 'HTTP 403 previously observed'})
            original = catalog.read_bytes()
            with patch.object(parser, 'fetch', side_effect=AssertionError('network forbidden')):
                with patch('sys.stdout', new_callable=io.StringIO):
                    self.assertEqual(parser.main(['--catalog', str(catalog), '--report', str(report),
                                                  '--access-state', str(access),
                                                  '--dry-run', '--headed']), 2)
            self.assertEqual(original, catalog.read_bytes())


if __name__ == '__main__':
    unittest.main()
