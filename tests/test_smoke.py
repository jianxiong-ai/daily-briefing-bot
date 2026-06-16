import importlib.util
import pathlib
import unittest
from io import StringIO
from contextlib import redirect_stdout


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


if __name__ == "__main__":
    unittest.main()
