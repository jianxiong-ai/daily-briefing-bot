import unittest
from unittest.mock import patch

from work.wechat_daily import wechat_daily


class WechatDailyFallbackTests(unittest.TestCase):
    def test_unavailable_followed_author_does_not_cancel_other_authors(self):
        authors = [
            {"account": "available", "accountName": "可用作者"},
            {"account": "unavailable", "accountName": "未收录作者"},
        ]

        def fake_redfox_post(_url, payload):
            if payload["account"] == "unavailable":
                return {"code": 4000, "msg": "未查询到相关数据"}
            return {
                "code": 2000,
                "data": {
                    "list": [
                        {
                            "workUuid": "work-1",
                            "title": "可用作者的新文章",
                            "account": "available",
                            "accountName": "可用作者",
                            "publishTime": "2026-06-23 09:00:00",
                        }
                    ],
                    "total": 1,
                    "hasMore": False,
                },
            }

        with (
            patch.object(wechat_daily, "WECHAT_FOLLOW_AUTHORS", authors),
            patch.object(wechat_daily, "WECHAT_FOLLOW_FETCH_WORKERS", 2),
            patch.object(wechat_daily, "WECHAT_FOLLOW_MAX_PAGES", 1),
            patch.object(wechat_daily, "get_redfox_raw_cache", return_value=None),
            patch.object(wechat_daily, "set_redfox_raw_cache"),
            patch.object(wechat_daily, "redfox_post_json", side_effect=fake_redfox_post),
        ):
            items = wechat_daily.fetch_follow_author_articles()

        self.assertEqual([item["title"] for item in items], ["可用作者的新文章"])


if __name__ == "__main__":
    unittest.main()
