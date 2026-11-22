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

    def test_partial_overlay_retains_all_other_wine_snapshots(self):
        catalog, overlay = sample()
        second_url = "https://spb.winestyle.ru/products/Other-Wine-2021.html"
        catalog["records"].append({
            "id": "other", "title": "Other Wine", "year": 2021,
            "stores": [{
                "url": second_url, "price_rub": 2150,
                "price_checked_at": "2026-11-21",
                "price_source_url": second_url, "regular_price_rub": None,
                "enrichment_status": {"status": "verified", "checked_at": "2026-11-21",
                                      "source_url": second_url},
                "product_details": {
                    "source_url": second_url, "checked_at": "2026-11-21",
                    "producer": "Other", "grapes": "Мерло",
                    "ratings": [{"source": "Wine Spectator", "score": 90, "scale": 100,
                                 "reported_by": "WineStyle", "source_url": second_url,
                                 "observed_on": "2026-11-21", "evidence": "Wine Spectator 90/100"}]
                }
            }]
        })
        catalog["retailer_snapshot"] = {
            "retailer": "WineStyle", "source": "user_supplied_browser_capture",
            "source_export_sha256": "b" * 64, "observed_on": "2026-11-21",
            "mismatched_urls": [], "matched_exact_products": 1,
            "collected_target_urls": 1, "mismatched_variants": 0,
            "direct_price_observations": 1, "retailer_reported_ratings": 1,
            "regular_prices_confirmed": 0
        }
        result, stats = verify_overlay(catalog, overlay)
        snapshot = result["retailer_snapshot"]
        self.assertEqual((snapshot["matched_exact_products"],
                          snapshot["direct_price_observations"],
                          snapshot["retailer_reported_ratings"]), (2, 2, 2))
        self.assertEqual(snapshot["source_export_sha256"], "b" * 64)
        self.assertEqual(snapshot["observed_on"], "2026-11-21")
        self.assertEqual(snapshot["latest_observed_on"], DATE)
        self.assertEqual(snapshot["additional_capture_sources"][0]["sha256"], "a" * 64)
        self.assertEqual(result["records"][1], catalog["records"][1])
        self.assertEqual(stats["changed"], 1)
        again, stats2 = verify_overlay(result, overlay)
        self.assertEqual(stats2["changed"], 0)
        self.assertEqual(again, result)

    def test_partial_overlay_preserves_older_score_description_and_price(self):
        catalog, overlay = sample()
        store = catalog["records"][0]["stores"][0]
        store.update(price_rub=1980, price_checked_at="2026-11-21", price_source_url=URL)
        store["product_details"] = {
            "checked_at": "2026-11-21", "source_url": URL,
            "description_excerpt": "Detailed existing description",
            "pairing_notes": "рыба, морепродукты",
            "field_evidence": {"description_excerpt": "Old text source"},
            "ratings": [
                {"source": "Wine Spectator", "score": 87, "scale": 100,
                 "reported_by": "WineStyle", "source_url": URL,
                 "observed_on": "2026-11-21", "evidence": "87/100"},
                {"source": "Wine Enthusiast", "score": 91, "scale": 100,
                 "reported_by": "WineStyle", "source_url": URL,
                 "observed_on": "2026-11-21", "evidence": "91/100"}
            ]
        }
        catalog["retailer_snapshot"] = {
            "retailer": "WineStyle", "source": "user_supplied_browser_capture",
            "observed_on": "2026-11-21", "source_export_sha256": "b" * 64,
            "mismatched_urls": []
        }
        details = overlay["updates"]["abc"]["product_details"]
        details.pop("description_excerpt")
        details.pop("field_evidence")
        details["ratings"][0]["score"] = 94
        overlay["updates"]["abc"]["price_rub"] = None
        overlay["updates"]["abc"]["price_checked_at"] = None
        overlay["updates"]["abc"]["price_source_url"] = None
        overlay["statistics"]["prices_with_direct_evidence"] = 0
        imported, stats = verify_overlay(catalog, overlay)
        result = imported["records"][0]["stores"][0]
        self.assertEqual(result["product_details"]["description_excerpt"],
                         "Detailed existing description")
        self.assertEqual(result["product_details"]["pairing_notes"], "рыба, морепродукты")
        self.assertEqual(result["product_details"]["field_checked_at"]["description_excerpt"],
                         "2026-11-21")
        self.assertEqual(result["product_details"]["field_evidence"]["description_excerpt"],
                         "Old text source")
        self.assertEqual({r["source"]: r["score"] for r in result["product_details"]["ratings"]},
                         {"Wine Spectator": 87, "Wine Enthusiast": 94})
        self.assertEqual(result["price_checked_at"], "2026-11-21")
        self.assertEqual((imported["retailer_snapshot"]["direct_price_observations"],
                          imported["retailer_snapshot"]["retailer_reported_ratings"]), (1, 2))
        self.assertEqual(stats["changed"], 1)

    def test_rating_date_required_and_not_future(self):
        for value in (None, "2099-01-01", "not-a-date"):
            catalog, overlay = sample()
            if value is None:
                del overlay["updates"]["abc"]["product_details"]["ratings"][0]["observed_on"]
            else:
                overlay["updates"]["abc"]["product_details"]["ratings"][0]["observed_on"] = value
            with self.subTest(date=value), self.assertRaises(ValueError):
                verify_overlay(catalog, overlay)

    def test_manifest_only_changes_persist_through_apply_cli(self):
        import json
        import sys
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from import_enrichment_overlay import main
        catalog, overlay = sample()
        url = "https://spb.winestyle.ru/products/Missing-Vintage-2021.html"
        catalog["records"].append({
            "id": "skipped", "title": "Missing Vintage", "year": 2021,
            "stores": [{"url": url, "price_rub": None}]
        })
        overlay["updates"] = {}
        overlay["skipped"] = [{"status": "identity_mismatch", "url": url}]
        overlay["statistics"].update(
            verified_exact_products=0, prices_with_direct_evidence=0,
            rating_scores_published_by_retailer=0, mismatched_variant_count=1)
        imported, stats = verify_overlay(catalog, overlay)
        self.assertEqual(stats["changed"], 0)
        self.assertTrue(stats["manifest_changed"])
        self.assertIn(url, imported["retailer_snapshot"]["mismatched_urls"])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "wines.json").write_text(json.dumps(catalog), encoding="utf-8")
            (root / "overlay.json").write_text(json.dumps(overlay), encoding="utf-8")
            with patch.object(sys, "argv", ["script", str(root / "overlay.json"),
                                             "--apply", "--catalog", str(root / "wines.json")]):
                main()
            saved = json.loads((root / "wines.json").read_text(encoding="utf-8"))
            self.assertIn(url, saved["retailer_snapshot"]["mismatched_urls"])

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
