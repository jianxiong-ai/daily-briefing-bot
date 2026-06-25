import importlib.util
import os
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name, digest_date="2026-06-24"):
    old = os.environ.get("DIGEST_DATE")
    os.environ["DIGEST_DATE"] = digest_date
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / "work/astock_daily/astock_daily.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old is None:
            os.environ.pop("DIGEST_DATE", None)
        else:
            os.environ["DIGEST_DATE"] = old


class AStockDailyTests(unittest.TestCase):
    def test_social_normalization_filters_stale_and_noise(self):
        module = load_module("astock_filter")
        data = {
            "gzhResult": [
                {
                    "title": "半导体板块景气度讨论",
                    "summary": "A股芯片公司订单与估值受到关注",
                    "author": "机构号",
                    "publicTime": "2026-06-24 09:00:00",
                    "clicksCount": 10000,
                },
                {
                    "title": "旧日A股复盘",
                    "summary": "大盘走势",
                    "author": "旧文章",
                    "publicTime": "2026-06-23 09:00:00",
                },
                {
                    "title": "明星夏日穿搭",
                    "summary": "美妆穿搭分享",
                    "author": "娱乐号",
                    "publicTime": "2026-06-24 10:00:00",
                },
            ]
        }
        items = module.normalize_social_data(data)
        self.assertEqual([item["title"] for item in items], ["半导体板块景气度讨论"])

    def test_social_normalization_deduplicates_similar_events(self):
        module = load_module("astock_dedupe")
        data = {
            "gzhResult": [
                {
                    "title": "机器人板块迎来政策利好",
                    "summary": "A股机器人产业链受到市场关注",
                    "publicTime": "2026-06-24 09:00:00",
                },
                {
                    "title": "机器人板块迎政策利好",
                    "summary": "A股机器人产业链受到市场关注",
                    "publicTime": "2026-06-24 10:00:00",
                },
            ]
        }
        self.assertEqual(len(module.normalize_social_data(data)), 1)

    def test_publish_normalization_classifies_official_and_kol(self):
        module = load_module("astock_publish")
        data = {
            "accounts": [
                {
                    "accountName": "财联社",
                    "works": [{"title": "A股市场要闻", "publishTime": "2026-06-24 08:00:00"}],
                },
                {
                    "accountName": "凯恩斯",
                    "works": [{"title": "A股投资随笔", "publishTime": "2026-06-24 09:00:00"}],
                },
            ]
        }
        items = module.normalize_publish_data(data)
        categories = {item["author"]: item["category"] for item in items}
        self.assertEqual(categories["财联社"], "机构/媒体")
        self.assertEqual(categories["凯恩斯"], "个人大V")

    def test_publish_normalization_filters_non_stock_posts(self):
        module = load_module("astock_publish_noise")
        data = {
            "accounts": [
                {
                    "accountName": "胡斐投资办公室",
                    "works": [
                        {
                            "title": "汉服很美",
                            "summary": "分享传统服饰审美",
                            "publishTime": "2026-06-24 09:00:00",
                        }
                    ],
                }
            ]
        }
        self.assertEqual(module.normalize_publish_data(data), [])

    def test_daily_lines_always_include_disclaimer(self):
        module = load_module("astock_lines")
        module.build_digest = lambda *_args: {
            "overview": "市场关注产业政策。",
            "topics": [],
            "views": [],
            "risks": [],
        }
        sections = module.build_daily_lines([], [])
        self.assertIn("不构成投资建议", "\n".join(sections[-1]))

    def test_daily_lines_split_multiline_overview(self):
        module = load_module("astock_multiline")
        module.build_digest = lambda *_args: {
            "overview": "第一段。\n\n第二段。",
            "topics": [],
            "views": [],
            "risks": [],
        }
        overview = module.build_daily_lines([], [])[0]
        self.assertEqual(overview[1:], ["第一段。", "第二段。"])

    def test_llm_views_are_limited_by_publish_authors(self):
        module = load_module("astock_view_limit")
        module.LLM_CACHE_STORE.get = lambda *_args, **_kwargs: None
        module.LLM_CACHE_STORE.set = lambda *_args, **_kwargs: None
        module.Process = _ImmediateProcess
        module.Queue = _FakeQueue
        payload = {
            "date": "2026-06-24",
            "social": [{"author": "社交作者", "title": "市场讨论"}],
            "publish": [{"author": "财联社", "title": "机构文章"}],
        }
        result = module.request_digest(payload)
        self.assertEqual(len(result["views"]), 1)


class _FakeQueue:
    def __init__(self):
        self.value = None

    def put(self, value):
        self.value = value

    def empty(self):
        return self.value is None

    def get(self):
        return self.value


class _ImmediateProcess:
    def __init__(self, target, args):
        self.target = target
        self.args = args
        self._alive = False

    def start(self):
        queue = self.args[-1]
        queue.put(
            (
                "ok",
                '{"overview":"概览","topics":[],"views":['
                '{"title":"观点1","summary":"摘要1"},'
                '{"title":"观点2","summary":"摘要2"}],"risks":[]}',
            )
        )

    def join(self, _timeout=None):
        return None

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False


if __name__ == "__main__":
    unittest.main()
