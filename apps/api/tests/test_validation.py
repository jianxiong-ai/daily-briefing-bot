import os
import unittest
from pathlib import Path

os.environ.setdefault("PROJECT_DIR", str(Path(__file__).resolve().parents[3]))


class ValidationTest(unittest.TestCase):
    def _levels(self, issues):
        return {issue["key"]: issue["level"] for issue in issues}

    def test_missing_required_fields_are_errors(self):
        from app.services.validation import errors_only, validate_subscription

        issues = validate_subscription(
            {
                "report_type": "wechat",
                "push_time": "07:55",
                "is_active": True,
                "feishu_webhook": "https://open.feishu.cn/hook",
                "config": {},
            }
        )
        levels = self._levels(issues)
        self.assertEqual(levels.get("REDFOX_API_KEY"), "error")
        self.assertEqual(levels.get("DEEPSEEK_API_KEYS"), "error")
        self.assertTrue(errors_only(issues))

    def test_valid_config_has_no_errors(self):
        from app.services.validation import errors_only, validate_subscription

        issues = validate_subscription(
            {
                "report_type": "wechat",
                "push_time": "07:55",
                "is_active": True,
                "feishu_webhook": "https://open.feishu.cn/hook",
                "config": {"REDFOX_API_KEY": "ak_real", "DEEPSEEK_API_KEYS": "sk-real"},
            }
        )
        self.assertEqual(errors_only(issues), [])

    def test_push_time_outside_window_is_warning(self):
        from app.services.validation import errors_only, validate_subscription

        issues = validate_subscription(
            {
                "report_type": "weibo",
                "push_time": "08:00",
                "is_active": True,
                "feishu_webhook": "https://open.feishu.cn/hook",
                "config": {"DEEPSEEK_API_KEYS": "sk-real"},
            }
        )
        levels = self._levels(issues)
        self.assertEqual(levels.get("push_time"), "warning")
        self.assertEqual(errors_only(issues), [])

    def test_active_without_webhook_warns(self):
        from app.services.validation import validate_subscription

        issues = validate_subscription(
            {
                "report_type": "cctv",
                "push_time": "08:00",
                "is_active": True,
                "feishu_webhook": "",
                "config": {"DEEPSEEK_API_KEYS": "sk-real"},
            }
        )
        levels = self._levels(issues)
        self.assertEqual(levels.get("feishu_webhook"), "warning")


if __name__ == "__main__":
    unittest.main()
