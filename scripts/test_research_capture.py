import unittest
from report_research_capture import report
from auto_research import inspect_offer
from import_research import join, merge, parse_offer, parse_rates, parse_review, window


class CaptureTests(unittest.TestCase):
    def test_falstaff_reads_german_points_and_keeps_tasting_date_separate(self):
        result = parse_review({'title': '2026 The First Lady Chardonnay',
                               'url': 'https://www.falstaff.com/at/weine/example',
                               'observed_at': '2026-11-24T12:00:00Z', 'blocks': {
                                   'producer': 'Warwick Estate',
                                   'review': 'Jahrgang 2026; mit 90 Falstaff-Punkten bewertet.\nPreis: bis 10 €'}},
                              'falstaff.com')
        self.assertEqual((result['year'], result['score'], result['scale'], result['amount']), (2026, 90, 100, '10'))
        self.assertIsNone(result['end'])

    def test_report_does_not_promote_observations(self):
        bundle = {'version': 1, 'kind': 'wine_atlas_research_capture', 'observations': [
            {'url': 'https://spb.luding.ru/collection/item/a/', 'source': 'Luding', 'status': 'needs_review'},
            {'url': 'https://www.falstaff.com/at/weine/', 'source': 'Falstaff', 'status': 'blocked'}]}
        result = report(bundle)
        self.assertEqual(result['catalog_updates'], 0)
        self.assertEqual(result['sources']['Falstaff']['blocked'], 1)

    def test_reject_bad_capture_url(self):
        with self.assertRaises(ValueError):
            report({'version': 1, 'kind': 'wine_atlas_research_capture', 'observations': [{'url': 'file:///private'}]})

    def test_luding_supplier_requires_city(self):
        review = {'name': 'Ramon Bilbao Crianza Rioja Reserva 2022', 'year': 2022}
        html = '<h1>Ramon Bilbao Crianza Rioja Reserva 2022 0.75 л</h1><p>Санкт-Петербург</p><p>В наличии у поставщика</p>'
        url = 'https://spb.luding.ru/collection/item/example/'
        self.assertEqual(inspect_offer(html, url, review)[1], 'candidate')
        self.assertEqual(inspect_offer(html.replace('Санкт-Петербург', 'Москва'), url, review)[1], 'spb_not_confirmed')

    def test_drinking_window_never_uses_tasting_date(self):
        self.assertEqual(window('Tasting from 14.10.2025. Issue Date 2029. Drink now.'), (None, None))
        self.assertEqual(window('Drinking Window\n2025 – 2034'), (2025, 2034))
        self.assertEqual(window('Drink now through 2029.'), (None, 2029))

    def test_join_verified_rioja_and_reject_wrong_vintage(self):
        date, rates = parse_rates('<ValCurs Date="24.11.2026"><Valute><CharCode>USD</CharCode><Nominal>1</Nominal><Value>82,1488</Value></Valute></ValCurs>')
        critic = {'url': 'https://www.wineenthusiast.com/buying-guide/ramon-bilbao-2022/',
                  'title': 'Bodegas Ramón Bilbao 2022 Crianza Tempranillo (Rioja)',
                  'blocks': {'review': 'Rating\n90\nPrice\n$17\nDrink now through 2029.'}}
        seller = {'url': 'https://sabonis.ru/productDetail/vino-ramon-bilbao-kriansa-doc-riokha-10',
                  'title': 'Вино Рамон Бильбао Крианса DOC Риоха', 'source': 'Sabonis',
                  'blocks': {'product': '1 580 ₽\nНаличие: Петроградская наб., 8 - 6 шт.',
                             'document_title': 'Купить Вино Ramon Bilbao Crianza DOC Риоха 2022 года 0.75 л. 2022.: цена 1580 ₽ в СПб'}}
        aliases = {r['url']: 'Ramón Bilbao Crianza Rioja DOCa' for r in (critic, seller)}
        bundle = {'kind': 'wine_atlas_research_capture', 'version': 1,
                  'observations': [dict(r, status='needs_review', observed_at='2026-11-23T23:00:00Z') for r in (critic, seller)]}
        accepted, unresolved = join(bundle, date, rates, aliases)
        self.assertFalse(unresolved)
        self.assertEqual(accepted[0]['foreign_reference']['amount_rub'], 1396.53)
        self.assertEqual(accepted[0]['stores'][0]['price_rub'], 1580)
        self.assertEqual(merge(accepted, accepted, [], {}), [])
        seller['blocks']['document_title'] = seller['blocks']['document_title'].replace('2022', '2021')
        self.assertFalse(join(bundle, date, rates, aliases)[0])

    def test_luding_structured_offer_requires_selected_city(self):
        row = {'title': 'Domaine Example 2022', 'url': 'https://spb.luding.ru/collection/item/example/',
               'observed_at': '2026-11-24T12:00:00Z',
               'blocks': {'product': 'Domaine Example 2022\n2 100 ₽\nВ наличии у поставщика',
                          'document_title': 'Domaine Example 2022 0.75 л', 'city': 'Санкт-Петербург'}}
        self.assertEqual(parse_offer(row, 'spb.luding.ru')['stock'], 'supplier_stock')
        row['blocks']['city'] = 'Москва'
        self.assertIsNone(parse_offer(row, 'spb.luding.ru'))

    def test_vinissimo_uses_availability_for_selected_vintage_and_volume_control(self):
        row = {'title': 'Фоскарино Соаве Классико', 'url': 'https://vinissimo.biz/catalog/wine/example-1/',
               'observed_at': '2026-11-24T12:00:00Z', 'blocks': {
                   'document_title': 'Фоскарино Соаве Классико 2023 — купить | Vinissimo', 'city': 'Санкт-Петербург',
                   'product': 'Фоскарино Соаве Классико\nFoscarino Soave Classico\nОбъём\n0.75\nГод урожая\n2023\nОбъёмы:\n0.75 л\n2022 г. - 4999 руб\nнет в наличии\n2023 г. - 4999 руб\nв наличии'}}
        offer = parse_offer(row, 'vinissimo.biz')
        self.assertEqual((offer['year'], offer['volume_l'], offer['price']), (2023, 0.75, 4999))
        row['blocks']['product'] = row['blocks']['product'].replace('Год урожая\n2023', 'Год урожая\n2022')
        self.assertIsNone(parse_offer(row, 'vinissimo.biz'))


if __name__ == '__main__':
    unittest.main()
