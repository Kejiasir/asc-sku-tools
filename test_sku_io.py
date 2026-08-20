#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from create_subscriptions import ASCError
from sku_io import (
    dump_skus,
    load_skus,
    merge_skus,
    write_excel_template,
    write_json_template,
)


SAMPLE_SKUS = [
    {
        "product_id": "dj.week.1.0",
        "reference_name": "vip-week-1.0-无试用",
        "period": "ONE_WEEK",
        "usd_price": "6.99",
        "group_level": 1,
    },
    {
        "product_id": "dj.month.1.1",
        "reference_name": "vip-month-1.1-前三天免费",
        "period": "ONE_MONTH",
        "usd_price": "29.99",
        "group_level": 2,
        "intro": {"mode": "FREE_TRIAL", "duration": "THREE_DAYS", "number_of_periods": 1},
        "review_note": "Monthly VIP",
    },
    {
        "product_id": "dj.month.1.2",
        "reference_name": "vip-month-1.2-首周折扣",
        "period": "ONE_MONTH",
        "usd_price": "29.99",
        "group_level": 3,
        "intro": {
            "mode": "PAY_AS_YOU_GO",
            "duration": "ONE_MONTH",
            "number_of_periods": 2,
            "usd_price": "0.99",
        },
    },
]


class JsonExchangeTests(unittest.TestCase):
    def test_roundtrip_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "skus.json"
            dump_skus(SAMPLE_SKUS, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["format"], "asc-sku.subscriptions")
            loaded = load_skus(path)
        self.assertEqual(loaded[0]["product_id"], "dj.week.1.0")
        self.assertEqual(loaded[1]["intro"]["mode"], "FREE_TRIAL")
        self.assertEqual(loaded[2]["intro"]["number_of_periods"], 2)
        self.assertEqual(loaded[2]["intro"]["usd_price"], "0.99")

    def test_accepts_bare_array_and_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            array_path = Path(raw) / "array.json"
            catalog_path = Path(raw) / "catalog.json"
            array_path.write_text(json.dumps(SAMPLE_SKUS, ensure_ascii=False), encoding="utf-8")
            catalog_path.write_text(
                json.dumps({"group_id": "1", "subscriptions": SAMPLE_SKUS}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(load_skus(array_path)[0]["product_id"], "dj.week.1.0")
            self.assertEqual(len(load_skus(catalog_path)), 3)

    def test_accepts_chinese_period_and_intro(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "zh.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "产品 ID": "dj.year.1.0",
                            "参考名称": "vip-year",
                            "持续时间": "1 年",
                            "美区价格": "99.99",
                            "级别": 4,
                            "推介优惠类型": "免费",
                            "推介持续时间": "3 天",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            loaded = load_skus(path)
        self.assertEqual(loaded[0]["period"], "ONE_YEAR")
        self.assertEqual(loaded[0]["group_level"], 4)
        self.assertEqual(loaded[0]["intro"]["mode"], "FREE_TRIAL")
        self.assertEqual(loaded[0]["intro"]["duration"], "THREE_DAYS")

    def test_rejects_missing_product_id(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "bad.json"
            path.write_text(json.dumps([{"reference_name": "x", "period": "ONE_WEEK", "usd_price": "1"}]), encoding="utf-8")
            with self.assertRaises(ASCError):
                load_skus(path)


class ExcelExchangeTests(unittest.TestCase):
    def test_roundtrip_excel(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "skus.xlsx"
            dump_skus(SAMPLE_SKUS, path)
            loaded = load_skus(path)
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0]["period"], "ONE_WEEK")
        self.assertEqual(loaded[0]["usd_price"], "6.99")
        self.assertEqual(loaded[1]["intro"]["duration"], "THREE_DAYS")
        self.assertEqual(loaded[2]["intro"]["mode"], "PAY_AS_YOU_GO")
        self.assertEqual(loaded[2]["intro"]["number_of_periods"], 2)
        self.assertEqual(loaded[2]["intro"]["usd_price"], "0.99")

    def test_json_and_excel_export_the_same_skus(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            json_path = Path(raw) / "skus.json"
            excel_path = Path(raw) / "skus.xlsx"
            dump_skus(SAMPLE_SKUS, json_path)
            dump_skus(SAMPLE_SKUS, excel_path)
            self.assertEqual(load_skus(json_path), load_skus(excel_path))

    def test_templates_are_importable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            json_path = Path(raw) / "template.json"
            excel_path = Path(raw) / "template.xlsx"
            write_json_template(json_path)
            write_excel_template(excel_path)
            json_skus = load_skus(json_path)
            excel_skus = load_skus(excel_path)
        self.assertGreaterEqual(len(json_skus), 1)
        self.assertEqual(len(json_skus), len(excel_skus))
        self.assertEqual(json_skus[0]["product_id"], excel_skus[0]["product_id"])


class MergeTests(unittest.TestCase):
    def test_merge_updates_and_appends(self) -> None:
        existing = [dict(SAMPLE_SKUS[0]), dict(SAMPLE_SKUS[1])]
        incoming = [
            {**SAMPLE_SKUS[0], "usd_price": "9.99"},
            dict(SAMPLE_SKUS[2]),
        ]
        merged, added, updated = merge_skus(existing, incoming, replace=False)
        by_id = {item["product_id"]: item for item in merged}
        self.assertEqual(added, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(by_id["dj.week.1.0"]["usd_price"], "9.99")
        self.assertEqual(by_id["dj.month.1.1"]["usd_price"], "29.99")
        self.assertIn("dj.month.1.2", by_id)

    def test_replace_discards_old_rows(self) -> None:
        merged, added, updated = merge_skus(SAMPLE_SKUS, [SAMPLE_SKUS[0]], replace=True)
        self.assertEqual(len(merged), 1)
        self.assertEqual(added, 1)
        self.assertEqual(updated, 0)


if __name__ == "__main__":
    unittest.main()
