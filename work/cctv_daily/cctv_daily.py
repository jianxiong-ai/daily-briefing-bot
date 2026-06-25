#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from multiprocessing import Process, Queue
from threading import BoundedSemaphore, Lock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from daily_briefing.runtime import (
    load_env_file as runtime_load_env_file,
    parse_webhook_robots as runtime_parse_webhook_robots,
    selected_robots as runtime_selected_robots,
    wait_until_local_time,
)
from daily_briefing.push import (
    build_wechat_content as push_build_wechat_content,
    send_feishu_card as push_send_feishu_card,
    send_wechat_work_markdown as push_send_wechat_work_markdown,
    truncate_utf8_plain as push_truncate_utf8_plain,
    wechat_work_markdown as push_wechat_work_markdown,
)
from daily_briefing.storage import runtime_storage
try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ENV_PATH = os.environ.get(
    "CCTV_DAILY_ENV",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
)


def load_env_file(path):
    return runtime_load_env_file(path, override=False)


def parse_webhook_robots(value, primary_url="", primary_name="主机器人"):
    return runtime_parse_webhook_robots(value, primary_url, primary_name)


def selected_robots(robots):
    return runtime_selected_robots(robots, PUSH_TARGETS)


load_env_file(ENV_PATH)
STORAGE = runtime_storage("cctv")

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "").strip()
WECHAT_WORK_WEBHOOK = os.environ.get("WECHAT_WORK_WEBHOOK", "").strip()
PUSH_TARGETS = os.environ.get("PUSH_TARGETS", "all").strip().lower()
FEISHU_ROBOTS = parse_webhook_robots(os.environ.get("FEISHU_WEBHOOKS", ""), FEISHU_WEBHOOK, "主机器人")
WECHAT_WORK_ROBOTS = parse_webhook_robots(os.environ.get("WECHAT_WORK_WEBHOOKS", ""), WECHAT_WORK_WEBHOOK, "主机器人")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "").strip()
FEISHU_IMAGE_DAILY_ENABLED = os.environ.get("FEISHU_IMAGE_DAILY_ENABLED", "1").strip() != "0"

DIGEST_DATE = os.environ.get("DIGEST_DATE", "").strip()
SEND_AT_LOCAL = os.environ.get("SEND_AT_LOCAL", "").strip()
RENDER_ONLY = os.environ.get("RENDER_ONLY", "").strip() == "1"
RENDER_OUTPUT = os.environ.get("RENDER_OUTPUT", "").strip()
LOG_PROGRESS = os.environ.get("LOG_PROGRESS", "1").strip() != "0"

CCTV_COLUMN_ID = os.environ.get("CCTV_COLUMN_ID", "TOPC1451558496100826").strip()
CCTV_API_BASE = os.environ.get("CCTV_API_BASE", "https://api.cntv.cn/NewVideo/getVideoListByColumn").strip()
CCTV_REFERER = os.environ.get("CCTV_REFERER", "https://tv.cctv.com/lm/zwtx/index.shtml").strip()
CCTV_PAGE_SIZE = int(os.environ.get("CCTV_PAGE_SIZE", "100"))
CCTV_FETCH_PAGES = int(os.environ.get("CCTV_FETCH_PAGES", "3"))
CCTV_ITEM_LIMIT = int(os.environ.get("CCTV_ITEM_LIMIT", "120"))

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_API_KEYS = [
    value.strip()
    for value in os.environ.get("DEEPSEEK_API_KEYS", "").replace("\n", ",").split(",")
    if value.strip()
]
if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY not in DEEPSEEK_API_KEYS:
    DEEPSEEK_API_KEYS.insert(0, DEEPSEEK_API_KEY)
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2").strip()
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "270"))
LLM_RETRY_ATTEMPTS = int(os.environ.get("LLM_RETRY_ATTEMPTS", "2"))
LLM_RETRY_BACKOFF_SECONDS = float(os.environ.get("LLM_RETRY_BACKOFF_SECONDS", "2"))
LLM_MAX_CONCURRENT_REQUESTS = int(os.environ.get("LLM_MAX_CONCURRENT_REQUESTS", "2"))
LLM_SEMAPHORE = BoundedSemaphore(max(1, LLM_MAX_CONCURRENT_REQUESTS))
DEEPSEEK_KEY_LOCK = Lock()
DEEPSEEK_KEY_INDEX = 0

