#!/usr/bin/env python3
import hashlib
import html
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from multiprocessing import Process, Queue
from threading import BoundedSemaphore, Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from daily_briefing.redfox import (
    RawJsonCache,
    post_json as shared_redfox_post_json,
)
try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ENV_PATH = os.environ.get("WECHAT_DAILY_ENV", os.path.join(ROOT_DIR, "work/wechat_daily/.env"))
SHARED_ENV_PATH = os.environ.get("SHARED_DAILY_ENV", "").strip()


def load_env_file(path, override=False):
    return runtime_load_env_file(path, override=override)


def parse_webhook_robots(value, primary_url="", primary_name="主机器人"):
    return runtime_parse_webhook_robots(value, primary_url, primary_name)


def selected_robots(robots):
    return runtime_selected_robots(robots, PUSH_TARGETS)


load_env_file(SHARED_ENV_PATH, override=False)
load_env_file(ENV_PATH, override=False)

REDFOX_API_KEY = os.environ.get("REDFOX_API_KEY", "").strip()
REDFOX_HOT_ARTICLE_URL = os.environ.get(
    "REDFOX_HOT_ARTICLE_URL",
    "https://redfox.hk/story/api/gzh/search/hotArticle",
).strip()
REDFOX_WORK_LIST_URL = os.environ.get(
    "REDFOX_WORK_LIST_URL",
    "https://redfox.hk/story/api/gzhData/queryWorkList",
).strip()
WECHAT_DAILY_KEYWORD = os.environ.get("WECHAT_DAILY_KEYWORD", "").strip()
WECHAT_HOT_CANDIDATE_LIMIT = int(os.environ.get("WECHAT_HOT_CANDIDATE_LIMIT", "50"))
WECHAT_HOT_REPORT_LIMIT = int(os.environ.get("WECHAT_HOT_REPORT_LIMIT", "10"))
WECHAT_FOLLOW_ARTICLE_LIMIT = int(os.environ.get("WECHAT_FOLLOW_ARTICLE_LIMIT", "30"))
WECHAT_FOLLOW_AUTHOR_LIMIT = int(os.environ.get("WECHAT_FOLLOW_AUTHOR_LIMIT", "20"))
WECHAT_FOLLOW_FETCH_WORKERS = int(os.environ.get("WECHAT_FOLLOW_FETCH_WORKERS", "4"))
WECHAT_FOLLOW_MAX_PAGES = int(os.environ.get("WECHAT_FOLLOW_MAX_PAGES", "2"))
WECHAT_MIN_READS = int(os.environ.get("WECHAT_MIN_READS", "5000"))
WECHAT_DAILY_TITLE = os.environ.get("WECHAT_DAILY_TITLE", "昨日公众号信息汇总").strip()
WECHAT_ORIGINAL_FETCH_ENABLED = os.environ.get("WECHAT_ORIGINAL_FETCH_ENABLED", "1").strip() != "0"
WECHAT_ORIGINAL_FETCH_LIMIT = int(os.environ.get("WECHAT_ORIGINAL_FETCH_LIMIT", "3"))
WECHAT_ORIGINAL_TEXT_LIMIT = int(os.environ.get("WECHAT_ORIGINAL_TEXT_LIMIT", "1800"))
WECHAT_ORIGINAL_CACHE_FILE = os.environ.get("WECHAT_ORIGINAL_CACHE_FILE", os.path.join(os.path.dirname(ENV_PATH), "original_article_cache.json"))
REDFOX_PAGE_SIZE = int(os.environ.get("REDFOX_PAGE_SIZE", str(max(50, WECHAT_HOT_CANDIDATE_LIMIT))))
REDFOX_RAW_CACHE_FILE = os.environ.get("REDFOX_RAW_CACHE_FILE", os.path.join(os.path.dirname(ENV_PATH), "redfox_raw_cache.json"))
REDFOX_FORCE_REFRESH = os.environ.get("REDFOX_FORCE_REFRESH", "0").strip() == "1"
REDFOX_TODAY_CACHE_TTL_SECONDS = int(os.environ.get("REDFOX_TODAY_CACHE_TTL_SECONDS", "3600"))
REDFOX_HOT_STABLE_AFTER_HOURS = int(os.environ.get("REDFOX_HOT_STABLE_AFTER_HOURS", "8"))
REDFOX_AUTHOR_STABLE_AFTER_HOURS = int(os.environ.get("REDFOX_AUTHOR_STABLE_AFTER_HOURS", "8"))
REDFOX_TIMEOUT_SECONDS = int(os.environ.get("REDFOX_TIMEOUT_SECONDS", "90"))
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
WECHAT_DIGEST_OFFSET_DAYS = int(os.environ.get("WECHAT_DIGEST_OFFSET_DAYS", "0"))
SEND_AT_LOCAL = os.environ.get("SEND_AT_LOCAL", "").strip()
RENDER_ONLY = os.environ.get("RENDER_ONLY", "").strip() == "1"
RENDER_OUTPUT = os.environ.get("RENDER_OUTPUT", "").strip()
LOG_PROGRESS = os.environ.get("LOG_PROGRESS", "1").strip() != "0"
SHANGHAI_TZ = timezone(timedelta(hours=8))

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
REDFOX_CACHE_LOCK = Lock()
REDFOX_CACHE_STORE = RawJsonCache(REDFOX_RAW_CACHE_FILE, max_entries=120)

