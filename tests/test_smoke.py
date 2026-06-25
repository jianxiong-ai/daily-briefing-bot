import importlib.util
import os
import pathlib
import unittest
from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmokeTests(unittest.TestCase):
    def test_daily_image_renderer_exports_expected_helpers(self):
        daily_image = load_module("daily_image", "work/daily_image.py")
        self.assertTrue(callable(daily_image.render_daily_image))
        self.assertTrue(callable(daily_image.upload_feishu_image))

    def test_daily_image_splits_long_text_at_sentence_boundaries(self):
        daily_image = load_module("daily_image_paragraphs", "work/daily_image.py")
        text = (
            "第一句介绍事件背景和主要参与者，并补充必要信息。"
            "第二句说明事件进展、影响范围和关键数据，帮助读者理解上下文。"
            "第三句继续解释各方反应以及后续值得关注的变化。"
            "第四句给出更多事实细节，使整段文字达到自动分段阈值。"
        )
        paragraphs = daily_image.split_spans_into_paragraphs(
            [(text, daily_image.BODY_FONT, daily_image.TEXT)]
        )
        self.assertGreaterEqual(len(paragraphs), 2)
        self.assertTrue(paragraphs[0][-1][0].endswith("。"))

    def test_daily_image_normalizes_latin_diacritics(self):
        daily_image = load_module("daily_image_latin", "work/daily_image.py")
        self.assertEqual(daily_image.sanitize_display_text("Jalapeño café"), "Jalapeno cafe")

    def test_report_modules_import_without_credentials(self):
        modules = {
            "ai_daily": "work/ai_daily/ai_daily.py",
            "cctv_daily": "work/cctv_daily/cctv_daily.py",
            "douyin_daily": "work/douyin_daily/douyin_daily.py",
            "wechat_daily": "work/wechat_daily/wechat_daily.py",
            "weibo_daily": "work/weibo_daily/weibo_daily.py",
            "zsxq_daily": "work/zsxq_daily/zsxq_daily.py",
        }
        for name, path in modules.items():
            with self.subTest(name=name):
                module = load_module(name, path)
                self.assertTrue(hasattr(module, "main"))

    def test_launchd_templates_use_placeholders(self):
        for name in ("daily-report.plist.example", "interval-report.plist.example"):
            text = (ROOT / "deploy/launchd" / name).read_text(encoding="utf-8")
            self.assertIn("__LABEL__", text)
            self.assertIn("__APP_DIR__", text)

    def test_report_registry_points_to_existing_scripts_and_examples(self):
        from daily_briefing.reports import REPORTS

        self.assertIn("wechat", REPORTS)
        for report in REPORTS.values():
            with self.subTest(report=report.name):
                self.assertTrue(report.script.exists(), report.script)
                self.assertTrue(report.example_env.exists(), report.example_env)
                self.assertTrue(report.env_var.endswith("_DAILY_ENV"))

    def test_cli_lists_reports(self):
        from daily_briefing.cli import main

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["list"]), 0)
        self.assertIn("wechat", output.getvalue())

    def test_cli_require_env_fails_before_running_report(self):
        from daily_briefing.cli import main

        missing_env = ROOT / "work/wechat_daily/__missing__.env"
        with self.assertRaises(SystemExit) as raised:
            main(["run", "wechat", "--env", str(missing_env), "--require-env"])
        self.assertIn("Env file not found", str(raised.exception))

    def test_cli_run_sets_common_environment_flags(self):
        from daily_briefing.cli import main

        env_path = ROOT / "examples/env/wechat_daily.env.example"
        keys = [
            "WECHAT_DAILY_ENV",
            "RENDER_ONLY",
            "RENDER_OUTPUT",
            "DIGEST_DATE",
            "PUSH_TARGETS",
            "SEND_AT_LOCAL",
        ]
        old_values = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            with patch("daily_briefing.cli.runpy.run_path") as run_path:
                self.assertEqual(
                    main(
                        [
                            "run",
                            "wechat",
                            "--env",
                            str(env_path),
                            "--render-only",
                            "--output",
                            "/tmp/wechat.png",
                            "--date",
                            "2026-06-13",
                            "--push-targets",
                            "primary",
                            "--send-at",
                            "",
                        ]
                    ),
                    0,
                )
            run_path.assert_called_once()
            self.assertEqual(os.environ["WECHAT_DAILY_ENV"], str(env_path))
            self.assertEqual(os.environ["RENDER_ONLY"], "1")
            self.assertEqual(os.environ["RENDER_OUTPUT"], "/tmp/wechat.png")
            self.assertEqual(os.environ["DIGEST_DATE"], "2026-06-13")
            self.assertEqual(os.environ["PUSH_TARGETS"], "primary")
            self.assertEqual(os.environ["SEND_AT_LOCAL"], "")
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
