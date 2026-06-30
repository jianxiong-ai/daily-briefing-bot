import os
import tempfile
import unittest
from pathlib import Path


class DashboardStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ["PROJECT_DIR"] = str(Path(__file__).resolve().parents[3])
        os.environ["DATABASE_PATH"] = str(root / "subscriptions.sqlite3")
        os.environ["SUBSCRIPTION_ENV_DIR"] = str(root / "env")
        os.environ["SUBSCRIPTION_OUTPUT_DIR"] = str(root / "outputs")

        from app.config import get_settings

        get_settings.cache_clear()

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_and_update_subscription(self):
        from app.store import create_subscription, init_db, list_subscriptions, update_subscription

        init_db()
        created = create_subscription(
            {
                "report_type": "wechat",
                "name": "公众号日报",
                "push_time": "07:55",
                "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                "config": {"WECHAT_FOLLOW_AUTHORS": "财联社|cls-telegraph"},
            }
        )

        self.assertEqual(created["report_type"], "wechat")
        self.assertEqual(created["push_time"], "07:55")
        self.assertEqual(len(list_subscriptions()), 1)

        updated = update_subscription(created["id"], {"push_time": "08:05", "config": {"WECHAT_HOT_REPORT_LIMIT": "8"}})
        self.assertEqual(updated["push_time"], "08:05")
        self.assertEqual(updated["config"]["WECHAT_HOT_REPORT_LIMIT"], "8")

    def test_generated_env_contains_subscription_values(self):
        from app.services.report_runner import build_subscription_env
        from app.store import create_subscription, init_db

        init_db()
        created = create_subscription(
            {
                "report_type": "weibo",
                "name": "微博日报",
                "push_time": "22:30",
                "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                "config": {"WEIBO_BLOGGER_IDS": "1763864272,1906286443"},
            }
        )

        env_path, values = build_subscription_env(created)
        text = env_path.read_text(encoding="utf-8")
        self.assertIn("WEIBO_BLOGGER_IDS", text)
        self.assertEqual(values["FEISHU_WEBHOOK"], "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        self.assertEqual(values["FEISHU_WEBHOOKS"], "")
        self.assertEqual(values["WECHAT_WORK_WEBHOOKS"], "")
        self.assertEqual(values["PUSH_TARGETS"], "primary")
        self.assertEqual(values["SEND_AT_LOCAL"], "")

    def test_wechat_subscription_defaults_to_previous_day(self):
        from app.services.report_runner import build_subscription_env
        from app.store import create_subscription, init_db

        init_db()
        created = create_subscription(
            {
                "report_type": "wechat",
                "name": "公众号日报",
                "push_time": "07:55",
                "config": {"WECHAT_FOLLOW_AUTHORS": "财联社|cls-telegraph"},
            }
        )

        _, values = build_subscription_env(created)

        self.assertEqual(values["WECHAT_DIGEST_OFFSET_DAYS"], "1")

    def test_generated_env_writes_cookie_to_private_file(self):
        from app.services.report_runner import build_subscription_env
        from app.store import create_subscription, init_db

        init_db()
        created = create_subscription(
            {
                "report_type": "weibo",
                "name": "微博日报",
                "push_time": "22:30",
                "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                "config": {
                    "WEIBO_COOKIE": "UNIT_COOKIE=test; UNIT_SESSION=test-sub",
                    "WEIBO_BLOGGER_IDS": "1763864272",
                },
            }
        )

        env_path, values = build_subscription_env(created)
        text = env_path.read_text(encoding="utf-8")
        cookie_path = Path(values["WEIBO_COOKIE_FILE"])

        self.assertNotIn("WEIBO_COOKIE=", text)
        self.assertIn("WEIBO_COOKIE_FILE", text)
        self.assertTrue(cookie_path.exists())
        self.assertEqual(cookie_path.read_text(encoding="utf-8").strip(), "UNIT_COOKIE=test; UNIT_SESSION=test-sub")

    def test_generated_env_isolates_runtime_per_subscription(self):
        from app.services.report_runner import build_subscription_env
        from app.store import create_subscription, init_db

        init_db()
        first = create_subscription({"report_type": "ai", "push_time": "07:50", "config": {}})
        second = create_subscription({"report_type": "ai", "push_time": "07:50", "config": {}})

        _, first_values = build_subscription_env(first)
        _, second_values = build_subscription_env(second)

        self.assertIn(f"subscription_{first['id']}_ai", first_values["DAILY_RUNTIME_DIR"])
        self.assertIn(f"subscription_{second['id']}_ai", second_values["DAILY_RUNTIME_DIR"])
        self.assertNotEqual(first_values["DAILY_RUNTIME_DIR"], second_values["DAILY_RUNTIME_DIR"])

    def test_extract_rendered_image_path_keeps_full_path(self):
        from app.services.report_runner import extract_rendered_image_path

        message = (
            "[2026-06-30 22:30:06] feishu image rendered path="
            "/data/runtime/subscription_7_weibo/images/weibo_daily_2026-06-30.png\n"
            "[2026-06-30 22:30:07] feishu image uploaded"
        )

        self.assertEqual(
            extract_rendered_image_path(message),
            "/data/runtime/subscription_7_weibo/images/weibo_daily_2026-06-30.png",
        )


if __name__ == "__main__":
    unittest.main()
