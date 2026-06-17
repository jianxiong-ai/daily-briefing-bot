import os
import re
import time


PRIMARY_TARGETS = {"primary", "main", "test"}


def load_env_file(path, override=False):
    if not path or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and (override or key not in os.environ):
                os.environ[key] = value


def parse_bool(value, default=False):
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def parse_webhook_robots(value, primary_url="", primary_name="主机器人"):
    robots = []
    if primary_url:
        robots.append({"name": primary_name, "url": primary_url.strip(), "primary": True})

    for index, raw_entry in enumerate((value or "").split(";"), start=1):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) >= 2:
            name, url = parts[0], parts[1]
            flags = {part.lower() for part in parts[2:]}
        else:
            name, url, flags = f"机器人{index}", parts[0], set()
        if not url:
            continue
        robots.append(
            {
                "name": name or f"机器人{index}",
                "url": url,
                "primary": "primary" in flags or "主" in flags,
            }
        )

    seen = set()
    result = []
    for robot in robots:
        if robot["url"] in seen:
            continue
        seen.add(robot["url"])
        result.append(robot)
    return result


def selected_robots(robots, push_targets=None):
    target_mode = (push_targets if push_targets is not None else os.environ.get("PUSH_TARGETS", "all")).strip().lower()
    if target_mode in PRIMARY_TARGETS:
        primary = [robot for robot in robots if robot.get("primary")]
        return primary or robots[:1]
    return robots


def wait_until_local_time(send_at_local, now_fn, sleep_fn=None, log_fn=None, strict=True):
    if not send_at_local:
        return 0
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", send_at_local)
    if not match:
        if strict:
            raise ValueError(f"Invalid SEND_AT_LOCAL: {send_at_local}")
        return 0

    now = now_fn()
    target = now.replace(
        hour=int(match.group(1)),
        minute=int(match.group(2)),
        second=0,
        microsecond=0,
    )
    if now >= target:
        return 0

    seconds = (target - now).total_seconds()
    if log_fn:
        log_fn(f"waiting until {send_at_local}, seconds={int(seconds)}")
    (sleep_fn or time.sleep)(seconds)
    return seconds
