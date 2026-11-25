import unittest
from decimal import Decimal
from report_research_capture import report
from auto_research import inspect_offer
from import_research import join, merge, parse_offer, parse_rates, parse_review, reconcile, window


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

    def test_report_separates_store_rating_leads_and_publisher_scores(self):
        bundle = {'version': 1, 'kind': 'wine_atlas_research_capture', 'observations': [
            {'source': 'SimpleWine', 'url': 'https://simplewine.ru/catalog/product/example/',
             'status': 'needs_review', 'title': 'Вино Example Producer 2024',
             'blocks': {'critic_hints': 'JS 90.0\nWS\n92.0\nVIVINO 4.1\nRP 84.0'}},
            {'source': 'Wine Spectator', 'url': 'https://top100.winespectator.com/2025/wine/example/',
             'status': 'needs_review', 'title': 'Example Producer Wine 2024',
             'observed_at': '2026-11-25T10:00:00Z',
             'blocks': {'review': 'Score\n92\nPrice\n$25\nTasting Note\nDrink now through 2030.'}},
            {'source': 'SimpleWine', 'url': 'https://simplewine.ru/catalog/vino/',
             'status': 'needs_review', 'discovery': {
                 'visible_details': 35, 'eligible_details': 35, 'queued_details': 25,
                 'detail_limit': 25, 'next_found': True, 'next_queued': False}},
        ]}
        result = report(bundle)
        self.assertEqual(result['catalog_updates'], 0)
        self.assertEqual(result['coverage']['Wine Spectator']['parsed_numeric_ratings'], 1)
        self.assertEqual(result['coverage']['Wine Spectator']['parsed_drinking_windows'], 1)
        self.assertEqual(result['coverage']['SimpleWine']['catalog_pages_hitting_detail_limit'], 1)
        self.assertEqual(result['coverage']['SimpleWine']['catalog_pages_hitting_pagination_limit'], 1)
        hints, = result['retailer_rating_leads']
        self.assertEqual(hints['year'], 2024)
        self.assertEqual(hints['status'], 'needs_primary_review')
        self.assertEqual([x['source'] for x in hints['reported_ratings']], ['James Suckling', 'Wine Spectator'])

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

    def test_luding_confirms_current_discount_with_visible_card_price(self):
        row = {'title': 'Вино Adagum Cabernet Franc 2024 0.75 л',
               'url': 'https://spb.luding.ru/collection/item/example/',
               'observed_at': '2026-11-24T18:30:00Z', 'blocks': {
                   'product': '501 ₽\n835 ₽\nВ корзину\nВ НАЛИЧИИ\nМНОГО\nОтзывы\nНет в наличии',
                   'document_title': 'Adagum Cabernet Franc 0,75 л купить в магазине в Санкт-Петербурге по цене 501 ₽',
                   'city': 'Санкт-Петербург'}}
        offer = parse_offer(row, 'spb.luding.ru')
        self.assertEqual((offer['year'], offer['price'], offer['stock']), (2024, 501, 'in_stock'))
        row['blocks']['document_title'] = row['blocks']['document_title'].replace('501', '499')
        self.assertIsNone(parse_offer(row, 'spb.luding.ru'))
        row['blocks']['document_title'] = row['blocks']['document_title'].replace('499', '501')
        row['title'] = row['title'].replace('2024', '')
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

    def test_other_store_cards_require_local_variant_price_and_stock(self):
        label = 'Domaine Example 2022'
        shared = 'Объём:\n0,75 л\nЦена: 4 975,20 ₽\nВ наличии в магазине'
        examples = {
            'winelab.ru': shared,
            'amwine.ru': shared,
            'joia.ru': shared,
            'simplewine.ru': 'Объем: 0.75 л\nЗабрать сегодня из 2 винотек\n2022 г. — 4 975,20 ₽\nв наличии',
            'ast.wine': 'Объем: 0.75 л\n4 975,20 ₽\nНаличие\nул. Жуковского, 22\nМаяковская\nМало',
        }
        for host, product in examples.items():
            with self.subTest(host=host):
                row = {'title': label, 'url': f'https://{host}/product/example',
                       'observed_at': '2026-11-24T12:00:00Z',
                       'blocks': {'city': 'Санкт-Петербург', 'product': product}}
                result = parse_offer(row, host)
                self.assertEqual((result['year'], result['volume_l'], result['price']), (2022, 0.75, 4975.20))
                row['blocks']['product'] += '\nГод урожая: 2021'
                self.assertIsNone(parse_offer(row, host))
                row['blocks'].update(city='Москва', product=product)
                self.assertIsNone(parse_offer(row, host))

    def test_import_reprices_critic_queue_and_supersedes_stale_stock(self):
        wine = 'Domaine Example'
        review = {'title': wine, 'year': 2022, 'score': 17, 'scale': 20, 'source': 'Example Critic',
                  'url': 'https://critic.example/review', 'start': 2024, 'end': 2029, 'currency': 'USD',
                  'amount': 60, 'price_kind': 'exact', 'date': '2026-11-23'}
        queue = {'kind': 'wine_atlas_critic_queue', 'version': 1,
                 'vintages': [{'title': wine, 'year': 2022, 'evidence': [review]}]}
        local = {'url': 'https://sabonis.ru/productDetail/example', 'title': wine,
                 'status': 'needs_review', 'observed_at': '2026-11-24T12:00:00Z', 'blocks': {
                     'product': '5 000 ₽\nНаличие: Петроградская наб., 8 - 1 шт.',
                     'document_title': 'Купить Вино Domaine Example 2022 0.75 л. цена 5000 ₽ в СПб'}}
        checked_on = '2026-11-24'
        rates = {'USD': Decimal('100')}
        report = reconcile([local], checked_on, rates, {}, checked_on, queue)
        self.assertEqual(report['eligible'][0]['critic_ratings'][0]['scale'], 20)
        self.assertEqual(report['eligible'][0]['foreign_reference']['amount_rub'], 6000)
        self.assertEqual(report['retailer_matches'][0]['result'], 'matched')
        self.assertFalse(reconcile([local], checked_on, {'USD': Decimal('100.01')}, {}, checked_on, queue)['eligible'])

        latest = dict(local, observed_at='2026-11-24T13:00:00Z', status='no_heading')
        report = reconcile([latest, local], checked_on, rates, {}, checked_on, queue)
        self.assertFalse(report['eligible'])
        self.assertEqual(report['retailer_matches'][0]['result'], 'no_exact_offer')
        wrong = dict(local, blocks=dict(local['blocks'], document_title=local['blocks']['document_title'].replace('2022', '2021')))
        self.assertFalse(reconcile([wrong], checked_on, rates, {}, checked_on, queue)['eligible'])

    def test_ast_selected_variant_may_include_its_price_on_second_line(self):
        row = {'title': 'Domaine Example', 'url': 'https://ast.wine/catalog/product/example/',
               'observed_at': '2026-11-24T18:30:00Z', 'blocks': {
                   'city': 'Санкт-Петербург', 'product': 'Объем:\t0.75 л',
                   'selected_variant': '2023, 0.75 л\n2 370 ₽', 'offer_price': '2 370 ₽',
                   'local_shops': 'ул. Жуковского, 22 | Мало'}}
        offer = parse_offer(row, 'ast.wine')
        self.assertEqual((offer['year'], offer['price'], offer['volume_l']), (2023, 2370, 0.75))
        row['blocks']['selected_variant'] = '2023, 0.75 л\n2024, 0.75 л'
        self.assertIsNone(parse_offer(row, 'ast.wine'))

    def test_orderable_winestyle_is_distinct_from_local_stock(self):
        wine = 'Domaine Example'
        date = '2026-11-24'
        row = {'url': 'https://spb.winestyle.ru/products/example.html', 'title': wine + ' 2022',
               'status': 'needs_review', 'observed_at': date + 'T12:00:00Z', 'blocks': {
                   'price_stock': '4 000 ₽\nДоступно под заказ', 'document_title': 'Domaine Example 2022 0.75 л'}}
        evidence = {'title': wine, 'year': 2022, 'score': 90, 'scale': 100, 'start': 2023,
                    'end': 2030, 'date': date, 'url': 'https://critic.example/review',
                    'source': 'Critic', 'currency': 'USD', 'amount': 20, 'price_kind': 'exact'}
        queue = {'vintages': [{'title': wine, 'year': 2022, 'evidence': [evidence]}]}
        report = reconcile([row], date, {'USD': Decimal(100)}, {}, date, queue)
        self.assertFalse(report['eligible'])
        self.assertEqual(report['retailer_matches'][0]['result'], 'local_stock_unconfirmed')


if __name__ == '__main__':
    unittest.main()