APP_DATA_DIR = str(STORAGE.images)
LLM_CACHE_FILE = os.environ.get("LLM_CACHE_FILE", str(STORAGE.cache / "llm_summary_cache.jsonl"))
LLM_CACHE_TTL_SECONDS = int(os.environ.get("LLM_CACHE_TTL_SECONDS", "43200"))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "1").strip() != "0"
LLM_PROMPT_VERSION = os.environ.get("LLM_PROMPT_VERSION", "cctv-v1").strip()
LLM_CACHE = {}


def shanghai_now():
    return datetime.now(timezone(timedelta(hours=8)))


def log_progress(message):
    if LOG_PROGRESS:
        print(f"[{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def digest_day():
    if DIGEST_DATE:
        return datetime.strptime(DIGEST_DATE, "%Y-%m-%d").date()
    return shanghai_now().date()


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def current_model_name():
    return DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else OPENAI_MODEL


def load_llm_cache():
    if not LLM_CACHE_ENABLED or not os.path.exists(LLM_CACHE_FILE):
        return
    cutoff = time.time() - LLM_CACHE_TTL_SECONDS
    with open(LLM_CACHE_FILE, "r", encoding="utf-8") as cache_file:
        for line in cache_file:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if float(record.get("created_at", 0)) < cutoff:
                continue
            key = record.get("key")
            if key and record.get("value"):
                LLM_CACHE[key] = record


def cache_key(kind, payload):
    identity = {
        "kind": kind,
        "provider": LLM_PROVIDER,
        "model": current_model_name(),
        "prompt_version": LLM_PROMPT_VERSION,
        "payload_hash": sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    }
    return sha256_text(json.dumps(identity, ensure_ascii=False, sort_keys=True))


def get_cached_summary(kind, payload):
    if not LLM_CACHE_ENABLED:
        return None
    key = cache_key(kind, payload)
    record = LLM_CACHE.get(key)
    if not record:
        return None
    if float(record.get("created_at", 0)) < time.time() - LLM_CACHE_TTL_SECONDS:
        return None
    log_progress(f"llm cache hit kind={kind}")
    return record.get("value")


def set_cached_summary(kind, payload, value):
    if not LLM_CACHE_ENABLED or not value:
        return
    key = cache_key(kind, payload)
    record = {
        "key": key,
        "kind": kind,
        "created_at": time.time(),
        "date": digest_day().strftime("%Y-%m-%d"),
        "provider": LLM_PROVIDER,
        "model": current_model_name(),
        "prompt_version": LLM_PROMPT_VERSION,
        "value": value,
    }
    LLM_CACHE[key] = record
    os.makedirs(os.path.dirname(LLM_CACHE_FILE), exist_ok=True)
    with open(LLM_CACHE_FILE, "a", encoding="utf-8") as cache_file:
        cache_file.write(json.dumps(record, ensure_ascii=False) + "\n")


load_llm_cache()


def wait_until_send_time():
    wait_until_local_time(SEND_AT_LOCAL, shanghai_now, time.sleep, log_progress, strict=True)


def compact_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def truncate(value, limit):
    value = compact_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def fetch_text(url, timeout=20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": CCTV_REFERER,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_json(url, timeout=20):
    text = fetch_text(url, timeout=timeout).strip()
    if text.startswith("cb(") and text.endswith(")"):
        text = text[3:-1]
    return json.loads(text)


def cctv_api_url(date_text, page):
    params = {
        "id": CCTV_COLUMN_ID,
        "n": CCTV_PAGE_SIZE,
        "sort": "desc",
        "p": page,
        "bd": date_text,
        "mode": 2,
        "serviceId": "tvcctv",
    }
    return CCTV_API_BASE + "?" + urllib.parse.urlencode(params)


def normalize_item(raw):
    title = compact_text(raw.get("title", ""))
    title = re.sub(r"^\s*完整版\s*", "", title)
    title = re.sub(r"^\[朝闻天下\]\s*", "", title)
    title = title.strip()
    brief = compact_text(raw.get("brief", ""))
    return {
        "id": str(raw.get("guid") or raw.get("id") or raw.get("url") or title),
        "title": title,
        "brief": brief,
        "url": raw.get("url") or "",
        "time": raw.get("time") or "",
        "is_full": title.startswith("《朝闻天下》") or "《朝闻天下》" in title,
    }


def load_cctv_items():
    date_text = digest_day().strftime("%Y%m%d")
    items = []
    seen = set()
    for page in range(1, max(1, CCTV_FETCH_PAGES) + 1):
        data = fetch_json(cctv_api_url(date_text, page))
        page_items = data.get("data", {}).get("list", [])
        if not page_items:
            break
        for raw in page_items:
            item = normalize_item(raw)
            key = item["id"] or item["url"] or item["title"]
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        if len(page_items) < CCTV_PAGE_SIZE:
            break
    log_progress(f"cctv items loaded count={len(items)}")
    return items[:CCTV_ITEM_LIMIT]


def next_deepseek_api_key():
    global DEEPSEEK_KEY_INDEX
    if not DEEPSEEK_API_KEYS:
        return ""
    with DEEPSEEK_KEY_LOCK:
        key = DEEPSEEK_API_KEYS[DEEPSEEK_KEY_INDEX % len(DEEPSEEK_API_KEYS)]
        DEEPSEEK_KEY_INDEX += 1
        return key


def openai_response_text(prompt):
    if not OPENAI_API_KEY:
        return ""
    payload = {"model": OPENAI_MODEL, "input": prompt}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=data,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("output_text"):
        return body["output_text"].strip()
    chunks = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    return "".join(chunks).strip()


def deepseek_response_text(prompt, api_key=None):
    api_key = api_key or next_deepseek_api_key()
    if not api_key:
        return ""
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是中文新闻早报编辑，擅长把央视新闻标题和摘要整理成结构清晰、"
                    "事实准确、适合飞书阅读的简报。你必须只输出 JSON。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()


def llm_response_text(prompt, deepseek_api_key=None):
    if LLM_PROVIDER == "deepseek":
        return deepseek_response_text(prompt, deepseek_api_key)
    return openai_response_text(prompt)


def llm_worker(prompt, queue, deepseek_api_key=None):
    try:
        queue.put({"text": llm_response_text(prompt, deepseek_api_key), "error": ""})
    except Exception as exc:
        queue.put({"text": "", "error": str(exc), "error_type": exc.__class__.__name__})


def is_timeout_error(error_type, message):
    message = (message or "").lower()
    return error_type in {"TimeoutError", "socket.timeout"} or "timed out" in message or "timeout" in message


def llm_response_text_once(prompt):
    started_at = time.time()
    with LLM_SEMAPHORE:
        deepseek_api_key = next_deepseek_api_key() if LLM_PROVIDER == "deepseek" else None
        queue = Queue()
        process = Process(target=llm_worker, args=(prompt, queue, deepseek_api_key))
        process.start()
        process.join(LLM_TIMEOUT_SECONDS)
        if process.is_alive():
            process.terminate()
            process.join(5)
            raise TimeoutError(f"LLM summary timed out after {LLM_TIMEOUT_SECONDS}s")
        if queue.empty():
            raise RuntimeError("LLM summary returned no result")
        result = queue.get()
        if result["error"]:
            error_type = result.get("error_type", "RuntimeError")
            raise RuntimeError(f"{error_type}: {result['error']}")
        elapsed = time.time() - started_at
        if elapsed >= 10:
            log_progress(f"llm request ok seconds={elapsed:.1f} prompt_chars={len(prompt)}")
        return result["text"]


def llm_response_text_with_timeout(prompt):
    attempts = max(1, LLM_RETRY_ATTEMPTS)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return llm_response_text_once(prompt)
        except TimeoutError:
            raise
        except Exception as exc:
            last_error = exc
            message = str(exc)
            if attempt >= attempts or is_timeout_error(exc.__class__.__name__, message):
                raise
            log_progress(f"llm request failed attempt={attempt}/{attempts}, retrying: {message}")
            time.sleep(max(0, LLM_RETRY_BACKOFF_SECONDS) * attempt)
    raise last_error


def extract_json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return json.loads(text[start : end + 1])


def json_llm_response(prompt, expected_shape):
    text = llm_response_text_with_timeout(prompt)
    try:
        return extract_json_object(text)
    except Exception as first_error:
        repair_prompt = (
            "下面是一段本应为 JSON 的模型输出，但格式不合法。请只根据原输出修复为合法 JSON，"
            "不要新增事实，不要解释。\n"
            f"目标 JSON 结构：{expected_shape}\n"
            "原输出：\n"
            + text[:8000]
        )
        repaired = llm_response_text_with_timeout(repair_prompt)
        try:
            return extract_json_object(repaired)
        except Exception as second_error:
            raise ValueError(f"JSON parse failed after retry: {first_error}; {second_error}") from second_error


def item_for_llm(item):
    return {
        "title": truncate(item["title"], 120),
        "brief": truncate(item["brief"], 260),
        "time": item.get("time", ""),
        "is_full": item.get("is_full", False),
    }


def build_llm_digest(items):
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return None
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return None
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "items": [item_for_llm(item) for item in items],
    }
    cached = get_cached_summary("cctv_digest", payload)
    if cached:
        return cached
    prompt = (
        "请根据央视《朝闻天下》当天节目条目，生成新闻早报摘要。\n"
        "只输出 JSON：{\"overview\":\"...\",\"highlights\":[\"...\"],"
        "\"sections\":[{\"topic\":\"国内要闻\",\"summary\":\"...\"}],\"risk_notes\":\"...\"}。\n"
        "要求：\n"
        "1. overview 用 2-3 句概括当天新闻主线。\n"
        "2. highlights 给 5-8 条最值得关注的重点，每条一句话。\n"
        "3. sections 按国内要闻、国际要闻、财经科技、社会民生、军事外交等归类；没有材料的板块不要硬写。\n"
        "4. summary 要写清楚事件、主体、动作和影响，不要只罗列标题，不要编造输入之外的信息。\n"
        "5. risk_notes 可简短指出当天需持续关注的国际冲突、灾害、安全或政策变化；没有则为空字符串。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    parsed = json_llm_response(
        prompt,
        "{\"overview\":\"...\",\"highlights\":[\"...\"],\"sections\":[{\"topic\":\"...\",\"summary\":\"...\"}],\"risk_notes\":\"...\"}",
    )
    result = {
        "overview": parsed.get("overview") if isinstance(parsed.get("overview"), str) else "",
        "highlights": parsed.get("highlights") if isinstance(parsed.get("highlights"), list) else [],
        "sections": parsed.get("sections") if isinstance(parsed.get("sections"), list) else [],
        "risk_notes": parsed.get("risk_notes") if isinstance(parsed.get("risk_notes"), str) else "",
    }
    set_cached_summary("cctv_digest", payload, result)
    return result


FALLBACK_CATEGORIES = [
    ("国内要闻", ("国家", "中国", "全国", "国务院", "外交部", "统计局", "市场监管", "教育部")),
    ("国际要闻", ("美国", "伊朗", "以色列", "联合国", "南非", "巴西", "日本", "俄罗斯", "欧洲", "国际")),
    ("财经科技", ("价格", "指数", "市场", "汽车", "软件", "科技", "产业", "贸易", "航空运输")),
    ("社会民生", ("健康", "医院", "天气", "高温", "事故", "枪击", "坠毁", "死亡", "伤")),
    ("军事外交", ("美军", "导弹", "空军", "防空", "军事", "安保", "战事", "油轮")),
]


def fallback_digest(items):
    news = [item for item in items if not item.get("is_full")]
    overview = f"今日《朝闻天下》共抓取 {len(items)} 条节目内容，其中分条新闻 {len(news)} 条。"
    highlights = [item["title"] for item in news[:8]]
    sections = []
    used = set()
    for topic, keywords in FALLBACK_CATEGORIES:
        matched = []
        for item in news:
            text = item["title"] + " " + item.get("brief", "")
            if item["id"] in used:
                continue
            if any(keyword in text for keyword in keywords):
                matched.append(item)
                used.add(item["id"])
        if matched:
            sample = "；".join(item["brief"] or item["title"] for item in matched[:5])
            sections.append({"topic": topic, "summary": sample})
    return {"overview": overview, "highlights": highlights, "sections": sections, "risk_notes": ""}


def markdown_escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("`", "\\`")
    )


