import os
import unittest
from unittest import mock

from scripts.fetch_trendforce import resolve_google_api_key


class FetchTrendforceTests(unittest.TestCase):
    def test_resolve_google_api_key_prefers_env_file(self):
        env_vars = {
            "GOOGLE_API_KEY": '"from_env_file"',
        }
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "from_process_env"}, clear=False):
            self.assertEqual(resolve_google_api_key(env_vars), "from_env_file")

    def test_resolve_google_api_key_uses_aliases(self):
        env_vars = {
            "GEMINI_API_KEY": "gemini_key",
        }
        with mock.patch.dict(os.environ, {}, clear=False):
            self.assertEqual(resolve_google_api_key(env_vars), "gemini_key")

    def test_resolve_google_api_key_falls_back_to_process_env(self):
        env_vars = {}
        with mock.patch.dict(os.environ, {"GOOGLE_GENAI_API_KEY": "genai_key"}, clear=False):
            self.assertEqual(resolve_google_api_key(env_vars), "genai_key")

    def test_resolve_google_api_key_returns_none_when_missing(self):
        env_vars = {}
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve_google_api_key(env_vars))


if __name__ == "__main__":
    unittest.main()