APP_DATA_DIR = os.path.dirname(ENV_PATH) if ENV_PATH else os.getcwd()
LLM_CACHE_FILE = os.environ.get("WECHAT_LLM_CACHE_FILE", os.path.join(APP_DATA_DIR, "llm_summary_cache.jsonl"))
LLM_CACHE_TTL_SECONDS = int(os.environ.get("WECHAT_LLM_CACHE_TTL_SECONDS", os.environ.get("LLM_CACHE_TTL_SECONDS", "43200")))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "1").strip() != "0"
LLM_PROMPT_VERSION = os.environ.get("WECHAT_LLM_PROMPT_VERSION", "wechat-hot-v1").strip()
LLM_CACHE = {}


def shanghai_now():
    return datetime.now(SHANGHAI_TZ)


def digest_day():
    if DIGEST_DATE:
        return datetime.strptime(DIGEST_DATE, "%Y-%m-%d").date()
    return (shanghai_now() - timedelta(days=max(0, WECHAT_DIGEST_OFFSET_DAYS))).date()


def is_today_digest():
    return digest_day() == shanghai_now().date()


def is_formal_run():
    return DAILY_RUN_MODE in {"formal", "prod", "production"}


def log_progress(message):
    if LOG_PROGRESS:
        print(f"[{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def compact_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def truncate(value, limit):
    value = compact_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


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


def parse_follow_authors(value):
    authors = []
    for raw_entry in re.split(r"[;\n]", value or ""):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split("|")]
        account = parts[0]
        name = parts[1] if len(parts) > 1 and parts[1] else parts[0]
        if account:
            authors.append({"account": account, "accountName": name})
    return authors[: max(1, WECHAT_FOLLOW_AUTHOR_LIMIT)]


WECHAT_FOLLOW_AUTHORS = parse_follow_authors(os.environ.get("WECHAT_FOLLOW_AUTHORS", ""))


def redfox_post_json(url, payload):
    return shared_redfox_post_json(
        url,
        payload,
        REDFOX_API_KEY,
        timeout=REDFOX_TIMEOUT_SECONDS,
        user_agent="Codex-WechatDaily/0.1",
    )


def fetch_redfox_hot_articles():
    if not REDFOX_API_KEY:
        raise RuntimeError("missing REDFOX_API_KEY")
    day = digest_day()
    payload = {
        "keyword": WECHAT_DAILY_KEYWORD,
        "startDate": day.strftime("%Y-%m-%d"),
        "endDate": (day + timedelta(days=1)).strftime("%Y-%m-%d"),
        "pageNum": 1,
        "pageSize": REDFOX_PAGE_SIZE,
        "source": "Codex-WechatDaily",
        "_cache_url": REDFOX_HOT_ARTICLE_URL,
    }
    cached = get_redfox_raw_cache(payload)
    if cached is not None:
        articles = cached.get("articles", []) or []
        latest = cached.get("latestHotArticles", []) or []
        log_progress(f"redfox raw cache hit articles={len(articles)} latest={len(latest)}")
        return articles, latest

    body = redfox_post_json(REDFOX_HOT_ARTICLE_URL, payload)
    if body.get("code") != 2000:
        raise RuntimeError(f"RedFox API error: {body.get('msg') or body.get('code')}")
    articles = body.get("data", {}).get("articles", []) or []
    latest = body.get("data", {}).get("latestHotArticles", []) or []
    log_progress(f"redfox loaded articles={len(articles)} latest={len(latest)}")
    set_redfox_raw_cache(payload, {"articles": articles, "latestHotArticles": latest})
    return articles, latest


def author_key(value):
    return re.sub(r"\s+", "", compact_text(value)).lower()


def hot_author_skip_set(articles):
    followed = {author_key(item["accountName"]) for item in WECHAT_FOLLOW_AUTHORS}
    return {
        author_key(article.get("author"))
        for article in articles
        if author_key(article.get("author")) in followed
    }


