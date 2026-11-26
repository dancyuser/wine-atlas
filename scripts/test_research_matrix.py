import unittest

from import_research import parse_review
from research_matrix import STORES, build_matrix, candidate_id, matrix_key, search_plan
from research_sitemaps import product_candidates, sitemap_link, sitemap_urls


DATE = '2026-11-25'
STAMP = DATE + 'T10:00:00Z'


def capture(*rows):
    return {'version': 1, 'kind': 'wine_atlas_research_capture', 'observations': list(rows)}


def row(url, title, blocks=None, **fields):
    return {'url': url, 'requested_url': url, 'title': title, 'blocks': blocks or {},
            'status': 'needs_review', 'observed_at': STAMP, **fields}


class MatrixTests(unittest.TestCase):
    def test_publisher_note_only_uses_explicit_score(self):
        base = row('https://www.jamessuckling.com/tasting-notes/1/example-2023', 'Domaine Example 2023')
        base['blocks']['review'] = 'Score\nAvg Price (ex-tax) $ 23\nDomaine Example 2023'
        self.assertIsNone(parse_review(base, 'jamessuckling.com')['score'])
        base['blocks']['review'] = 'Score\n92\nAvg Price (ex-tax) $ 23\nDomaine Example 2023'
        self.assertEqual(parse_review(base, 'jamessuckling.com')['score'], 92)

    def test_public_index_prefers_producer_over_region(self):
        origin = 'https://spb.winestyle.ru'
        index = {'stores': {'WineStyle': {'products': [
            origin + '/products/Caymus-Cabernet-Sauvignon-Napa-Valley-2021.html',
            origin + '/products/Faust-Cabernet-Sauvignon-Napa-Valley-2021.html',
        ]}}}
        hits, sizes = product_candidates(
            [{'id': 'faust', 'title': 'Faust Cabernet Sauvignon Napa Valley', 'year': 2021}], index)
        self.assertEqual(sizes['WineStyle'], 2)
        self.assertEqual(hits['faust', 'WineStyle'], [
            origin + '/products/Faust-Cabernet-Sauvignon-Napa-Valley-2021.html'])
        self.assertTrue(sitemap_link(origin + '/sitemap.php?data=prods&page=3', 'spb.winestyle.ru'))
        self.assertFalse(sitemap_link(origin + '/sitemap.php?data=reviews&page=3', 'spb.winestyle.ru'))
        kind, links = sitemap_urls(b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url>'
                                   b'<loc>https://wine.test/product/123</loc></url></urlset>')
        self.assertEqual((kind, links), ('urlset', ['https://wine.test/product/123']))

    def test_all_store_pairs_and_distinct_evidence(self):
        wine = 'Domaine Exemple Cuvée'
        critic = {'url': 'https://www.wineenthusiast.com/buying-guide/exemple/', 'title': wine,
                  'source': 'Wine Enthusiast', 'year': 2022, 'score': 91, 'scale': 100, 'end': None}
        product = row('https://simplewine.ru/catalog/product/exemple/',
                      f'Вино {wine}, 2022, 0.375л',
                      {'city': 'Санкт-Петербург', 'product': '2022 г. — 2 890 ₽\nв наличии\nЗабрать сегодня из 2 винотек',
                       'critic_hints': 'JS 90.0\nAG 91.5\nPENIN 90.0'})
        other = row('https://spb.luding.ru/collection/item/exemple/', f'Вино {wine} 2024 0.75л',
                    {'city': 'Санкт-Петербург', 'product': '2 100 ₽\nВ наличии у поставщика',
                     'document_title': f'{wine} 2024 0.75 л'})
        target = row('https://ast.wine/search/?q=exemple', 'Результаты поиска',
                     lookup={'id': candidate_id(matrix_key(wine, 2022)), 'role': 'query'})
        target['status'] = 'no_results'
        out = build_matrix([capture(product, other, target)], {}, {}, DATE, [critic])
        self.assertEqual(tuple(out['wines'][0]['stores']), STORES)
        self.assertEqual(len(out['wines']), 1)
        item = out['wines'][0]
        self.assertEqual([rating['score'] for rating in item['published_ratings']], [91])
        self.assertEqual(len(item['retailer_claims'][0]['reported_ratings']), 3)
        self.assertEqual(item['stores']['SimpleWine']['status'], 'matched')
        self.assertEqual(item['stores']['SimpleWine']['price_rub'], 2890)
        self.assertEqual(item['stores']['Luding']['status'], 'other_vintage')
        self.assertIsNone(item['stores']['Luding']['spb_stock'])
        self.assertEqual(item['stores']['AST.WINE']['status'], 'search_no_results')
        self.assertEqual(item['stores']['Joia']['status'], 'not_checked')
        self.assertEqual(search_plan(out)['wines'],
                         [{'id': item['id'], 'title': wine, 'year': 2022}])

    def test_store_reported_score_stays_visible_with_no_primary_score_or_stock(self):
        url = 'https://simplewine.ru/catalog/product/limited/'
        product = row(url, 'Вино Domaine Limited 2023, 0.75л',
                      {'city': 'Санкт-Петербург', 'product': '2023 г. — 5 900 ₽\nнет в наличии',
                       'critic_hints': 'PENIN 89.0'})
        result = build_matrix([capture(product)], {}, {}, DATE)['wines'][0]
        self.assertEqual(result['published_ratings'], [])
        self.assertEqual(result['retailer_claims'][0]['reported_ratings'][0]['score'], 89)
        offer = result['stores']['SimpleWine']
        self.assertEqual(offer['status'], 'out_of_stock')
        self.assertFalse(offer['spb_stock'])
        self.assertFalse(offer['price_within_budget'])


if __name__ == '__main__':
    unittest.main()
