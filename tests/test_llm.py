import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from daily_briefing.llm import (
    ApiKeyRing,
    JsonlSummaryCache,
    LlmClient,
    LlmSettings,
    cache_key,
    chat_completion_text,
    split_api_keys,
)


class LlmTests(unittest.TestCase):
    def test_split_api_keys_prefers_primary_without_duplicates(self):
        self.assertEqual(split_api_keys("a", "b,a,c"), ["b", "a", "c"])
        self.assertEqual(split_api_keys("a", "b,c"), ["a", "b", "c"])

    def test_api_key_ring_rotates(self):
        ring = ApiKeyRing(["a", "b"])
        self.assertEqual([ring.next(), ring.next(), ring.next()], ["a", "b", "a"])
        with self.assertRaises(RuntimeError):
            ApiKeyRing([]).next()

    def test_cache_key_is_stable_for_sorted_payload(self):
        one = cache_key("kind", {"b": 2, "a": 1}, "deepseek", "model", "v1")
        two = cache_key("kind", {"a": 1, "b": 2}, "deepseek", "model", "v1")
        three = cache_key("kind", {"a": 1, "b": 3}, "deepseek", "model", "v1")
        self.assertEqual(one, two)
        self.assertNotEqual(one, three)

    def test_jsonl_summary_cache_load_get_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.jsonl"
            path.write_text(
                json.dumps({"key": "old", "created_at": 1, "value": "old"}, ensure_ascii=False)
                + "\n"
                + json.dumps({"key": "fresh", "created_at": 100, "value": "fresh"}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            cache = JsonlSummaryCache(str(path), ttl_seconds=50)
            cache.load(now=120)
            self.assertIsNone(cache.get("old", now=120))
            self.assertEqual(cache.get("fresh", now=120), "fresh")
            cache.set("new", "kind", "value", metadata={"model": "m"}, now=130)
            self.assertEqual(cache.get("new", now=130), "value")
            self.assertIn('"model": "m"', path.read_text(encoding="utf-8"))

    def test_chat_completion_text_posts_expected_payload(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")

        requests = []

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch("daily_briefing.llm.urllib.request.urlopen", fake_urlopen):
            text = chat_completion_text(
                base_url="https://api.example.com/",
                api_key="secret",
                model="model",
                messages=[{"role": "user", "content": "hi"}],
                timeout=12,
                response_format={"type": "json_object"},
            )
        self.assertEqual(text, "ok")
        req, timeout = requests[0]
        self.assertEqual(timeout, 12)
        self.assertEqual(req.full_url, "https://api.example.com/chat/completions")
        self.assertEqual(req.headers["Authorization"], "Bearer secret")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["response_format"], {"type": "json_object"})

    def test_llm_client_retries_with_next_key(self):
        calls = []

        def fake_chat_completion_text(**kwargs):
            calls.append(kwargs["api_key"])
            if len(calls) == 1:
                raise TimeoutError("slow")
            return "ok"

        settings = LlmSettings(
            provider="deepseek",
            base_url="https://api.example.com",
            model="model",
            api_keys=["k1", "k2"],
            timeout=3,
            retries=1,
            retry_backoff_seconds=0,
        )
        with patch("daily_briefing.llm.chat_completion_text", fake_chat_completion_text):
            result = LlmClient(settings).chat([{"role": "user", "content": "hi"}])

        self.assertEqual(result, "ok")
        self.assertEqual(calls, ["k1", "k2"])

    def test_llm_settings_from_env_selects_provider(self):
        settings = LlmSettings.from_env(
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "oa",
                "OPENAI_MODEL": "gpt-test",
                "LLM_TIMEOUT_SECONDS": "9",
            }
        )
        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.model, "gpt-test")
        self.assertEqual(settings.api_keys, ["oa"])
        self.assertEqual(settings.timeout, 9)


if __name__ == "__main__":
    unittest.main()
