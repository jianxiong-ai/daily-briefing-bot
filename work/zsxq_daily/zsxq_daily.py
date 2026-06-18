#!/usr/bin/env python3
import html
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
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
try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ENV_PATH = os.environ.get(
    "ZSXQ_DAILY_ENV",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
)


def load_env_file(path):
    return runtime_load_env_file(path, override=False)


def parse_webhook_robots(value, primary_url="", primary_name="主机器人"):
    return runtime_parse_webhook_robots(value, primary_url, primary_name)


def selected_robots(robots):
    return runtime_selected_robots(robots, PUSH_TARGETS)


load_env_file(ENV_PATH)

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "").strip()
WECHAT_WORK_WEBHOOK = os.environ.get("WECHAT_WORK_WEBHOOK", "").strip()
PUSH_TARGETS = os.environ.get("PUSH_TARGETS", "all").strip().lower()
FEISHU_ROBOTS = parse_webhook_robots(os.environ.get("FEISHU_WEBHOOKS", ""), FEISHU_WEBHOOK, "主机器人")
WECHAT_WORK_ROBOTS = parse_webhook_robots(os.environ.get("WECHAT_WORK_WEBHOOKS", ""), WECHAT_WORK_WEBHOOK, "主机器人")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "").strip()
FEISHU_IMAGE_DAILY_ENABLED = os.environ.get("FEISHU_IMAGE_DAILY_ENABLED", "1").strip() != "0"
ZSXQ_COOKIE = os.environ.get("ZSXQ_COOKIE", "").strip()
ZSXQ_COOKIE_FILE = os.environ.get("ZSXQ_COOKIE_FILE", "").strip()
ZSXQ_GROUP_ID = os.environ.get("ZSXQ_GROUP_ID", "").strip()
ZSXQ_GROUP_NAME = os.environ.get("ZSXQ_GROUP_NAME", "").strip()
ZSXQ_API_BASE = os.environ.get("ZSXQ_API_BASE", "https://api.zsxq.com/v2").rstrip("/")
ZSXQ_FETCH_PAGES = int(os.environ.get("ZSXQ_FETCH_PAGES", "3"))
ZSXQ_PAGE_SIZE = int(os.environ.get("ZSXQ_PAGE_SIZE", "20"))
ZSXQ_DETAIL_WORKERS = int(os.environ.get("ZSXQ_DETAIL_WORKERS", "8"))
ZSXQ_ARTICLE_WORKERS = int(os.environ.get("ZSXQ_ARTICLE_WORKERS", str(ZSXQ_DETAIL_WORKERS)))
ZSXQ_INCLUDE_USER_IDS = {
    value.strip()
    for value in os.environ.get("ZSXQ_INCLUDE_USER_IDS", "").split(",")
    if value.strip()
}
ZSXQ_INCLUDE_USER_PRIORITY = [
    value.strip()
    for value in os.environ.get("ZSXQ_INCLUDE_USER_PRIORITY", "145548258122,844188812841442").split(",")
    if value.strip()
]
DIGEST_DATE = os.environ.get("DIGEST_DATE", "").strip()
SEND_AT_LOCAL = os.environ.get("SEND_AT_LOCAL", "").strip()
RENDER_ONLY = os.environ.get("RENDER_ONLY", "").strip() == "1"
RENDER_OUTPUT = os.environ.get("RENDER_OUTPUT", "").strip()
LOG_PROGRESS = os.environ.get("LOG_PROGRESS", "1").strip() != "0"
PRECOMPUTE_ONLY = os.environ.get("PRECOMPUTE_ONLY", "").strip() == "1"
NIGHTLY_SUPPLEMENT_ENABLED = os.environ.get("NIGHTLY_SUPPLEMENT_ENABLED", "1").strip() != "0"
NIGHTLY_SUPPLEMENT_CUTOFF = os.environ.get("NIGHTLY_SUPPLEMENT_CUTOFF", "22:00").strip()

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
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
LLM_RETRY_ATTEMPTS = int(os.environ.get("LLM_RETRY_ATTEMPTS", "2"))
LLM_RETRY_BACKOFF_SECONDS = float(os.environ.get("LLM_RETRY_BACKOFF_SECONDS", "2"))
LLM_BATCH_SIZE = int(os.environ.get("LLM_BATCH_SIZE", "8"))
LLM_BATCH_WORKERS = int(os.environ.get("LLM_BATCH_WORKERS", "4"))
LLM_MAX_CONCURRENT_REQUESTS = int(os.environ.get("LLM_MAX_CONCURRENT_REQUESTS", str(LLM_BATCH_WORKERS)))
APP_DATA_DIR = os.path.dirname(ENV_PATH) if ENV_PATH else os.getcwd()
LLM_CACHE_FILE = os.environ.get("LLM_CACHE_FILE", os.path.join(APP_DATA_DIR, "llm_summary_cache.jsonl"))
LLM_CACHE_TTL_SECONDS = int(os.environ.get("LLM_CACHE_TTL_SECONDS", "1800"))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "1").strip() != "0"
LLM_PROMPT_VERSION = os.environ.get("LLM_PROMPT_VERSION", "zsxq-v2").strip()
ZSXQ_TOPIC_NOTE_THRESHOLD = int(os.environ.get("ZSXQ_TOPIC_NOTE_THRESHOLD", "1400"))
ZSXQ_TOPIC_NOTE_LIMIT = int(os.environ.get("ZSXQ_TOPIC_NOTE_LIMIT", "700"))
ZSXQ_ESSENCE_DIRECT_LIMIT = int(os.environ.get("ZSXQ_ESSENCE_DIRECT_LIMIT", "8000"))
ZSXQ_ESSENCE_CHUNK_SIZE = int(os.environ.get("ZSXQ_ESSENCE_CHUNK_SIZE", "3500"))
ZSXQ_ESSENCE_CHUNK_WORKERS = int(os.environ.get("ZSXQ_ESSENCE_CHUNK_WORKERS", "4"))
ZSXQ_ESSENCE_SUMMARY_RATIO = float(os.environ.get("ZSXQ_ESSENCE_SUMMARY_RATIO", "0.04"))
ZSXQ_ESSENCE_SUMMARY_MIN_CHARS = int(os.environ.get("ZSXQ_ESSENCE_SUMMARY_MIN_CHARS", "350"))
ZSXQ_ESSENCE_SUMMARY_MAX_CHARS = int(os.environ.get("ZSXQ_ESSENCE_SUMMARY_MAX_CHARS", "1200"))
LLM_SEMAPHORE = BoundedSemaphore(max(1, LLM_MAX_CONCURRENT_REQUESTS))
DEEPSEEK_KEY_LOCK = Lock()
DEEPSEEK_KEY_INDEX = 0
LLM_CACHE = {}