def markdown_link(text, href):
    return f"[{markdown_escape(text)}]({href})"


def build_daily_lines(items):
    try:
        digest = build_llm_digest(items) or fallback_digest(items)
    except Exception as exc:
        log_progress(f"cctv llm summary failed, fallback to rule summary: {exc}")
        digest = fallback_digest(items)

    full_items = [item for item in items if item.get("is_full")]
    news_items = [item for item in items if not item.get("is_full")]
    overview_lines = ["**今日概览**", markdown_escape(digest.get("overview") or "暂无概览。")]
    if digest.get("risk_notes"):
        overview_lines.append("")
        overview_lines.append(f"持续关注：{markdown_escape(digest['risk_notes'])}")

    highlight_lines = ["**重点新闻**"]
    highlights = [compact_text(str(item)) for item in digest.get("highlights", []) if compact_text(str(item))]
    if highlights:
        for index, item in enumerate(highlights[:8], start=1):
            highlight_lines.append(f"{index}. {markdown_escape(item)}")
    else:
        for index, item in enumerate(news_items[:8], start=1):
            highlight_lines.append(f"{index}. {markdown_escape(item['title'])}")

    section_lines = ["**板块总结**"]
    sections = digest.get("sections") or []
    if sections:
        for item in sections[:8]:
            topic = compact_text(str(item.get("topic", ""))) if isinstance(item, dict) else ""
            summary = compact_text(str(item.get("summary", ""))) if isinstance(item, dict) else ""
            if topic and summary:
                section_lines.append("")
                section_lines.append(f"<font color=\"blue\">**{markdown_escape(topic)}**</font>：{markdown_escape(summary)}")
    else:
        section_lines.append("今日暂无可归纳板块。")

    link_lines = ["**原文入口**"]
    if full_items:
        full_link_text = " ".join(
            markdown_link(str(index), item["url"])
            for index, item in enumerate(full_items[:5], start=1)
            if item.get("url")
        )
        if full_link_text:
            link_lines.append(f"完整版：{full_link_text}")
    detail_links = " ".join(
        markdown_link(str(index), item["url"])
        for index, item in enumerate(news_items[:10], start=1)
        if item.get("url")
    )
    if detail_links:
        link_lines.append(f"分条新闻：{detail_links}")

    return overview_lines, highlight_lines, section_lines, link_lines


