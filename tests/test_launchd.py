import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from daily_briefing.launchd import install_launchd_report, render_plist, render_wrapper


class LaunchdTests(unittest.TestCase):
    def test_render_plist_daily_schedule(self):
        text = render_plist(label="com.example", app_dir="/tmp/app", hour=7, minute=50)
        self.assertIn("<string>com.example</string>", text)
        self.assertIn("<key>StartCalendarInterval</key>", text)
        self.assertIn("<integer>7</integer>", text)
        self.assertIn("<integer>50</integer>", text)

    def test_render_plist_interval_schedule(self):
        text = render_plist(label="com.example", app_dir="/tmp/app", interval_seconds=1800)
        self.assertIn("<key>StartInterval</key>", text)
        self.assertIn("<integer>1800</integer>", text)

    def test_render_wrapper_includes_alert_command(self):
        text = render_wrapper(
            app_dir="/tmp/app",
            project_dir="/tmp/project",
            report_name="wechat",
            env_file="/tmp/app/.env",
            python_bin="python3",
        )
        self.assertIn("daily_briefing.cli run", text)
        self.assertIn("daily_briefing.cli alert", text)

    def test_install_launchd_report_writes_files_without_loading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            app_dir = Path(tmpdir) / "app"
            project_dir = Path(__file__).resolve().parents[1]
            with patch("daily_briefing.launchd.Path.home", return_value=home):
                result = install_launchd_report(
                    report_name="cctv",
                    project_dir=project_dir,
                    app_dir=app_dir,
                    hour=8,
                    minute=0,
                    load=False,
                )
                self.assertTrue(result.wrapper_path.exists())
                self.assertTrue(result.plist_path.exists())
                self.assertIn("cctv", result.wrapper_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
