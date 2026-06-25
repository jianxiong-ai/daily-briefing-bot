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

    def test_filter_items_for_digest_date_drops_stale_and_missing_items(self):
        items = [
            {"channel": "小红书", "title": "new", "publishTime": "2026-06-23 09:00:00"},
            {"channel": "小红书", "title": "old", "publishTime": "2026-03-06 06:55:18"},
            {"channel": "小红书", "title": "unknown", "publishTime": ""},
        ]
        with patch.object(ai_daily, "DIGEST_DATE", "2026-06-23"):
            filtered = ai_daily.filter_items_for_digest_date(items)
        self.assertEqual([item["title"] for item in filtered], ["new"])

    def test_filter_items_keeps_recent_gzh_pool_item(self):
        items = [
            {"channel": "公众号", "title": "recent", "publishTime": "2026-06-18 09:00:00"},
            {"channel": "公众号", "title": "stale", "publishTime": "2026-05-01 09:00:00"},
        ]
        with (
            patch.object(ai_daily, "DIGEST_DATE", "2026-06-23"),
            patch.object(ai_daily, "AI_GZH_MAX_AGE_DAYS", 14),
        ):
            filtered = ai_daily.filter_items_for_digest_date(items)
        self.assertEqual([item["title"] for item in filtered], ["recent"])

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


if __name__ == "__main__":
    unittest.main()
