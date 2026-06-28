import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class CryptoStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ["PROJECT_DIR"] = str(Path(__file__).resolve().parents[3])
        os.environ["DATABASE_PATH"] = str(root / "subscriptions.sqlite3")
        os.environ["SUBSCRIPTION_ENV_DIR"] = str(root / "env")
        os.environ["SUBSCRIPTION_OUTPUT_DIR"] = str(root / "outputs")
        os.environ["DASHBOARD_SECRET_KEY"] = "unit-test-secret-passphrase"

        from app.config import get_settings

        get_settings.cache_clear()
        from app import crypto

        crypto._fernet.cache_clear()

    def tearDown(self):
        os.environ.pop("DASHBOARD_SECRET_KEY", None)
        self.tmp.cleanup()

    @unittest.skipUnless(__import__("importlib").util.find_spec("cryptography"), "cryptography not installed")
    def test_secret_values_are_encrypted_at_rest_but_readable_via_api(self):
        from app.config import get_settings
        from app.store import create_subscription, get_subscription, init_db

        init_db()
        created = create_subscription(
            {
                "report_type": "weibo",
                "name": "微博日报",
                "push_time": "22:30",
                "feishu_webhook": "https://open.feishu.cn/hook",
                "config": {
                    "DEEPSEEK_API_KEYS": "sk-super-secret",
                    "WEIBO_COOKIE": "SUB=secret-cookie",
                    "WEIBO_BLOGGER_IDS": "1763864272",
                },
            }
        )

        # Reading back through the store transparently decrypts.
        fetched = get_subscription(created["id"])
        self.assertEqual(fetched["config"]["DEEPSEEK_API_KEYS"], "sk-super-secret")
        self.assertEqual(fetched["config"]["WEIBO_COOKIE"], "SUB=secret-cookie")
        # Non-secret keys stay plaintext.
        self.assertEqual(fetched["config"]["WEIBO_BLOGGER_IDS"], "1763864272")

        # The raw row must not contain the plaintext secret.
        db_path = get_settings().database_file
        conn = sqlite3.connect(db_path)
        raw = conn.execute("SELECT config_json FROM subscriptions WHERE id = ?", (created["id"],)).fetchone()[0]
        conn.close()
        self.assertNotIn("sk-super-secret", raw)
        self.assertNotIn("secret-cookie", raw)
        stored = json.loads(raw)
        self.assertTrue(stored["DEEPSEEK_API_KEYS"].startswith("enc:v1:"))
        self.assertTrue(stored["WEIBO_COOKIE"].startswith("enc:v1:"))
        self.assertEqual(stored["WEIBO_BLOGGER_IDS"], "1763864272")


if __name__ == "__main__":
    unittest.main()