def send_feishu_card(webhook, sections, today):
    return push_send_feishu_card(webhook, f"朝闻天下日报 {today}", sections)


def build_feishu_image_key(title, sections):
    if not FEISHU_IMAGE_DAILY_ENABLED:
        return ""
    if not (FEISHU_APP_ID and FEISHU_APP_SECRET):
        return ""
    if not (render_daily_image and upload_feishu_image and send_feishu_image):
        raise RuntimeError("daily image renderer unavailable")
    image_path = os.path.join(APP_DATA_DIR, f"cctv_daily_{digest_day().strftime('%Y-%m-%d')}.png")
    render_daily_image(title, sections, image_path)
    log_progress(f"feishu image rendered path={image_path}")
    return upload_feishu_image(image_path, FEISHU_APP_ID, FEISHU_APP_SECRET)


def wechat_work_markdown(value):
    return push_wechat_work_markdown(value)


def truncate_utf8_plain(value, max_bytes):
    return push_truncate_utf8_plain(value, max_bytes)


def wechat_line(value):
    value = wechat_work_markdown(value).strip()
    if not value or value.startswith("原文"):
        return ""
    value = value.replace("**", "")
    value = re.sub(r"\s+", " ", value)
    return truncate_utf8_plain(value, 700)


def build_wechat_content(title, sections, max_bytes=3900):
    return push_build_wechat_content(title, sections, max_bytes=max_bytes, skip_prefixes=("原文",))


