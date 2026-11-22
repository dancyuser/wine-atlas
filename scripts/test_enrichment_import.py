"""Offline regression tests for the reviewed browser-capture overlay importer."""
import copy
import unittest

from import_enrichment_overlay import verify_overlay


URL = "https://spb.winestyle.ru/products/Example-Wine-2023.html"
DATE = "2026-11-22"
SHA = "a" * 64


def sample():
    catalog = {"region": "Санкт-Петербург", "records": [{
        "id": "abc", "title": "Example Wine", "year": 2023,
        "stores": [{"url": URL, "price_rub": None, "regular_price_rub": None,
                    "price_checked_at": None, "reference_price_rub": 2000,
                    "reference_regular_price_rub": None, "reference_date": "2026-11-14"}]
    }]}
    rating = {"source": "Wine Enthusiast", "score": 94, "scale": 100,
              "reported_by": "WineStyle", "source_url": URL,
              "observed_on": DATE, "evidence": "Wine Enthusiast 94/100"}
    overlay = {
        "schema_version": 2, "kind": "reviewed_overlay_not_complete_catalog",
        "source_capture_sha256": SHA, "source_observed_at": DATE + "T18:54:25Z",
        "statistics": {"verified_exact_products": 1,
                       "prices_with_direct_evidence": 1,
                       "rating_scores_published_by_retailer": 1,
                       "mismatched_variant_count": 0, "target_count": 1,
                       "regular_prices_explicitly_present": 0},
        "skipped": [],
        "updates": {"abc": {
            "id": "abc", "title": "Example Wine", "year": 2023, "url": URL,
            "enrichment_status": {"status": "verified", "checked_at": DATE,
                                  "source_url": URL},
            "price_rub": 1490, "price_checked_at": DATE, "price_source_url": URL,
            "regular_price_rub": None,
            "product_details": {
                "producer": "Example", "grapes": "Рислинг",
                "description_excerpt": "Dry white wine.",
                "checked_at": DATE, "source_url": URL,
                "ratings": [rating],
                "field_evidence": {"producer": "Производитель: Example"},
                "all_characteristics": {"Unrelated": "Similar product"},
                "sections": [{"heading": "Other wines", "text": "Ignore"}],
                "identity_evidence": {"canonical_url": URL},
                "unparsed_rating_lines": ["unrelated"],
                "excluded_conflicting_fields": {"producer": "related wine"},
            }
        }}
    }
    return catalog, overlay


class OverlayTests(unittest.TestCase):
    def test_apply_preserves_archives_and_prunes_related_noise(self):
        catalog, overlay = sample()
        result, stats = verify_overlay(catalog, overlay)
        self.assertEqual((stats["changed"], stats["prices"], stats["ratings"]), (1, 1, 1))
        store = result["records"][0]["stores"][0]
        self.assertEqual(store["price_rub"], 1490)
        self.assertEqual(store["reference_price_rub"], 2000)
        self.assertEqual(store["product_details"]["ratings"][0]["score"], 94)
        for field in ("all_characteristics", "sections", "identity_evidence",
                      "excluded_conflicting_fields", "unparsed_rating_lines"):
            self.assertNotIn(field, store["product_details"])
        self.assertIsNone(catalog["records"][0]["stores"][0]["price_rub"])

    def test_idempotent_on_same_capture(self):
        catalog, overlay = sample()
        once, _ = verify_overlay(catalog, overlay)
        again, result = verify_overlay(once, overlay)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(once, again)

    def test_unverified_status_rejected(self):
        catalog, overlay = sample()
        overlay["updates"]["abc"]["enrichment_status"]["status"] = "unknown"
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_redirect_never_substitutes_products(self):
        catalog, overlay = sample()
        overlay["updates"]["abc"]["url"] = URL.replace("2023", "2024")
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_different_vintage_rejected(self):
        catalog, overlay = sample()
        overlay["updates"]["abc"]["year"] = 2022
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_wrong_rating_provenance_rejected(self):
        catalog, overlay = sample()
        overlay["updates"]["abc"]["product_details"]["ratings"][0]["source_url"] = \
            URL.replace("2023", "2024")
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_wrong_rating_scale_rejected(self):
        catalog, overlay = sample()
        overlay["updates"]["abc"]["product_details"]["ratings"][0]["scale"] = 7
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_false_discount_rejected(self):
        catalog, overlay = sample()
        overlay["updates"]["abc"]["regular_price_rub"] = 1400
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_newer_price_not_overwritten(self):
        catalog, overlay = sample()
        catalog["records"][0]["stores"][0]["price_checked_at"] = "2026-11-23"
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_missing_or_bad_source_hash_rejected(self):
        catalog, overlay = sample()
        overlay["source_capture_sha256"] = "a short hash"
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)

    def test_mismatch_skip_is_preserved(self):
        catalog, overlay = sample()
        skipped_url = "https://spb.winestyle.ru/products/Skipped-Wine-2021.html"
        catalog["records"].append({
            "id": "skip", "title": "Skipped Wine", "year": 2021,
            "stores": [{"url": skipped_url, "price_rub": None}]
        })
        overlay["skipped"] = [{"status": "identity_mismatch", "url": skipped_url}]
        overlay["statistics"]["mismatched_variant_count"] = 1
        result, stats = verify_overlay(catalog, overlay)
        self.assertEqual(stats["skipped_mismatches"], 1)
        self.assertNotIn("product_details", result["records"][1]["stores"][0])
        self.assertIn(skipped_url, result["retailer_snapshot"]["mismatched_urls"])

    def test_reject_invalid_audit_counts_atomically(self):
        catalog, overlay = sample()
        original = copy.deepcopy(catalog)
        overlay["statistics"]["rating_scores_published_by_retailer"] = 0
        with self.assertRaises(ValueError):
            verify_overlay(catalog, overlay)
        self.assertEqual(catalog, original)


if __name__ == "__main__":
    unittest.main()
