import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daily_briefing.runtime import (
    load_env_file,
    parse_bool,
    parse_webhook_robots,
    selected_robots,
    wait_until_local_time,
)


class RuntimeTests(unittest.TestCase):
    def test_load_env_file_keeps_existing_values_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("A=from_file\nB='quoted value'\n", encoding="utf-8")

            old_a = os.environ.get("A")
            old_b = os.environ.get("B")
            try:
                os.environ["A"] = "existing"
                os.environ.pop("B", None)
                load_env_file(str(env_path))
                self.assertEqual(os.environ["A"], "existing")
                self.assertEqual(os.environ["B"], "quoted value")

                load_env_file(str(env_path), override=True)
                self.assertEqual(os.environ["A"], "from_file")
            finally:
                if old_a is None:
                    os.environ.pop("A", None)
                else:
                    os.environ["A"] = old_a
                if old_b is None:
                    os.environ.pop("B", None)
                else:
                    os.environ["B"] = old_b

    def test_parse_bool(self):
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("yes"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("", default=False))
        self.assertTrue(parse_bool("", default=True))

    def test_parse_webhook_robots_deduplicates_and_marks_primary(self):
        robots = parse_webhook_robots(
            "大老师|https://example.com/1|primary;重复|https://example.com/1;普通|https://example.com/2",
            primary_url="https://example.com/main",
        )
        self.assertEqual([robot["url"] for robot in robots], [
            "https://example.com/main",
            "https://example.com/1",
            "https://example.com/2",
        ])
        self.assertTrue(robots[0]["primary"])
        self.assertTrue(robots[1]["primary"])
        self.assertFalse(robots[2]["primary"])

    def test_selected_robots_prefers_primary(self):
        robots = [
            {"name": "a", "url": "a", "primary": False},
            {"name": "b", "url": "b", "primary": True},
        ]
        self.assertEqual(selected_robots(robots, "primary"), [robots[1]])
        self.assertEqual(selected_robots(robots, "all"), robots)

    def test_wait_until_local_time(self):
        now = datetime(2026, 6, 17, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        sleeps = []
        seconds = wait_until_local_time(
            "08:05",
            now_fn=lambda: now,
            sleep_fn=sleeps.append,
            log_fn=lambda _message: None,
        )
        self.assertEqual(seconds, 300)
        self.assertEqual(sleeps, [300])
        self.assertEqual(wait_until_local_time("07:59", now_fn=lambda: now), 0)

        with self.assertRaises(ValueError):
            wait_until_local_time("bad", now_fn=lambda: now)
        self.assertEqual(wait_until_local_time("bad", now_fn=lambda: now, strict=False), 0)


if __name__ == "__main__":
    unittest.main()