def fetch_follow_author_articles(skip_authors=None):
    skip_authors = set(skip_authors or set())
    if not WECHAT_FOLLOW_AUTHORS:
        return []
    if not REDFOX_API_KEY:
        raise RuntimeError("missing REDFOX_API_KEY")
    day = digest_day()
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")

    def should_fetch_next_page(data, collected_count):
        has_more = data.get("hasMore")
        if has_more in {1, True, "1", "true", "True"}:
            return True
        total = int_value(data.get("total"))
        if total:
            return total > collected_count
        return collected_count > 0 and collected_count % 20 == 0

    def fetch_one_author(author):
        if author_key(author.get("accountName") or author.get("account")) in skip_authors:
            log_progress(f"skip follow author already covered by hot articles account={author['account']}")
            return []
        raw_items = []
        max_pages = max(1, WECHAT_FOLLOW_MAX_PAGES)
        for page_index in range(max_pages):
            offset = page_index * 20
            payload = {
                "account": author["account"],
                "accountName": author.get("accountName", ""),
                "offset": offset,
                "sortType": "0",
                "publishTimeStart": start,
                "publishTimeEnd": end,
                "_cache_url": REDFOX_WORK_LIST_URL,
            }
            cached = get_redfox_raw_cache(payload)
            if cached is not None:
                data = cached
                page_list = data.get("list", []) or []
                log_progress(
                    f"redfox author cache hit account={author['account']} offset={offset} count={len(page_list)}"
                )
            else:
                body = redfox_post_json(REDFOX_WORK_LIST_URL, payload)
                if body.get("code") not in {2000, 200}:
                    raise RuntimeError(
                        f"RedFox author API error account={author['account']}: {body.get('msg') or body.get('code')}"
                    )
                data = body.get("data") or {}
                page_list = data.get("list", []) or []
                set_redfox_raw_cache(
                    payload,
                    {
                        "list": page_list,
                        "total": data.get("total"),
                        "hasMore": data.get("hasMore"),
                    },
                )
                log_progress(
                    f"redfox author loaded account={author['account']} offset={offset} count={len(page_list)} "
                    f"total={data.get('total')} hasMore={data.get('hasMore')}"
                )
            raw_items.extend(page_list)
            if not should_fetch_next_page(data, len(raw_items)):
                break
        return [normalize_follow_article(raw, author) for raw in raw_items]

    all_items = []
    seen = set()

    workers = max(1, min(WECHAT_FOLLOW_FETCH_WORKERS, len(WECHAT_FOLLOW_AUTHORS)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_one_author, author) for author in WECHAT_FOLLOW_AUTHORS]
        for future in as_completed(futures):
            for item in future.result():
                key = item["id"] or item["url"] or item["title"]
                if not key or key in seen or not item["title"]:
                    continue
                seen.add(key)
                all_items.append(item)
    all_items.sort(key=lambda item: item.get("publishTime", ""), reverse=True)
    return all_items[: max(1, WECHAT_FOLLOW_ARTICLE_LIMIT)]


def redfox_cache_key(payload):
    identity = {
        "url": payload.get("_cache_url", REDFOX_HOT_ARTICLE_URL),
        "keyword": payload.get("keyword", ""),
        "account": payload.get("account", ""),
        "accountName": payload.get("accountName", ""),
        "startDate": payload.get("startDate", ""),
        "endDate": payload.get("endDate", ""),
        "publishTimeStart": payload.get("publishTimeStart", ""),
        "publishTimeEnd": payload.get("publishTimeEnd", ""),
        "pageNum": payload.get("pageNum", ""),
        "pageSize": payload.get("pageSize", ""),
        "offset": payload.get("offset", ""),
        "sortType": payload.get("sortType", ""),
    }
    return sha256_text(json.dumps(identity, ensure_ascii=False, sort_keys=True))


def load_redfox_raw_cache():
    return REDFOX_CACHE_STORE.load()


def save_redfox_raw_cache(cache):
    REDFOX_CACHE_STORE.save(cache)


def get_redfox_raw_cache(payload):
    cache = load_redfox_raw_cache()
    record = cache.get(redfox_cache_key(payload))
    if not record:
        return None
    if REDFOX_FORCE_REFRESH:
        return None
    if is_today_digest():
        if is_formal_run():
            log_progress("redfox raw cache skipped for formal run on today")
            return None
        created_at = float(record.get("created_at", 0) or 0)
        age = time.time() - created_at
        if age > REDFOX_TODAY_CACHE_TTL_SECONDS:
            log_progress(f"redfox raw cache expired age_seconds={int(age)}")
            return None
    if should_expire_unstable_hot_cache(payload, record):
        return None
    data = record.get("data")
    if should_expire_empty_author_cache(payload, record, data):
        return None
    if should_refresh_incomplete_hot_cache(payload, data):
        return None
    return data


