#!/usr/bin/env python3
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
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
from daily_briefing.llm import (
    JsonlSummaryCache,
    LlmClient,
    LlmSettings,
    cache_key as shared_cache_key,
    split_api_keys,
)
from daily_briefing.redfox import (
    RawJsonCache,
    post_json as shared_redfox_post_json,
    redfox_cache_key as shared_redfox_cache_key,
)
from daily_briefing.quality import dedupe_by_similarity
try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ENV_PATH = os.environ.get("AI_DAILY_ENV", os.path.join(ROOT_DIR, "work/ai_daily/.env"))


def load_env_file(path, override=False):
    return runtime_load_env_file(path, override=override)


def parse_webhook_robots(value, primary_url="", primary_name="主机器人"):
    return runtime_parse_webhook_robots(value, primary_url, primary_name)


def selected_robots(robots):
    return runtime_selected_robots(robots, PUSH_TARGETS)


load_env_file(ENV_PATH, override=False)

REDFOX_API_KEY = os.environ.get("REDFOX_API_KEY", "").strip()
XHS_AI_URL = os.environ.get("AI_XHS_URL", "https://redfox.hk/story/api/parseWork/queryXhsAiMsgs").strip()
AIHOT_ITEMS_URL = os.environ.get("AIHOT_ITEMS_URL", "https://aihot.virxact.com/api/public/items").strip()
AI_DAILY_TITLE = os.environ.get("AI_DAILY_TITLE", "AI领域日报").strip()
AI_XHS_KEYWORD = os.environ.get("AI_XHS_KEYWORD", "AI").strip() or "AI"
AI_XHS_PAGE_SIZE = int(os.environ.get("AI_XHS_PAGE_SIZE", "50"))
AI_XHS_USE_DATE_RANGE = os.environ.get("AI_XHS_USE_DATE_RANGE", "1").strip() != "0"
AIHOT_PAGE_SIZE = int(os.environ.get("AIHOT_PAGE_SIZE", "100"))
AIHOT_MAX_PAGES = int(os.environ.get("AIHOT_MAX_PAGES", "3"))
AIHOT_TIMEOUT_SECONDS = int(os.environ.get("AIHOT_TIMEOUT_SECONDS", "45"))
AIHOT_FORCE_REFRESH = os.environ.get("AIHOT_FORCE_REFRESH", "0").strip() == "1"
AIHOT_CACHE_FILE = os.environ.get("AIHOT_CACHE_FILE", os.path.join(os.path.dirname(ENV_PATH), "aihot_raw_cache.json"))
AI_INPUT_LIMIT = int(os.environ.get("AI_INPUT_LIMIT", "80"))
AI_TOPIC_LIMIT = int(os.environ.get("AI_TOPIC_LIMIT", "8"))
AI_DEDUP_ENABLED = os.environ.get("AI_DEDUP_ENABLED", "1").strip() != "0"
AI_DEDUP_LOOKBACK_DAYS = int(os.environ.get("AI_DEDUP_LOOKBACK_DAYS", "7"))
AI_HISTORY_FILE = os.environ.get("AI_HISTORY_FILE", os.path.join(os.path.dirname(ENV_PATH), "ai_daily_history.json"))
AI_HISTORY_VERSION = os.environ.get("AI_HISTORY_VERSION", "aihot-v1").strip() or "aihot-v1"
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
DEEPSEEK_API_KEYS = split_api_keys(DEEPSEEK_API_KEY, os.environ.get("DEEPSEEK_API_KEYS", ""))
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip()
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "270"))
LLM_MAX_CONCURRENT_REQUESTS = int(os.environ.get("LLM_MAX_CONCURRENT_REQUESTS", "4"))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "1").strip() != "0"
LLM_CACHE_TTL_SECONDS = int(os.environ.get("LLM_CACHE_TTL_SECONDS", "21600"))
LLM_CACHE_FILE = os.environ.get("AI_LLM_CACHE_FILE", os.path.join(os.path.dirname(ENV_PATH), "llm_summary_cache.jsonl"))
LLM_PROMPT_VERSION = os.environ.get("AI_LLM_PROMPT_VERSION", "ai-v4")

