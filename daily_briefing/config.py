from dataclasses import dataclass
from pathlib import Path


SECRET_HINTS = ("API_KEY", "SECRET", "TOKEN", "COOKIE", "WEBHOOK", "PASSWORD")


@dataclass(frozen=True)
class ConfigIssue:
    level: str
    key: str
    message: str


REPORT_RULES = {
    "ai": {
        "required": ("REDFOX_API_KEY",),
        "cookie_files": (),
    },
    "cctv": {
        "required": (),
        "cookie_files": (),
    },
    "douyin": {
        "required": ("REDFOX_API_KEY",),
        "cookie_files": (),
    },
    "wechat": {
        "required": ("REDFOX_API_KEY",),
        "cookie_files": (),
    },
    "weibo": {
        "required": (),
        "cookie_files": ("WEIBO_COOKIE_FILE",),
    },
    "zsxq": {
        "required": ("ZSXQ_GROUP_ID",),
        "cookie_files": ("ZSXQ_COOKIE_FILE",),
    },
}


def parse_env_file(path):
    values = {}
    path = Path(path).expanduser()
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def merged_env(file_values, environ):
    values = dict(file_values)
    for key, value in environ.items():
        values.setdefault(key, value)
    return values


def mask_value(key, value):
    if value is None:
        return "<unset>"
    text = str(value)
    if not any(hint in key.upper() for hint in SECRET_HINTS):
        return text
    if not text:
        return "<empty>"
    return f"<set:{len(text)} chars>"


def is_placeholder(value):
    text = (value or "").strip().lower()
    return (
        not text
        or text.startswith(("your-", "sk-your-", "ak_your-"))
        or "your-webhook" in text
        or "your-key" in text
        or text in {"xxx", "changeme", "change-me"}
    )


def _has_any(values, keys):
    return any(not is_placeholder(values.get(key, "")) for key in keys)


def validate_report_config(report_name, env_path, environ=None):
    environ = {} if environ is None else environ
    env_path = Path(env_path).expanduser()
    file_values = parse_env_file(env_path)
    values = merged_env(file_values, environ)
    issues = []

    if not env_path.exists():
        issues.append(ConfigIssue("error", str(env_path), "env file does not exist"))
        return issues

    rules = REPORT_RULES.get(report_name, {})
    for key in rules.get("required", ()):
        if is_placeholder(values.get(key, "")):
            issues.append(ConfigIssue("error", key, "required value is missing or still a placeholder"))

    llm_provider = (values.get("LLM_PROVIDER") or "deepseek").strip().lower()
    if llm_provider == "deepseek":
        if not _has_any(values, ("DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS")):
            issues.append(ConfigIssue("error", "DEEPSEEK_API_KEY", "DeepSeek key is required for LLM summaries"))
    elif llm_provider == "openai":
        if not _has_any(values, ("OPENAI_API_KEY",)):
            issues.append(ConfigIssue("error", "OPENAI_API_KEY", "OpenAI key is required for LLM summaries"))
    else:
        issues.append(ConfigIssue("warn", "LLM_PROVIDER", f"unknown provider '{llm_provider}', report may fallback"))

    if not _has_any(values, ("FEISHU_WEBHOOK", "FEISHU_WEBHOOKS", "WECHAT_WORK_WEBHOOK", "WECHAT_WORK_WEBHOOKS")):
        issues.append(ConfigIssue("warn", "PUSH_TARGETS", "no push webhook configured; render-only runs are still possible"))

    if values.get("FEISHU_IMAGE_DAILY_ENABLED", "1").strip() not in {"0", "false", "False"}:
        if _has_any(values, ("FEISHU_WEBHOOK", "FEISHU_WEBHOOKS")) and not _has_any(values, ("FEISHU_APP_ID",)):
            issues.append(ConfigIssue("warn", "FEISHU_APP_ID", "Feishu image upload may fallback to text without app credentials"))
        if _has_any(values, ("FEISHU_WEBHOOK", "FEISHU_WEBHOOKS")) and not _has_any(values, ("FEISHU_APP_SECRET",)):
            issues.append(ConfigIssue("warn", "FEISHU_APP_SECRET", "Feishu image upload may fallback to text without app credentials"))

    for key in rules.get("cookie_files", ()):
        cookie_path = values.get(key, "")
        if not cookie_path:
            level = "error" if report_name == "zsxq" else "warn"
            issues.append(ConfigIssue(level, key, "cookie file path is not configured"))
            continue
        expanded = Path(cookie_path).expanduser()
        if not expanded.is_absolute():
            expanded = env_path.parent / expanded
        if not expanded.exists() or expanded.stat().st_size == 0:
            level = "error" if report_name == "zsxq" else "warn"
            issues.append(ConfigIssue(level, key, f"cookie file is missing or empty: {expanded}"))

    return issues


def has_errors(issues):
    return any(issue.level == "error" for issue in issues)
