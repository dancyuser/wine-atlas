import unittest
from decimal import Decimal

from import_research import parse_reviews, window
from stage_critic_research import botti_observations, browser_observations, stage


class CriticStageTest(unittest.TestCase):
    def test_vinous_public_countdown_pairs_each_printed_score_with_its_wine(self):
        row = {
            'url': 'https://billing.vinous.com/articles/vinous-top-100-wines-of-2024-5-2-nov-2024',
            'title': 'Vinous Top 100 Wines',
            'observed_at': '2026-11-25T12:00:00+03:00',
            'blocks': {'review': "#5: 2021 Hirsch Pinot Noir Raschen Ridge\n$105, Sonoma\n"
                       "100 points – Antonio Galloni, January 2024\n"
                       "#4: 2021 La Ca' Nova Barbaresco Montefico Vigna Bric Mentina\n$50, Piedmont\n"
                       "97 points – Antonio Galloni, September 2024"},
        }
        reviews = parse_reviews(row, 'billing.vinous.com')
        self.assertEqual([(r['source'], r['year'], r['score'], r['amount'], r['end']) for r in reviews],
                         [('Vinous', 2021, 100, '105', None), ('Vinous', 2021, 97, '50', None)])

    def test_public_archive_keeps_the_score_price_and_window_with_each_vintage(self):
        url = 'https://timatkin.com/score-ranges/90-95/'
        row = {'url': url, 'status': 'needs_review', 'title': 'Score Range: 90-95',
               'observed_at': '2026-11-25T12:00:00Z', 'blocks': {
                   'review': "2nd July 2026\n94\n2024 Domaine Example Sancerre\n( £22, 12.5%, shop )\n"
                             "Drinking window: 2026-33\n7th March 2025 91\n2018 Domaine Example Jura\n"
                             "( £27, 14.5%, shop )\nDrinking window: 2025-30"}}
        bundle = {'kind': 'wine_atlas_research_capture', 'version': 1, 'observations': [row]}
        records = list(browser_observations(bundle, {}))
        self.assertEqual([(r['year'], r['score'], r['amount'], r['end']) for r in records],
                         [(2024, 94, '22', 2033), (2018, 91, '27', 2030)])

    def test_medal_only_does_not_create_a_numeric_critic_record(self):
        url = 'https://results.concoursmondial.com/fr/resultats/2024'
        row = {'url': url, 'status': 'needs_review', 'title': 'Results',
               'blocks': {'medal_leads': "Domaine Example 2022\tGrande Médaille d'Or"}}
        bundle = {'kind': 'wine_atlas_research_capture', 'version': 1, 'observations': [row]}
        self.assertEqual(list(browser_observations(bundle, {})), [])

    def test_parker_article_keeps_the_cuvee_after_parenthetical_producer(self):
        row = {'status': 'needs_review', 'observed_at': '2026-11-25T12:00:00Z',
               'url': 'https://content.robertparker.com/best-wines-2019-mark-squires',
               'blocks': {'review': '2017 Domaine Example (Producer Name) • Single Vineyard ($60, 96 points)'}}
        bundle = {'kind': 'wine_atlas_research_capture', 'version': 1, 'observations': [row]}
        record, = list(browser_observations(bundle, {}))
        self.assertEqual(record['title'], 'Domaine Example (Producer Name) Single Vineyard')

    def test_matches_vintage_and_requires_an_explicit_window_and_price(self):
        evidence = {'observed_on': '2026-11-24', 'sources': [{'source': 'Critic'}], 'observations': []}
        for year, kwargs in [
            (2020, {'score': 17, 'scale': 20}),
            (2020, {'end': 2030, 'start': 2021, 'amount': 50, 'price_kind': 'upper_bound'}),
            (2021, {'score': 90, 'scale': 100, 'amount': 35, 'price_kind': 'exact'}),
            (2022, {'score': 93, 'scale': 100, 'end': 2026, 'amount': 25, 'price_kind': 'exact'}),
            (2023, {'score': 93, 'scale': 100, 'end': 2027, 'amount': 15, 'price_kind': 'conditional'}),
        ]:
            evidence['observations'].append(dict(title='Same Name', year=year, source='Critic',
                                                 url='https://example.com/review', currency='EUR', **kwargs))
        report = stage(evidence, '2026-11-24', {'EUR': Decimal('120')})
        vintages = {v['year']: v for v in report['vintages']}
        self.assertEqual(report['status_counts'], {'ready_for_retailer_search': 1, 'pending_evidence': 3})
        self.assertEqual(vintages[2020]['prices'][0]['price_rub'], 6000)
        self.assertEqual(vintages[2021]['issues'], ['missing_window'])
        self.assertEqual(vintages[2022]['issues'], ['window_ends_before_2027'])
        self.assertEqual(vintages[2023]['issues'], ['missing_qualifying_price'])

    def test_note_dates_and_start_only_are_distinct_from_windows(self):
        self.assertEqual(window('Tasted in 2028. Drink from 2030.'), (None, None))
        self.assertEqual(window('Best from 2027 through 2040.'), (2027, 2040))
        self.assertEqual(window('Drink now–2040.'), (None, 2040))

    def test_botti_records_keep_prices_on_their_own_wine(self):
        rows = list(botti_observations({
            'url': 'https://www.botti.no/smaksnotater-1/',
            'observed_at': '2026-11-24T08:00:00Z',
            'blocks': {'review': 'Varenr: 1\nVin: Rosé 2023\nPris: 179,90 kr\nPoeng: 87\n'
                                 'Varenr: 2\nVin: Red 2020\nPris: 1 449,90 kr\nPoeng: 93\n'
                                 'Varenr: 3\nVin: NV Red\nPris: 225,– kr\nPoeng: 94\n'},
        }))
        self.assertEqual([(r['title'], r['year'], r['score'], r['amount']) for r in rows],
                         [('Rosé', 2023, 87, 179.9), ('Red', 2020, 93, 1449.9)])


if __name__ == '__main__':
    unittest.main()
