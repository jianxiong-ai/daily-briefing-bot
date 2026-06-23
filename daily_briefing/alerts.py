from pathlib import Path

from .push import (
    PushResult,
    send_feishu_card,
    send_wechat_work_markdown,
)
from .runtime import load_env_file, parse_webhook_robots, selected_robots


def read_log_tail(path, max_chars=1600):
    if not path:
        return ""
    path = Path(path).expanduser()
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:].strip()


def build_failure_sections(report, message, exit_code=None, log_tail=""):
    lines = [
        f"**日报任务失败：{report}**",
        f"原因：{message or '未提供'}",
    ]
    if exit_code is not None:
        lines.append(f"退出码：{exit_code}")
    if log_tail:
        cleaned = log_tail.replace("```", "'''")
        lines.extend(["", "**最近日志**", f"```text\n{cleaned}\n```"])
    return [lines]


def send_failure_alert(
    *,
    report,
    message,
    env_path=None,
    exit_code=None,
    log_path=None,
    push_targets="primary",
):
    if env_path:
        load_env_file(str(Path(env_path).expanduser()), override=False)

    import os

    log_tail = read_log_tail(log_path)
    title = f"日报任务失败：{report}"
    sections = build_failure_sections(report, message, exit_code=exit_code, log_tail=log_tail)
    result = PushResult()

    feishu_robots = parse_webhook_robots(
        os.environ.get("FEISHU_WEBHOOKS", ""),
        primary_url=os.environ.get("FEISHU_WEBHOOK", ""),
    )
    for robot in selected_robots(feishu_robots, push_targets):
        try:
            send_feishu_card(robot["url"], title, sections, template="red")
            result.add_success()
        except Exception as exc:
            result.add_error("feishu", robot["name"], exc)

    wechat_robots = parse_webhook_robots(
        os.environ.get("WECHAT_WORK_WEBHOOKS", ""),
        primary_url=os.environ.get("WECHAT_WORK_WEBHOOK", ""),
    )
    for robot in selected_robots(wechat_robots, push_targets):
        try:
            send_wechat_work_markdown(robot["url"], title, sections, max_bytes=3800)
            result.add_success()
        except Exception as exc:
            result.add_error("wechat", robot["name"], exc)

    return result
