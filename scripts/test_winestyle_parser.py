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
