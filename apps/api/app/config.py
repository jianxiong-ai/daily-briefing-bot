from functools import lru_cache
import os
from pathlib import Path
from typing import List, Optional


class Settings:
    def __init__(self) -> None:
        self.database_path = os.environ.get("DATABASE_PATH", "data/subscriptions/subscriptions.sqlite3")
        self.subscription_env_dir = os.environ.get("SUBSCRIPTION_ENV_DIR", "data/subscriptions/env")
        self.subscription_output_dir = os.environ.get("SUBSCRIPTION_OUTPUT_DIR", "data/subscriptions/outputs")
        self.subscription_runtime_dir = os.environ.get("SUBSCRIPTION_RUNTIME_DIR", "data/subscriptions/runtime")
        self.secret_key = os.environ.get("DASHBOARD_SECRET_KEY", "").strip()
        self.api_cors_origins = os.environ.get(
            "API_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3010,http://127.0.0.1:3010,http://100.108.43.1:3010",
        )
        self.api_cors_origin_regex = os.environ.get(
            "API_CORS_ORIGIN_REGEX",
            r"^http://(localhost|127\.0\.0\.1|100\.\d+\.\d+\.\d+)(:3000|:3010)$",
        )
        self.scheduler_enabled = os.environ.get("SCHEDULER_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
        self.scheduler_timezone = os.environ.get("SCHEDULER_TIMEZONE", "Asia/Shanghai")
        self.run_retention_days = int(os.environ.get("DASHBOARD_RUN_RETENTION_DAYS", "3"))
        self.project_dir = os.environ.get("PROJECT_DIR", str(Path(__file__).resolve().parents[3]))

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def cors_origin_regex(self) -> Optional[str]:
        return self.api_cors_origin_regex or None

    @property
    def project_path(self) -> Path:
        return Path(self.project_dir).expanduser().resolve()

    @property
    def database_file(self) -> Path:
        path = Path(self.database_path).expanduser()
        if not path.is_absolute():
            path = self.project_path / path
        return path

    @property
    def env_dir(self) -> Path:
        path = Path(self.subscription_env_dir).expanduser()
        if not path.is_absolute():
            path = self.project_path / path
        return path

    @property
    def output_dir(self) -> Path:
        path = Path(self.subscription_output_dir).expanduser()
        if not path.is_absolute():
            path = self.project_path / path
        return path

    @property
    def runtime_dir(self) -> Path:
        path = Path(self.subscription_runtime_dir).expanduser()
        if not path.is_absolute():
            path = self.project_path / path
        return path

    @property
    def secret_key_file(self) -> Path:
        return self.env_dir.parent / "secret.key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