def should_expire_unstable_hot_cache(payload, record):
    if payload.get("_cache_url") != REDFOX_HOT_ARTICLE_URL:
        return False
    start_date = payload.get("startDate")
    if not start_date:
        return False
    try:
        day = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=SHANGHAI_TZ)
    except ValueError:
        return False
    stable_at = day + timedelta(days=1, hours=REDFOX_HOT_STABLE_AFTER_HOURS)
    created_at = datetime.fromtimestamp(float(record.get("created_at", 0) or 0), SHANGHAI_TZ)
    if created_at >= stable_at:
        return False
    age = time.time() - float(record.get("created_at", 0) or 0)
    if age <= REDFOX_TODAY_CACHE_TTL_SECONDS:
        return False
    log_progress(
        "redfox hot cache created before stable window expired "
        f"created_at={created_at.strftime('%Y-%m-%d %H:%M:%S')} stable_at={stable_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return True


def should_refresh_incomplete_hot_cache(payload, data):
    if payload.get("_cache_url") != REDFOX_HOT_ARTICLE_URL:
        return False
    if not isinstance(data, dict):
        return False
    articles = data.get("articles", []) or []
    latest = data.get("latestHotArticles", []) or []
    count = len(articles) + len(latest)
    if count >= max(6, WECHAT_HOT_REPORT_LIMIT):
        return False
    times = [
        compact_text(item.get("publicTime") or item.get("publishTime"))
        for item in articles + latest
        if isinstance(item, dict)
    ]
    early_count = sum(1 for value in times if re.search(r"\b00:\d{2}", value))
    if count < max(5, WECHAT_HOT_REPORT_LIMIT // 2) or (times and early_count == len(times)):
        log_progress(f"redfox hot cache looks incomplete count={count}, refreshing")
        return True
    return False


def should_expire_empty_author_cache(payload, record, data):
    if payload.get("_cache_url") != REDFOX_WORK_LIST_URL:
        return False
    if not isinstance(data, dict):
        return False
    if len(data.get("list", []) or []) > 0:
        return False
    start_date = payload.get("publishTimeStart")
    if not start_date:
        return False
    try:
        day = datetime.strptime(start_date[:10], "%Y-%m-%d").replace(tzinfo=SHANGHAI_TZ)
    except ValueError:
        return False
    stable_at = day + timedelta(days=1, hours=REDFOX_AUTHOR_STABLE_AFTER_HOURS)
    created_at = datetime.fromtimestamp(float(record.get("created_at", 0) or 0), SHANGHAI_TZ)
    if created_at >= stable_at:
        return False
    age = time.time() - float(record.get("created_at", 0) or 0)
    if age <= REDFOX_TODAY_CACHE_TTL_SECONDS:
        return False
    log_progress(
        "redfox author empty cache created before stable window expired "
        f"account={payload.get('account', '')} created_at={created_at.strftime('%Y-%m-%d %H:%M:%S')} "
        f"stable_at={stable_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return True


def set_redfox_raw_cache(payload, data):
    with REDFOX_CACHE_LOCK:
        cache = load_redfox_raw_cache()
        cache[redfox_cache_key(payload)] = {
            "created_at": time.time(),
            "date": payload.get("startDate") or payload.get("publishTimeStart", ""),
            "keyword": payload.get("keyword", ""),
            "account": payload.get("account", ""),
            "data": data,
        }
        save_redfox_raw_cache(cache)


def int_value(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def normalize_article(raw):
    title = compact_text(raw.get("title"))
    url = str(raw.get("url") or "").strip()
    summary = compact_text(raw.get("summary"))
    reads = int_value(raw.get("clicksCount"))
    return {
        "id": str(raw.get("id") or url or title),
        "title": title,
        "author": compact_text(raw.get("author") or raw.get("sourceUsernickname")),
        "publicTime": compact_text(raw.get("publicTime")),
        "url": url,
        "summary": summary,
        "clicksCount": reads,
        "watchCount": int_value(raw.get("watchCount")),
        "likeCount": int_value(raw.get("likeCount")),
        "commentsCount": int_value(raw.get("commentsCount")),
        "imageUrl": str(raw.get("imageUrl") or "").strip(),
        "popularityScore": raw.get("popularityScore"),
        "recencyScore": raw.get("recencyScore"),
        "relevanceScore": raw.get("relevanceScore"),
        "totalScore": raw.get("totalScore"),
    }


def normalize_follow_article(raw, author):
    title = compact_text(raw.get("title"))
    url = str(raw.get("workUrl") or raw.get("url") or raw.get("sourceUrl") or "").strip()
    summary = compact_text(raw.get("summary") or raw.get("memo"))
    content = compact_text(raw.get("content"))
    return {
        "id": str(raw.get("workUuid") or raw.get("workId") or raw.get("id") or url or title),
        "title": title,
        "author": compact_text(raw.get("author") or raw.get("accountName") or author.get("accountName") or author.get("account")),
        "account": compact_text(raw.get("account") or author.get("account")),
        "publishTime": compact_text(raw.get("publishTime")),
        "url": url,
        "summary": summary,
        "content": content,
        "readCount": int_value(raw.get("readCount")),
        "watchCount": int_value(raw.get("watchCount")),
        "likeCount": int_value(raw.get("likeCount")),
        "commentCount": int_value(raw.get("commentCount")),
        "collectCount": int_value(raw.get("collectCount")),
        "shareCount": int_value(raw.get("shareCount")),
        "isOriginal": int_value(raw.get("isOriginal")),
    }


AD_KEYWORDS = (
    "优惠券",
    "限时抢",
    "直播间",
    "购买链接",
    "课程报名",
    "招商",
    "加盟",
    "返现",
    "福利码",
)


LOW_VALUE_KEYWORDS = (
    "装修",
    "家装",
    "拆错",
    "赔偿",
    "明星",
    "女明星",
    "男明星",
    "直播带货",
    "八卦",
    "绯闻",
    "爽文",
    "穿搭",
    "妆容",
    "减肥",
    "种草",
)


CATEGORY_RULES = [
    (
        "国际局势",
        50,
        ("美国", "伊朗", "以色列", "俄罗斯", "乌克兰", "中东", "欧盟", "联合国", "外交", "战争", "制裁", "关税", "特朗普", "日本", "印度"),
    ),
    (
        "宏观经济",
        48,
        ("央行", "存款", "居民", "CPI", "PPI", "经济", "金融", "消费", "财政", "货币", "利率", "通胀", "楼市", "股市", "债券", "就业"),
    ),
    (
        "科技产业",
        46,
        ("AI", "人工智能", "芯片", "半导体", "机器人", "SpaceX", "马斯克", "新能源", "汽车", "互联网", "大模型", "算力"),
    ),
    (
        "社会公共",
        42,
        ("教育", "高考", "医疗", "社保", "人口", "养老", "食品安全", "事故", "天气", "灾害", "法律", "政策", "监管", "城市"),
    ),
    (
        "文化体育",
        28,
        (
            "世界杯",
            "体育",
            "足球",
            "电影",
            "音乐",
            "演出",
            "综艺",
            "游戏",
            "文旅",
            "旅游",
            "WSBK",
            "WorldSSP",
            "摩托",
            "机车",
            "赛车",
            "车手",
            "夺冠",
            "分站冠军",
        ),
    ),
    (
        "商业消费",
        18,
        ("品牌", "销量", "涨价", "上市", "价格", "促销", "电商", "消费品", "门店", "直播间"),
    ),
    (
        "生活娱乐",
        8,
        ("明星", "娱乐", "情感", "家庭", "装修", "穿搭", "美妆", "减肥", "八卦"),
    ),
]


def is_probable_ad(article):
    text = f"{article['title']} {article['summary']}"
    return any(keyword in text for keyword in AD_KEYWORDS)


def classify_article(article):
    title = article["title"]
    title_lower = title.lower()
    if any(keyword in title for keyword in ("教育", "学校", "家长", "孩子", "学生", "高考")):
        return "社会公共"
    if any(keyword.lower() in title_lower for keyword in ("影视", "电视剧", "爽剧", "剧集", "收视", "电影", "综艺")):
        return "文化体育"
    text = f"{article['title']} {article['summary']} {article['author']}"
    for category, _weight, keywords in CATEGORY_RULES:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return category
    return "其他"


def is_low_value_article(article):
    text = f"{article['title']} {article['summary']} {article['author']}"
    if any(keyword in text for keyword in LOW_VALUE_KEYWORDS):
        return True
    if article.get("category") in {"生活娱乐"}:
        return True
    return False


LOCAL_WEATHER_KEYWORDS = ("天气", "暴雨", "强降雨", "大暴雨", "特大暴雨", "降水", "台风", "洪水", "地质灾害", "列车停运")
NEARBY_REGION_KEYWORDS = ("浙江", "杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州", "舟山", "台州", "丽水", "上海", "江苏", "南京", "苏州", "无锡", "常州", "南通", "安徽", "合肥", "福建")
REMOTE_REGION_KEYWORDS = ("广东", "广西", "福建", "江西", "湖南", "湖北", "河南", "河北", "山东", "山西", "陕西", "四川", "重庆", "云南", "贵州", "海南", "新疆", "西藏", "青海", "甘肃", "宁夏", "内蒙古", "黑龙江", "吉林", "辽宁", "北京", "天津")
NATIONAL_IMPACT_KEYWORDS = ("全国", "多地", "中央气象台", "国家防总", "应急管理部", "中国气象局", "交通运输部", "农业", "粮食", "能源", "供应链")


def is_remote_local_weather(article):
    title = article["title"]
    text = f"{title} {article['summary']} {article['author']}"
    if not any(keyword in text for keyword in LOCAL_WEATHER_KEYWORDS):
        return False
    if any(keyword in title for keyword in REMOTE_REGION_KEYWORDS):
        return True
    if any(keyword in text for keyword in NEARBY_REGION_KEYWORDS):
        return False
    if any(keyword in text for keyword in NATIONAL_IMPACT_KEYWORDS):
        return False
    return any(keyword in text for keyword in REMOTE_REGION_KEYWORDS)


def quality_score(article):
    text = f"{article['title']} {article['summary']} {article['author']}"
    category = article.get("category") or classify_article(article)
    category_weight = next((weight for name, weight, _keywords in CATEGORY_RULES if name == category), 12)
    score = category_weight
    score += math.log10(max(article.get("clicksCount") or 0, 1)) * 8
    score += min(article.get("watchCount") or 0, 500) / 35
    score += min(article.get("likeCount") or 0, 2000) / 300
    if any(word in text for word in ("政策", "央行", "外交", "战争", "监管", "数据", "报告", "危机", "风险", "趋势")):
        score += 10
    if any(word in text for word in LOW_VALUE_KEYWORDS):
        score -= 28
    if article.get("category") == "商业消费":
        score -= 10
    if is_remote_local_weather(article):
        score -= 35
    if len(article.get("summary", "")) < 20:
        score -= 6
    return score


def diversify_articles(articles):
    for item in articles:
        item["category"] = classify_article(item)
        item["qualityScore"] = quality_score(item)

    preferred = [item for item in articles if not is_low_value_article(item)]
    if len(preferred) >= min(6, WECHAT_HOT_REPORT_LIMIT):
        primary_pool = preferred
    else:
        primary_pool = articles

    primary_pool = sorted(primary_pool, key=lambda item: item["qualityScore"], reverse=True)
    all_pool = sorted(articles, key=lambda item: item["qualityScore"], reverse=True)
    buckets = {}
    for item in primary_pool:
        buckets.setdefault(item["category"], []).append(item)

    category_order = ["国际局势", "宏观经济", "科技产业", "社会公共", "文化体育", "商业消费", "其他", "生活娱乐"]
    selected = []
    used = set()
    max_per_category = 2

    for _round in range(max_per_category):
        for category in category_order:
            bucket = buckets.get(category, [])
            if len([item for item in selected if item.get("category") == category]) > _round:
                continue
            for item in bucket:
                key = item["id"] or item["url"] or item["title"]
                if key not in used:
                    selected.append(item)
                    used.add(key)
                    break
            if len(selected) >= WECHAT_HOT_REPORT_LIMIT:
                return selected

    for item in primary_pool:
        key = item["id"] or item["url"] or item["title"]
        if key in used:
            continue
        selected.append(item)
        used.add(key)
        if len(selected) >= WECHAT_HOT_REPORT_LIMIT:
            return selected

    for item in all_pool:
        key = item["id"] or item["url"] or item["title"]
        if key in used:
            continue
        selected.append(item)
        used.add(key)
        if len(selected) >= WECHAT_HOT_REPORT_LIMIT:
            break
    return selected


def load_hot_articles():
    articles, latest = fetch_redfox_hot_articles()
    merged = []
    seen = set()
    for raw in articles + latest:
        item = normalize_article(raw)
        key = item["id"] or item["url"] or item["title"]
        if not key or key in seen or not item["title"]:
            continue
        seen.add(key)
        if item["clicksCount"] < WECHAT_MIN_READS:
            continue
        if is_probable_ad(item):
            continue
        merged.append(item)
    merged = merged[: max(1, WECHAT_HOT_CANDIDATE_LIMIT)]
    selected = diversify_articles(merged)
    log_progress(
        "hot articles selected count="
        f"{len(selected)} categories={','.join(item.get('category', '') for item in selected)}"
    )
    return selected[: max(1, WECHAT_HOT_REPORT_LIMIT)]


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
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
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
                "content": "你是中文新媒体日报编辑，擅长把公众号热门文章整理成准确、克制、信息密度高的中文摘要。你必须只输出 JSON。",
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
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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


def load_original_article_cache():
    if not os.path.exists(WECHAT_ORIGINAL_CACHE_FILE):
        return {}
    try:
        with open(WECHAT_ORIGINAL_CACHE_FILE, "r", encoding="utf-8") as cache_file:
            data = json.load(cache_file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_original_article_cache(cache):
    os.makedirs(os.path.dirname(WECHAT_ORIGINAL_CACHE_FILE), exist_ok=True)
    trimmed = dict(list(cache.items())[-160:])
    with open(WECHAT_ORIGINAL_CACHE_FILE, "w", encoding="utf-8") as cache_file:
        json.dump(trimmed, cache_file, ensure_ascii=False)


def clean_original_html(html_text):
    match = re.search(r'<div[^>]+id=["\']js_content["\'][^>]*>(.*?)</div>\s*<script', html_text, re.S)
    if not match:
        match = re.search(r'<div[^>]+id=["\']js_content["\'][^>]*>(.*?)</div>', html_text, re.S)
    if not match:
        return ""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", match.group(1), flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>|</section>|</div>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[\t\r\f\v ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return compact_text(text)


def fetch_original_article_text(url):
    if not url:
        return ""
    cache = load_original_article_cache()
    key = sha256_text(url)
    record = cache.get(key)
    if record:
        return record.get("text", "")
    text = ""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.49"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=min(20, REDFOX_TIMEOUT_SECONDS)) as response:
            body = response.read().decode("utf-8", errors="ignore")
        text = clean_original_html(body)
        if not text and "secitptpage/verify" in body:
            log_progress("wechat original article hit verify page")
    except Exception as exc:
        log_progress(f"wechat original article fetch failed: {exc}")
    cache[key] = {"created_at": time.time(), "url": url, "text": text[:WECHAT_ORIGINAL_TEXT_LIMIT]}
    save_original_article_cache(cache)
    return cache[key]["text"]


def needs_original_article_context(article):
    text = f"{article.get('title', '')} {article.get('summary', '')}"
    keywords = (
        "指南", "攻略", "清单", "报告", "数据", "解读", "深度", "测评",
        "某部剧", "某家公司", "某公司", "某明星", "某产品", "一部剧", "这部剧",
    )
    return any(keyword in text for keyword in keywords)


def enrich_hot_articles_with_original_text(articles):
    if not WECHAT_ORIGINAL_FETCH_ENABLED:
        return articles
    enriched = 0
    for article in articles:
        if enriched >= max(0, WECHAT_ORIGINAL_FETCH_LIMIT):
            break
        if not needs_original_article_context(article):
            continue
        original_text = fetch_original_article_text(article.get("url", ""))
        if original_text:
            article["originalText"] = truncate(original_text, WECHAT_ORIGINAL_TEXT_LIMIT)
            enriched += 1
            log_progress(f"wechat original article enriched title={article.get('title', '')[:40]}")
    return articles


def article_for_llm(article):
    return {
        "title": truncate(article["title"], 120),
        "account": truncate(article["author"], 40),
        "public_time": article.get("publicTime", ""),
        "category": article.get("category", ""),
        "reads": article.get("clicksCount", 0),
        "watch": article.get("watchCount", 0),
        "likes": article.get("likeCount", 0),
        "summary": truncate(article.get("summary", ""), 700),
        "original_text": truncate(article.get("originalText", ""), WECHAT_ORIGINAL_TEXT_LIMIT),
    }


def fallback_digest(articles):
    return {
        "overview": f"昨日共收集 {len(articles)} 篇公众号热门文章，主要按阅读数和互动数据排序。",
        "trend_topics": [],
        "articles": [
            {
                "index": index,
                "title": item["title"],
                "summary": item["summary"] or "RedFox 暂未返回可用摘要，建议打开原文查看。",
            }
            for index, item in enumerate(articles, start=1)
        ],
    }


def build_llm_digest(articles):
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return None
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return None
    articles = enrich_hot_articles_with_original_text(articles)
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "keyword": WECHAT_DAILY_KEYWORD,
        "articles": [article_for_llm(item) for item in articles],
    }
    cached = get_cached_summary("wechat_hot_digest", payload)
    if cached:
        return cached
    prompt = (
        "请根据 RedFox 返回的公众号热门文章数据，生成昨日公众号信息汇总。\n"
        "注意：输入里的 summary 可能只是摘要或正文片段，不能编造原文没有的信息。\n"
        "只输出 JSON：{\"overview\":\"...\",\"trend_topics\":[\"...\"],"
        "\"articles\":[{\"index\":1,\"title\":\"...\",\"summary\":\"...\"}]}。\n"
        "要求：\n"
        "1. overview 用 2-3 句概括昨日公众号热门文章的内容主线和主要领域。\n"
        "2. trend_topics 提炼 3-6 个昨日热门方向，每条一句话。\n"
        "3. articles 必须和输入文章一一对应，按输入顺序输出 index；每篇 summary 90-170 字，写清文章核心观点、事件和看点。\n"
        "4. 必须优先保留标题或 summary 中出现的明确对象、实体名、关键数字和实用建议，例如剧名、公司名、明星名、产品名、比赛时间、数量比例、操作建议等。\n"
        "5. 如果输入含 original_text，优先使用 original_text 补充文章中的具体实体、关键数字、清单项和建议。\n"
        "6. 遇到“指南、攻略、清单、报告、数据”等文章，要说明它具体指南/攻略/报告了什么，不要只写“提供参考”。\n"
        "7. 不要把输入里的明确实体泛化为“某部剧、某家公司、某明星、某产品”。如果输入本身没有实体名，则可使用较概括表述。\n"
        "8. 不要评价文章质量，不要写营销建议，不要杜撰数据。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    parsed = json_llm_response(
        prompt,
        "{\"overview\":\"...\",\"trend_topics\":[\"...\"],\"articles\":[{\"index\":1,\"title\":\"...\",\"summary\":\"...\"}]}",
    )
    result = {
        "overview": parsed.get("overview") if isinstance(parsed.get("overview"), str) else "",
        "trend_topics": parsed.get("trend_topics") if isinstance(parsed.get("trend_topics"), list) else [],
        "articles": parsed.get("articles") if isinstance(parsed.get("articles"), list) else [],
    }
    set_cached_summary("wechat_hot_digest", payload, result)
    return result


def follow_article_for_llm(article):
    source_text = article.get("content") or article.get("summary") or ""
    return {
        "title": truncate(article["title"], 140),
        "account": truncate(article["author"], 50),
        "publish_time": article.get("publishTime", ""),
        "reads": article.get("readCount", 0),
        "watch": article.get("watchCount", 0),
        "likes": article.get("likeCount", 0),
        "summary_or_content": truncate(source_text, 900),
    }


def fallback_follow_digest(articles):
    if not articles:
        return {"authors": []}
    by_author = {}
    for item in articles:
        by_author.setdefault(item["author"] or "未知作者", []).append(item["title"])
    authors = []
    for author, titles in by_author.items():
        authors.append({"author": author, "summary": "；".join(titles[:5])})
    return {"authors": authors}


def build_follow_digest(articles):
    if not articles:
        return {"authors": []}
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return fallback_follow_digest(articles)
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return fallback_follow_digest(articles)
    configured_order = {author_key(item["accountName"]): index for index, item in enumerate(WECHAT_FOLLOW_AUTHORS)}
    actual_authors = []
    seen_authors = set()
    for item in sorted(
        articles,
        key=lambda value: configured_order.get(author_key(value.get("author")), len(configured_order)),
    ):
        author = compact_text(item.get("author"))
        key = author_key(author)
        if author and key not in seen_authors:
            actual_authors.append(author)
            seen_authors.add(key)
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "authors": actual_authors,
        "articles": [follow_article_for_llm(item) for item in articles],
    }
    cached = get_cached_summary("wechat_follow_author_digest", payload)
    if cached:
        return cached
    prompt = (
        "请根据我关注的公众号作者昨日文章，按作者生成汇总。每个关注作者单独一条，不要跨作者合并成主题。\n"
        "只输出 JSON：{\"authors\":[{\"author\":\"...\",\"summary\":\"...\"}]}。\n"
        "要求：\n"
        "1. author 必须使用输入中的公众号作者名；同一作者多篇文章要合并总结。\n"
        "2. summary 写清该作者昨日文章的主要事件、观点和看点；文章多的作者 140-240 字，文章少的作者 80-140 字。\n"
        "3. 每个作者至少写两句：第一句概括发文数量和主题，第二句说明看点、情绪或可能影响。\n"
        "4. 如果输入只有标题、没有正文或摘要，也不要只写一句话；可以基于标题谨慎概括，不要提及数据源、接口、正文缺失、摘要缺失或无法确认。\n"
        "5. 不要把不同作者混在同一条里，不要生成宏观、科技、社会等主题标题。\n"
        "6. 不要编造输入以外的信息。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    parsed = json_llm_response(prompt, "{\"authors\":[{\"author\":\"...\",\"summary\":\"...\"}]}")
    result = {"authors": parsed.get("authors") if isinstance(parsed.get("authors"), list) else []}
    set_cached_summary("wechat_follow_author_digest", payload, result)
    return result


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


def format_num(n):
    n = int_value(n)
    if n >= 10000:
        return f"{n / 10000:.1f}w"
    return str(n)


def summary_by_index(digest):
    result = {}
    for item in digest.get("articles") or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        summary = compact_text(item.get("summary"))
        if summary:
            result[index] = summary
    return result


def build_follow_lines(follow_articles):
    follow_lines = ["**关注作者**"]
    if not WECHAT_FOLLOW_AUTHORS:
        follow_lines.append("尚未配置关注作者。")
        return follow_lines
    if not follow_articles:
        follow_lines.append("昨日关注作者暂无新文章。")
        return follow_lines
    try:
        digest = build_follow_digest(follow_articles)
    except Exception as exc:
        log_progress(f"wechat follow llm summary failed, fallback to rule summary: {exc}")
        digest = fallback_follow_digest(follow_articles)
    authors = digest.get("authors") or []
    if not authors:
        follow_lines.append("昨日关注作者暂无可汇总内容。")
        return follow_lines
    author_order = {item["accountName"]: index for index, item in enumerate(WECHAT_FOLLOW_AUTHORS)}
    authors.sort(key=lambda item: author_order.get(compact_text(item.get("author")), len(author_order)))
    for item in authors[:10]:
        if not isinstance(item, dict):
            continue
        author = compact_text(item.get("author"))
        summary = compact_text(item.get("summary"))
        if not author or not summary:
            continue
        follow_lines.append("")
        follow_lines.append(f"<font color=\"blue\">**{markdown_escape(author)}**</font>：{markdown_escape(summary)}")
    if len(follow_lines) == 1:
        follow_lines.append("昨日关注作者暂无可汇总内容。")
    return follow_lines


def build_daily_lines(articles, follow_articles):
    try:
        digest = build_llm_digest(articles) or fallback_digest(articles)
    except Exception as exc:
        log_progress(f"wechat hot llm summary failed, fallback to rule summary: {exc}")
        digest = fallback_digest(articles)

    overview_lines = ["**昨日概览**", markdown_escape(digest.get("overview") or "暂无概览。")]
    topics = [compact_text(str(item)) for item in digest.get("trend_topics", []) if compact_text(str(item))]
    if topics:
        overview_lines.append("")
        overview_lines.append("热门方向：" + "；".join(markdown_escape(item) for item in topics[:6]) + "。")

    article_lines = ["**昨日热门**"]
    summaries = summary_by_index(digest)
    for index, article in enumerate(articles, start=1):
        article_lines.append("")
        article_lines.append(f"<font color=\"blue\">**{index}. {markdown_escape(article['title'])}**</font>")
        meta_parts = [
            f"公众号：{markdown_escape(article['author'] or '-')}",
            f"阅读：{format_num(article['clicksCount'])}",
        ]
        if article.get("watchCount"):
            meta_parts.append(f"在看：{format_num(article['watchCount'])}")
        if article.get("publicTime"):
            meta_parts.append(f"发布时间：{markdown_escape(article['publicTime'][:16])}")
        article_lines.append(" | ".join(meta_parts))
        summary = summaries.get(index) or article.get("summary") or "RedFox 暂未返回可用摘要，建议打开原文查看。"
        article_lines.append(f"摘要：{markdown_escape(summary)}")
        if article.get("url"):
            article_lines.append(f"原文：{markdown_link(str(index), article['url'])}")

    follow_lines = build_follow_lines(follow_articles)
    return overview_lines, article_lines, follow_lines


def send_feishu_card(webhook, sections, today):
    return push_send_feishu_card(webhook, f"{WECHAT_DAILY_TITLE} {today}", sections)


def build_feishu_image_key(title, sections):
    if not FEISHU_IMAGE_DAILY_ENABLED:
        return ""
    if not (FEISHU_APP_ID and FEISHU_APP_SECRET):
        return ""
    if not (render_daily_image and upload_feishu_image and send_feishu_image):
        raise RuntimeError("daily image renderer unavailable")
    image_path = os.path.join(APP_DATA_DIR, f"wechat_daily_{digest_day().strftime('%Y-%m-%d')}.png")
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


def send_notifications(articles, follow_articles):
    today = digest_day().strftime("%Y-%m-%d")
    title = f"{WECHAT_DAILY_TITLE} {today}"
    sections = build_daily_lines(articles, follow_articles)
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
    log_progress("start loading wechat hot articles")
    articles = load_hot_articles()
    log_progress(f"wechat hot loaded count={len(articles)}")
    log_progress("start loading followed author articles")
    follow_articles = fetch_follow_author_articles(skip_authors=hot_author_skip_set(articles))
    log_progress(f"wechat follow loaded count={len(follow_articles)}")
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        today = digest_day().strftime("%Y-%m-%d")
        title = f"{WECHAT_DAILY_TITLE} {today}"
        sections = build_daily_lines(articles, follow_articles)
        output_path = RENDER_OUTPUT or os.path.join(APP_DATA_DIR, f"wechat_daily_render_only_{today}.png")
        render_daily_image(title, sections, output_path)
        log_progress(f"render only output={output_path}")
        return
    wait_until_send_time()
    log_progress("sending notifications")
    send_notifications(articles, follow_articles)
    log_progress("done")


if __name__ == "__main__":
    main()