if not ZSXQ_COOKIE and ZSXQ_COOKIE_FILE and os.path.exists(ZSXQ_COOKIE_FILE):
    with open(ZSXQ_COOKIE_FILE, "r", encoding="utf-8") as cookie_file:
        ZSXQ_COOKIE = cookie_file.read().strip()


def shanghai_now():
    return datetime.now(timezone(timedelta(hours=8)))


def log_progress(message):
    if LOG_PROGRESS:
        print(f"[{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


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


def digest_day():
    if DIGEST_DATE:
        return datetime.strptime(DIGEST_DATE, "%Y-%m-%d").date()
    return shanghai_now().date()


def parse_hhmm(value):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def shanghai_datetime(day, hhmm):
    parsed = parse_hhmm(hhmm) or (22, 0)
    return datetime(day.year, day.month, day.day, parsed[0], parsed[1], tzinfo=timezone(timedelta(hours=8)))


def previous_supplement_window():
    previous_day = digest_day() - timedelta(days=1)
    start = shanghai_datetime(previous_day, NIGHTLY_SUPPLEMENT_CUTOFF)
    end = datetime(previous_day.year, previous_day.month, previous_day.day, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))
    return start, end


def wait_until_send_time():
    wait_until_local_time(SEND_AT_LOCAL, shanghai_now, time.sleep, log_progress, strict=False)


def decode_attr_value(value):
    value = html.unescape(value or "")
    if "%" in value:
        value = urllib.parse.unquote(value)
    return value


def expand_zsxq_rich_text(value):
    value = html.unescape(value or "")

    def replace_e_tag(match):
        attrs = match.group(1) or ""
        title_match = re.search(r"""title\s*=\s*(['"])(.*?)\1""", attrs, flags=re.I | re.S)
        if title_match:
            return "\n" + decode_attr_value(title_match.group(2)) + "\n"
        return " "

    value = re.sub(r"<e\b([^>]*)/?>", replace_e_tag, value, flags=re.I | re.S)
    return value


def text_from_html(value):
    value = expand_zsxq_rich_text(value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def compact_text(value):
    value = text_from_html(value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def truncate(value, limit):
    value = (value or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "..."


def parse_zsxq_time(value):
    if not value:
        return None
    text = str(value).strip()
    text = re.sub(r"Z$", "+00:00", text)
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
    iso_text = text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(iso_text)
        if not parsed.tzinfo:
            parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
        return parsed.astimezone(timezone(timedelta(hours=8)))
    except ValueError:
        pass
    plain_text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(plain_text[:19], fmt).replace(tzinfo=timezone(timedelta(hours=8)))
        except ValueError:
            pass
    return None


def is_digest_day(value):
    parsed = parse_zsxq_time(value)
    return bool(parsed and parsed.date() == digest_day())


def in_time_window(value, start, end):
    parsed = parse_zsxq_time(value)
    return bool(parsed and start <= parsed <= end)


def zsxq_headers():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://wx.zsxq.com/dweb2/index/group/{ZSXQ_GROUP_ID}",
        "Origin": "https://wx.zsxq.com",
    }
    if ZSXQ_COOKIE:
        headers["Cookie"] = ZSXQ_COOKIE
    return headers


def fetch_json(url):
    req = urllib.request.Request(url, headers=zsxq_headers())
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url):
    req = urllib.request.Request(url, headers=zsxq_headers())
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="replace")


def zsxq_api_get(path, params=None):
    query = urllib.parse.urlencode(params or {})
    url = f"{ZSXQ_API_BASE}/{path.lstrip('/')}"
    if query:
        url += "?" + query
    data = fetch_json(url)
    if data.get("succeeded") is False:
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
        else:
            message = error
        raise RuntimeError(message or "zsxq api failed")
    return data


def zsxq_api_get_with_retry(path, params=None, retries=3):
    last_error = None
    for attempt in range(retries):
        try:
            return zsxq_api_get(path, params)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def topic_url(topic_id):
    return f"https://wx.zsxq.com/dweb2/index/topic_detail/{topic_id}"


def extract_topic_text(topic):
    candidates = []
    talk = topic.get("talk") or {}
    if talk.get("text"):
        candidates.append(talk.get("text"))
    question = topic.get("question") or {}
    answer = topic.get("answer") or {}
    if question.get("text"):
        candidates.append("提问：" + question.get("text"))
    if answer.get("text"):
        candidates.append("回答：" + answer.get("text"))
    task = topic.get("task") or {}
    if task.get("text"):
        candidates.append(task.get("text"))
    article = topic.get("article") or {}
    if article.get("title"):
        candidates.append(article.get("title"))
    if article.get("text"):
        candidates.append(article.get("text"))
    if topic.get("text"):
        candidates.append(topic.get("text"))
    return compact_text("\n".join(candidates))


def article_from_topic(topic):
    talk = topic.get("talk") or {}
    article = talk.get("article") or topic.get("article") or {}
    if not isinstance(article, dict):
        return {}
    return article


def article_url_from_topic(topic):
    article = article_from_topic(topic)
    return article.get("inline_article_url") or article.get("article_url") or ""


def article_title_from_topic(topic):
    return article_from_topic(topic).get("title") or ""


def text_from_article_html(value):
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<svg\b[^>]*>.*?</svg>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<head\b[^>]*>.*?</head>", " ", value, flags=re.I | re.S)
    return compact_text(value)


def extract_topic_tags(topic):
    tags = []
    for key in ("hashtags", "tags"):
        for tag in topic.get(key) or []:
            if isinstance(tag, dict):
                name = tag.get("name") or tag.get("tag") or tag.get("title")
            else:
                name = str(tag)
            name = compact_text(name)
            if name:
                tags.append(name.strip("#"))
    text = extract_topic_text(topic)
    for match in re.findall(r"#([^#\s]{1,30})#", text):
        tags.append(match.strip())
    return list(dict.fromkeys(tags))


def normalize_topic(topic):
    topic_id = str(topic.get("topic_id") or topic.get("topicId") or topic.get("id") or "")
    create_time = topic.get("create_time") or topic.get("created_at") or topic.get("createTime") or ""
    talk = topic.get("talk") or {}
    author = topic.get("owner") or topic.get("user") or topic.get("author") or talk.get("owner") or {}
    author_id = str(author.get("user_id") or author.get("id") or author.get("userId") or "")
    author_name = normalize_author_name(author.get("name") or author.get("nickname") or author.get("screen_name") or "未知成员")
    text = extract_topic_text(topic)
    article_url = article_url_from_topic(topic)
    article_title = article_title_from_topic(topic)
    tags = extract_topic_tags(topic)
    is_essence = bool(
        topic.get("digested")
        or topic.get("is_digest")
        or topic.get("is_essence")
        or topic.get("sticky")
        or topic.get("excellent")
    )
    return {
        "id": topic_id,
        "author_id": author_id,
        "author": author_name,
        "created_at": create_time,
        "text": text,
        "article_title": article_title,
        "article_url": article_url,
        "article_text": "",
        "tags": tags,
        "is_essence": is_essence,
        "type": topic.get("type") or topic.get("topic_type") or "",
        "link": article_url or (topic_url(topic_id) if topic_id else f"https://wx.zsxq.com/dweb2/index/group/{ZSXQ_GROUP_ID}"),
    }


