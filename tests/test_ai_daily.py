import json
import unittest
from unittest.mock import patch

from work.ai_daily import ai_daily


class AIDailyDateTests(unittest.TestCase):
    def test_source_publish_time_uses_gmt_create(self):
        self.assertEqual(
            ai_daily.source_publish_time({"gmtCreate": "2026-06-23 08:30:00"}),
            "2026-06-23 08:30:00",
        )

    def test_parse_source_date_supports_iso_and_millisecond_timestamp(self):
        self.assertEqual(str(ai_daily.parse_source_date("2026-06-23T23:30:00+08:00")), "2026-06-23")
        self.assertEqual(str(ai_daily.parse_source_date("1782187200000")), "2026-06-23")

    def test_source_time_shanghai_converts_utc_timestamp(self):
        self.assertEqual(
            ai_daily.source_time_shanghai("2026-06-23T18:30:00Z"),
            "2026-06-24 02:30",
        )

    def test_filter_items_for_digest_date_drops_stale_and_missing_items(self):
        items = [
            {"channel": "小红书", "title": "new", "publishTime": "2026-06-23 09:00:00"},
            {"channel": "小红书", "title": "old", "publishTime": "2026-03-06 06:55:18"},
            {"channel": "小红书", "title": "unknown", "publishTime": ""},
        ]
        with patch.object(ai_daily, "DIGEST_DATE", "2026-06-23"):
            filtered = ai_daily.filter_items_for_digest_date(items)
        self.assertEqual([item["title"] for item in filtered], ["new"])

    def test_filter_items_requires_exact_digest_date_for_aihot(self):
        items = [
            {"channel": "AI资讯", "title": "today", "publishTime": "2026-06-23T02:00:00Z"},
            {"channel": "AI资讯", "title": "next-day", "publishTime": "2026-06-23T16:30:00Z"},
        ]
        with patch.object(ai_daily, "DIGEST_DATE", "2026-06-23"):
            filtered = ai_daily.filter_items_for_digest_date(items)
        self.assertEqual([item["title"] for item in filtered], ["today"])

    def test_normalize_aihot_maps_source_fields(self):
        item = ai_daily.normalize_aihot(
            {
                "id": "item-1",
                "title": "新模型发布",
                "summary": "模型能力得到更新。",
                "source": "OpenAI News",
                "url": "https://example.com/article",
                "publishedAt": "2026-06-23T09:00:00Z",
                "category": "ai-models",
                "score": 72,
            }
        )
        self.assertEqual(item["channel"], "AI资讯")
        self.assertEqual(item["author"], "OpenAI News")
        self.assertEqual(item["score"], 72)

    def test_fetch_aihot_page_uses_selected_window(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"count": 0, "hasNext": False, "items": []}).encode()

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("work.ai_daily.ai_daily.urllib.request.urlopen", side_effect=fake_urlopen):
            ai_daily.fetch_aihot_page(
                {"mode": "selected", "since": "2026-06-22T16:00:00Z", "take": 50}
            )
        self.assertIn("mode=selected", captured["url"])
        self.assertIn("since=2026-06-22T16%3A00%3A00Z", captured["url"])
        self.assertEqual(captured["timeout"], ai_daily.AIHOT_TIMEOUT_SECONDS)

    def test_redfox_cache_rejects_record_from_another_digest_date(self):
        payload = {"_channel": "gzh", "keyword": "AI"}
        key = ai_daily.redfox_cache_key(payload)
        cache = {
            key: {
                "created_at": 1,
                "date": "2026-06-21",
                "data": {"items": [{"title": "stale"}]},
            }
        }
        with (
            patch.object(ai_daily, "DIGEST_DATE", "2026-06-23"),
            patch.object(ai_daily, "load_redfox_raw_cache", return_value=cache),
        ):
            self.assertIsNone(ai_daily.get_redfox_raw_cache(payload))

    def test_history_ignores_records_from_previous_source_version(self):
        records = [
            {"date": "2026-06-22", "items": [{"title": "old"}]},
            {
                "date": "2026-06-22",
                "version": ai_daily.AI_HISTORY_VERSION,
                "items": [{"title": "current"}],
            },
        ]
        with patch.object(ai_daily, "DIGEST_DATE", "2026-06-23"):
            pruned = ai_daily.prune_ai_history(records)
        self.assertEqual([record["items"][0]["title"] for record in pruned], ["current"])


if __name__ == "__main__":
    unittest.main()
