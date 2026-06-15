import importlib.util
import pathlib
import unittest


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


if __name__ == "__main__":
    unittest.main()
