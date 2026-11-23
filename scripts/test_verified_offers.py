import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verified_offers import exact_volume, verified_offer

BASE = "https://shop.example/products/kopke-lbv-2018"
RECORD = {
    "title": "Kopke Late Bottled Vintage Port (LBV)",
    "year": 2018,
    "volume_l": 0.75,
    "publication_review": {"status": "verified", "final_url": BASE}
}


def page(name="Kopke LBV Port 2018, 750 ml", url=BASE, price="6348",
         availability="https://schema.org/InStock", volume="", extra=""):
    return ('<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"Product","name":' +
            __import__("json").dumps(name) + ',"url":' + __import__("json").dumps(url) +
            ',"description":' + __import__("json").dumps(volume) +
            ',"offers":{"@type":"Offer","priceCurrency":"RUB","price":' +
            __import__("json").dumps(price) + ',"availability":' +
            __import__("json").dumps(availability) + extra + "}}</script>")


class ExactOfferTests(unittest.TestCase):
    def check(self, source, record=None, original=BASE, final=BASE):
        return verified_offer(source, RECORD if record is None else record, original, final)

    def test_exact_offer_and_current_stock(self):
        offer, why = self.check(page())
        self.assertEqual(why, "verified")
        self.assertEqual(offer["price_rub"], 6348)
        self.assertEqual(offer["availability"], "in_stock")
        self.assertIsNone(offer["regular_price_rub"])

    def test_explicit_old_price_only(self):
        offer, why = self.check(page(extra=',"oldPrice":"7100"'))
        self.assertEqual(why, "verified")
        self.assertEqual(offer["regular_price_rub"], 7100)

    def test_changed_vintage_rejected(self):
        self.assertIsNone(self.check(page(name="Kopke LBV Port 2025, 750 ml"))[0])

    def test_changed_volume_rejected(self):
        self.assertIsNone(self.check(page(name="Kopke LBV Port 2018, 1.5 l"))[0])

    def test_different_wine_rejected(self):
        self.assertIsNone(self.check(page(name="Taylor LBV Port 2018, 750 ml"))[0])

    def test_missing_vintage_rejected(self):
        self.assertIsNone(self.check(page(name="Kopke LBV Port 750 ml"))[0])

    def test_missing_volume_rejected(self):
        self.assertIsNone(self.check(page(name="Kopke LBV Port 2018"))[0])

    def test_redirect_variant_rejected(self):
        _, reason = self.check(page(), final="https://shop.example/products/kopke-lbv-2025")
        self.assertEqual(reason, "redirected_to_different_product")

    def test_query_variant_cannot_substitute_product(self):
        self.assertEqual(
            self.check(page(), final=BASE + "?variant=2025")[1],
            "redirected_to_different_product"
        )
        self.assertIsNone(self.check(page(url=BASE + "?variant=2025"))[0])

    def test_schema_product_url_rejected(self):
        self.assertIsNone(self.check(page(url="https://shop.example/products/kopke-lbv-2025"))[0])

    def test_not_reviewed_cannot_update(self):
        record = dict(RECORD, publication_review={"status": "excluded", "final_url": BASE})
        self.assertEqual(self.check(page(), record=record)[1], "no_manual_identity_review")

    def test_out_of_stock_is_explicit(self):
        offer, _ = self.check(page(availability="https://schema.org/OutOfStock"))
        self.assertEqual(offer["availability"], "out_of_stock")

    def test_ambiguous_offers_rejected(self):
        source = page(price="6348") + page(price="7000")
        self.assertEqual(self.check(source)[1], "ambiguous_product_offers")

    def test_hash_and_terminal_slash_only(self):
        offer, _ = self.check(page(), original=BASE + "/#details")
        self.assertEqual(offer["price_rub"], 6348)

    def test_volume_validation(self):
        self.assertTrue(exact_volume("0,75 л", 0.75))
        self.assertTrue(exact_volume("750 ml", 0.75))
        self.assertFalse(exact_volume("1500 ml", 0.75))


if __name__ == "__main__":
    unittest.main()
