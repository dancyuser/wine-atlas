import unittest
from decimal import Decimal

from import_research import window
from stage_critic_research import botti_observations, stage


class CriticStageTest(unittest.TestCase):
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
