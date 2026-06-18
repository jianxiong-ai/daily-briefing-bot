import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field


def post_json(url, payload, timeout=20):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    if body:
        sys.stdout.write(body)
    return body


def build_feishu_card_payload(title, sections, template="blue"):
    elements = []
    for index, section in enumerate(sections):
        if index:
            elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": "\n".join(section)})
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }


def send_feishu_card(webhook, title, sections, template="blue"):
    return post_json(webhook, build_feishu_card_payload(title, sections, template=template))


def send_feishu_image(webhook, image_key):
    return post_json(webhook, {"msg_type": "image", "content": {"image_key": image_key}})


def wechat_work_markdown(value):
    value = re.sub(r"</?font\b[^>]*>", "", value or "")
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return value


def truncate_utf8_plain(value, max_bytes):
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    if max_bytes <= 3:
        return "." * max(0, max_bytes)
    return data[: max_bytes - 3].decode("utf-8", errors="ignore").rstrip() + "..."


def wechat_line(value, max_bytes=700, skip_prefixes=()):
    value = wechat_work_markdown(value).strip()
    if not value:
        return ""
    if skip_prefixes and value.startswith(tuple(skip_prefixes)):
        return ""
    value = value.replace("**", "")
    value = re.sub(r"\s+", " ", value)
    return truncate_utf8_plain(value, max_bytes)


def build_wechat_content(title, sections, max_bytes=3900, skip_prefixes=()):
    suffix = "\n\n其余内容见飞书完整版。"
    budget = max_bytes - len(suffix.encode("utf-8"))
    lines = [f"**{title}**"]
    omitted = False
    for section_index, section in enumerate(sections):
        if section_index:
            candidate = lines + [""]
            if len("\n".join(candidate).encode("utf-8")) <= budget:
                lines = candidate
        for raw_line in section:
            line = wechat_line(raw_line, skip_prefixes=skip_prefixes)
            if not line:
                continue
            candidate = lines + [line]
            if len("\n".join(candidate).encode("utf-8")) > budget:
                remaining = budget - len("\n".join(lines + [""]).encode("utf-8"))
                if remaining > 16:
                    truncated = truncate_utf8_plain(line, remaining)
                    candidate = lines + [truncated]
                    if len("\n".join(candidate).encode("utf-8")) <= budget:
                        lines = candidate
                omitted = True
                break
            lines = candidate
        if omitted:
            break
    content = "\n".join(lines)
    if omitted:
        content += suffix
    return content


def send_wechat_work_markdown(webhook, title, sections, max_bytes=3900, skip_prefixes=()):
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": build_wechat_content(title, sections, max_bytes=max_bytes, skip_prefixes=skip_prefixes)},
    }
    return post_json(webhook, payload)


@dataclass
class PushResult:
    sent: int = 0
    errors: list = field(default_factory=list)

    def add_success(self):
        self.sent += 1

    def add_error(self, channel, robot_name, error):
        self.errors.append(f"{channel}/{robot_name}: {error}")

    def raise_if_empty(self, extra_errors=None):
        if self.sent:
            return
        errors = list(self.errors)
        if extra_errors:
            errors.extend(extra_errors)
        if errors:
            raise RuntimeError("; ".join(errors))
        raise RuntimeError("no push target configured")
