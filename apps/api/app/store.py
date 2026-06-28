import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from daily_briefing.reports import REPORTS

from .config import get_settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: Optional[str]):
    if not value:
        return None
    return datetime.fromisoformat(value)


def connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_file)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                push_time TEXT NOT NULL DEFAULT '08:00',
                push_targets TEXT NOT NULL DEFAULT 'primary',
                feishu_webhook TEXT NOT NULL DEFAULT '',
                wechat_work_webhook TEXT NOT NULL DEFAULT '',
                config_json TEXT NOT NULL DEFAULT '{}',
                last_run_at TEXT,
                last_status TEXT NOT NULL DEFAULT '',
                last_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                output_path TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT ''
            )
            """
        )


def _row_to_subscription(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "report_type": row["report_type"],
        "name": row["name"],
        "is_active": bool(row["is_active"]),
        "push_time": row["push_time"],
        "feishu_webhook": row["feishu_webhook"],
        "config": json.loads(row["config_json"] or "{}"),
        "last_run_at": parse_dt(row["last_run_at"]),
        "last_status": row["last_status"],
        "last_message": row["last_message"],
        "created_at": parse_dt(row["created_at"]),
        "updated_at": parse_dt(row["updated_at"]),
    }


def list_subscriptions() -> list[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM subscriptions ORDER BY report_type, push_time, id").fetchall()
    return [_row_to_subscription(row) for row in rows]


def get_subscription(subscription_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)).fetchone()
    return _row_to_subscription(row) if row else None


def create_subscription(data: Dict[str, Any]) -> Dict[str, Any]:
    report_type = data["report_type"]
    if report_type not in REPORTS:
        raise ValueError(f"unknown report type: {report_type}")
    now = utc_now()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO subscriptions (
                report_type, name, is_active, push_time, push_targets,
                feishu_webhook, wechat_work_webhook, config_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_type,
                data.get("name") or REPORTS[report_type].title,
                1 if data.get("is_active", True) else 0,
                data.get("push_time", "08:00"),
                "primary",
                data.get("feishu_webhook", ""),
                "",
                json.dumps(data.get("config", {}), ensure_ascii=False),
                now,
                now,
            ),
        )
        subscription_id = int(cur.lastrowid)
    return get_subscription(subscription_id)


def update_subscription(subscription_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = get_subscription(subscription_id)
    if not existing:
        raise KeyError(subscription_id)
    merged = dict(existing)
    for key, value in data.items():
        if value is not None:
            merged[key] = value
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            UPDATE subscriptions
            SET name = ?, is_active = ?, push_time = ?, push_targets = ?,
                feishu_webhook = ?, wechat_work_webhook = ?, config_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged["name"],
                1 if merged["is_active"] else 0,
                merged["push_time"],
                "primary",
                merged["feishu_webhook"],
                "",
                json.dumps(merged.get("config", {}), ensure_ascii=False),
                now,
                subscription_id,
            ),
        )
    return get_subscription(subscription_id)


def delete_subscription(subscription_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))


def create_run_log(subscription_id: int, report_type: str, status: str, output_path: str = "", message: str = "") -> int:
    now = utc_now()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO run_logs (subscription_id, report_type, status, started_at, output_path, message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (subscription_id, report_type, status, now, output_path, message),
        )
        return int(cur.lastrowid)


def finish_run_log(run_id: int, status: str, message: str = "", output_path: str = "") -> None:
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            UPDATE run_logs
            SET status = ?, finished_at = ?, message = ?, output_path = COALESCE(NULLIF(?, ''), output_path)
            WHERE id = ?
            """,
            (status, now, message, output_path, run_id),
        )
        row = conn.execute("SELECT subscription_id FROM run_logs WHERE id = ?", (run_id,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE subscriptions
                SET last_run_at = ?, last_status = ?, last_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, status, message[:1000], now, row["subscription_id"]),
            )


def list_run_logs(limit: int = 50) -> list[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM run_logs ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "subscription_id": row["subscription_id"],
            "report_type": row["report_type"],
            "status": row["status"],
            "started_at": parse_dt(row["started_at"]),
            "finished_at": parse_dt(row["finished_at"]),
            "output_path": row["output_path"],
            "message": row["message"],
        }
        for row in rows
    ]


def ensure_private_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.chmod(0o600)