APP_DATA_DIR = os.path.dirname(ENV_PATH)
SH_TZ = timezone(timedelta(hours=8))
REDFOX_CACHE_LOCK = Lock()
REDFOX_CACHE_STORE = RawJsonCache(REDFOX_RAW_CACHE_FILE, max_entries=120)
AIHOT_CACHE_LOCK = Lock()
AIHOT_CACHE_STORE = RawJsonCache(AIHOT_CACHE_FILE, max_entries=30)
LLM_SEMAPHORE = BoundedSemaphore(max(1, LLM_MAX_CONCURRENT_REQUESTS))
LLM_CLIENT = LlmClient(
    LlmSettings(
        provider=LLM_PROVIDER,
        base_url=DEEPSEEK_BASE_URL if LLM_PROVIDER == "deepseek" else "https://api.openai.com/v1",
        model=DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else OPENAI_MODEL,
        api_keys=DEEPSEEK_API_KEYS if LLM_PROVIDER == "deepseek" else ([OPENAI_API_KEY] if OPENAI_API_KEY else []),
        timeout=LLM_TIMEOUT_SECONDS,
        retries=int(os.environ.get("LLM_RETRIES", "1")),
    ),
    semaphore=LLM_SEMAPHORE,
)
LLM_CACHE = {}
LLM_CACHE_STORE = JsonlSummaryCache(LLM_CACHE_FILE, LLM_CACHE_TTL_SECONDS, LLM_CACHE_ENABLED, LLM_CACHE)


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
    wait_until_local_time(SEND_AT_LOCAL, shanghai_now, time.sleep, log_progress, strict=True)


def redfox_cache_key(payload):
    return shared_redfox_cache_key(payload)


def load_redfox_raw_cache():
    return REDFOX_CACHE_STORE.load()


def save_redfox_raw_cache(cache):
    REDFOX_CACHE_STORE.save(cache)


def get_redfox_raw_cache(payload):
    cache = load_redfox_raw_cache()
    record = cache.get(redfox_cache_key(payload))
    if not record or REDFOX_FORCE_REFRESH:
        return None
    expected_date = digest_day().strftime("%Y-%m-%d")
    if record.get("date") != expected_date:
        log_progress(
            "redfox raw cache date mismatch "
            f"cached={record.get('date') or '-'} expected={expected_date}"
        )
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
    return shared_redfox_post_json(
        url,
        payload,
        REDFOX_API_KEY,
        timeout=REDFOX_TIMEOUT_SECONDS,
        user_agent="Codex-AIDaily/0.1",
    )


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


def digest_window_utc():
    start = digest_day().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def iso_utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def aihot_cache_payload():
    start, end = digest_window_utc()
    return {
        "_cache_url": AIHOT_ITEMS_URL,
        "mode": "selected",
        "since": iso_utc(start),
        "until": iso_utc(end),
        "take": max(1, AIHOT_PAGE_SIZE),
    }


def fetch_aihot_page(params):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{AIHOT_ITEMS_URL}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "DailyBriefingBot/0.2 (+https://github.com/jianxiong-ai/daily-briefing-bot)",
        },
    )
    with urllib.request.urlopen(request, timeout=AIHOT_TIMEOUT_SECONDS) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        raise RuntimeError("AIHot response missing items")
    return body


def fetch_aihot_items():
    cache_payload = aihot_cache_payload()
    cached = AIHOT_CACHE_STORE.get(cache_payload, force_refresh=AIHOT_FORCE_REFRESH)
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        log_progress(f"aihot cache hit items={len(cached['items'])}")
        return cached["items"]

    params = {
        "mode": "selected",
        "since": cache_payload["since"],
        "take": max(1, AIHOT_PAGE_SIZE),
    }
    items = []
    seen = set()
    cursor = ""
    for page in range(1, max(1, AIHOT_MAX_PAGES) + 1):
        if cursor:
            params["cursor"] = cursor
        body = fetch_aihot_page(params)
        for raw in body.get("items") or []:
            item_id = compact_text(raw.get("id") or raw.get("url") or raw.get("title"))
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            items.append(raw)
        cursor = compact_text(body.get("nextCursor"))
        if not body.get("hasNext") or not cursor:
            break
        log_progress(f"aihot page loaded page={page} accumulated={len(items)}")

    AIHOT_CACHE_STORE.set(
        cache_payload,
        {"items": items},
        metadata={"date": digest_day().strftime("%Y-%m-%d")},
    )
    log_progress(f"aihot loaded items={len(items)}")
    return items