def normalize_author_name(value):
    value = compact_text(value or "未知成员")
    value = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufe0e\ufe0f]", "", value)
    value = re.sub(r"[\ue000-\uf8ff]", "", value)
    if value in {"大户助理-囚", "大户助理-🉑"} or value.startswith("大户助理-"):
        return "大户助理-可"
    return value or "未知成员"


def order_essence_topics(topics):
    priority = {user_id: index for index, user_id in enumerate(ZSXQ_INCLUDE_USER_PRIORITY)}
    return [
        topic
        for _index, topic in sorted(
            enumerate(topics),
            key=lambda item: (
                priority.get(item[1].get("author_id"), 1000),
                item[0],
            ),
        )
    ]


def list_topics_page(scope="all", end_time=None, extra_params=None):
    params = {
        "scope": scope,
        "count": ZSXQ_PAGE_SIZE,
    }
    if extra_params:
        params.update(extra_params)
    if end_time:
        params["end_time"] = end_time
    try:
        data = zsxq_api_get_with_retry(f"groups/{ZSXQ_GROUP_ID}/topics", params)
    except RuntimeError:
        fallback_params = dict(params)
        fallback_params.pop("scope", None)
        data = zsxq_api_get_with_retry(f"groups/{ZSXQ_GROUP_ID}/topics", fallback_params)
    topics = data.get("resp_data", {}).get("topics", [])
    return topics


def get_topic_detail(topic_id):
    if not topic_id:
        return None
    try:
        data = zsxq_api_get_with_retry(f"topics/{topic_id}", retries=2)
        return data.get("resp_data", {}).get("topic") or data.get("resp_data")
    except Exception:
        return None


def dedupe_topics(topics):
    seen = set()
    result = []
    for topic in topics:
        key = topic["id"] or topic["text"]
        if not topic["text"] or key in seen:
            continue
        seen.add(key)
        result.append(topic)
    return result


def backfill_topic_details(topics):
    missing_text = [topic for topic in topics if topic["id"] and len(topic["text"]) < 20]
    if missing_text:
        log_progress(f"fetching topic details count={len(missing_text)}")
        with ThreadPoolExecutor(max_workers=max(1, ZSXQ_DETAIL_WORKERS)) as executor:
            future_map = {executor.submit(get_topic_detail, topic["id"]): topic for topic in missing_text}
            for future in as_completed(future_map):
                base = future_map[future]
                detail = future.result()
                if detail:
                    base.update(normalize_topic(detail))
    return topics


def fetch_article_text(topic):
    url = topic.get("article_url")
    if not url:
        return ""
    try:
        return text_from_article_html(fetch_text(url))
    except Exception as exc:
        log_progress(f"article fetch failed topic={topic.get('id')}: {exc}")
        return ""


def backfill_article_texts(topics):
    article_topics = [
        topic
        for topic in topics
        if topic.get("article_url") and not topic.get("article_text")
    ]
    if not article_topics:
        return topics
    log_progress(f"fetching article texts count={len(article_topics)}")
    with ThreadPoolExecutor(max_workers=max(1, ZSXQ_ARTICLE_WORKERS)) as executor:
        future_map = {executor.submit(fetch_article_text, topic): topic for topic in article_topics}
        for future in as_completed(future_map):
            topic = future_map[future]
            article_text = future.result()
            if article_text:
                topic["article_text"] = article_text
    return topics


def load_topics_by_scope(scope="all", extra_params=None, topic_filter=None, stop_before=None):
    if not ZSXQ_GROUP_ID:
        raise RuntimeError("ZSXQ_GROUP_ID is required")
    if not ZSXQ_COOKIE:
        raise RuntimeError("ZSXQ_COOKIE or ZSXQ_COOKIE_FILE is required")

    raw_topics = []
    end_time = None
    for page in range(max(1, ZSXQ_FETCH_PAGES)):
        try:
            page_topics = list_topics_page(scope=scope, end_time=end_time, extra_params=extra_params)
        except Exception as exc:
            if raw_topics:
                log_progress(f"topic pagination stopped scope={scope} page={page + 1}: {exc}")
                break
            raise
        if not page_topics:
            break
        raw_topics.extend(page_topics)
        last_time = page_topics[-1].get("create_time") or page_topics[-1].get("created_at")
        end_time = last_time
        if topic_filter:
            parsed_times = [
                parse_zsxq_time(topic.get("create_time") or topic.get("created_at") or "")
                for topic in page_topics
            ]
            if stop_before and parsed_times and all(parsed and parsed < stop_before for parsed in parsed_times):
                break
        elif all(not is_digest_day(topic.get("create_time") or topic.get("created_at") or "") for topic in page_topics):
            break

    today_topics = [
        normalize_topic(topic)
        for topic in raw_topics
        if (
            topic_filter(topic.get("create_time") or topic.get("created_at") or "")
            if topic_filter
            else is_digest_day(topic.get("create_time") or topic.get("created_at") or "")
        )
    ]
    return dedupe_topics(backfill_article_texts(backfill_topic_details(today_topics)))


def load_digest_data():
    fetch_status = {
        "all_error": "",
        "digests_error": "",
    }
    try:
        topics = load_topics_by_scope("all")
    except Exception as exc:
        fetch_status["all_error"] = str(exc) or exc.__class__.__name__
        log_progress(f"topics fetch failed scope=all: {exc}")
        topics = []

    try:
        digest_topics = load_topics_by_scope("digests")
    except Exception as exc:
        fetch_status["digests_error"] = str(exc) or exc.__class__.__name__
        log_progress(f"topics fetch failed scope=digests: {exc}")
        digest_topics = []

    included = []
    if ZSXQ_INCLUDE_USER_IDS:
        included = [topic for topic in topics if topic.get("author_id") in ZSXQ_INCLUDE_USER_IDS]
        log_progress(f"included user topics count={len(included)} users={len(ZSXQ_INCLUDE_USER_IDS)}")
    essence_topics = order_essence_topics(dedupe_topics(digest_topics + included))
    return topics, essence_topics, fetch_status


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


def next_deepseek_api_key():
    global DEEPSEEK_KEY_INDEX
    if not DEEPSEEK_API_KEYS:
        return ""
    with DEEPSEEK_KEY_LOCK:
        key = DEEPSEEK_API_KEYS[DEEPSEEK_KEY_INDEX % len(DEEPSEEK_API_KEYS)]
        DEEPSEEK_KEY_INDEX += 1
        return key


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
                    "你是中文知识社群日报编辑，擅长把星球内容按主题整理成高信息密度简报。"
                    "你必须只输出 JSON，不要输出解释文字。"
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
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return json.loads(text[start : end + 1])


