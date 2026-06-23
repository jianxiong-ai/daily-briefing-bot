import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from daily_briefing.alerts import build_failure_sections, read_log_tail, send_failure_alert


class AlertTests(unittest.TestCase):
    def test_build_failure_sections_includes_log_tail(self):
        sections = build_failure_sections("wechat", "failed", exit_code=2, log_tail="Traceback")
        text = "\n".join(sections[0])
        self.assertIn("wechat", text)
        self.assertIn("退出码：2", text)
        self.assertIn("Traceback", text)

    def test_read_log_tail_limits_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.log"
            path.write_text("a" * 100, encoding="utf-8")
            self.assertEqual(read_log_tail(path, max_chars=10), "aaaaaaaaaa")

    def test_send_failure_alert_uses_primary_feishu(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "FEISHU_WEBHOOK=https://example.com/main\n"
                "FEISHU_WEBHOOKS='Other|https://example.com/other'\n",
                encoding="utf-8",
            )
            old = {key: os.environ.get(key) for key in ("FEISHU_WEBHOOK", "FEISHU_WEBHOOKS", "WECHAT_WORK_WEBHOOK")}
            try:
                for key in old:
                    os.environ.pop(key, None)
                with patch("daily_briefing.alerts.send_feishu_card") as send_card:
                    result = send_failure_alert(report="ai", message="bad", env_path=env_path)
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        self.assertEqual(result.sent, 1)
        send_card.assert_called_once()
        self.assertEqual(send_card.call_args.args[0], "https://example.com/main")


if __name__ == "__main__":
    unittest.main()