def send_wechat_work_markdown(webhook, title, sections):
    return push_send_wechat_work_markdown(webhook, title, sections, skip_prefixes=("原文",))


def send_notifications(items):
    today = digest_day().strftime("%Y-%m-%d")
    title = f"朝闻天下日报 {today}"
    sections = build_daily_lines(items)
    errors = []
    sent = 0
    image_key = ""
    image_error = ""
    if selected_robots(FEISHU_ROBOTS) and FEISHU_IMAGE_DAILY_ENABLED:
        try:
            image_key = build_feishu_image_key(title, sections)
            if image_key:
                log_progress("feishu image uploaded")
        except Exception as exc:
            image_error = str(exc)
            log_progress(f"feishu image unavailable, fallback to card: {exc}")
    for robot in selected_robots(FEISHU_ROBOTS):
        try:
            if image_key:
                send_feishu_image(robot["url"], image_key)
            else:
                send_feishu_card(robot["url"], sections, today)
            sent += 1
        except Exception as exc:
            errors.append(f"feishu/{robot['name']}: {exc}")
            log_progress(f"feishu send failed robot={robot['name']}: {exc}")
            if image_key:
                try:
                    send_feishu_card(robot["url"], sections, today)
                    sent += 1
                    log_progress(f"feishu card fallback sent robot={robot['name']}")
                except Exception as fallback_exc:
                    errors.append(f"feishu-card-fallback/{robot['name']}: {fallback_exc}")
                    log_progress(f"feishu card fallback failed robot={robot['name']}: {fallback_exc}")
    for robot in selected_robots(WECHAT_WORK_ROBOTS):
        try:
            send_wechat_work_markdown(robot["url"], title, sections)
            sent += 1
        except Exception as exc:
            errors.append(f"wechat work/{robot['name']}: {exc}")
            log_progress(f"wechat work send failed robot={robot['name']}: {exc}")
    if sent == 0:
        if image_error:
            errors.append(f"feishu-image: {image_error}")
        raise RuntimeError("all notification channels failed: " + "; ".join(errors))


def main():
    log_progress("start loading cctv items")
    items = load_cctv_items()
    log_progress(f"cctv loaded count={len(items)}")
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        today = digest_day().strftime("%Y-%m-%d")
        title = f"朝闻天下日报 {today}"
        sections = build_daily_lines(items)
        output_path = RENDER_OUTPUT or os.path.join(APP_DATA_DIR, f"cctv_daily_render_only_{today}.png")
        render_daily_image(title, sections, output_path)
        log_progress(f"render only output={output_path}")
        return
    wait_until_send_time()
    log_progress("sending notifications")
    send_notifications(items)
    log_progress("done")


if __name__ == "__main__":
    main()
