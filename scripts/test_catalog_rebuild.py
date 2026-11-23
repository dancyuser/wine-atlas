"""Repeat the documented Google Doc text-import without losing WineStyle provenance."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_catalog
from retailer_manifest import reconcile_manifest

WINE = "https://spb.winestyle.ru/products/Peter-Zemmer-Chardonnay-Alto-Adige-DOC-2023.html"
SKIPPED = "https://spb.winestyle.ru/products/Rotari-Blanc-de-Blancs-Extra-Brut-Trento-DOC-2018.html"


def fixture():
    rec = build_catalog.make_record(WINE, "Шардоне")
    skipped = build_catalog.make_record(SKIPPED, "Игристое")
    store = rec["stores"][0]
    store.update(
        price_rub=2490, price_checked_at="2026-11-22", price_source_url=WINE,
        enrichment_status={"status": "verified", "checked_at": "2026-11-22",
                           "source_url": WINE, "method": "user_supplied_browser_capture"},
        product_details={
            "checked_at": "2026-11-22", "source_url": WINE,
            "producer": "Peter Zemmer", "grapes": "Шардоне",
            "ratings": [{"source": "Wine Enthusiast", "score": 94, "scale": 100,
                         "source_url": WINE, "reported_by": "WineStyle",
                         "observed_on": "2026-11-22", "evidence": "94/100"}]
        }
    )
    store["live_offer"]={"verification_method":"exact_jsonld_product","price_rub":2590,
                         "regular_price_rub":None,"availability":"in_stock",
                         "observed_on":"2026-11-24","product_name":"Peter Zemmer Chardonnay",
                         "source_url":WINE}
    rec["availability"]={"status":"in_stock","observed_on":"2026-11-23",
                         "source_url":WINE,"evidence":"primary purchase button",
                         "snapshot_source":"fixture.zip"}
    manifest = {
        "retailer": "WineStyle", "source": "user_supplied_browser_capture",
        "source_export_sha256": "a" * 64, "observed_on": "2026-11-22",
        "collected_target_urls": 2, "matched_exact_products": 1,
        "mismatched_variants": 1, "mismatched_urls": [SKIPPED],
        "direct_price_observations": 1, "retailer_reported_ratings": 1,
        "regular_prices_confirmed": 0
    }
    return {"records": [rec, skipped], "retailer_snapshot": manifest,
            "inventory_snapshot": {
               "observed_on":"2026-11-23", "archive_sha256":"b"*64,
               "targets":2, "exact_matches":1, "in_stock":1,
               "out_of_stock":0, "unconfirmed_identity":1},
            "source": {"kind": "google_docs", "revision_id": "source-revision-1"}}


class RebuildTest(unittest.TestCase):
    def rebuild(self, root, urls):
        source = root / "source.txt"
        source.write_text("Шардоне\n" + ("\n".join(urls)) + "\n", encoding="utf-8")
        with patch.object(build_catalog, "ROOT", root), patch.object(
            sys, "argv", ["build_catalog.py", str(source)]
        ), contextlib.redirect_stdout(io.StringIO()):
            build_catalog.main()
        return json.loads((root / "data" / "wines.json").read_text(encoding="utf-8"))

    def test_same_membership_preserves_every_snapshot_and_manifest(self):
        original = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data" / "wines.json").write_text(
                json.dumps(original, ensure_ascii=False), encoding="utf-8"
            )
            actual = self.rebuild(root, [WINE, SKIPPED])
            manifest = actual["retailer_snapshot"]
            self.assertEqual(manifest["source_export_sha256"], "a" * 64)
            self.assertEqual(manifest["collected_target_urls"], 2)
            self.assertEqual(actual["source"]["revision_id"], "source-revision-1")
            self.assertEqual(manifest["matched_exact_products"], 1)
            self.assertEqual(manifest["mismatched_variants"], 1)
            self.assertEqual(manifest["retailer_reported_ratings"], 1)
            observed = next(r for r in actual["records"] if r["stores"][0]["url"] == WINE)
            self.assertEqual(observed["stores"][0]["product_details"],
                             original["records"][0]["stores"][0]["product_details"])
            self.assertEqual(observed["availability"],original["records"][0]["availability"])
            self.assertEqual(observed["stores"][0].get("live_offer"),original["records"][0]["stores"][0].get("live_offer"))
            self.assertEqual(actual["inventory_snapshot"],original["inventory_snapshot"])
            again = self.rebuild(root, [WINE, SKIPPED])
            self.assertEqual(again["retailer_snapshot"], actual["retailer_snapshot"])

    def test_removed_wishlist_url_prunes_obsolete_manifest_counts(self):
        original = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data" / "wines.json").write_text(
                json.dumps(original, ensure_ascii=False), encoding="utf-8"
            )
            pruned = self.rebuild(root, [WINE])
            manifest = pruned["retailer_snapshot"]
            self.assertEqual(manifest["collected_target_urls"], 1)
            self.assertNotIn("revision_id", pruned["source"])
            self.assertEqual(manifest["matched_exact_products"], 1)
            self.assertEqual(manifest["mismatched_variants"], 0)
            self.assertEqual(manifest["mismatched_urls"], [])
            self.assertEqual(manifest["direct_price_observations"], 1)
            self.assertNotIn("inventory_snapshot",pruned,
                             "Old full-catalog inventory snapshot must not survive membership changes")

    def test_no_manifest_does_not_fabricate_source_capture(self):
        original = fixture()
        original.pop("retailer_snapshot")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data" / "wines.json").write_text(
                json.dumps(original, ensure_ascii=False), encoding="utf-8"
            )
            rebuilt = self.rebuild(root, [WINE])
            self.assertNotIn("retailer_snapshot", rebuilt)

    def test_reconcile_new_observation_does_not_falsify_source_date(self):
        source = fixture()
        source["records"][0]["stores"][0]["product_details"]["checked_at"] = "2026-11-23"
        source["records"][0]["stores"][0]["enrichment_status"]["checked_at"] = "2026-11-23"
        manifest = reconcile_manifest(source["retailer_snapshot"], source["records"])
        self.assertEqual(manifest["observed_on"], "2026-11-22")
        self.assertEqual(manifest["latest_observed_on"], "2026-11-23")


if __name__ == "__main__":
    unittest.main()