def source_publish_time(raw):
    return compact_text(
        raw.get("publishTime")
        or raw.get("publicTime")
        or raw.get("gmtCreate")
        or raw.get("createTime")
        or raw.get("time")
    )


def parse_source_date(value):
    value = compact_text(value)
    if not value:
        return None
    if re.fullmatch(r"\d{10,13}", value):
        timestamp = int(value)
        if len(value) == 13:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, SH_TZ).date()
        except (OverflowError, OSError, ValueError):
            return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        match = re.search(r"\d{4}-\d{2}-\d{2}", value)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(0), "%Y-%m-%d").date()
        except ValueError:
            return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(SH_TZ)
    return parsed.date()


def source_time_shanghai(value):
    value = compact_text(value)
    if not value:
        return ""
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    if parsed.tzinfo:
        parsed = parsed.astimezone(SH_TZ)
    return parsed.strftime("%Y-%m-%d %H:%M")


def filter_items_for_digest_date(items):
    expected = digest_day().date()
    kept = []
    stale = 0
    missing = 0
    for item in items:
        published = parse_source_date(item.get("publishTime"))
        if published is None:
            missing += 1
            continue
        valid = published == expected
        if not valid:
            stale += 1
            continue
        kept.append(item)
    if stale or missing:
        log_progress(
            "ai date filter "
            f"expected={expected.isoformat()} kept={len(kept)} stale={stale} missing={missing}"
        )
    return kept


def normalize_aihot(raw):
    title = compact_text(raw.get("title"))
    if not title:
        return None
    url = compact_text(raw.get("url") or raw.get("permalink"))
    return {
        "channel": "AI资讯",
        "id": compact_text(raw.get("id") or url or title),
        "title": title,
        "summary": compact_text(raw.get("summary")),
        "author": compact_text(raw.get("source") or "AIHot"),
        "category": compact_text(raw.get("category") or "未分类"),
        "url": url,
        "readCount": 0,
        "likeCount": 0,
        "commentCount": 0,
        "shareCount": 0,
        "score": int_value(raw.get("score")),
        "publishTime": compact_text(raw.get("publishedAt")),
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
        "publishTime": source_publish_time(raw),
    }


def load_ai_items():
    if not REDFOX_API_KEY:
        raise RuntimeError("missing REDFOX_API_KEY")
    day = digest_day().strftime("%Y-%m-%d")
    next_day = (digest_day() + timedelta(days=1)).strftime("%Y-%m-%d")
    items = []

    for raw in fetch_aihot_items():
        item = normalize_aihot(raw)
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
    deduped = filter_items_for_digest_date(deduped)
    deduped = dedupe_by_similarity(
        deduped,
        lambda item: f"{item.get('title', '')} {item.get('summary', '')}",
        threshold=0.42,
    )
    deduped.sort(key=lambda item: item_score(item), reverse=True)
    return deduped


def item_score(item):
    if item["channel"] == "AI资讯":
        return item.get("score", 0) * 100
    return item["likeCount"] * 20 + item["shareCount"] * 30 + item["commentCount"] * 40


def normalize_dedup_text(value):
    value = compact_text(value).lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def dedup_terms(value):
    text = normalize_dedup_text(value)
    terms = set()
    for token in re.findall(r"[a-z][a-z0-9.+-]{1,}|[0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{2,}", text):
        if len(token) > 4 and re.search(r"[\u4e00-\u9fff]", token):
            for size in (2, 3, 4):
                for index in range(0, len(token) - size + 1):
                    terms.add(token[index : index + size])
        else:
            terms.add(token)
    stopwords = {
        "今日",
        "昨日",
        "行业",
        "领域",
        "信息",
        "日报",
        "内容",
        "关注",
        "发布",
        "宣布",
        "显示",
        "用户",
        "小红书",
        "公众号",
        "ai资讯",
    }
    return terms - stopwords


def item_dedup_signature(item):
    return sorted(dedup_terms(f"{item.get('title', '')} {item.get('summary', '')}") or dedup_terms(item.get("title", "")))


def item_identity(item):
    return {
        "channel": item.get("channel", ""),
        "id": item.get("id", ""),
        "title": normalize_dedup_text(item.get("title", "")),
        "signature": item_dedup_signature(item),
    }