def extract_summary_response(text):
    try:
        parsed = extract_json_object(text)
        value = parsed.get("summary", "")
        return value if isinstance(value, str) else ""
    except Exception:
        return compact_text(text)


def extract_topic_summary_response(text):
    try:
        parsed = extract_json_object(text)
        value = parsed.get("topics", [])
        return value if isinstance(value, list) else []
    except Exception:
        cleaned = compact_text(text)
        if not cleaned:
            return []
        lines = re.split(r"(?:\n|；|;)", cleaned)
        topics = []
        for line in lines:
            line = line.strip(" -")
            if not line:
                continue
            match = re.match(r"(.{2,24}?)[：:](.+)", line)
            if match:
                topics.append({"topic": match.group(1).strip(), "summary": match.group(2).strip()})
        if topics:
            return topics
        return [{"topic": "综合讨论", "summary": cleaned}]


def strip_topic_meta_prefix(text):
    text = compact_text(text)
    if len(text) < 300:
        return text
    if re.search(r"^.{0,120}(帖子被删|被删了|重发|换个内容发)", text, flags=re.S):
        start_match = re.search(r"(最近在写|以下是|案例\\d*拆解|第一步[：:])", text)
        if start_match and start_match.start() > 0 and len(text[start_match.start():]) > 200:
            return text[start_match.start():].strip()
    patterns = [
        r"^.{0,80}帖子被删了[，,。；;、 ]*",
        r"^.{0,80}被删了[，,。；;、 ]*",
        r"^.{0,80}重发[，,。；;、 ]*",
        r"^.{0,80}换个内容发[，,。；;、 ]*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", text, count=1)
        if cleaned != text and len(cleaned) > 200:
            return cleaned.strip()
    return text


def item_payload(topic, text_limit=1800, prefer_article=False, strip_meta=False):
    source_text = topic.get("text", "")
    if prefer_article and topic.get("article_text"):
        source_text = topic["article_text"]
    elif topic.get("article_text") and len(topic.get("text", "")) < 200:
        source_text = topic["article_text"]
    if strip_meta:
        source_text = strip_topic_meta_prefix(source_text)
    source_text = compact_text(source_text)
    return {
        "id": topic["id"],
        "author": topic["author"],
        "time": topic["created_at"],
        "tags": topic["tags"],
        "is_essence": topic["is_essence"],
        "title": topic.get("article_title") or "",
        "source": "article" if source_text == topic.get("article_text") else "topic",
        "text_chars": len(source_text),
        "text": truncate(source_text, text_limit),
    }


def essence_source_text(topic):
    return compact_text(topic.get("article_text") or topic.get("text") or "")


def clamp(value, low, high):
    return max(low, min(high, value))


def essence_summary_target(text_len):
    dynamic_min = min(
        ZSXQ_ESSENCE_SUMMARY_MIN_CHARS,
        max(180, int(text_len * 0.45)),
    )
    dynamic_max = min(
        ZSXQ_ESSENCE_SUMMARY_MAX_CHARS,
        max(dynamic_min, int(text_len * 0.75)),
    )
    target_chars = clamp(
        int(text_len * ZSXQ_ESSENCE_SUMMARY_RATIO),
        dynamic_min,
        dynamic_max,
    )
    target_sentences = clamp(round(target_chars / 90), 2, 14)
    min_chars = max(140, int(target_chars * 0.75))
    max_chars = int(target_chars * 1.25)
    return {
        "source_chars": text_len,
        "target_chars": target_chars,
        "min_chars": min_chars,
        "max_chars": max_chars,
        "target_sentences": target_sentences,
    }


def split_text_chunks(text, chunk_size):
    text = compact_text(text)
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n+|(?<=。)", text) if part.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            for index in range(0, len(paragraph), chunk_size):
                chunks.append(paragraph[index : index + chunk_size].strip())
            continue
        if current and len(current) + len(paragraph) + 1 > chunk_size:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = (current + "\n" + paragraph).strip() if current else paragraph
    if current:
        chunks.append(current.strip())
    return chunks


def fallback_item_summary(topic):
    text = essence_source_text(topic)
    target = essence_summary_target(len(text))
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
    summary = ""
    for sentence in sentences:
        if len(summary) >= target["target_chars"]:
            break
        summary += sentence
    return truncate(summary or text, target["max_chars"])


def fallback_chunk_summary(text):
    text = compact_text(text)
    if not text:
        return ""
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
    return truncate("".join(sentences[:6]) or text, 900)


def fallback_topic_summaries(topics):
    grouped = {}
    for topic in topics:
        tags = topic["tags"] or ["未标记话题"]
        for tag in tags[:3]:
            grouped.setdefault(tag, []).append(topic)
    summaries = []
    for tag, items in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)[:8]:
        sample = "；".join(fallback_item_summary(item) for item in items[:3])
        summaries.append({"topic": tag, "summary": f"共 {len(items)} 条相关内容。{sample}"})
    return summaries


def topic_summary_target(batch):
    source_chars = sum(len(essence_source_text(topic)) for topic in batch)
    target_chars = clamp(int(source_chars * 0.12), 180, 900)
    target_sentences = clamp(round(target_chars / 85), 2, 10)
    return {
        "source_chars": source_chars,
        "target_chars": target_chars,
        "min_chars": max(120, int(target_chars * 0.75)),
        "max_chars": int(target_chars * 1.35),
        "target_sentences": target_sentences,
    }


def fallback_topic_note(topic):
    text = strip_topic_meta_prefix(essence_source_text(topic))
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
    return truncate("".join(sentences[:8]) or text, ZSXQ_TOPIC_NOTE_LIMIT)


