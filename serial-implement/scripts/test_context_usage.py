#!/usr/bin/env python3
"""context_usage.py 的回退链自检：只测纯解析与选择函数，不碰真实库和网络。

    uv run python -m unittest discover -s serial-implement/scripts -p "test_*.py"
"""

import json
import unittest

import context_usage


def provider_catalog():
    return {
        "deepseek": {
            "id": "deepseek",
            "models": {
                "deepseek-flash": {"limit": {"context": 1048576, "output": 393216}},
                "no-limit-model": {"limit": {"output": 8192}},
            },
        },
        "openai": {"models": {"broken": "not-a-dict"}},
    }


class CatalogValueTest(unittest.TestCase):
    def test_body_is_json_encoded_twice(self):
        raw = json.dumps(
            {
                "updatedAt": 1795052111864,
                "digest": "x",
                "body": json.dumps(provider_catalog()),
            }
        )
        limits, updated_at = context_usage.limits_from_catalog_value(raw)
        self.assertEqual(limits[("deepseek", "deepseek-flash")], 1048576)
        self.assertNotIn(("deepseek", "no-limit-model"), limits)
        self.assertEqual(updated_at, 1795052111864)

    def test_malformed_value_yields_nothing(self):
        for raw in ("not json", "[]", json.dumps({"body": "{"})):
            with self.subTest(raw=raw):
                self.assertEqual(context_usage.limits_from_catalog_value(raw), ({}, None))


class ModelsJsonTest(unittest.TestCase):
    def test_reads_provider_model_limit(self):
        limits = context_usage.limits_from_models_json(json.dumps(provider_catalog()))
        self.assertEqual(limits[("deepseek", "deepseek-flash")], 1048576)

    def test_malformed_file_yields_nothing(self):
        for raw in ("", "null", "[]"):
            with self.subTest(raw=raw):
                self.assertEqual(context_usage.limits_from_models_json(raw), {})


class ApiPayloadTest(unittest.TestCase):
    def test_reads_data_array(self):
        raw = json.dumps(
            {
                "location": {"directory": "/x"},
                "data": [
                    {
                        "providerID": "deepseek",
                        "modelID": "deepseek-flash",
                        "limit": {"context": 1048576},
                    },
                    {"providerID": "custom", "id": "local", "limit": {"context": 32768}},
                    {"providerID": "sans-limit", "modelID": "m"},
                ],
            }
        )
        limits = context_usage.limits_from_api_payload(raw)
        self.assertEqual(limits[("deepseek", "deepseek-flash")], 1048576)
        self.assertEqual(limits[("custom", "local")], 32768)
        self.assertNotIn(("sans-limit", "m"), limits)

    def test_malformed_payload_yields_nothing(self):
        for raw in (None, "", "not json", json.dumps({"data": "nope"})):
            with self.subTest(raw=raw):
                self.assertEqual(context_usage.limits_from_api_payload(raw), {})


class ResolveLimitTest(unittest.TestCase):
    def setUp(self):
        self.api = {("deepseek", "deepseek-flash"): 1048576}
        self.sqlite = {("deepseek", "deepseek-flash"): 200000, ("legacy", "only-here"): 65536}
        self.file = {("legacy", "only-here"): 32768, ("file", "only"): 8192}
        self.sources = [("api", self.api), ("sqlite", self.sqlite), ("file", self.file)]

    def test_api_wins(self):
        self.assertEqual(
            context_usage.resolve_limit("deepseek", "deepseek-flash", self.sources),
            (1048576, "api"),
        )

    def test_falls_back_to_sqlite_per_pair(self):
        self.assertEqual(
            context_usage.resolve_limit("legacy", "only-here", self.sources),
            (65536, "sqlite"),
        )

    def test_falls_back_to_file(self):
        self.assertEqual(
            context_usage.resolve_limit("file", "only", self.sources), (8192, "file")
        )

    def test_unknown_pair_has_no_source(self):
        self.assertEqual(context_usage.resolve_limit("nope", "nope", self.sources), (None, None))

    def test_missing_provider_or_model(self):
        self.assertEqual(context_usage.resolve_limit(None, "x", self.sources), (None, None))
        self.assertEqual(context_usage.resolve_limit("x", None, self.sources), (None, None))


class StalenessTest(unittest.TestCase):
    def test_recent_is_fresh(self):
        now = 1_800_000_000_000
        self.assertFalse(context_usage.catalog_is_stale(now - 86_400_000, now))

    def test_old_is_stale(self):
        now = 1_800_000_000_000
        self.assertTrue(context_usage.catalog_is_stale(now - 31 * 86_400_000, now))

    def test_unknown_timestamp_is_not_stale(self):
        self.assertFalse(context_usage.catalog_is_stale(None))


if __name__ == "__main__":
    unittest.main()
