import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from daily_briefing.redfox import RawJsonCache, post_json, public_payload, redfox_cache_key


class RedfoxTests(unittest.TestCase):
    def test_public_payload_strips_internal_keys(self):
        self.assertEqual(public_payload({"a": 1, "_cache_url": "x"}), {"a": 1})

    def test_cache_key_includes_url_and_public_payload(self):
        one = redfox_cache_key({"_cache_url": "a", "q": "x"})
        two = redfox_cache_key({"_cache_url": "b", "q": "x"})
        three = redfox_cache_key({"_cache_url": "a", "q": "x", "_channel": "ignored"})
        self.assertNotEqual(one, two)
        self.assertEqual(one, three)

    def test_raw_json_cache_get_set_and_ttl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "raw.json"
            cache = RawJsonCache(str(path), max_entries=2)
            payload = {"_cache_url": "u", "q": "x"}
            cache.set(payload, {"items": [1]}, metadata={"date": "2026-06-18"}, now=100)
            self.assertEqual(cache.get(payload, now=120, ttl_seconds=30), {"items": [1]})
            self.assertIsNone(cache.get(payload, now=140, ttl_seconds=30))
            self.assertIsNone(cache.get(payload, force_refresh=True))
            self.assertIn("2026-06-18", path.read_text(encoding="utf-8"))

    def test_post_json_strips_internal_payload_fields(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"code": 2000}).encode("utf-8")

        requests = []

        def fake_urlopen(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch("daily_briefing.redfox.urllib.request.urlopen", fake_urlopen):
            result = post_json("https://redfox.example/api", {"a": 1, "_cache_url": "x"}, "key", timeout=7)
        self.assertEqual(result, {"code": 2000})
        req, timeout = requests[0]
        self.assertEqual(timeout, 7)
        self.assertEqual(json.loads(req.data.decode("utf-8")), {"a": 1})
        headers = {key.lower(): value for key, value in req.headers.items()}
        self.assertEqual(headers["x-api-key"], "key")


if __name__ == "__main__":
    unittest.main()
