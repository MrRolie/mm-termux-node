import unittest
from types import SimpleNamespace
from unittest import mock

from mm_termux_node import trendforce_ai


class FakeModels:
    def __init__(self, store):
        self._store = store

    def generate_content(self, model, contents):
        self._store["model"] = model
        self._store["contents"] = contents
        return SimpleNamespace(text="SUMMARY")


class FakeClient:
    def __init__(self, api_key, store):
        self.api_key = api_key
        self.models = FakeModels(store)


class TrendforceAiTests(unittest.TestCase):
    def test_generate_ai_summary_returns_none_when_no_updates(self):
        result = trendforce_ai.generate_ai_summary("key", [], [])
        self.assertIsNone(result)

    def test_generate_ai_summary_builds_prompt_and_returns_text(self):
        store = {}
        fake_genai = SimpleNamespace(Client=lambda api_key: FakeClient(api_key, store))

        with mock.patch.object(trendforce_ai, "genai", fake_genai):
            result = trendforce_ai.generate_ai_summary(
                "key",
                ["ID 1 (DRAM Spot): 10.0 USD (+1.0%)"],
                ["⚠️ DRAM Golden Cross: TRIGGERED"],
            )

        self.assertEqual(result, "SUMMARY")
        self.assertEqual(store["model"], "gemini-flash-latest")
        self.assertIn("ID 1 (DRAM Spot)", store["contents"])
        self.assertIn("⚠️ DRAM Golden Cross", store["contents"])


if __name__ == "__main__":
    unittest.main()
