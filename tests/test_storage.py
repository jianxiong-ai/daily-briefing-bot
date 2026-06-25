import json
import os
import tempfile
import unittest
from pathlib import Path

from daily_briefing.storage import cleanup_runtime, compact_jsonl_cache, runtime_storage


class StorageTests(unittest.TestCase):
    def test_runtime_storage_uses_normalized_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = runtime_storage(
                "wechat",
                {
                    "DAILY_BRIEFING_DATA_ROOT": str(Path(tmpdir) / "data"),
                    "DAILY_BRIEFING_LOG_ROOT": str(Path(tmpdir) / "logs"),
                },
            )
            self.assertEqual(storage.cache, Path(tmpdir) / "data/wechat/cache")
            self.assertEqual(storage.images, Path(tmpdir) / "data/wechat/images")
            self.assertEqual(storage.state, Path(tmpdir) / "data/wechat/state")
            self.assertEqual(storage.logs, Path(tmpdir) / "logs/wechat")
            self.assertTrue(storage.cache.is_dir())

    def test_cleanup_removes_old_images_but_preserves_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = runtime_storage(
                "ai",
                {
                    "DAILY_RUNTIME_DIR": tmpdir,
                    "DAILY_BRIEFING_LOG_ROOT": str(Path(tmpdir) / "logs"),
                },
            )
            old_image = storage.images / "old.png"
            state_file = storage.state / "history.json"
            state_backup = storage.state / "history.json.bak"
            old_image.write_bytes(b"x")
            os.utime(old_image, (1, 1))
            state_file.write_text("keep", encoding="utf-8")
            state_backup.write_text("keep backup", encoding="utf-8")
            os.utime(state_backup, (1, 1))
            cleanup_runtime(storage, image_days=1, now=2 * 86400)
            self.assertFalse(old_image.exists())
            self.assertTrue(state_file.exists())
            self.assertTrue(state_backup.exists())

    def test_compact_jsonl_cache_drops_expired_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.jsonl"
            path.write_text(
                json.dumps({"key": "old", "created_at": 1}) + "\n"
                + json.dumps({"key": "new", "created_at": 100}) + "\n",
                encoding="utf-8",
            )
            retained = compact_jsonl_cache(path, ttl_seconds=50, now=120)
            self.assertEqual(retained, 1)
            self.assertIn('"new"', path.read_text(encoding="utf-8"))
            self.assertNotIn('"old"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
