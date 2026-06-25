import unittest
from unittest.mock import patch

from work.wechat_daily import wechat_daily


class WechatDailyCompletenessTests(unittest.TestCase):
    def test_retries_hot_before_fetching_authors(self):
        sleeps = []
        hot_results = [
            [{"title": f"partial-{index}"} for index in range(4)],
            [{"title": f"complete-{index}"} for index in range(8)],
        ]
        followed = [{"title": "followed"}]
        with (
            patch.object(wechat_daily, "WECHAT_MIN_HOT_ARTICLES", 6),
            patch.object(wechat_daily, "WECHAT_SOURCE_RETRY_ATTEMPTS", 2),
            patch.object(wechat_daily, "WECHAT_SOURCE_RETRY_DELAY_SECONDS", 1),
            patch.object(wechat_daily, "is_formal_run", return_value=True),
            patch.object(wechat_daily, "load_hot_articles", side_effect=hot_results),
            patch.object(
                wechat_daily,
                "fetch_follow_author_articles",
                return_value=followed,
            ) as fetch_follow,
            patch.object(wechat_daily, "hot_author_skip_set", return_value=set()),
            patch.object(wechat_daily, "clear_digest_redfox_cache"),
        ):
            articles, follow_articles = wechat_daily.load_complete_daily_data(
                sleep_fn=sleeps.append
            )
        self.assertEqual(len(articles), 8)
        self.assertEqual(follow_articles, followed)
        self.assertEqual(sleeps, [1])
        fetch_follow.assert_called_once()

    def test_raises_instead_of_sending_incomplete_report(self):
        with (
            patch.object(wechat_daily, "WECHAT_MIN_HOT_ARTICLES", 6),
            patch.object(wechat_daily, "WECHAT_SOURCE_RETRY_ATTEMPTS", 1),
            patch.object(
                wechat_daily,
                "load_hot_articles",
                return_value=[{"title": "partial"}],
            ),
        ):
            with self.assertRaises(RuntimeError):
                wechat_daily.load_complete_daily_data(sleep_fn=lambda _seconds: None)

    def test_retries_when_all_followed_authors_are_empty(self):
        hot = [{"title": f"hot-{index}"} for index in range(8)]
        sleeps = []
        with (
            patch.object(wechat_daily, "WECHAT_MIN_HOT_ARTICLES", 6),
            patch.object(wechat_daily, "WECHAT_SOURCE_RETRY_ATTEMPTS", 2),
            patch.object(wechat_daily, "WECHAT_SOURCE_RETRY_DELAY_SECONDS", 2),
            patch.object(wechat_daily, "WECHAT_REQUIRE_FOLLOW_CONTENT", True),
            patch.object(wechat_daily, "is_formal_run", return_value=True),
            patch.object(wechat_daily, "load_hot_articles", return_value=hot),
            patch.object(
                wechat_daily,
                "fetch_follow_author_articles",
                side_effect=[[], [{"title": "followed"}]],
            ),
            patch.object(wechat_daily, "hot_author_skip_set", return_value=set()),
            patch.object(wechat_daily, "clear_digest_redfox_cache"),
        ):
            _articles, follow_articles = wechat_daily.load_complete_daily_data(
                sleep_fn=sleeps.append
            )
        self.assertEqual(follow_articles, [{"title": "followed"}])
        self.assertEqual(sleeps, [2])


if __name__ == "__main__":
    unittest.main()
