import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from daily_briefing.doctor import launchd_status, tail_log_findings


class DoctorTests(unittest.TestCase):
    def test_launchd_status_parses_print_output(self):
        output = """
state = not running
runs = 8
last exit code = 2
"""

        class Result:
            returncode = 0
            stdout = output
            stderr = ""

        with patch("daily_briefing.doctor._run", return_value=Result()):
            status = launchd_status("com.example")
        self.assertTrue(status["loaded"])
        self.assertEqual(status["state"], "not running")
        self.assertEqual(status["runs"], "8")
        self.assertEqual(status["last_exit"], "2")

    def test_tail_log_findings_reports_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.log"
            path.write_text("ok\nHTTP Error 401: Unauthorized\n", encoding="utf-8")
            findings = tail_log_findings(path)
        self.assertEqual(findings[0].level, "warn")
        self.assertIn("HTTP Error 401", findings[0].message)

    def test_tail_log_findings_handles_missing_log(self):
        findings = tail_log_findings("/tmp/not-a-real-daily-briefing-log")
        self.assertEqual(findings[0].level, "warn")
        self.assertIn("log missing", findings[0].message)


if __name__ == "__main__":
    unittest.main()
