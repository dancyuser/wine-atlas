"""Regression suite for evidence-based wine category assignments."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'data' / 'wines.json').read_text(encoding='utf-8'))
OVERRIDES = json.loads((ROOT / 'data' / 'overrides.json').read_text(encoding='utf-8'))

def wine_subtype(text):
    text = str(text or '').lower()
    if re.search(r'оранжев', text): return 'Оранжевое'
    if re.search(r'розов', text): return 'Розовое'
    if re.search(r'красн', text): return 'Красное'
    if re.search(r'бел', text): return 'Белое'
    if re.search(r'портвейн', text): return 'Портвейн'
    return None


class WineCategoryTests(unittest.TestCase):
    def test_no_wine_color_conflicts_in_124_records(self):
        conflicts = []
        for wine in CATALOG['records']:
            details = wine['stores'][0].get('product_details') or wine['stores'][0].get('research_details') or {}
            style = details.get('wine_style')
            subtype = wine_subtype(style)
            if subtype is None:
                continue
            typ = wine['type']
            if typ == 'Игристое' and subtype in ('Розовое', 'Белое'):
                continue  # Sparkling is the primary type, color is a subtype.
            if subtype != typ:
                conflicts.append((wine['id'],typ,style))
        self.assertFalse(conflicts, f'Wine category conflicts with retailer: {conflicts}')

    def test_reviewed_special_cases_survive_catalog_rebuilds(self):
        cases = {
            '209d7a6d9fe0':('Оранжевое','Loimer Glügglich'),
            '1d4b1fae8d7a':('Розовое','El Esteco Blanc de Noir'),
            '5427ef8902aa':('Игристое','Pitars Prosecco DOC'),
        }
        ids={r['id']:r for r in CATALOG['records']}
        for id_, (category,name) in cases.items():
            with self.subTest(wine=name):
                wine=ids[id_]
                self.assertEqual(wine['type'],category)
                self.assertEqual(OVERRIDES[id_]['type'],category)
                review=wine.get('classification_review')
                self.assertEqual(review['status'],'verified')
                self.assertTrue(review['source_url'].startswith('https://'))
                self.assertTrue(review['evidence'])

    def test_sparkling_color_is_not_misclassified_as_still_wine(self):
        ids={r['id']:r for r in CATALOG['records']}
        pitars=ids['5427ef8902aa']
        self.assertEqual(pitars['type'],'Игристое')
        self.assertIn('Игристое-белое',pitars['stores'][0]['product_details']['wine_style'])


if __name__ == '__main__':
    unittest.main()
