import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ["PROJECT_DIR"] = str(Path(__file__).resolve().parents[3])
        os.environ["DATABASE_PATH"] = str(root / "subscriptions.sqlite3")
        os.environ["SUBSCRIPTION_ENV_DIR"] = str(root / "env")
        os.environ["SUBSCRIPTION_OUTPUT_DIR"] = str(root / "outputs")
        os.environ["SUBSCRIPTION_RUNTIME_DIR"] = str(root / "runtime")
        os.environ["DASHBOARD_RUN_RETENTION_DAYS"] = "3"

        from app.config import get_settings

        get_settings.cache_clear()
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def _set_started_at(self, run_id: int, value: str) -> None:
        conn = sqlite3.connect(os.environ["DATABASE_PATH"])
        try:
            conn.execute("UPDATE run_logs SET started_at = ? WHERE id = ?", (value, run_id))
            conn.commit()
        finally:
            conn.close()

    def test_cleanup_prunes_old_logs_and_rendered_images(self):
        from app.services.retention import cleanup_old_run_records
        from app.store import create_run_log, init_db, list_run_logs

        init_db()
        output_dir = self.root / "outputs"
        runtime_dir = self.root / "runtime" / "subscription_1_ai" / "images"
        output_dir.mkdir(parents=True)
        runtime_dir.mkdir(parents=True)
        old_image = output_dir / "old.png"
        recent_image = output_dir / "recent.png"
        orphan_image = runtime_dir / "orphan.png"
        old_image.write_bytes(b"old")
        recent_image.write_bytes(b"recent")
        orphan_image.write_bytes(b"orphan")

        old = datetime.now(timezone.utc) - timedelta(days=5)
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        old_ts = old.timestamp()
        os.utime(old_image, (old_ts, old_ts))
        os.utime(orphan_image, (old_ts, old_ts))
        recent_ts = recent.timestamp()
        os.utime(recent_image, (recent_ts, recent_ts))

        old_run = create_run_log(1, "ai", "success", output_path=str(old_image))
        recent_run = create_run_log(1, "wechat", "success", output_path=str(recent_image))
        self._set_started_at(old_run, old.isoformat())
        self._set_started_at(recent_run, recent.isoformat())

        result = cleanup_old_run_records(retention_days=3)

        self.assertEqual(result["pruned_run_logs"], 1)
        self.assertFalse(old_image.exists())
        self.assertFalse(orphan_image.exists())
        self.assertTrue(recent_image.exists())
        self.assertEqual([row["id"] for row in list_run_logs()], [recent_run])


if __name__ == "__main__":
    unittest.main()
