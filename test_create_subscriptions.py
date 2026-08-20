#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from create_subscriptions import (
    ASCError,
    coerce_paid_intro_duration,
    discover_p8,
    intro_payload,
    IntroOffer,
    key_id_from_p8_name,
    load_catalog,
    localization_payload,
    match_price_point,
    normalize_period,
    price_payload,
    scaffold_catalog,
    subscription_create_payload,
)


class PeriodTests(unittest.TestCase):
    def test_aliases(self) -> None:
        self.assertEqual(normalize_period("week"), "ONE_WEEK")
        self.assertEqual(normalize_period("P1M"), "ONE_MONTH")
        self.assertEqual(normalize_period("quarter"), "THREE_MONTHS")
        self.assertEqual(normalize_period("one-year"), "ONE_YEAR")

    def test_rejects_unknown(self) -> None:
        with self.assertRaises(ASCError):
            normalize_period("daily")


class PriceMatchTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        points = [
            {"id": "a", "attributes": {"customerPrice": "4.99"}},
            {"id": "b", "attributes": {"customerPrice": "6.99"}},
        ]
        selected, nearest = match_price_point(points, "6.99", nearest=False)
        self.assertEqual(selected["id"], "b")
        self.assertFalse(nearest)

    def test_nearest_match(self) -> None:
        points = [
            {"id": "a", "attributes": {"customerPrice": "4.99"}},
            {"id": "b", "attributes": {"customerPrice": "6.99"}},
        ]
        selected, nearest = match_price_point(points, "7.00", nearest=True)
        self.assertEqual(selected["id"], "b")
        self.assertTrue(nearest)

    def test_missing_without_nearest(self) -> None:
        points = [{"id": "a", "attributes": {"customerPrice": "4.99"}}]
        with self.assertRaises(ASCError):
            match_price_point(points, "6.99", nearest=False)


