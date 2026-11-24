import unittest
from auto_research import extract_links, parse_review, inspect_offer, parse_search_rss


class ResearchTest(unittest.TestCase):
    def test_review_extracts_exact_vintage_and_window(self):
        html = '''<h1>Bodegas Ramon Bilbao 2022 Crianza Tempranillo (Rioja)</h1>
        <div>Rating</div><div>90</div><div>Price</div><div>$17</div>
        <p>Drink now through 2029.</p><h2>What Is Blind Tasting?</h2>'''
        row = parse_review(html, 'https://www.wineenthusiast.com/buying-guide/example/')
        self.assertEqual((row['year'], row['score'], row['drink_until']), (2022, 90, 2029))
        self.assertEqual(row['foreign_price'], 17)
        self.assertIsNone(parse_review(html.replace('through 2029', 'through 2026'), row['critic_url']))
        self.assertIsNone(parse_review(html.replace('Rating</div><div>90', 'Rating</div><div>84'), row['critic_url']))

    def test_same_year_and_variant_are_not_inferred_from_recommendations(self):
        review = {'name':'Bodegas Ramon Bilbao 2022 Crianza Tempranillo Rioja', 'year':2022}
        html = '''<title>Ramon Bilbao Crianza 2022 0.75 �</title>
        <h1>Ramon Bilbao Crianza 2022 0.75 �</h1><p>����稥: �㪮�᪮��, 10 - 12 ��.</p>'''
        found, reason = inspect_offer(html, 'https://sabonis.ru/productDetail/example', review)
        self.assertEqual(reason, 'candidate')
        self.assertEqual(found['status'], 'needs_price_and_stock_verification')
        wrong = html.replace('2022', '2021') + '<p>�������������� ⮢��� Ramon Bilbao Crianza 2022</p>'
        self.assertIsNone(inspect_offer(wrong, 'https://sabonis.ru/productDetail/example', review)[0])
        self.assertIsNone(inspect_offer(html.replace('0.75 �', '1.5 �'), 'https://sabonis.ru/productDetail/example', review)[0])

    def test_urls_are_scoped(self):
        html = '<a href="/buying-guide/foo/">x</a><a href="https://elsewhere.com/buying-guide/bar/">y</a>'
        self.assertEqual(extract_links(html, 'https://www.wineenthusiast.com/wine-ratings/'), ['https://www.wineenthusiast.com/buying-guide/foo/'])
        xml = '<rss><channel><item><link>https://sabonis.ru/product/1</link></item><item><link>https://sabonis.ru.evil.test/product/2</link></item></channel></rss>'
        self.assertEqual(parse_search_rss(xml, 'sabonis.ru'), ['https://sabonis.ru/product/1'])


if __name__ == '__main__':
    unittest.main()

