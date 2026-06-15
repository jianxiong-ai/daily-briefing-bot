#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from multiprocessing import Process, Queue
from threading import BoundedSemaphore, Lock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.environ.get("AI_DAILY_ENV", os.path.join(ROOT_DIR, "work/ai_daily/.env"))


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
        if url:
            robots.append({"name": name or f"机器人{index}", "url": url, "primary": "primary" in flags or "主" in flags})
    seen = set()
    result = []
    for robot in robots:
        if robot["url"] in seen:
            continue
        seen.add(robot["url"])
        result.append(robot)
    return result


def selected_robots(robots):
    if PUSH_TARGETS in {"primary", "main", "test"}:
        primary = [robot for robot in robots if robot.get("primary")]
        return primary or robots[:1]
    return robots


load_env_file(ENV_PATH, override=False)

REDFOX_API_KEY = os.environ.get("REDFOX_API_KEY", "").strip()
GZH_AI_URL = os.environ.get("AI_GZH_URL", "https://redfox.hk/story/api/parseWork/queryAiMsgs").strip()
XHS_AI_URL = os.environ.get("AI_XHS_URL", "https://redfox.hk/story/api/parseWork/queryXhsAiMsgs").strip()
AI_DAILY_TITLE = os.environ.get("AI_DAILY_TITLE", "AI领域日报").strip()
AI_GZH_KEYWORDS = [item.strip() for item in os.environ.get("AI_GZH_KEYWORDS", "AI").split(",") if item.strip()]
AI_XHS_KEYWORD = os.environ.get("AI_XHS_KEYWORD", "AI").strip() or "AI"
AI_GZH_PAGE_SIZE = int(os.environ.get("AI_GZH_PAGE_SIZE", "20"))
AI_XHS_PAGE_SIZE = int(os.environ.get("AI_XHS_PAGE_SIZE", "50"))
AI_GZH_USE_DATE_RANGE = os.environ.get("AI_GZH_USE_DATE_RANGE", "0").strip() == "1"
AI_XHS_USE_DATE_RANGE = os.environ.get("AI_XHS_USE_DATE_RANGE", "0").strip() == "1"
AI_INPUT_LIMIT = int(os.environ.get("AI_INPUT_LIMIT", "80"))
AI_TOPIC_LIMIT = int(os.environ.get("AI_TOPIC_LIMIT", "8"))
REDFOX_TIMEOUT_SECONDS = int(os.environ.get("REDFOX_TIMEOUT_SECONDS", "90"))
REDFOX_RAW_CACHE_FILE = os.environ.get("REDFOX_RAW_CACHE_FILE", os.path.join(os.path.dirname(ENV_PATH), "redfox_raw_cache.json"))
REDFOX_FORCE_REFRESH = os.environ.get("REDFOX_FORCE_REFRESH", "0").strip() == "1"
REDFOX_TODAY_CACHE_TTL_SECONDS = int(os.environ.get("REDFOX_TODAY_CACHE_TTL_SECONDS", "3600"))
DAILY_RUN_MODE = os.environ.get("DAILY_RUN_MODE", "").strip().lower()

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "").strip()
WECHAT_WORK_WEBHOOK = os.environ.get("WECHAT_WORK_WEBHOOK", "").strip()
PUSH_TARGETS = os.environ.get("PUSH_TARGETS", "all").strip().lower()
FEISHU_ROBOTS = parse_webhook_robots(os.environ.get("FEISHU_WEBHOOKS", ""), FEISHU_WEBHOOK, "主机器人")
WECHAT_WORK_ROBOTS = parse_webhook_robots(os.environ.get("WECHAT_WORK_WEBHOOKS", ""), WECHAT_WORK_WEBHOOK, "主机器人")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "").strip()
FEISHU_IMAGE_DAILY_ENABLED = os.environ.get("FEISHU_IMAGE_DAILY_ENABLED", "1").strip() != "0"