def summarize_topic_note(topic):
    text = strip_topic_meta_prefix(essence_source_text(topic))
    if len(text) < ZSXQ_TOPIC_NOTE_THRESHOLD:
        return text
    payload = {
        "id": topic["id"],
        "author": topic["author"],
        "time": topic["created_at"],
        "tags": topic["tags"],
        "text_chars": len(text),
        "text": truncate(text, 3600),
        "note_limit": ZSXQ_TOPIC_NOTE_LIMIT,
    }
    cached = get_cached_summary("topic_note", payload)
    if cached:
        return cached
    prompt = (
        "请把一条较长的知识星球内容压缩成供日报话题聚类使用的事实笔记。\n"
        "只输出 JSON：{\"note\":\"笔记\"}。\n"
        "要求：\n"
        "1. 保留这条内容的主体框架、关键步骤、例子、判断依据和结论。\n"
        "2. 如果开头是删帖/重发说明，只当背景，不要作为重点。\n"
        "3. 不要写成一句空泛概括；不要编造；不要省略号。\n"
        f"4. note 不超过 {ZSXQ_TOPIC_NOTE_LIMIT} 字。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        parsed = extract_json_object(llm_response_text_with_timeout(prompt))
        note = parsed.get("note", "")
        note = note if isinstance(note, str) else ""
    except Exception as exc:
        log_progress(f"topic note summary failed topic={topic.get('id')}: {exc}")
        return fallback_topic_note(topic)
    if not note:
        return fallback_topic_note(topic)
    set_cached_summary("topic_note", payload, note)
    return note


def summarize_essence_direct(topic):
    source_text = essence_source_text(topic)
    target = essence_summary_target(len(source_text))
    payload = {
        "summary_target": target,
        "item": item_payload(topic, text_limit=max(ZSXQ_ESSENCE_DIRECT_LIMIT, 1000), prefer_article=True),
    }
    cached = get_cached_summary("essence_direct", payload)
    if cached:
        return cached
    prompt = (
        "请为知识星球日报的“精选内容”摘要单条内容。\n"
        "只输出 JSON：{\"summary\":\"摘要\"}。\n"
        "要求：\n"
        "1. 摘要长度必须参考 summary_target：尽量接近 target_chars，通常不少于 min_chars，不超过 max_chars。\n"
        "2. 句数尽量接近 target_sentences；原文越长，摘要应越详细。\n"
        "3. 先说明这条内容在讲什么，再提炼关键事实、时间线、观点、方法或结论。\n"
        "4. 如果原文包含清单、步骤、数字、因果关系或判断依据，尽量保留这些信息。\n"
        "5. 不要过度压缩成一句话；不要按作者总结，不要省略号，不要编造输入中没有的信息。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    summary = extract_summary_response(llm_response_text_with_timeout(prompt))
    set_cached_summary("essence_direct", payload, summary)
    return summary


def summarize_essence_chunk(topic, chunk, chunk_index, chunk_count):
    source_text = essence_source_text(topic)
    final_target = essence_summary_target(len(source_text))
    chunk_target = essence_summary_target(len(chunk))
    payload = {
        "title": topic.get("article_title") or "",
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
        "final_summary_target": final_target,
        "chunk_summary_target": chunk_target,
        "text": chunk,
    }
    cached = get_cached_summary("essence_chunk", payload)
    if cached:
        return cached
    prompt = (
        "请摘要一篇知识星球精选长文的其中一个分块。\n"
        "只输出 JSON：{\"summary\":\"分块摘要\"}。\n"
        "要求：\n"
        "1. 分块摘要长度参考 chunk_summary_target，尽量接近 target_chars；全文最终摘要目标参考 final_summary_target。\n"
        "2. 尽量保留本分块中的关键事实、时间线、数字、政策/事件、因果关系、推理链和结论。\n"
        "3. 不要为了简短删掉重要限定条件、历史背景或作者判断依据。\n"
        "4. 不要补充本分块没有的信息；不要省略号。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    summary = extract_summary_response(llm_response_text_with_timeout(prompt))
    set_cached_summary("essence_chunk", payload, summary)
    return summary


def merge_essence_chunk_summaries(topic, chunk_summaries):
    target = essence_summary_target(len(essence_source_text(topic)))
    payload = {
        "title": topic.get("article_title") or "",
        "summary_target": target,
        "chunk_summaries": chunk_summaries,
    }
    cached = get_cached_summary("essence_merge", payload)
    if cached:
        return cached
    prompt = (
        "请把一篇知识星球精选长文的多个分块摘要整合为最终日报摘要。\n"
        "只输出 JSON：{\"summary\":\"最终摘要\"}。\n"
        "要求：\n"
        "1. 输出自然连贯的一条详细摘要，不要像简单拼接，也不要压缩成一句短评。\n"
        "2. 摘要长度必须参考 summary_target：尽量接近 target_chars，通常不少于 min_chars，不超过 max_chars。\n"
        "3. 句数尽量接近 target_sentences；原文越长，最终摘要应越详细。\n"
        "4. 必须覆盖全文主线、关键事实、重要日期和数字、政策或市场影响、作者推理链和结论。\n"
        "5. 合并重复信息，但不要删掉关键背景、限定条件、历史类比、监管条款、产业/市场影响等细节。\n"
        "6. 保留逻辑顺序；不要编造分块摘要之外的信息；不要省略号。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    summary = extract_summary_response(llm_response_text_with_timeout(prompt))
    set_cached_summary("essence_merge", payload, summary)
    return summary


def summarize_essence_topic(topic):
    text = essence_source_text(topic)
    if len(text) <= ZSXQ_ESSENCE_DIRECT_LIMIT:
        try:
            return summarize_essence_direct(topic)
        except Exception as exc:
            log_progress(f"essence direct summary failed topic={topic.get('id')}: {exc}")
            return fallback_item_summary(topic)

    chunks = split_text_chunks(text, max(1000, ZSXQ_ESSENCE_CHUNK_SIZE))
    log_progress(f"chunking essence topic={topic.get('id')} chars={len(text)} chunks={len(chunks)}")
    chunk_summaries = ["" for _ in chunks]
    with ThreadPoolExecutor(max_workers=max(1, ZSXQ_ESSENCE_CHUNK_WORKERS)) as executor:
        future_map = {
            executor.submit(summarize_essence_chunk, topic, chunk, index + 1, len(chunks)): index
            for index, chunk in enumerate(chunks)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            try:
                chunk_summaries[index] = future.result()
            except Exception as exc:
                log_progress(
                    f"essence chunk summary failed topic={topic.get('id')} chunk={index + 1}: {exc}"
                )
                chunk_summaries[index] = fallback_chunk_summary(chunks[index])

    chunk_summaries = [summary for summary in chunk_summaries if summary]
    if not chunk_summaries:
        return fallback_item_summary(topic)
    try:
        return merge_essence_chunk_summaries(topic, chunk_summaries)
    except Exception as exc:
        log_progress(f"merge essence chunks failed topic={topic.get('id')}: {exc}")
        return " ".join(chunk_summaries)


def summarize_essence_batch(batch):
    summaries = {}
    with ThreadPoolExecutor(max_workers=max(1, LLM_BATCH_WORKERS)) as executor:
        future_map = {executor.submit(summarize_essence_topic, topic): topic for topic in batch}
        for future in as_completed(future_map):
            topic = future_map[future]
            try:
                summaries[topic["id"]] = future.result()
            except Exception as exc:
                log_progress(f"essence topic summary failed topic={topic.get('id')}: {exc}")
                summaries[topic["id"]] = fallback_item_summary(topic)
    return summaries


def summarize_topic_batch(batch):
    topic_items = []
    for topic in batch:
        source_text = strip_topic_meta_prefix(essence_source_text(topic))
        if len(source_text) >= ZSXQ_TOPIC_NOTE_THRESHOLD:
            note = summarize_topic_note(topic)
            item = item_payload(topic, text_limit=ZSXQ_TOPIC_NOTE_LIMIT + 200, strip_meta=True)
            item["source"] = "topic_note"
            item["original_text_chars"] = len(source_text)
            item["text"] = note
            item["text_chars"] = len(note)
        else:
            item = item_payload(topic, text_limit=2200, strip_meta=True)
            item["original_text_chars"] = len(source_text)
        topic_items.append(item)
    payload = {
        "summary_target": topic_summary_target(batch),
        "items": topic_items,
    }
    cached = get_cached_summary("topic_batch", payload)
    if cached:
        return cached
    prompt = (
        "请把知识星球内容按话题聚类总结。\n"
        "只输出 JSON：{\"topics\":[{\"topic\":\"话题名\",\"summary\":\"总结\"}]}。\n"
        "要求：\n"
        "1. 不按人总结，按议题/问题/方法归类。\n"
        "2. 摘要长度参考 summary_target：输入越长、同话题材料越多，话题摘要也要更详细，尽量接近 target_chars。\n"
        "3. 每个话题通常 2-6 句；如果某条 item 的 original_text_chars 超过 1000，必须提炼其主体框架、关键步骤、案例和结论，不要压缩成一句。\n"
        "4. 如果开头出现“帖子被删、重发、换内容”等说明，只当发布背景，不要把它作为话题名或摘要重点；重点总结后面的实质内容。\n"
        "5. 不要只写“有人讨论/用户询问”，要写清楚具体问题、主要观点、给出的建议、可执行方法或结论。\n"
        "6. 优先使用输入里的 tags；没有 tags 时自行归纳短话题名。\n"
        "7. 不要出现省略号，不要编造输入中没有的信息。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    topics = extract_topic_summary_response(llm_response_text_with_timeout(prompt))
    set_cached_summary("topic_batch", payload, topics)
    return topics


def build_llm_digest(topics, essence_topics):
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return {}, []
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return {}, []

    batch_size = max(1, LLM_BATCH_SIZE)
    essence_batches = [essence_topics[index : index + batch_size] for index in range(0, len(essence_topics), batch_size)]
    topic_batches = [topics[index : index + batch_size] for index in range(0, len(topics), batch_size)]
    log_progress(
        f"calling llm provider={LLM_PROVIDER} model={DEEPSEEK_MODEL if LLM_PROVIDER == 'deepseek' else OPENAI_MODEL} "
        f"essence_batches={len(essence_batches)} topic_batches={len(topic_batches)}"
    )

    essence_summaries = {}
    topic_summaries = []

    if essence_batches:
        log_progress("calling essence llm batches first")
        with ThreadPoolExecutor(max_workers=max(1, LLM_BATCH_WORKERS)) as executor:
            future_map = {
                executor.submit(summarize_essence_batch, batch): batch
                for batch in essence_batches
            }
            for future in as_completed(future_map):
                batch = future_map[future]
                try:
                    essence_summaries.update(future.result())
                except Exception as exc:
                    log_progress(f"essence llm batch failed, fallback later: {exc}")
                    for topic in batch:
                        essence_summaries[topic["id"]] = fallback_item_summary(topic)

    if topic_batches:
        log_progress("calling topic llm batches after essence")
    with ThreadPoolExecutor(max_workers=max(1, LLM_BATCH_WORKERS)) as executor:
        future_map = {
            executor.submit(summarize_topic_batch, batch): batch
            for batch in topic_batches
        }
        for future in as_completed(future_map):
            batch = future_map[future]
            try:
                topic_summaries.extend(future.result())
            except Exception as exc:
                log_progress(f"topics llm batch failed, fallback later: {exc}")

    return essence_summaries, merge_topic_summaries(topic_summaries)


def merge_topic_summaries(topic_summaries):
    merged = {}
    for item in topic_summaries:
        if not isinstance(item, dict):
            continue
        topic = canonical_topic_title(item.get("topic", ""), item.get("summary", ""))
        summary = compact_text(item.get("summary", ""))
        if not topic or not summary:
            continue
        if topic in merged:
            merged[topic] += " " + summary
        else:
            merged[topic] = summary
    return [{"topic": topic, "summary": dedupe_summary_sentences(summary)} for topic, summary in merged.items()]


def dedupe_summary_sentences(value):
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", compact_text(value)) if part.strip()]
    if not sentences:
        return compact_text(value)
    kept = []
    seen = set()
    for sentence in sentences:
        key = re.sub(r"[，,。！？!?；;\s]+", "", sentence)
        if not key or key in seen:
            continue
        if any(key in old or old in key for old in seen if min(len(key), len(old)) >= 18):
            continue
        seen.add(key)
        kept.append(sentence)
    return " ".join(kept)


def canonical_topic_title(topic, summary=""):
    topic = compact_text(topic)
    summary_text = compact_text(summary)
    topic_text = topic
    if any(
        keyword in topic_text
        for keyword in ("每日新闻", "新闻简报", "每日早报", "每日简报", "每日资讯", "资讯简报", "每日日报", "日报简报", "60秒", "时事")
    ):
        return "每日新闻简报"
    if any(keyword in topic_text for keyword in ("拉尼娜", "厄尔尼诺", "天气", "气候")):
        return "拉尼娜现象及其气候影响" if "拉尼娜" in topic_text else "天气气候"
    if any(keyword in topic_text for keyword in ("宏观", "政策", "法规", "美联储", "央行", "财政", "关税", "国际", "地缘")):
        return topic
    if any(keyword in topic_text for keyword in ("星球", "合集", "索引", "问答汇总", "过往帖子")):
        return "星球多领域问答汇总"
    if any(keyword in topic_text for keyword in ("投资", "长期主义", "财富", "内心充盈")):
        return "投资心态与长期主义"
    if any(keyword in topic_text for keyword in ("触机", "占卜", "直觉", "玄学", "易经")):
        return "触机与占卜"
    if any(keyword in topic_text for keyword in ("川普", "特朗普")):
        return "对川普言论的反感"
    if any(keyword in topic_text for keyword in ("课程", "推荐课程", "星球课程")):
        return "课程推荐"
    if any(keyword in topic_text for keyword in ("信息疲劳", "断舍离", "头条", "信息过载")):
        return "信息疲劳与主动断舍离"
    if any(keyword in topic_text for keyword in ("个人成长", "工作决心", "职场", "工作", "决心", "成长")):
        return "个人成长与工作决心"
    if not topic and any(keyword in summary_text for keyword in ("每日新闻", "新闻简报", "每日早报", "每日简报", "每日资讯", "资讯简报", "60秒", "时事")):
        return "每日新闻简报"
    return topic


def topic_order_rank(item):
    text = f"{item.get('topic', '')} {item.get('summary', '')}"
    if any(keyword in text for keyword in ("每日新闻", "新闻简报", "每日早报", "每日简报", "每日资讯", "资讯简报", "60秒", "时事")):
        return 0
    if any(keyword in text for keyword in ("天气", "气候", "拉尼娜", "厄尔尼诺")):
        return 1
    if any(keyword in text for keyword in ("宏观", "经济", "政策", "法规", "央行", "美联储", "财政", "关税", "国际", "地缘", "社会", "公共", "教育", "高考")):
        return 2
    if any(keyword in text for keyword in ("投资", "市场", "股票", "基金", "ETF", "保险", "房产", "理财")):
        return 10
    if any(keyword in text for keyword in ("产业", "科技", "AI", "人工智能", "半导体", "能源", "汽车", "商业")):
        return 11
    if any(keyword in text for keyword in ("方法", "工具", "编程", "效率", "学习", "写作", "思维", "决策", "占卜", "触机", "易经", "认知")):
        return 20
    if any(keyword in text for keyword in ("课程", "推荐")):
        return 25
    if any(keyword in text for keyword in ("职场", "工作", "个人", "成长", "情绪", "健康", "家庭", "生活", "感受", "反感", "决心", "选择", "信息疲劳", "断舍离")):
        return 30
    if any(keyword in text for keyword in ("星球", "合集", "索引", "问答汇总", "过往帖子")):
        return 90
    return 20


def order_topic_summaries(topic_summaries):
    normalized = [
        {
            **item,
            "topic": canonical_topic_title(item.get("topic", ""), item.get("summary", "")),
        }
        for item in topic_summaries
    ]
    return sorted(
        normalized,
        key=lambda item: (
            topic_order_rank(item),
            item.get("topic", ""),
            -len(item.get("summary", "")),
        ),
    )


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


def status_message(value):
    value = compact_text(value)
    if not value:
        return ""
    if len(value) > 120:
        value = value[:119] + "..."
    return value


def non_essence_topics(topics, essence_topics):
    essence_ids = {topic.get("id") for topic in essence_topics if topic.get("id")}
    return [topic for topic in topics if topic.get("id") not in essence_ids]


def sentence_boundary_summary(value, limit=100):
    value = compact_text(value)
    if not value:
        return ""
    parts = re.split(r"(?<=[。！？!?])", value)
    summary = parts[0].strip() if parts else value
    if len(summary) <= limit:
        return summary if re.search(r"[。！？!?]$", summary) else summary + "。"
    cut = max(
        value.rfind("，", 0, limit),
        value.rfind("；", 0, limit),
        value.rfind("、", 0, limit),
        value.rfind(" ", 0, limit),
    )
    if cut < 24:
        cut = limit
    return value[:cut].rstrip("，；、:： ") + "。"


def short_topic_summary(topic, limit=120):
    title = compact_text(topic.get("article_title") or "")
    text = strip_topic_meta_prefix(essence_source_text(topic))
    if title:
        return sentence_boundary_summary(f"{title}：{text}", limit)
    return sentence_boundary_summary(text, limit)


def nightly_supplement_payload():
    start, end = previous_supplement_window()
    return {
        "date": digest_day().strftime("%Y-%m-%d"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "group_id": ZSXQ_GROUP_ID,
        "include_user_ids": sorted(ZSXQ_INCLUDE_USER_IDS),
    }


def build_nightly_supplement_lines_uncached():
    start, end = previous_supplement_window()
    topic_filter = lambda value: in_time_window(value, start, end)
    try:
        topics = load_topics_by_scope("all", topic_filter=topic_filter, stop_before=start)
    except Exception as exc:
        log_progress(f"nightly supplement topics fetch failed: {exc}")
        topics = []
    try:
        digest_topics = load_topics_by_scope("digests", topic_filter=topic_filter, stop_before=start)
    except Exception as exc:
        log_progress(f"nightly supplement digest fetch failed: {exc}")
        digest_topics = []

    included = [topic for topic in topics if topic.get("author_id") in ZSXQ_INCLUDE_USER_IDS]
    essence_topics = order_essence_topics(dedupe_topics(digest_topics + included))
    topic_inputs = non_essence_topics(topics, essence_topics)
    if not essence_topics and not topic_inputs:
        return []

    payload = {
        "version": "zsxq-nightly-v3",
        "date": digest_day().strftime("%Y-%m-%d"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "essence_items": [
            item_payload(topic, text_limit=1200, prefer_article=True, strip_meta=True)
            for topic in essence_topics[:5]
        ],
        "topic_items": [
            item_payload(topic, text_limit=1000, strip_meta=True)
            for topic in topic_inputs[:8]
        ],
    }
    if (LLM_PROVIDER == "deepseek" and DEEPSEEK_API_KEYS) or (LLM_PROVIDER != "deepseek" and OPENAI_API_KEY):
        try:
            prompt = (
                "请为知识星球日报生成“昨夜补遗”的简短摘要。\n"
                "只输出 JSON：{\"essence\":\"精选补遗或空字符串\",\"topics\":\"话题补遗或空字符串\"}。\n"
                "要求：\n"
                "1. 这是昨日推送后到 24:00 的新增内容补充，不要写成完整日报。\n"
                "2. essence 最多 2 句，说明昨夜新增精选/指定用户内容的核心观点；没有就空字符串。\n"
                "3. topics 最多 2 句，按议题合并新增话题，不要逐条贴原文，不要出现省略号。\n"
                "4. 文字要自然，避免截断感；只根据输入，不要编造。\n"
                "输入 JSON：\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            parsed = extract_json_object(llm_response_text_with_timeout(prompt))
            lines = [
                "**昨夜补遗**",
                f"范围：昨日推送后至 24:00（{start.strftime('%H:%M')}-{end.strftime('%H:%M')}）新增内容。",
            ]
            essence_summary = compact_text(parsed.get("essence", "")) if isinstance(parsed, dict) else ""
            topic_summary = compact_text(parsed.get("topics", "")) if isinstance(parsed, dict) else ""
            if essence_summary:
                lines.append("精选：" + markdown_escape(essence_summary))
            if topic_summary:
                lines.append("话题：" + markdown_escape(topic_summary))
            if len(lines) > 2:
                return lines
        except Exception as exc:
            log_progress(f"nightly supplement llm failed, fallback to rule summary: {exc}")

    lines = [
        "**昨夜补遗**",
        f"范围：昨日推送后至 24:00（{start.strftime('%H:%M')}-{end.strftime('%H:%M')}）新增内容。",
    ]
    if essence_topics:
        parts = [
            f"{topic.get('author') or '未知成员'}：{short_topic_summary(topic, 90)}"
            for topic in essence_topics[:3]
        ]
        more = f" 等 {len(essence_topics)} 条" if len(essence_topics) > 3 else ""
        lines.append("精选：" + markdown_escape("；".join(parts) + more))
    if topic_inputs:
        grouped = {}
        for topic in topic_inputs:
            tags = topic.get("tags") or ["综合讨论"]
            grouped.setdefault(tags[0], []).append(topic)
        parts = []
        for tag, items in list(grouped.items())[:4]:
            sample = short_topic_summary(items[0], 80)
            parts.append(f"{tag}：{sample}")
        more = f" 等 {len(topic_inputs)} 条" if len(topic_inputs) > 4 else ""
        lines.append("话题：" + markdown_escape("；".join(parts) + more))
    return lines


def build_nightly_supplement_lines():
    if not NIGHTLY_SUPPLEMENT_ENABLED:
        return []
    payload = nightly_supplement_payload()
    payload["version"] = "zsxq-nightly-v3"
    cached = get_cached_summary("nightly_supplement_v3", payload)
    if isinstance(cached, list):
        return cached
    try:
        lines = build_nightly_supplement_lines_uncached()
    except Exception as exc:
        log_progress(f"nightly supplement build failed: {exc}")
        return []
    if lines:
        set_cached_summary("nightly_supplement_v3", payload, lines)
    return lines


def build_daily_lines(topics, essence_topics, fetch_status=None):
    fetch_status = fetch_status or {}
    topic_inputs = non_essence_topics(topics, essence_topics)
    essence_summaries, topic_summaries = build_llm_digest(topic_inputs, essence_topics)
    if not topic_summaries:
        topic_summaries = fallback_topic_summaries(topic_inputs)

    supplement_lines = build_nightly_supplement_lines()
    essence_lines = []
    if supplement_lines:
        essence_lines.extend(supplement_lines)
        essence_lines.append("")
    essence_lines.append("**精选内容**")
    if fetch_status.get("digests_error") and not essence_topics:
        essence_lines.append(
            "精选内容获取异常，今日精选摘要不可用。"
            + f"原因：{markdown_escape(status_message(fetch_status.get('digests_error')))}"
        )
    elif fetch_status.get("digests_error"):
        essence_lines.append(
            "精选接口获取异常，以下仅包含已从全量内容中识别到的指定用户内容。"
            + f"原因：{markdown_escape(status_message(fetch_status.get('digests_error')))}"
        )
    if essence_topics:
        for index, topic in enumerate(essence_topics, start=1):
            summary = essence_summaries.get(topic["id"]) or fallback_item_summary(topic)
            author = topic.get("author") or "未知成员"
            essence_lines.append("")
            essence_lines.append(f"{index}. 作者：<font color=\"blue\">**{markdown_escape(author)}**</font>")
            essence_lines.append(markdown_escape(summary))
            essence_lines.append(f"原文：{markdown_link(str(index), topic['link'])}")
    else:
        if not fetch_status.get("digests_error"):
            essence_lines.append("今日无精选内容。")

    topic_lines = ["**话题总结**"]
    if fetch_status.get("all_error") and not topic_inputs:
        topic_lines.append(
            "全量话题获取异常，今日话题摘要不可用。"
            + f"原因：{markdown_escape(status_message(fetch_status.get('all_error')))}"
        )
    elif topic_summaries:
        for item in order_topic_summaries(topic_summaries)[:10]:
            topic_lines.append("")
            topic_lines.append(f"<font color=\"blue\">**{markdown_escape(item['topic'])}**</font>：{markdown_escape(item['summary'])}")
    else:
        topic_lines.append("今日无可归纳话题。")

    return essence_lines, topic_lines


def send_feishu_card(webhook, essence_lines, topic_lines, today, title_name):
    return push_send_feishu_card(webhook, f"知识星球日报 {title_name} {today}", [essence_lines, topic_lines])


def build_feishu_image_key(title, sections):
    if not FEISHU_IMAGE_DAILY_ENABLED:
        return ""
    if not (FEISHU_APP_ID and FEISHU_APP_SECRET):
        return ""
    if not (render_daily_image and upload_feishu_image and send_feishu_image):
        raise RuntimeError("daily image renderer unavailable")
    image_path = os.path.join(APP_DATA_DIR, f"zsxq_daily_{digest_day().strftime('%Y-%m-%d')}.png")
    render_daily_image(title, sections, image_path)
    log_progress(f"feishu image rendered path={image_path}")
    return upload_feishu_image(image_path, FEISHU_APP_ID, FEISHU_APP_SECRET)


def wechat_work_markdown(value):
    return push_wechat_work_markdown(value)


def truncate_utf8(value, max_bytes):
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    suffix = "\n\n内容较长，已截断。"
    keep = max(0, max_bytes - len(suffix.encode("utf-8")))
    return data[:keep].decode("utf-8", errors="ignore").rstrip() + suffix


def truncate_utf8_plain(value, max_bytes):
    return push_truncate_utf8_plain(value, max_bytes)


def wechat_line(value):
    value = wechat_work_markdown(value).strip()
    if not value or value.startswith("原文："):
        return ""
    value = value.replace("**", "")
    value = re.sub(r"\s+", " ", value)
    return truncate_utf8_plain(value, 700)


def build_wechat_content(title, sections, max_bytes=3900):
    return push_build_wechat_content(title, sections, max_bytes=max_bytes, skip_prefixes=("原文：",))


def send_wechat_work_markdown(webhook, title, sections):
    return push_send_wechat_work_markdown(webhook, title, sections, skip_prefixes=("原文：",))


def main():
    log_progress("start loading zsxq topics")
    topics, essence_topics, fetch_status = load_digest_data()
    status_notes = [key for key, value in fetch_status.items() if value]
    log_progress(
        f"topics loaded count={len(topics)} essence_count={len(essence_topics)} "
        f"fetch_status={','.join(status_notes) if status_notes else 'ok'}"
    )
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        today = digest_day().strftime("%Y-%m-%d")
        title_name = ZSXQ_GROUP_NAME or ZSXQ_GROUP_ID
        title = f"知识星球日报 {title_name} {today}"
        essence_lines, topic_lines = build_daily_lines(topics, essence_topics, fetch_status)
        output_path = RENDER_OUTPUT or os.path.join(APP_DATA_DIR, f"zsxq_daily_render_only_{today}.png")
        render_daily_image(title, [essence_lines, topic_lines], output_path)
        log_progress(f"render only output={output_path}")
        return
    if PRECOMPUTE_ONLY:
        log_progress("precompute only: building llm cache")
        build_llm_digest(non_essence_topics(topics, essence_topics), essence_topics)
        log_progress("precompute only: building nightly supplement cache")
        build_nightly_supplement_lines()
        log_progress("precompute done")
        return
    wait_until_send_time()
    log_progress("sending notifications")
    today = digest_day().strftime("%Y-%m-%d")
    title_name = ZSXQ_GROUP_NAME or ZSXQ_GROUP_ID
    title = f"知识星球日报 {title_name} {today}"
    essence_lines, topic_lines = build_daily_lines(topics, essence_topics, fetch_status)
    sections = [essence_lines, topic_lines]
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
                send_feishu_card(robot["url"], essence_lines, topic_lines, today, title_name)
            sent += 1
        except Exception as exc:
            errors.append(f"feishu/{robot['name']}: {exc}")
            log_progress(f"feishu send failed robot={robot['name']}: {exc}")
            if image_key:
                try:
                    send_feishu_card(robot["url"], essence_lines, topic_lines, today, title_name)
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
    log_progress("done")


if __name__ == "__main__":
    main()
