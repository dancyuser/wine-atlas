#!/usr/bin/env python3
"""No-network regression tests for agent-produced WineStyle price snapshots."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_winestyle import ObservationError, apply_observations, load_observations  # noqa: E402

DAY = dt.date(2026, 11, 22)
URL = 'https://spb.winestyle.ru/products/Example-2021.html'


def catalog():
    return {'updated_at': '2026-11-14', 'source': {'unique_wine_urls': 1}, 'records': [{
        'id': 'a', 'stores': [{'url': URL, 'price_rub': None, 'regular_price_rub': None,
                              'price_checked_at': None, 'reference_price_rub': 1500,
                              'reference_date': '2026-11-14'}]}]}


def observation(**changes):
    row = {'url': URL, 'source_url': URL, 'currency': 'RUB',
           'checked_at': '2026-11-22', 'price_rub': 1290, 'price_text': '1 290 ₽',
           'regular_price_rub': 1590, 'regular_price_text': '1 590 ₽'}
    row.update(changes)
    return row


class ImportTests(unittest.TestCase):
    def test_valid_and_archive_preserved(self):
        original = catalog()
        result, count, skipped = apply_observations(original, [observation()], today=DAY)
        self.assertEqual((count, skipped), (1, 0))
        self.assertEqual(result['records'][0]['stores'][0]['price_rub'], 1290)
        self.assertEqual(result['records'][0]['stores'][0]['regular_price_rub'], 1590)
        self.assertEqual(result['records'][0]['stores'][0]['reference_price_rub'], 1500)
        self.assertIsNone(original['records'][0]['stores'][0]['price_rub'])

    def test_idempotence(self):
        first, _, _ = apply_observations(catalog(), [observation()], today=DAY)
        second, count, skipped = apply_observations(first, [observation()], today=DAY)
        self.assertEqual((count, skipped), (0, 1))
        self.assertEqual(first, second)

    def test_reject_stale_or_future_date(self):
        for checked in ('2026-11-14', '2026-11-23', '2026-11-31'):
            with self.subTest(checked=checked), self.assertRaises(ObservationError):
                apply_observations(catalog(), [observation(checked_at=checked)], today=DAY)

    def test_reject_invalid_prices_and_mismatched_evidence(self):
        cases = [dict(price_rub=1291), dict(price_rub=True),
                 dict(regular_price_rub=1200, regular_price_text='1 200 ₽'),
                 dict(regular_price_rub=None, regular_price_text='1 590 ₽'),
                 dict(regular_price_rub=1600, regular_price_text=None),
                 dict(price_text='1 290 ₽; 2 000 ₽')]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ObservationError):
                apply_observations(catalog(), [observation(**case)], today=DAY)

    def test_reject_wrong_url_or_source(self):
        for case in [dict(url='https://spb.winestyle.ru/products/Other.html'),
                     dict(source_url='https://winestyle.ru/products/Example-2021.html'),
                     dict(url=URL+'?ref=agent'), dict(url='https://evil.winestyle.ru.attacker.com/products/Example-2021.html')]:
            with self.subTest(case=case), self.assertRaises(ObservationError):
                apply_observations(catalog(), [observation(**case)], today=DAY)

    def test_reject_duplicate_batch_and_same_day_conflict(self):
        with self.assertRaises(ObservationError):
            apply_observations(catalog(), [observation(), observation()], today=DAY)
        saved, _, _ = apply_observations(catalog(), [observation()], today=DAY)
        with self.assertRaises(ObservationError):
            apply_observations(saved, [observation(price_rub=1390, price_text='1 390 ₽')], today=DAY)

    def test_never_partial_apply(self):
        original = catalog()
        with self.assertRaises(ObservationError):
            apply_observations(original, [observation(), observation(price_rub=0)], today=DAY)
        self.assertIsNone(original['records'][0]['stores'][0]['price_rub'])

    def test_json_and_jsonl_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for suffix, payload in [('.json', json.dumps({'observations': [observation()]})),
                                    ('.jsonl', json.dumps(observation()) + '\n')]:
                p = directory / ('agent' + suffix)
                p.write_text(payload, encoding='utf-8')
                self.assertEqual(load_observations(p), [observation()])


if __name__ == '__main__':
    unittest.main()