DIGEST_DATE = os.environ.get("DIGEST_DATE", "").strip()
AI_DIGEST_OFFSET_DAYS = int(os.environ.get("AI_DIGEST_OFFSET_DAYS", "1"))
SEND_AT_LOCAL = os.environ.get("SEND_AT_LOCAL", "").strip()
RENDER_ONLY = os.environ.get("RENDER_ONLY", "").strip() == "1"
RENDER_OUTPUT = os.environ.get("RENDER_OUTPUT", "").strip()
LOG_PROGRESS = os.environ.get("LOG_PROGRESS", "1").strip() != "0"

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_API_KEYS = [
    value.strip()
    for value in os.environ.get("DEEPSEEK_API_KEYS", "").replace("\n", ",").split(",")
    if value.strip()
]
if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY not in DEEPSEEK_API_KEYS:
    DEEPSEEK_API_KEYS.insert(0, DEEPSEEK_API_KEY)
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip()
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "270"))
LLM_MAX_CONCURRENT_REQUESTS = int(os.environ.get("LLM_MAX_CONCURRENT_REQUESTS", "4"))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "1").strip() != "0"
LLM_CACHE_TTL_SECONDS = int(os.environ.get("LLM_CACHE_TTL_SECONDS", "21600"))
LLM_CACHE_FILE = os.environ.get("AI_LLM_CACHE_FILE", os.path.join(os.path.dirname(ENV_PATH), "llm_summary_cache.jsonl"))
LLM_PROMPT_VERSION = os.environ.get("AI_LLM_PROMPT_VERSION", "ai-v2")

APP_DATA_DIR = os.path.dirname(ENV_PATH)
SH_TZ = timezone(timedelta(hours=8))
REDFOX_CACHE_LOCK = Lock()
LLM_SEMAPHORE = BoundedSemaphore(max(1, LLM_MAX_CONCURRENT_REQUESTS))
LLM_CACHE = {}


