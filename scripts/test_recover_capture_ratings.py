import copy
import unittest

from recover_capture_ratings import recover, score_rows


class CaptureRatingRecoveryTests(unittest.TestCase):
    def test_source_after_score_and_non_decimal_scale(self):
        text = ("Wine A О товаре 8 рейтингов и наград "
                "90 /100 Wine Spectator 16.5 /20 Jancis Robinson "
                "4.2 /5 Vivino 92 /100 Decanter | 100 "
                "Все товары Wine A 100 /100 James Suckling")
        got = {(r["source"], r["score"], r["scale"]) for r in score_rows(text)}
        self.assertEqual(got, {
            ("Wine Spectator", 90, 100), ("Jancis Robinson", 16.5, 20),
            ("Vivino", 4.2, 5), ("Decanter", 92, 100),
        })

    def test_reject_missing_product_boundary(self):
        self.assertEqual(score_rows("91 /100 Wine Spectator Все товары"), [])
        self.assertEqual(score_rows("О товаре 91 /100 Wine Spectator"), [])

    def test_reject_conflicting_values_and_out_of_range(self):
        text = (" О товаре 90 /100 Vinous 91 /100 Vinous "
                "102 /100 Wine Spectator 4.2 /5 Vivino Все товары ")
        self.assertEqual([(x["source"], x["score"]) for x in score_rows(text)],
                         [("Vivino", 4.2)])

    def test_url_id_and_capture_hash_are_required(self):
        url = "https://spb.winestyle.ru/products/Exactly-Matched-2023.html"
        record = {
            "id": "abc", "title": "Exactly Matched", "year": 2023,
            "stores": [{"url": url, "enrichment_status": {"status": "verified"},
                        "product_details": {"source_url": url,
                                            "checked_at": "2026-11-22",
                                            "ratings": []}}],
        }
        catalog = {"records": [record],
                   "retailer_snapshot": {"source_export_sha256": "secret",
                                          "retailer_reported_ratings": 0}}
        capture = {"captures": [
            {"status": "captured", "url": url,
             "identity": {"target_id": "abc", "target_year": 2023,
                          "canonical_url": url},
             "raw_product_text": "Wine О товаре 93 /100 Wine Enthusiast Все товары Wine"}
        ]}
        self.assertRaises(ValueError, recover, copy.deepcopy(catalog), capture, "wrong")
        wrong = copy.deepcopy(capture)
        wrong["captures"][0]["identity"]["target_id"] = "other"
        self.assertEqual(recover(copy.deepcopy(catalog), wrong, "secret"), (0, 0))
        changed, added = recover(catalog, capture, "secret")
        self.assertEqual((changed, added), (1, 1))
        self.assertEqual(record["stores"][0]["product_details"]["ratings"][0]["score"], 93)
        self.assertEqual(recover(catalog, capture, "secret"), (0, 0))


if __name__ == "__main__":
    unittest.main()
