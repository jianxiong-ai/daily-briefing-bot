from typing import Any, Dict, List

from daily_briefing.config import is_placeholder

from app.report_metadata import REPORT_FIELDS, REPORT_WINDOWS


def _blank(value: Any) -> bool:
    return is_placeholder(str(value or ""))


def _to_minutes(hhmm: str) -> int:
    hour, minute = [int(part) for part in hhmm.split(":")]
    return hour * 60 + minute


def validate_subscription(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return config issues for a subscription payload.

    Each issue is {"level": "error"|"warning", "key": str, "message": str}.
    Errors should block create/update; warnings are advisory.
    """
    issues: List[Dict[str, str]] = []
    report_type = payload.get("report_type", "")
    config = payload.get("config") or {}

    for field in REPORT_FIELDS.get(report_type, []):
        value = config.get(field["key"], "")
        if field.get("required") and _blank(value):
            issues.append({"level": "error", "key": field["key"], "message": f"{field['label']} 为必填项"})
        elif field.get("recommended") and _blank(value):
            issues.append(
                {
                    "level": "warning",
                    "key": field["key"],
                    "message": f"未配置「{field['label']}」，相关模块将不会展示",
                }
            )

    if payload.get("is_active", True) and _blank(payload.get("feishu_webhook")):
        issues.append(
            {
                "level": "warning",
                "key": "feishu_webhook",
                "message": "订阅已启用但未配置飞书 Webhook，到点只会渲染、不会实际推送",
            }
        )

    window = REPORT_WINDOWS.get(report_type)
    push_time = payload.get("push_time")
    if window and push_time:
        start = window.get("recommended_start")
        end = window.get("recommended_end")
        if start and end and not (_to_minutes(start) <= _to_minutes(push_time) <= _to_minutes(end)):
            issues.append(
                {
                    "level": "warning",
                    "key": "push_time",
                    "message": (
                        f"{window.get('summary', '')}建议推送时间在 {start}–{end} 之间，"
                        f"当前为 {push_time}，可能导致数据为空或过时。"
                    ),
                }
            )

    return issues


def errors_only(issues: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [issue for issue in issues if issue["level"] == "error"]


def format_errors(issues: List[Dict[str, str]]) -> str:
    return "配置校验未通过：" + "；".join(issue["message"] for issue in errors_only(issues))