def log_progress(message):
    if LOG_PROGRESS:
        print(f"[{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def shanghai_now():
    return datetime.now(SH_TZ)


def digest_day():
    if DIGEST_DATE:
        return datetime.strptime(DIGEST_DATE, "%Y-%m-%d").replace(tzinfo=SH_TZ)
    return (shanghai_now() - timedelta(days=AI_DIGEST_OFFSET_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)


def is_today_digest():
    return digest_day().date() == shanghai_now().date()


def is_formal_run():
    return DAILY_RUN_MODE == "formal"


def compact_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def truncate(value, limit):
    value = compact_text(value)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def int_value(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def format_num(value):
    n = int_value(value)
    if n >= 100000:
        return f"{n // 10000}w+"
    if n >= 10000:
        return f"{n / 10000:.1f}w"
    return str(n)


def wait_until_send_time():
    if not SEND_AT_LOCAL:
        return
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", SEND_AT_LOCAL)
    if not match:
        raise ValueError(f"Invalid SEND_AT_LOCAL: {SEND_AT_LOCAL}")
    now = shanghai_now()
    target = now.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
    if now >= target:
        return
    seconds = (target - now).total_seconds()
    log_progress(f"waiting until {SEND_AT_LOCAL}, seconds={int(seconds)}")
    time.sleep(seconds)


def redfox_cache_key(payload):
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def load_redfox_raw_cache():
    if not os.path.exists(REDFOX_RAW_CACHE_FILE):
        return {}
    try:
        with open(REDFOX_RAW_CACHE_FILE, "r", encoding="utf-8") as cache_file:
            data = json.load(cache_file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_redfox_raw_cache(cache):
    os.makedirs(os.path.dirname(REDFOX_RAW_CACHE_FILE), exist_ok=True)
    trimmed = dict(list(cache.items())[-120:])
    with open(REDFOX_RAW_CACHE_FILE, "w", encoding="utf-8") as cache_file:
        json.dump(trimmed, cache_file, ensure_ascii=False)


def get_redfox_raw_cache(payload):
    cache = load_redfox_raw_cache()
    record = cache.get(redfox_cache_key(payload))
    if not record or REDFOX_FORCE_REFRESH:
        return None
    if is_today_digest():
        if is_formal_run():
            log_progress("redfox raw cache skipped for formal run on today")
            return None
        age = time.time() - float(record.get("created_at", 0) or 0)
        if age > REDFOX_TODAY_CACHE_TTL_SECONDS:
            log_progress(f"redfox raw cache expired age_seconds={int(age)}")
            return None
    return record.get("data")


def set_redfox_raw_cache(payload, data):
    with REDFOX_CACHE_LOCK:
        cache = load_redfox_raw_cache()
        cache[redfox_cache_key(payload)] = {
            "created_at": time.time(),
            "date": digest_day().strftime("%Y-%m-%d"),
            "channel": payload.get("_channel"),
            "data": data,
        }
        save_redfox_raw_cache(cache)


def redfox_post_json(url, payload):
    send_payload = {key: value for key, value in payload.items() if not key.startswith("_")}
    data = json.dumps(send_payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-KEY": REDFOX_API_KEY,
            "User-Agent": "Codex-AIDaily/0.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REDFOX_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_redfox_list(url, payload):
    cached = get_redfox_raw_cache(payload)
    if cached is not None:
        items = cached.get("items", []) or []
        log_progress(f"redfox cache hit channel={payload.get('_channel')} items={len(items)}")
        return items
    body = redfox_post_json(url, payload)
    if body.get("code") not in (200, 2000):
        raise RuntimeError(f"RedFox API error channel={payload.get('_channel')}: {body.get('msg') or body.get('code')}")
    data = body.get("data") or {}
    items = data.get("list") if isinstance(data, dict) else data
    if not isinstance(items, list):
        items = []
    set_redfox_raw_cache(payload, {"items": items})
    log_progress(f"redfox loaded channel={payload.get('_channel')} items={len(items)}")
    return items


def normalize_gzh(raw):
    title = compact_text(raw.get("title"))
    if not title:
        return None
    summary = compact_text(raw.get("summary") or raw.get("content") or raw.get("memo"))
    url = compact_text(raw.get("workUrl") or raw.get("url") or raw.get("sourceUrl"))
    return {
        "channel": "公众号",
        "id": compact_text(raw.get("photoId") or raw.get("workUuid") or raw.get("id") or url or title),
        "title": title,
        "summary": summary,
        "author": compact_text(raw.get("userName") or raw.get("author") or raw.get("accountName")),
        "category": compact_text(raw.get("type") or raw.get("topic") or raw.get("accountType") or "未分类"),
        "url": url,
        "readCount": int_value(raw.get("readCount")),
        "likeCount": int_value(raw.get("likeCount")),
        "commentCount": int_value(raw.get("commentCount")),
        "shareCount": int_value(raw.get("shareCount")),
        "publishTime": compact_text(raw.get("publishTime") or raw.get("publicTime")),
    }


def normalize_xhs(raw):
    title = compact_text(raw.get("title"))
    if not title:
        return None
    photo_id = compact_text(raw.get("photoId"))
    url = f"https://www.xiaohongshu.com/explore/{photo_id}" if photo_id else compact_text(raw.get("url") or raw.get("workUrl"))
    return {
        "channel": "小红书",
        "id": photo_id or compact_text(raw.get("id") or url or title),
        "title": title,
        "summary": compact_text(raw.get("desc") or raw.get("content") or raw.get("summary")),
        "author": compact_text(raw.get("userName") or raw.get("author") or raw.get("accountName")),
        "category": compact_text(raw.get("type") or raw.get("topic") or "未分类"),
        "url": url,
        "readCount": 0,
        "likeCount": int_value(raw.get("likeCount")),
        "commentCount": int_value(raw.get("commentCount")),
        "shareCount": int_value(raw.get("shareCount")),
        "publishTime": compact_text(raw.get("publishTime") or raw.get("time")),
    }


def load_ai_items():
    if not REDFOX_API_KEY:
        raise RuntimeError("missing REDFOX_API_KEY")
    day = digest_day().strftime("%Y-%m-%d")
    next_day = (digest_day() + timedelta(days=1)).strftime("%Y-%m-%d")
    items = []

    for keyword in AI_GZH_KEYWORDS[:3]:
        payload = {
            "_channel": "gzh",
            "_url": GZH_AI_URL,
            "keyword": keyword,
            "pageNum": 1,
            "pageSize": AI_GZH_PAGE_SIZE,
            "source": "AI公众号信息源-Codex",
        }
        if AI_GZH_USE_DATE_RANGE:
            payload["startTime"] = day
            payload["endTime"] = next_day
        for raw in fetch_redfox_list(GZH_AI_URL, payload):
            item = normalize_gzh(raw)
            if item:
                items.append(item)

    xhs_payload = {
        "_channel": "xhs",
        "_url": XHS_AI_URL,
        "keyword": AI_XHS_KEYWORD,
        "pageNum": 1,
        "pageSize": AI_XHS_PAGE_SIZE,
        "source": "AI小红书信息源-Codex",
    }
    if AI_XHS_USE_DATE_RANGE:
        xhs_payload["startTime"] = day
        xhs_payload["endTime"] = next_day
    for raw in fetch_redfox_list(XHS_AI_URL, xhs_payload):
        item = normalize_xhs(raw)
        if item:
            items.append(item)

    seen = set()
    deduped = []
    for item in items:
        key = f"{item['channel']}:{item['id'] or item['title']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=lambda item: item_score(item), reverse=True)
    return deduped


def item_score(item):
    if item["channel"] == "公众号":
        return item["readCount"] + item["likeCount"] * 20 + item["commentCount"] * 50
    return item["likeCount"] * 20 + item["shareCount"] * 30 + item["commentCount"] * 40


def current_model_name():
    return DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else OPENAI_MODEL


def load_llm_cache():
    if not LLM_CACHE_ENABLED or not os.path.exists(LLM_CACHE_FILE):
        return
    try:
        with open(LLM_CACHE_FILE, "r", encoding="utf-8") as cache_file:
            for line in cache_file:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = record.get("key")
                if key:
                    LLM_CACHE[key] = record
    except OSError:
        return


def cache_key(kind, payload):
    identity = {
        "kind": kind,
        "provider": LLM_PROVIDER,
        "model": current_model_name(),
        "prompt_version": LLM_PROMPT_VERSION,
        "payload": payload,
    }
    return sha256_text(json.dumps(identity, ensure_ascii=False, sort_keys=True))


def get_cached_summary(kind, payload):
    if not LLM_CACHE_ENABLED:
        return None
    record = LLM_CACHE.get(cache_key(kind, payload))
    if not record:
        return None
    age = time.time() - float(record.get("created_at", 0) or 0)
    if age > LLM_CACHE_TTL_SECONDS:
        return None
    log_progress(f"llm cache hit kind={kind}")
    return record.get("value")


def set_cached_summary(kind, payload, value):
    if not LLM_CACHE_ENABLED or value is None:
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


def run_llm_request(prompt, response_format):
    if LLM_PROVIDER == "deepseek":
        api_keys = DEEPSEEK_API_KEYS
        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        model = DEEPSEEK_MODEL
    else:
        api_keys = [OPENAI_API_KEY] if OPENAI_API_KEY else []
        url = "https://api.openai.com/v1/chat/completions"
        model = OPENAI_MODEL
    if not api_keys:
        raise RuntimeError("missing LLM API key")
    key = api_keys[int(time.time() * 1000) % len(api_keys)]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的 AI 行业信息分析助手，只根据输入内容总结，输出有效 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    start = time.time()
    with LLM_SEMAPHORE:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    log_progress(f"llm request ok seconds={time.time() - start:.1f} prompt_chars={len(prompt)}")
    return body["choices"][0]["message"]["content"]


def llm_request_worker(prompt, response_format, queue):
    try:
        queue.put(("ok", run_llm_request(prompt, response_format)))
    except Exception as exc:
        queue.put(("error", repr(exc)))


def json_llm_response(prompt, response_format):
    queue = Queue()
    process = Process(target=llm_request_worker, args=(prompt, response_format, queue))
    process.start()
    process.join(LLM_TIMEOUT_SECONDS + 10)
    if process.is_alive():
        process.terminate()
        process.join()
        raise TimeoutError(f"LLM request timed out after {LLM_TIMEOUT_SECONDS}s")
    if queue.empty():
        raise RuntimeError("LLM request failed without result")
    status, value = queue.get()
    if status != "ok":
        raise RuntimeError(value)
    return json.loads(value)


def item_for_llm(item):
    return {
        "channel": item["channel"],
        "title": truncate(item["title"], 120),
        "summary": truncate(item["summary"], 260),
        "author": truncate(item["author"], 50),
        "category": truncate(item["category"], 80),
        "reads": item["readCount"],
        "likes": item["likeCount"],
        "comments": item["commentCount"],
        "shares": item["shareCount"],
        "publish_time": item["publishTime"],
    }


def balanced_items(items, per_channel_limit):
    by_channel = {}
    for item in items:
        by_channel.setdefault(item["channel"], []).append(item)
    for channel in by_channel:
        by_channel[channel].sort(key=item_score, reverse=True)
    result = []
    channels = ["公众号", "小红书"]
    for index in range(per_channel_limit):
        for channel in channels:
            bucket = by_channel.get(channel) or []
            if index < len(bucket):
                result.append(bucket[index])
    return result


def fallback_digest(items):
    channels = {}
    for item in items:
        channels[item["channel"]] = channels.get(item["channel"], 0) + 1
    channel_text = "、".join(f"{name}{count}条" for name, count in channels.items())
    topics = []
    for name in ("模型与产品", "Agent 与应用", "AI 创作", "算力与产业", "投融资与商业化", "教程与方法"):
        matches = [item for item in items if any(word in f"{item['title']} {item['summary']}" for word in name.split(" 与 "))]
        if matches:
            topics.append({"topic": name, "summary": "；".join(item["title"] for item in matches[:5])})
    if not topics:
        topics = [{"topic": "AI热点", "summary": "；".join(item["title"] for item in items[:8])}]
    return {
        "overview": f"昨日 AI 信息源共收集 {len(items)} 条内容，来源包括{channel_text or '公众号和小红书'}。",
        "topics": topics[:AI_TOPIC_LIMIT],
        "signals": [],
    }


def build_llm_digest(items):
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return fallback_digest(items)
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return fallback_digest(items)
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "items": [item_for_llm(item) for item in balanced_items(items, max(1, AI_INPUT_LIMIT // 2))[:AI_INPUT_LIMIT]],
    }
    cached = get_cached_summary("ai_daily_digest", payload)
    if cached:
        return cached
    prompt = (
        "请根据 AI 公众号和 AI 小红书两个信息源，生成一份 AI 领域信息日报。请先分类聚合，再总结，不要逐条流水账。\n"
        "只输出 JSON：{\"overview\":\"...\",\"topics\":[{\"topic\":\"...\",\"summary\":\"...\"}],\"signals\":[\"...\"]}。\n"
        "要求：\n"
        "1. overview 用 2-3 句概括昨日 AI 信息主线，说明公众号偏深度/产业，小红书偏实操/消费/创作者反馈时的差异。\n"
        "2. topics 聚合 5-8 个主题，每条 180-320 字，信息密度要高。主题优先关注：大模型与产品、Agent/RAG/开发工具、AI 应用落地、AI 创作与视频、算力芯片与基础设施、商业化与投融资、教程方法论。\n"
        "3. 每个主题要合并两个渠道的信息，不要在主题标题里写“公众号”“小红书”等来源名；来源差异放在正文里自然说明。\n"
        "4. 小红书内容不要当成行业事实，应表达为用户体验、创作者反馈或使用场景；公众号内容可作为行业资讯和深度文章线索。\n"
        "5. signals 输出 3-5 条今日值得关注的信号，短句即可。\n"
        "6. 不要编造输入以外的信息，不要写投资建议。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    parsed = json_llm_response(
        prompt,
        "{\"overview\":\"...\",\"topics\":[{\"topic\":\"...\",\"summary\":\"...\"}],\"signals\":[\"...\"]}",
    )
    result = {
        "overview": parsed.get("overview") if isinstance(parsed.get("overview"), str) else "",
        "topics": parsed.get("topics") if isinstance(parsed.get("topics"), list) else [],
        "signals": parsed.get("signals") if isinstance(parsed.get("signals"), list) else [],
    }
    set_cached_summary("ai_daily_digest", payload, result)
    return result


def markdown_escape(value):
    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def markdown_link(text, href):
    return f"[{markdown_escape(text)}]({href})"


def build_daily_lines(items):
    try:
        digest = build_llm_digest(items)
    except Exception as exc:
        log_progress(f"ai llm summary failed, fallback to rule summary: {exc}")
        digest = fallback_digest(items)

    overview_lines = ["**昨日概览**", markdown_escape(digest.get("overview") or "暂无概览。")]

    signal_lines = ["**关键信号**"]
    for signal in (digest.get("signals") or [])[:5]:
        text = compact_text(signal)
        if text:
            signal_lines.append(f"- {markdown_escape(text)}")
    if len(signal_lines) == 1:
        top = items[:3]
        signal_lines.extend(f"- {markdown_escape(item['title'])}" for item in top)

    topic_lines = ["**主题总结**"]
    for topic in (digest.get("topics") or [])[:AI_TOPIC_LIMIT]:
        if not isinstance(topic, dict):
            continue
        topic_name = compact_text(topic.get("topic"))
        summary = compact_text(topic.get("summary"))
        if topic_name and summary:
            topic_lines.append("")
            topic_lines.append(f"<font color=\"blue\">**{markdown_escape(topic_name)}**</font>")
            topic_lines.append(markdown_escape(summary))
    if len(topic_lines) == 1:
        topic_lines.append("暂无可归纳主题。")

    return overview_lines, signal_lines, topic_lines


def send_feishu_card(webhook, sections, today):
    elements = []
    for index, section in enumerate(sections):
        if index:
            elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": "\n".join(section)})
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"{AI_DAILY_TITLE} {today}"}},
            "elements": elements,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        sys.stdout.write(resp.read().decode("utf-8"))


def build_feishu_image_key(title, sections):
    if not FEISHU_IMAGE_DAILY_ENABLED:
        return ""
    if not (FEISHU_APP_ID and FEISHU_APP_SECRET):
        return ""
    if not (render_daily_image and upload_feishu_image and send_feishu_image):
        raise RuntimeError("daily image renderer unavailable")
    image_path = os.path.join(APP_DATA_DIR, f"ai_daily_{digest_day().strftime('%Y-%m-%d')}.png")
    render_daily_image(title, sections, image_path)
    log_progress(f"feishu image rendered path={image_path}")
    return upload_feishu_image(image_path, FEISHU_APP_ID, FEISHU_APP_SECRET)


def wechat_work_markdown(value):
    value = re.sub(r"</?font\b[^>]*>", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return value


def truncate_utf8_plain(value, max_bytes):
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    return data[:max_bytes].decode("utf-8", errors="ignore").rstrip() + "..."


def wechat_line(value):
    value = wechat_work_markdown(value).strip()
    if not value:
        return ""
    value = value.replace("**", "")
    value = re.sub(r"\s+", " ", value)
    return truncate_utf8_plain(value, 700)


def build_wechat_content(title, sections, max_bytes=3900):
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
            line = wechat_line(raw_line)
            if not line:
                continue
            candidate = lines + [line]
            if len("\n".join(candidate).encode("utf-8")) > budget:
                omitted = True
                break
            lines = candidate
        if omitted:
            break
    content = "\n".join(lines)
    if omitted:
        content += suffix
    return content


def send_wechat_work_markdown(webhook, title, sections):
    payload = {"msgtype": "markdown", "markdown": {"content": build_wechat_content(title, sections)}}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        sys.stdout.write(resp.read().decode("utf-8"))


def send_notifications(items):
    today = digest_day().strftime("%Y-%m-%d")
    title = f"{AI_DAILY_TITLE} {today}"
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
                except Exception as fallback_exc:
                    errors.append(f"feishu-card-fallback/{robot['name']}: {fallback_exc}")
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
    log_progress("start loading ai daily items")
    items = load_ai_items()
    log_progress(f"ai items loaded count={len(items)}")
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        today = digest_day().strftime("%Y-%m-%d")
        title = f"{AI_DAILY_TITLE} {today}"
        sections = build_daily_lines(items)
        output_path = RENDER_OUTPUT or os.path.join(APP_DATA_DIR, f"ai_daily_render_only_{today}.png")
        render_daily_image(title, sections, output_path)
        log_progress(f"render only output={output_path}")
        return
    wait_until_send_time()
    log_progress("sending notifications")
    send_notifications(items)
    log_progress("done")


if __name__ == "__main__":
    main()
