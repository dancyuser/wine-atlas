import copy
import unittest

from recover_capture_prices import first_exact_product_price, recover_prices


class CapturePriceRecoveryTests(unittest.TestCase):
    def test_exact_price_before_recommendations(self):
        source = ("Вино A Все товары Producer Производитель Цена 4 835 ₽ "
                  "Добавить в корзину Условия для бизнеса "
                  "В наличии похожее Всё 2 350 ₽ Вино другое")
        self.assertEqual(first_exact_product_price(source),
                         (4835, "Цена 4 835 ₽"))

    def test_no_price_derived_from_similar_wine(self):
        self.assertIsNone(first_exact_product_price(
            "Вино A Все товары Producer Производитель "
            "Условия для бизнеса В наличии похожее Цена 3 000 ₽"))
        self.assertIsNone(first_exact_product_price(
            "Вино A Цена 3 000 ₽"))

    def test_strict_identity_source_and_idempotence(self):
        url="https://spb.winestyle.ru/products/Exact-2023.html"
        source=("Вино A Все товары Estate Производитель Цена 2 899 ₽ "
                "Ожидаем поступление Условия для бизнеса")
        catalog={"retailer_snapshot":{"source_export_sha256":"abc",
                                      "direct_price_observations":0},
                 "records":[{"id":"wine1","year":2023,"stores":[
                  {"url":url,"price_rub":None,
                   "enrichment_status":{"status":"verified"},
                   "product_details":{"source_url":url,"checked_at":"2026-11-22"}}]}]}
        data={"captures":[{"status":"captured","url":url,
              "identity":{"target_id":"wine1","canonical_url":url,
                          "target_year":2023},
              "raw_product_text":source,"price":None}]}
        with self.assertRaises(ValueError):
            recover_prices(copy.deepcopy(catalog),data,"wrong")
        mismatched=copy.deepcopy(data)
        mismatched["captures"][0]["identity"]["canonical_url"]=url.replace("Exact","Other")
        self.assertEqual(recover_prices(copy.deepcopy(catalog),mismatched,"abc"),0)
        self.assertEqual(recover_prices(catalog,data,"abc"),1)
        store=catalog["records"][0]["stores"][0]
        self.assertEqual(store["price_rub"],2899)
        self.assertEqual(store["price_checked_at"],"2026-11-22")
        self.assertEqual(recover_prices(catalog,data,"abc"),0)
        self.assertEqual(catalog["retailer_snapshot"]["direct_price_observations"],1)


if __name__=="__main__":
    unittest.main()
