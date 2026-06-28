#!/usr/bin/env python3
"""Migrate existing launchd reports into dashboard subscriptions.

Runs on the host (where the real env files and cookies live) and creates one
subscription per report through the running dashboard API, so the API encrypts
secrets at rest and validates the config. Secrets are never printed in full.

Usage:
    python3 scripts/migrate_launchd_to_dashboard.py            # dry run
    python3 scripts/migrate_launchd_to_dashboard.py --apply    # actually create
    python3 scripts/migrate_launchd_to_dashboard.py --apply --reports ai weibo
"""

import argparse
import json
import plistlib
import sys
import urllib.error
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "apps/api"))

from daily_briefing.config import SECRET_HINTS, is_placeholder, parse_env_file  # noqa: E402
from app.report_metadata import REPORT_FIELDS  # noqa: E402


DEFAULT_REPORTS = ["ai", "astock", "cctv", "wechat", "weibo", "zsxq"]

# Fallback schedule if the launchd plist cannot be read.
FALLBACK_TIMES = {
    "ai": "07:50",
    "wechat": "07:55",
    "cctv": "08:00",
    "astock": "08:15",
    "douyin": "08:15",
    "zsxq": "22:05",
    "weibo": "22:30",
}

COOKIE_FILE_KEY = {"weibo": "WEIBO_COOKIE_FILE", "zsxq": "ZSXQ_COOKIE_FILE"}
COOKIE_FIELD = {"weibo": "WEIBO_COOKIE", "zsxq": "ZSXQ_COOKIE"}
COOKIE_FALLBACKS = {
    "weibo": [
        Path.home() / "Library/Application Support/CodexWeiboDaily/weibo.cookie",
        REPO / "work/weibo_daily/weibo.cookie",
    ],
    "zsxq": [
        Path.home() / "Library/Application Support/CodexZsxqDaily/zsxq.cookie",
        REPO / "work/zsxq_daily/zsxq.cookie",
    ],
}


def env_file_for(report: str) -> Path:
    return REPO / f"work/{report}_daily/.env"


def read_schedule(report: str) -> str:
    plist = Path.home() / f"Library/LaunchAgents/com.jason.{report}-daily.plist"
    try:
        data = plistlib.loads(plist.read_bytes())
        sci = data.get("StartCalendarInterval")
        if isinstance(sci, dict):
            return f"{int(sci.get('Hour', 8)):02d}:{int(sci.get('Minute', 0)):02d}"
    except Exception:
        pass
    return FALLBACK_TIMES.get(report, "08:00")


def resolve_cookie(report: str, env_values: dict, env_file: Path) -> str:
    candidates = []
    raw = env_values.get(COOKIE_FILE_KEY.get(report, ""), "")
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = env_file.parent / path
        candidates.append(path)
    candidates.extend(COOKIE_FALLBACKS.get(report, []))
    for path in candidates:
        try:
            if path.exists() and path.stat().st_size > 0:
                return path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
    return ""


def build_config(report: str, env_values: dict, env_file: Path) -> dict:
    config = {}
    for field in REPORT_FIELDS.get(report, []):
        key = field["key"]
        if key in COOKIE_FIELD.values():
            value = resolve_cookie(report, env_values, env_file)
        elif key == "DEEPSEEK_API_KEYS":
            value = env_values.get("DEEPSEEK_API_KEYS") or env_values.get("DEEPSEEK_API_KEY") or ""
        else:
            value = env_values.get(key, "")
        value = (value or "").strip()
        if value and not is_placeholder(value):
            config[key] = value
    return config


def mask(key: str, value: str) -> str:
    if not value:
        return "<empty>"
    if any(hint in key.upper() for hint in SECRET_HINTS):
        return f"<set:{len(value)} chars>"
    return value if len(value) <= 60 else value[:57] + "..."


def api_get(base: str, path: str):
    with urllib.request.urlopen(f"{base}{path}", timeout=15) as resp:
        return json.load(resp)


def api_post(base: str, path: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Migrate launchd reports into dashboard subscriptions")
    parser.add_argument("--api-base", default="http://localhost:8010", help="Dashboard API base URL")
    parser.add_argument("--reports", nargs="*", default=DEFAULT_REPORTS, help="Reports to migrate")
    parser.add_argument("--apply", action="store_true", help="Actually create subscriptions (default: dry run)")
    parser.add_argument("--active", action="store_true", help="Create subscriptions enabled (default: paused)")
    args = parser.parse_args(argv)

    try:
        existing = api_get(args.api_base, "/api/subscriptions")
    except urllib.error.URLError as exc:
        print(f"error: cannot reach dashboard API at {args.api_base}: {exc}")
        print("Make sure the docker stack is running (docker compose -f docker-compose.private.yml up -d).")
        return 1
    existing_types = {item["report_type"] for item in existing}

    print(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}   api: {args.api_base}")
    print(f"existing subscriptions: {sorted(existing_types) or 'none'}\n")

    created, skipped = 0, 0
    for report in args.reports:
        env_file = env_file_for(report)
        if not env_file.exists():
            print(f"[{report}] skip: env file not found at {env_file}")
            skipped += 1
            continue
        if report in existing_types:
            print(f"[{report}] skip: a subscription of this type already exists")
            skipped += 1
            continue

        env_values = parse_env_file(env_file)
        config = build_config(report, env_values, env_file)
        payload = {
            "report_type": report,
            "name": "",
            "is_active": bool(args.active),
            "push_time": read_schedule(report),
            "feishu_webhook": (env_values.get("FEISHU_WEBHOOK") or "").strip(),
            "config": config,
        }

        print(f"[{report}] push_time={payload['push_time']} active={payload['is_active']}")
        print(f"         feishu_webhook={mask('FEISHU_WEBHOOK', payload['feishu_webhook'])}")
        for key in sorted(config):
            print(f"         {key}={mask(key, config[key])}")

        if not args.apply:
            skipped += 1
            continue

        try:
            result = api_post(args.api_base, "/api/subscriptions", payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            print(f"         -> FAILED ({exc.code}): {detail}")
            skipped += 1
            continue
        warnings = result.get("warnings") or []
        print(f"         -> created id={result['id']}")
        for warning in warnings:
            print(f"            warn: {warning}")
        created += 1

    print(f"\nsummary: created={created} skipped={skipped}")
    if not args.apply:
        print("This was a dry run. Re-run with --apply to create the subscriptions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