class CatalogTests(unittest.TestCase):
    def test_example_config_loads(self) -> None:
        catalog = load_catalog(Path(__file__).parent / "tests" / "example.json")
        self.assertEqual(catalog.group_id, "22115962")
        self.assertEqual(len(catalog.subscriptions), 4)
        self.assertEqual(catalog.subscriptions[1].intro.mode, "FREE_TRIAL")
        self.assertEqual(catalog.subscriptions[2].intro.usd_price, "4.99")

    def test_global_catalog_matches_requested_skus(self) -> None:
        catalog = load_catalog(Path(__file__).parent / "projects" / "duanju-no1.json")
        self.assertEqual(catalog.price_scope, "all")
        self.assertEqual(catalog.base_territory, "USA")
        by_id = {sku.product_id: sku for sku in catalog.subscriptions}
        self.assertEqual(set(by_id), {
            "dj.month.1.0",
            "dj.month.1.1",
            "dj.month.1.2",
            "dj.month.1.3",
            "dj.quarter.1.0",
            "dj.quarter.1.1",
            "dj.year.1.0",
            "dj.year.1.1",
        })
        self.assertIsNone(by_id["dj.month.1.0"].intro)
        self.assertEqual(by_id["dj.month.1.0"].usd_price, "29.99")
        self.assertEqual(by_id["dj.month.1.1"].intro.duration, "THREE_DAYS")
        self.assertEqual(by_id["dj.month.1.2"].intro.mode, "PAY_AS_YOU_GO")
        self.assertEqual(by_id["dj.month.1.2"].intro.duration, "ONE_MONTH")
        self.assertEqual(by_id["dj.month.1.2"].intro.usd_price, "6.99")
        self.assertEqual(by_id["dj.month.1.3"].intro.duration, "ONE_WEEK")
        self.assertEqual(by_id["dj.quarter.1.0"].period, "THREE_MONTHS")
        self.assertEqual(by_id["dj.quarter.1.0"].usd_price, "69.99")
        self.assertEqual(by_id["dj.year.1.1"].usd_price, "99.99")
        self.assertEqual(by_id["dj.year.1.1"].intro.duration, "THREE_DAYS")

    def test_payg_week_on_month_is_coerced(self) -> None:
        intro = IntroOffer(
            mode="PAY_AS_YOU_GO",
            duration="ONE_WEEK",
            number_of_periods=1,
            usd_price="6.99",
        )
        coerced = coerce_paid_intro_duration("ONE_MONTH", intro)
        assert coerced is not None
        self.assertEqual(coerced.duration, "ONE_MONTH")

    def test_catalog_roundtrip(self) -> None:
        from create_subscriptions import catalog_from_dict, catalog_to_dict

        original = load_catalog(Path(__file__).parent / "projects" / "duanju-no1.json")
        dumped = catalog_to_dict(original)
        restored = catalog_from_dict(dumped)
        self.assertEqual(restored.group_id, original.group_id)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(
            [sku.product_id for sku in restored.subscriptions],
            [sku.product_id for sku in original.subscriptions],
        )
        for sku in dumped["subscriptions"]:
            self.assertNotIn("localizations", sku)

    def test_draft_catalog_allows_empty_skus(self) -> None:
        from create_subscriptions import catalog_from_dict

        catalog = catalog_from_dict({"group_id": "", "subscriptions": []}, strict=False)
        self.assertEqual(catalog.subscriptions, ())

    def test_template_project_loads(self) -> None:
        catalog = load_catalog(Path(__file__).with_name("projects") / "_template.json", strict=False)
        self.assertEqual(catalog.group_id, "")
        self.assertEqual(catalog.subscriptions, ())

    def test_data_dir_is_source_tree_when_not_frozen(self) -> None:
        from create_subscriptions import data_dir

        self.assertEqual(data_dir(), Path(__file__).resolve().parent)

    def test_duplicate_product_ids(self) -> None:
        payload = {
            "group_id": "1",
            "default_localizations": [{"locale": "en-US", "name": "VIP"}],
            "subscriptions": [
                {
                    "product_id": "dj.week.1.0",
                    "reference_name": "a",
                    "period": "ONE_WEEK",
                    "usd_price": "6.99",
                },
                {
                    "product_id": "dj.week.1.0",
                    "reference_name": "b",
                    "period": "ONE_WEEK",
                    "usd_price": "6.99",
                },
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = Path(handle.name)
        try:
            with self.assertRaises(ASCError):
                load_catalog(path)
        finally:
            path.unlink(missing_ok=True)

    def test_scaffold_matrix(self) -> None:
        catalog = scaffold_catalog(
            group_id="22115962",
            prefix="dj",
            name_prefix="vip",
            period="week",
            version=1,
            usd_price="6.99",
            intro_usd="0.99",
            start_level=1,
            display_name="VIP Membership",
            display_description="Unlock all premium short dramas.",
        )
        product_ids = [item["product_id"] for item in catalog["subscriptions"]]
        self.assertEqual(
            product_ids,
            ["dj.week.1.0", "dj.week.1.1", "dj.week.1.2", "dj.week.1.3"],
        )
        self.assertEqual(catalog["subscriptions"][0]["reference_name"], "vip-week-1.0-无试用")
        self.assertEqual(catalog["subscriptions"][2]["intro"]["usd_price"], "0.99")
        self.assertNotIn("intro", catalog["subscriptions"][0])


class PayloadTests(unittest.TestCase):
    def test_create_payload(self) -> None:
        catalog = load_catalog(Path(__file__).parent / "tests" / "example.json")
        sku = catalog.subscriptions[0]
        payload = subscription_create_payload(sku, catalog.group_id, catalog)
        attributes = payload["data"]["attributes"]
        self.assertEqual(attributes["productId"], "dj.month.1.0")
        self.assertEqual(attributes["subscriptionPeriod"], "ONE_MONTH")
        self.assertNotIn("availableInAllTerritories", attributes)
        self.assertEqual(payload["data"]["relationships"]["group"]["data"]["id"], "22115962")

    def test_localization_and_price_payloads(self) -> None:
        localization = localization_payload(
            "sub-1",
            load_catalog(Path(__file__).parent / "tests" / "example.json").default_localizations[0],
        )
        self.assertEqual(localization["data"]["attributes"]["locale"], "en-US")
        price = price_payload("sub-1", "point-1")
        self.assertEqual(price["data"]["relationships"]["subscriptionPricePoint"]["data"]["id"], "point-1")

    def test_intro_payload_includes_price_point_for_paid_offer(self) -> None:
        catalog = load_catalog(Path(__file__).parent / "tests" / "example.json")
        intro = catalog.subscriptions[2].intro
        assert intro is not None
        payload = intro_payload("sub-1", intro, territory_id=None, price_point_id="point-1")
        self.assertEqual(payload["data"]["attributes"]["offerMode"], "PAY_AS_YOU_GO")
        self.assertEqual(
            payload["data"]["relationships"]["subscriptionPricePoint"]["data"]["id"],
            "point-1",
        )


class AuthDiscoveryTests(unittest.TestCase):
    def test_key_id_from_apple_filename(self) -> None:
        self.assertEqual(key_id_from_p8_name(Path("AuthKey_ABC12DEF34.p8")), "ABC12DEF34")
        self.assertIsNone(key_id_from_p8_name(Path("secret.p8")))

    def test_discover_single_p8(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "AuthKey_ABC12DEF34.p8").write_text("placeholder", encoding="utf-8")
            found = discover_p8(directory)
            assert found is not None
            self.assertEqual(found.name, "AuthKey_ABC12DEF34.p8")

    def test_save_credentials_copies_key(self) -> None:
        from create_subscriptions import save_credentials

        with tempfile.TemporaryDirectory() as raw:
            incoming = Path(raw) / "incoming"
            incoming.mkdir()
            p8 = incoming / "AuthKey_ABC12DEF34.p8"
            p8.write_text("placeholder", encoding="utf-8")
            dest_dir = Path(raw) / "data"
            stored = save_credentials("issuer-id", "ABC12DEF34", p8, directory=dest_dir)
            self.assertTrue(stored.is_file())
            env_text = (dest_dir / ".env").read_text(encoding="utf-8")
            self.assertIn("ASC_ISSUER_ID=issuer-id", env_text)
            self.assertIn("ASC_KEY_ID=ABC12DEF34", env_text)
            self.assertNotIn("placeholder", env_text)


class VersionBumpTests(unittest.TestCase):
    def test_carry_at_nine(self) -> None:
        sys.path.insert(0, str(Path(__file__).parent / "scripts"))
        from next_version import bump

        self.assertEqual(bump("1.0.0"), "1.0.1")
        self.assertEqual(bump("1.0.9"), "1.1.0")
        self.assertEqual(bump("1.9.9"), "2.0.0")


class AscPricingParseTests(unittest.TestCase):
    def test_current_usa_price_from_included_point(self) -> None:
        from create_subscriptions import current_usa_customer_price

        prices = [
            {
                "attributes": {"startDate": "2024-01-01"},
                "relationships": {
                    "territory": {"data": {"id": "USA"}},
                    "subscriptionPricePoint": {"data": {"id": "pp-1"}},
                },
            },
            {
                "attributes": {"startDate": "2099-01-01"},
                "relationships": {
                    "territory": {"data": {"id": "USA"}},
                    "subscriptionPricePoint": {"data": {"id": "pp-future"}},
                },
            },
        ]
        included = {
            "pp-1": {"attributes": {"customerPrice": "4.99"}},
            "pp-future": {"attributes": {"customerPrice": "9.99"}},
        }
        self.assertEqual(
            current_usa_customer_price(prices, included, today="2026-08-20"),
            "4.99",
        )

    def test_current_usa_intro_free_trial(self) -> None:
        from create_subscriptions import current_usa_intro

        offers = [
            {
                "attributes": {
                    "offerMode": "FREE_TRIAL",
                    "duration": "THREE_DAYS",
                    "numberOfPeriods": 1,
                },
                "relationships": {"territory": {"data": {"id": "USA"}}},
            }
        ]
        intro = current_usa_intro(offers, {}, today="2026-08-20")
        self.assertEqual(
            intro,
            {"mode": "FREE_TRIAL", "duration": "THREE_DAYS", "number_of_periods": 1},
        )

    def test_merge_overwrites_placeholder_price_and_intro(self) -> None:
        from create_subscriptions import merge_local_sku_with_asc, sku_dict_from_asc_row

        local = {
            "product_id": "dj.week.1.0",
            "reference_name": "old",
            "period": "ONE_WEEK",
            "usd_price": "0.99",
            "group_level": 1,
        }
        row = {
            "product": "dj.week.1.0",
            "name": "vip-week-1.0-无试用",
            "period": "ONE_WEEK",
            "level": "1",
            "state": "READY_TO_SUBMIT",
            "pricing": {
                "usd_price": "4.99",
                "intro": {"mode": "FREE_TRIAL", "duration": "THREE_DAYS", "number_of_periods": 1},
            },
        }
        merged = merge_local_sku_with_asc(local, row)
        self.assertEqual(merged["usd_price"], "4.99")
        self.assertEqual(merged["state"], "READY_TO_SUBMIT")
        self.assertEqual(merged["intro"]["mode"], "FREE_TRIAL")
        created = sku_dict_from_asc_row(row)
        self.assertEqual(created["usd_price"], "4.99")
        self.assertNotEqual(created["usd_price"], "0.99")


class ReviewScreenshotTests(unittest.TestCase):
    def test_reserve_and_commit_payloads(self) -> None:
        from create_subscriptions import (
            file_md5,
            review_screenshot_commit_payload,
            review_screenshot_reserve_payload,
        )

        reserved = review_screenshot_reserve_payload("sub-1", "shot.png", 12)
        self.assertEqual(reserved["data"]["type"], "subscriptionAppStoreReviewScreenshots")
        self.assertEqual(reserved["data"]["attributes"]["fileName"], "shot.png")
        self.assertEqual(reserved["data"]["relationships"]["subscription"]["data"]["id"], "sub-1")
        checksum = file_md5(b"hello")
        commit = review_screenshot_commit_payload("shot-1", checksum)
        self.assertTrue(commit["data"]["attributes"]["uploaded"])
        self.assertEqual(commit["data"]["attributes"]["sourceFileChecksum"], checksum)

    def test_store_review_screenshot_copies_png(self) -> None:
        from create_subscriptions import store_review_screenshot

        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "source.png"
            source.write_bytes(b"png-bytes")
            stored = store_review_screenshot("dj.month.1.0", str(source), directory=Path(raw))
            dest = Path(stored)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.name, "dj.month.1.0.png")
            self.assertEqual(dest.read_bytes(), b"png-bytes")


if __name__ == "__main__":
    unittest.main()