def load_ai_history():
    if not AI_HISTORY_FILE or not os.path.exists(AI_HISTORY_FILE):
        return []
    try:
        with open(AI_HISTORY_FILE, "r", encoding="utf-8") as history_file:
            data = json.load(history_file)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def prune_ai_history(history):
    cutoff = digest_day().date() - timedelta(days=max(1, AI_DEDUP_LOOKBACK_DAYS))
    pruned = []
    for record in history:
        if record.get("version") != AI_HISTORY_VERSION:
            continue
        try:
            record_date = datetime.strptime(record.get("date", ""), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if record_date >= cutoff and record_date != digest_day().date():
            pruned.append(record)
    return pruned


def save_ai_history(history):
    if not AI_HISTORY_FILE:
        return
    directory = os.path.dirname(AI_HISTORY_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(AI_HISTORY_FILE, "w", encoding="utf-8") as history_file:
        json.dump(history[-max(1, AI_DEDUP_LOOKBACK_DAYS) :], history_file, ensure_ascii=False)


def similarity(left, right):
    left_set = set(left or [])
    right_set = set(right or [])
    if not left_set or not right_set:
        return 0.0
    overlap = len(left_set & right_set)
    if overlap < 3:
        return 0.0
    return overlap / max(1, min(len(left_set), len(right_set)))


def has_strong_event_overlap(left, right):
    left_set = set(left or [])
    right_set = set(right or [])
    overlap = left_set & right_set
    entity_overlap = {
        term
        for term in overlap
        if re.search(r"[a-z]", term) or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", term)
    }
    chinese_overlap = {term for term in overlap if re.search(r"[\u4e00-\u9fff]", term)}
    if len(entity_overlap) >= 2 and len(chinese_overlap) >= 2:
        return True
    if len(overlap) >= 8 and similarity(left_set, right_set) >= 0.24:
        return True
    return False


def is_recent_duplicate(item, recent_identities):
    identity = item_identity(item)
    if not identity["title"] and not identity["signature"]:
        return False
    for previous in recent_identities:
        if identity["id"] and identity["channel"] == previous.get("channel") and identity["id"] == previous.get("id"):
            return True
        if identity["title"] and identity["title"] == previous.get("title"):
            return True
        if similarity(identity["signature"], previous.get("signature")) >= 0.72:
            return True
        if has_strong_event_overlap(identity["signature"], previous.get("signature")):
            return True
    return False


def recent_history_identities(history):
    identities = []
    for record in prune_ai_history(history):
        identities.extend(record.get("items") or [])
    return identities


def dedupe_recent_ai_items(items):
    if not AI_DEDUP_ENABLED:
        return items
    history = load_ai_history()
    recent_identities = recent_history_identities(history)
    if not recent_identities:
        return items
    result = []
    skipped = 0
    for item in items:
        if is_recent_duplicate(item, recent_identities):
            skipped += 1
            continue
        result.append(item)
    if skipped:
        log_progress(f"ai recent dedupe skipped={skipped} kept={len(result)}")
    return result


def recent_history_context(history, limit=12):
    texts = []
    for record in reversed(prune_ai_history(history)):
        for value in record.get("highlights") or []:
            text = truncate(value, 120)
            if text and text not in texts:
                texts.append(text)
            if len(texts) >= limit:
                return texts
    return texts


def record_ai_history(items, digest):
    if not AI_DEDUP_ENABLED:
        return
    history = prune_ai_history(load_ai_history())
    highlights = []
    if digest.get("overview"):
        highlights.append(compact_text(digest.get("overview")))
    for signal in digest.get("signals") or []:
        text = compact_text(signal)
        if text:
            highlights.append(text)
    for topic in digest.get("topics") or []:
        if isinstance(topic, dict):
            text = compact_text(f"{topic.get('topic', '')}: {topic.get('summary', '')}")
            if text:
                highlights.append(text)
    history.append(
        {
            "date": digest_day().strftime("%Y-%m-%d"),
            "version": AI_HISTORY_VERSION,
            "items": [item_identity(item) for item in items[:AI_INPUT_LIMIT]],
            "highlights": highlights[:24],
        }
    )
    save_ai_history(history)


def current_model_name():
    return DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else OPENAI_MODEL


def load_llm_cache():
    try:
        LLM_CACHE_STORE.load()
    except OSError:
        return


def cache_key(kind, payload):
    return shared_cache_key(kind, payload, LLM_PROVIDER, current_model_name(), LLM_PROMPT_VERSION)


def get_cached_summary(kind, payload):
    value = LLM_CACHE_STORE.get(cache_key(kind, payload))
    if value is not None:
        log_progress(f"llm cache hit kind={kind}")
    return value


def set_cached_summary(kind, payload, value):
    key = cache_key(kind, payload)
    metadata = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "provider": LLM_PROVIDER,
        "model": current_model_name(),
        "prompt_version": LLM_PROMPT_VERSION,
    }
    LLM_CACHE_STORE.set(key, kind, value, metadata=metadata)


load_llm_cache()


def run_llm_request(prompt, response_format):
    if not LLM_CLIENT.settings.api_keys:
        raise RuntimeError("missing LLM API key")
    start = time.time()
    text = LLM_CLIENT.chat(
        [
            {"role": "system", "content": "你是严谨的 AI 行业信息分析助手，只根据输入内容总结，输出有效 JSON。"},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    log_progress(f"llm request ok seconds={time.time() - start:.1f} prompt_chars={len(prompt)}")
    return text


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
        "publish_time": source_time_shanghai(item["publishTime"]),
    }


def balanced_items(items, per_channel_limit):
    by_channel = {}
    for item in items:
        by_channel.setdefault(item["channel"], []).append(item)
    for channel in by_channel:
        by_channel[channel].sort(key=item_score, reverse=True)
    result = []
    channels = ["AI资讯", "小红书"]
    for index in range(per_channel_limit):
        for channel in channels:
            bucket = by_channel.get(channel) or []
            if index < len(bucket):
                result.append(bucket[index])
    return result


SOURCE_META_PATTERNS = (
    r"缺少.{0,12}(小红书|AIHot|渠道|来源).{0,20}(内容|反馈|数据|样本)?",
    r"(小红书|AIHot).{0,12}(无|暂无|未提供|未返回|没有).{0,16}(内容|反馈|数据|样本)",
    r"日报.{0,12}(主要|仅|基本).{0,8}(基于|来自|依赖)",
    r"(信息源|数据源|渠道|样本).{0,12}(缺失|缺少|不足|有限|为零|未覆盖)",
    r"(本次|今日|昨日).{0,8}(未抓取|未获取|未收集).{0,16}(内容|数据|信息)",
)


def remove_source_meta_commentary(value):
    text = compact_text(value)
    if not text:
        return ""
    sentences = re.split(r"(?<=[。！？；!?])", text)
    kept = [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
        and not any(re.search(pattern, sentence, re.I) for pattern in SOURCE_META_PATTERNS)
    ]
    return "".join(kept).strip()


def clean_digest_content(digest):
    cleaned_topics = []
    for topic in digest.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        topic_name = compact_text(topic.get("topic"))
        summary = remove_source_meta_commentary(topic.get("summary"))
        if topic_name and summary:
            cleaned_topics.append({"topic": topic_name, "summary": summary})
    return {
        "overview": remove_source_meta_commentary(digest.get("overview")),
        "topics": cleaned_topics,
        "signals": [
            text
            for text in (
                remove_source_meta_commentary(item)
                for item in digest.get("signals") or []
            )
            if text
        ],
    }


def fallback_digest(items):
    topics = []
    for name in ("模型与产品", "Agent 与应用", "AI 创作", "算力与产业", "投融资与商业化", "教程与方法"):
        matches = [item for item in items if any(word in f"{item['title']} {item['summary']}" for word in name.split(" 与 "))]
        if matches:
            topics.append({"topic": name, "summary": "；".join(item["title"] for item in matches[:5])})
    if not topics:
        topics = [{"topic": "AI热点", "summary": "；".join(item["title"] for item in items[:8])}]
    return {
        "overview": "昨日 AI 动态聚焦于"
        + "、".join(item["title"] for item in items[:4])
        + "等事件与进展。",
        "topics": topics[:AI_TOPIC_LIMIT],
        "signals": [],
    }


def build_llm_digest(items):
    if not items:
        return fallback_digest(items)
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return fallback_digest(items)
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return fallback_digest(items)
    history = load_ai_history()
    recent_context = recent_history_context(history)
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "items": [item_for_llm(item) for item in balanced_items(items, max(1, AI_INPUT_LIMIT // 2))[:AI_INPUT_LIMIT]],
        "recent_published_highlights": recent_context,
    }
    cached = get_cached_summary("ai_daily_digest", payload)
    if cached:
        return cached
    prompt = (
        "请根据 AIHot 精选资讯和 AI 小红书两个信息源，生成一份 AI 领域信息日报。请先分类聚合，再总结，不要逐条流水账。\n"
        "只输出 JSON：{\"overview\":\"...\",\"topics\":[{\"topic\":\"...\",\"summary\":\"...\"}],\"signals\":[\"...\"]}。\n"
        "要求：\n"
        "1. 本日报日期是输入 JSON 的 date。overview 用 2-3 句概括该日期的 AI 信息主线，不要把 UTC 日期或文章正文中提到的其他日期误写成日报日期。\n"
        "2. topics 聚合 5-8 个主题，每条 180-320 字，信息密度要高。主题优先关注：大模型与产品、Agent/RAG/开发工具、AI 应用落地、AI 创作与视频、算力芯片与基础设施、商业化与投融资、教程方法论。\n"
        "3. 只聚焦输入内容本身，包括事件、明确对象、产品能力、关键数据、研究结论、产业影响和用户反馈。不要讨论信息源、数据源、渠道构成、样本数量、抓取状态、内容缺失或日报生成过程。\n"
        "4. 不要写“缺少小红书内容”“主要基于AIHot”“某渠道没有反馈”等编辑说明。若某一渠道没有内容，直接忽略，不要在任何字段中提及。小红书内容若存在，应表达为用户体验、创作者反馈或使用场景，不要当成行业事实。\n"
        "5. signals 输出 3-5 条今日值得关注的信号，短句即可。\n"
        "6. recent_published_highlights 是最近几天已经写进日报的重点，请避免重复这些旧内容；只有输入里出现了明确的新进展、新数据、新产品或新观点时才可再次提及，并要突出新增信息。\n"
        "7. 不要编造输入以外的信息，不要写投资建议。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    parsed = json_llm_response(
        prompt,
        "{\"overview\":\"...\",\"topics\":[{\"topic\":\"...\",\"summary\":\"...\"}],\"signals\":[\"...\"]}",
    )
    result = clean_digest_content({
        "overview": parsed.get("overview") if isinstance(parsed.get("overview"), str) else "",
        "topics": parsed.get("topics") if isinstance(parsed.get("topics"), list) else [],
        "signals": parsed.get("signals") if isinstance(parsed.get("signals"), list) else [],
    })
    set_cached_summary("ai_daily_digest", payload, result)
    return result


def markdown_escape(value):
    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def markdown_link(text, href):
    return f"[{markdown_escape(text)}]({href})"


def build_daily_payload(items):
    try:
        digest = build_llm_digest(items)
    except Exception as exc:
        log_progress(f"ai llm summary failed, fallback to rule summary: {exc}")
        digest = fallback_digest(items)
    digest = clean_digest_content(digest)

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

    return (overview_lines, signal_lines, topic_lines), digest


def build_daily_lines(items):
    return build_daily_payload(items)[0]


def send_feishu_card(webhook, sections, today):
    return push_send_feishu_card(webhook, f"{AI_DAILY_TITLE} {today}", sections)


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
    return push_wechat_work_markdown(value)


def truncate_utf8_plain(value, max_bytes):
    return push_truncate_utf8_plain(value, max_bytes)


def wechat_line(value):
    value = wechat_work_markdown(value).strip()
    if not value:
        return ""
    value = value.replace("**", "")
    value = re.sub(r"\s+", " ", value)
    return truncate_utf8_plain(value, 700)


def build_wechat_content(title, sections, max_bytes=3900):
    return push_build_wechat_content(title, sections, max_bytes=max_bytes)


def send_wechat_work_markdown(webhook, title, sections):
    return push_send_wechat_work_markdown(webhook, title, sections)


def send_notifications(items):
    today = digest_day().strftime("%Y-%m-%d")
    title = f"{AI_DAILY_TITLE} {today}"
    sections, digest = build_daily_payload(items)
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
    record_ai_history(items, digest)


def main():
    log_progress("start loading ai daily items")
    items = dedupe_recent_ai_items(load_ai_items())
    log_progress(f"ai items loaded count={len(items)}")
    if not items:
        raise RuntimeError(
            "AI daily has no fresh items after source date and history filtering; "
            "skip empty report and alert instead"
        )
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        today = digest_day().strftime("%Y-%m-%d")
        title = f"{AI_DAILY_TITLE} {today}"
        sections, _digest = build_daily_payload(items)
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
