import json
import unittest
from pathlib import Path

from daily_briefing.quality import (
    dedupe_by_similarity,
    is_local_weather_noise,
    is_similar_event,
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

    def test_similar_event_detects_rewritten_market_story(self):
        self.assertTrue(
            is_similar_event(
                "美股芯片股深夜全线下挫，闪迪大跌12%，SpaceX反弹拉升2%，百度、阿里巴巴、拼多多集体下跌",
                "存储芯片制造商闪迪股价大跌12%，中概股与芯片股集体承压。",
                "美股开盘：闪迪、美光科技暴跌，半导体板块集体重挫",
                "闪迪跌12%，美光科技与西部数据跌超10%，半导体指数走低。",
            )
        )

    def test_similar_event_detects_same_person_and_score(self):
        self.assertTrue(
            is_similar_event(
                "郭斌（武汉学生，721分），全国第一！",
                "失明考生郭斌取得优异成绩。",
                "高考721分！郭斌已被录取，全国同专业第一",
                "郭斌以721分被长春大学录取。",
            )
        )

    def test_similar_event_keeps_distinct_stories_in_same_field(self):
        self.assertFalse(
            is_similar_event(
                "美股芯片股大跌，闪迪跌12%",
                "半导体板块集体走低。",
                "国产芯片研发取得新突破",
                "新型存储芯片进入量产阶段。",
            )
        )

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
