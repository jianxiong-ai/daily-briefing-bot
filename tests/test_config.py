import os
import tempfile
import unittest
from pathlib import Path

from daily_briefing.config import has_errors, mask_value, validate_report_config


class ConfigTests(unittest.TestCase):
    def test_mask_value_hides_secrets(self):
        self.assertEqual(mask_value("FEISHU_WEBHOOK", "https://example.com"), "<set:19 chars>")
        self.assertEqual(mask_value("REPORT_TITLE", "日报"), "日报")

    def test_validate_missing_env_is_error(self):
        issues = validate_report_config("wechat", "/tmp/not-here.env", {})
        self.assertTrue(has_errors(issues))
        self.assertIn("env file does not exist", issues[0].message)

    def test_validate_redfox_report_requires_redfox_and_llm_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text(
                "LLM_PROVIDER=deepseek\n"
                "FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/x\n",
                encoding="utf-8",
            )
            issues = validate_report_config("wechat", path, {})
        messages = {issue.key: issue.message for issue in issues}
        self.assertIn("REDFOX_API_KEY", messages)
        self.assertIn("DEEPSEEK_API_KEY", messages)

    def test_validate_uses_process_env_as_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text("LLM_PROVIDER=deepseek\nREDFOX_API_KEY=ak_live\n", encoding="utf-8")
            issues = validate_report_config(
                "wechat",
                path,
                {"DEEPSEEK_API_KEY": "sk-live", "FEISHU_WEBHOOK": "https://open.feishu.cn/open-apis/bot/v2/hook/x"},
            )
        self.assertFalse(has_errors(issues), issues)

    def test_validate_zsxq_requires_cookie_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text(
                "ZSXQ_GROUP_ID=123\nLLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-live\n",
                encoding="utf-8",
            )
            issues = validate_report_config("zsxq", path, {})
        self.assertTrue(any(issue.key == "ZSXQ_COOKIE_FILE" and issue.level == "error" for issue in issues))


if __name__ == "__main__":
    unittest.main()
