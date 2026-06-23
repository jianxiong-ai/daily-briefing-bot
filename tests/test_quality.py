import json
import unittest
from pathlib import Path

from daily_briefing.quality import (
    dedupe_by_similarity,
    is_local_weather_noise,
    low_priority_topic_sort_key,
    text_similarity,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "quality"


class QualityTests(unittest.TestCase):
    def test_similarity_detects_close_ai_items(self):
        items = json.loads((FIXTURE_DIR / "ai_items.json").read_text(encoding="utf-8"))
        self.assertGreater(text_similarity(items[0]["title"], items[1]["title"]), 0.25)
        deduped = dedupe_by_similarity(items, lambda item: item["title"] + item["summary"], threshold=0.30)
        self.assertEqual([item["title"] for item in deduped], [items[0]["title"], items[2]["title"]])

    def test_local_weather_noise_keeps_broad_weather(self):
        articles = json.loads((FIXTURE_DIR / "wechat_articles.json").read_text(encoding="utf-8"))
        self.assertTrue(is_local_weather_noise(articles[0]["title"] + articles[0]["summary"]))
        self.assertFalse(is_local_weather_noise(articles[1]["title"] + articles[1]["summary"]))
        self.assertFalse(is_local_weather_noise(articles[2]["title"] + articles[2]["summary"]))

    def test_low_priority_topic_sort_key_moves_roundups_last(self):
        topics = [
            {"topic": "星球多领域问答汇总"},
            {"topic": "拉尼娜现象及其气候影响"},
            {"topic": "投资心态与长期主义"},
        ]
        ordered = sorted(topics, key=low_priority_topic_sort_key)
        self.assertEqual(ordered[-1]["topic"], "星球多领域问答汇总")


if __name__ == "__main__":
    unittest.main()
