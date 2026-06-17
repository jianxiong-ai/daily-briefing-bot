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
import xml.etree.ElementTree as ET
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
try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ENV_PATH = os.environ.get(
    "WEIBO_DAILY_ENV",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
)


def load_env_file(path):
    return runtime_load_env_file(path, override=False)


def parse_webhook_robots(value, primary_url="", primary_name="主机器人"):
    return runtime_parse_webhook_robots(value, primary_url, primary_name)


def selected_robots(robots):
    return runtime_selected_robots(robots, PUSH_TARGETS)


load_env_file(ENV_PATH)

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
RSSHUB_BASE = os.environ.get("RSSHUB_BASE", "https://rsshub.app").rstrip("/")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "").strip()
WECHAT_WORK_WEBHOOK = os.environ.get("WECHAT_WORK_WEBHOOK", "").strip()
PUSH_TARGETS = os.environ.get("PUSH_TARGETS", "all").strip().lower()
FEISHU_ROBOTS = parse_webhook_robots(os.environ.get("FEISHU_WEBHOOKS", ""), FEISHU_WEBHOOK, "主机器人")
WECHAT_WORK_ROBOTS = parse_webhook_robots(os.environ.get("WECHAT_WORK_WEBHOOKS", ""), WECHAT_WORK_WEBHOOK, "主机器人")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "").strip()
FEISHU_IMAGE_DAILY_ENABLED = os.environ.get("FEISHU_IMAGE_DAILY_ENABLED", "1").strip() != "0"
WEIBO_COOKIE = os.environ.get("WEIBO_COOKIE", "").strip()
WEIBO_COOKIE_FILE = os.environ.get("WEIBO_COOKIE_FILE", "").strip()
DIGEST_DATE = os.environ.get("DIGEST_DATE", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2").strip()
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
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
SEND_AT_LOCAL = os.environ.get("SEND_AT_LOCAL", "").strip()
RENDER_ONLY = os.environ.get("RENDER_ONLY", "").strip() == "1"
RENDER_OUTPUT = os.environ.get("RENDER_OUTPUT", "").strip()
LOG_PROGRESS = os.environ.get("LOG_PROGRESS", "1").strip() != "0"
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "45"))
LLM_RETRY_ATTEMPTS = int(os.environ.get("LLM_RETRY_ATTEMPTS", "2"))
LLM_RETRY_BACKOFF_SECONDS = float(os.environ.get("LLM_RETRY_BACKOFF_SECONDS", "2"))
LLM_BATCH_SIZE = int(os.environ.get("LLM_BATCH_SIZE", "8"))
LLM_BATCH_WORKERS = int(os.environ.get("LLM_BATCH_WORKERS", "4"))
LLM_MAX_CONCURRENT_REQUESTS = int(os.environ.get("LLM_MAX_CONCURRENT_REQUESTS", str(LLM_BATCH_WORKERS)))
LLM_SEMAPHORE = BoundedSemaphore(max(1, LLM_MAX_CONCURRENT_REQUESTS))
DEEPSEEK_KEY_LOCK = Lock()
DEEPSEEK_KEY_INDEX = 0
APP_DATA_DIR = os.path.dirname(ENV_PATH) if ENV_PATH else os.getcwd()
LLM_CACHE_FILE = os.environ.get("LLM_CACHE_FILE", os.path.join(APP_DATA_DIR, "llm_summary_cache.jsonl"))
LLM_CACHE_TTL_SECONDS = int(os.environ.get("LLM_CACHE_TTL_SECONDS", "21600"))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "1").strip() != "0"
LLM_PROMPT_VERSION = os.environ.get("LLM_PROMPT_VERSION", "weibo-v1").strip()
PRECOMPUTE_ONLY = os.environ.get("PRECOMPUTE_ONLY", "").strip() == "1"
HOT_ARCHIVE_FILE = os.environ.get(
    "HOT_ARCHIVE_FILE",
    os.path.join(APP_DATA_DIR, "weibo_hot_history.jsonl"),
)
COLLECT_HOT_ONLY = os.environ.get("COLLECT_HOT_ONLY", "").strip() == "1"
HOT_COLLECT_START = os.environ.get("HOT_COLLECT_START", "08:00")
HOT_COLLECT_END = os.environ.get("HOT_COLLECT_END", "22:30")
HOT_ARCHIVE_RETENTION_DAYS = int(os.environ.get("HOT_ARCHIVE_RETENTION_DAYS", "14"))
HOT_OFFICIAL_BRIEF_ENABLED = os.environ.get("HOT_OFFICIAL_BRIEF_ENABLED", "1").strip() != "0"
HOT_OFFICIAL_BRIEF_QUERY = os.environ.get("HOT_OFFICIAL_BRIEF_QUERY", "热搜简报").strip()
HOT_OFFICIAL_BRIEF_LIMIT = int(os.environ.get("HOT_OFFICIAL_BRIEF_LIMIT", "5000"))
NIGHTLY_SUPPLEMENT_ENABLED = os.environ.get("NIGHTLY_SUPPLEMENT_ENABLED", "1").strip() != "0"
NIGHTLY_SUPPLEMENT_CUTOFF = os.environ.get("NIGHTLY_SUPPLEMENT_CUTOFF", "22:30").strip()
HOT_AD_KEYWORDS = tuple(
    value.strip()
    for value in os.environ.get(
        "HOT_AD_KEYWORDS",
        "五粮液,蒙牛,伊利,京东,淘宝,天猫,抖音商城,官方旗舰店,直播间,优惠券,补贴,大促,喊大咖,看球喝,来预测,发布会,赞助,美团外卖,带货,代言,联名,礼盒,新品,权益价,满配超值",
    ).split(",")
    if value.strip()
)
HOT_COMMERCIAL_KEYWORDS = tuple(
    value.strip()
    for value in os.environ.get(
        "HOT_COMMERCIAL_KEYWORDS",
        "Labubu,labubu,周边,销量暴涨,销量,潮玩,票房,文旅,消费,上市,开盘大涨,股价,市值,车型,汽车",
    ).split(",")
    if value.strip()
)


def log_progress(message):
    if LOG_PROGRESS:
        print(f"[{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)
UIDS = [
    "1763864272",  # 中国气象爱好者
    "1906286443",
    "1111681197",
    "1747780592",
    "1639529981",  # flypig
    "5167198527",
    "1192966660",
    "2403484123",  # 李大锤同学
    "1783497251",  # 李杰灵
    "1822894882",  # 极速拍档-小乔
    "5395738687",  # 陈抱一
    "1775948951",  # 硬哥
    "1749127163",  # 雷军
    "1728715190",  # 庄时利和
    "6154203482",  # 西门大妈
    "1404727022",  # 樊百乐
    "2886358364",  # Eva的科技生活
    "2032759640",  # 皇城根下刀笔吏
    "2423757750",  # 白衣山猫
    "1654184992",  # 小艾大叔
    "1679272984",  # 知食分子西门
    "7827771738",  # 睡前视频基地
    "1953896874",  # 弃医从文吃包包
    "1412758841",  # 猴大宝
    "1865990891",  # sunwear
    "1989660417",  # 胡锡进
    "1695038020",  # Mr厉害
    "6420726021",  # 食贫道
    "6529876887",  # 老师好我叫何同学
    "1044980795",  # 影视飓风MediaStorm
    "1401966845",  # 孟庆嘉
    "5992829552",  # 河森堡
    "1678105910",  # turbosun
    "5400369364",  # 闲人王昱珩
    "1195210033",  # 佟大为
    "1644492510",  # 孟非
    "1192504311",  # 黄觉
    "1234692083",  # 马天宇
    "6364943754",  # 所长林超
    "3163152700",  # 报姐
    "7461652315",  # 奥特快啊
    "6190030326",  # 盗月社食遇记
    "7483312068",  # Yooupi食途
    "6210709410",  # 地缘志
    "6344295434",  # 洛杉矶赢政
    "7810921185",  # 真探高文麒
    "1844937292",  # 大象放映室
]
UID_LABELS = {
    "1763864272": "中国气象爱好者",
    "1906286443": "钟文泽",
    "1111681197": "来去之间",
    "1747780592": "花叔",
    "1639529981": "flypig",
    "5167198527": "迪仔Dizzz",
    "1192966660": "韩路",
    "2403484123": "李大锤同学",
    "1783497251": "李杰灵",
    "1822894882": "极速拍档-小乔",
    "5395738687": "陈抱一",
    "1749127163": "雷军",
    "1728715190": "庄时利和",
    "6154203482": "西门大妈",
    "1404727022": "樊百乐",
    "2886358364": "Eva的科技生活",
    "2032759640": "皇城根下刀笔吏",
    "2423757750": "白衣山猫",
    "1654184992": "小艾大叔",
    "1679272984": "知食分子西门",
    "7827771738": "睡前视频基地",
    "1953896874": "弃医从文吃包包",
    "1412758841": "猴大宝",
    "1865990891": "sunwear",
    "1989660417": "胡锡进",
    "1695038020": "Mr厉害",
    "6420726021": "食贫道",
    "6529876887": "老师好我叫何同学",
    "1044980795": "影视飓风MediaStorm",
    "1401966845": "孟庆嘉",
    "5992829552": "河森堡",
    "1678105910": "turbosun",
    "5400369364": "闲人王昱珩",
    "1195210033": "佟大为",
    "1644492510": "孟非",
    "1192504311": "黄觉",
    "1234692083": "马天宇",
    "6364943754": "所长林超",
    "3163152700": "报姐",
    "7461652315": "奥特快啊",
    "6190030326": "盗月社食遇记",
    "7483312068": "Yooupi食途",
    "6210709410": "地缘志",
    "6344295434": "洛杉矶嬴政W",
    "7810921185": "真探高文麒",
    "1844937292": "大象放映室",
}
UNIQUE_UIDS = list(dict.fromkeys(UIDS))
EXCLUDED_AUTHORS = {"杰克涛", "谢欣哲", "蘸盐", "小特叔叔"}
EXCLUDED_REPOST_AUTHORS = {"谢欣哲", "蘸盐", "小特叔叔"}
MAX_WORKERS = int(os.environ.get("WEIBO_FETCH_WORKERS", "8"))

if not WEIBO_COOKIE_FILE:
    default_cookie_file = os.path.join(APP_DATA_DIR, "weibo.cookie")
    if os.path.exists(default_cookie_file):
        WEIBO_COOKIE_FILE = default_cookie_file

if not WEIBO_COOKIE and WEIBO_COOKIE_FILE:
    with open(WEIBO_COOKIE_FILE, "r", encoding="utf-8") as cookie_file:
        WEIBO_COOKIE = cookie_file.read().strip()


def shanghai_now():
    return datetime.now(timezone(timedelta(hours=8)))


def digest_day():
    if DIGEST_DATE:
        return datetime.strptime(DIGEST_DATE, "%Y-%m-%d").date()
    return shanghai_now().date()


def shanghai_datetime(day, hhmm):
    parsed = parse_hhmm(hhmm)
    if not parsed:
        parsed = (22, 30)
    return datetime(day.year, day.month, day.day, parsed[0], parsed[1], tzinfo=timezone(timedelta(hours=8)))


def previous_supplement_window():
    previous_day = digest_day() - timedelta(days=1)
    start = shanghai_datetime(previous_day, NIGHTLY_SUPPLEMENT_CUTOFF)
    end = datetime(previous_day.year, previous_day.month, previous_day.day, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))
    return start, end


LLM_CACHE = {}


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
    wait_until_local_time(SEND_AT_LOCAL, shanghai_now, time.sleep, log_progress, strict=False)


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DESKTOP_UA,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read()


def fetch_json(url, referer=None, cookie=None, desktop=False):
    user_agent = DESKTOP_UA if desktop else MOBILE_UA
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    if referer:
        headers["Referer"] = referer
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def text_from_html(value):
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_rss(data, limit=None):
    root = ET.fromstring(data)
    channel = root.find("channel")
    feed_title = text_from_html(channel.findtext("title") if channel is not None else "")
    items = []
    for item in root.findall(".//item"):
        title = text_from_html(item.findtext("title"))
        description = text_from_html(item.findtext("description"))
        link = (item.findtext("link") or "").strip()
        pub_date = text_from_html(item.findtext("pubDate"))
        items.append(
            {
                "feed_title": feed_title,
                "title": title,
                "description": description,
                "link": link,
                "pub_date": pub_date,
            }
        )
        if limit and len(items) >= limit:
            break
    return items


def rss_url(path):
    return f"{RSSHUB_BASE}/{path.lstrip('/')}"


def hot_entry_meta(entry):
    return {
        "is_ad": entry.get("is_ad", 0),
        "topic_ad": entry.get("topic_ad", 0),
        "icon_desc": entry.get("icon_desc", ""),
        "small_icon_desc": entry.get("small_icon_desc", ""),
        "label_name": entry.get("label_name", ""),
        "flag_desc": entry.get("flag_desc", ""),
        "category": entry.get("category", ""),
        "subject_label": entry.get("subject_label", ""),
        "channel_type": entry.get("channel_type", ""),
        "word_scheme": entry.get("word_scheme", ""),
    }


def hot_title_from_entry(entry):
    return entry.get("word") or entry.get("note") or entry.get("word_scheme") or ""


def load_hot_direct():
    try:
        data = fetch_json(
            "https://weibo.com/ajax/side/hotSearch",
            referer="https://weibo.com/hot/search",
        )
        realtime = data.get("data", {}).get("realtime", [])
    except Exception:
        data = fetch_json(
            "https://weibo.com/ajax/statuses/hot_band",
            referer="https://weibo.com/hot/search",
        )
        realtime = data.get("data", {}).get("band_list", [])
    items = []
    for entry in realtime[:20]:
        word = hot_title_from_entry(entry).strip("#")
        query = urllib.parse.quote(word)
        meta = hot_entry_meta(entry)
        items.append(
            {
                "feed_title": "微博热搜",
                "title": word,
                "description": entry.get("note", ""),
                "link": f"https://s.weibo.com/weibo?q={query}",
                "pub_date": "",
                "meta": meta,
            }
        )
    return items


def load_hot_items():
    try:
        return load_hot_direct()
    except Exception:
        return parse_rss(fetch(rss_url("/weibo/search/hot")), limit=20)


def parse_hhmm(value):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def within_hot_collect_window():
    now = shanghai_now()
    start = parse_hhmm(HOT_COLLECT_START)
    end = parse_hhmm(HOT_COLLECT_END)
    if not start or not end:
        return True
    current = now.hour * 60 + now.minute
    start_minutes = start[0] * 60 + start[1]
    end_minutes = end[0] * 60 + end[1]
    return start_minutes <= current <= end_minutes


def collect_hot_snapshot():
    if not within_hot_collect_window():
        log_progress("hot collect skipped outside collection window")
        return
    items = load_hot_items()
    os.makedirs(os.path.dirname(HOT_ARCHIVE_FILE), exist_ok=True)
    record = {
        "date": shanghai_now().strftime("%Y-%m-%d"),
        "ts": shanghai_now().isoformat(),
        "items": [
            {
                "rank": index,
                "title": item["title"],
                "link": item.get("link", ""),
                "description": item.get("description", ""),
                "meta": item.get("meta", {}),
            }
            for index, item in enumerate(items, start=1)
        ],
    }
    with open(HOT_ARCHIVE_FILE, "a", encoding="utf-8") as archive:
        archive.write(json.dumps(record, ensure_ascii=False) + "\n")
    prune_hot_archive()
    log_progress(f"hot snapshot collected items={len(items)} file={HOT_ARCHIVE_FILE}")


def prune_hot_archive():
    if HOT_ARCHIVE_RETENTION_DAYS <= 0 or not os.path.exists(HOT_ARCHIVE_FILE):
        return
    cutoff = digest_day() - timedelta(days=HOT_ARCHIVE_RETENTION_DAYS - 1)
    kept = []
    with open(HOT_ARCHIVE_FILE, "r", encoding="utf-8") as archive:
        for line in archive:
            try:
                record = json.loads(line)
                record_date = datetime.strptime(record.get("date", ""), "%Y-%m-%d").date()
            except Exception:
                continue
            if record_date >= cutoff:
                kept.append(line)
    tmp_file = HOT_ARCHIVE_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as archive:
        archive.writelines(kept)
    os.replace(tmp_file, HOT_ARCHIVE_FILE)


def hot_item_meta(item):
    meta = item.get("meta") or {}
    return meta if isinstance(meta, dict) else {}


def is_hard_ad_hot_item(item):
    title = (item.get("title") or "").strip()
    meta = hot_item_meta(item)
    icon_desc = str(meta.get("icon_desc") or "")
    small_icon_desc = str(meta.get("small_icon_desc") or "")
    if str(meta.get("topic_ad") or "") == "1":
        return True
    if small_icon_desc == "商" or icon_desc in {"商", "广告"}:
        return True
    if str(meta.get("is_ad") or "") == "1" and icon_desc not in {"辟谣", "公益", "政务"}:
        if icon_desc in {"官宣", "荐"} or small_icon_desc in {"商", "荐"}:
            return True
    return any(keyword in title for keyword in HOT_AD_KEYWORDS)


def is_commercial_hot_item(item):
    title = (item.get("title") or "").strip()
    meta = hot_item_meta(item)
    text = " ".join(
        str(meta.get(key) or "")
        for key in ("category", "subject_label", "flag_desc", "channel_type", "icon_desc", "small_icon_desc")
    )
    if any(keyword in title for keyword in HOT_COMMERCIAL_KEYWORDS):
        return True
    return any(keyword in text for keyword in ("汽车", "财经", "旅游", "消费", "电商", "商业"))


def hot_item_weight(item):
    return 0.45 if is_commercial_hot_item(item) else 1.0


def aggregate_hot_items(current_items):
    target_date = digest_day().strftime("%Y-%m-%d")
    scores = {}

    def add_item(item, rank):
        title = item.get("title", "").strip()
        if not title or is_hard_ad_hot_item(item):
            return
        weight = hot_item_weight(item)
        entry = scores.setdefault(
            title,
            {
                "feed_title": "微博热搜",
                "title": title,
                "description": item.get("description", ""),
                "link": item.get("link", ""),
                "pub_date": "",
                "seen": 0,
                "weighted_seen": 0.0,
                "best_rank": rank,
                "rank_sum": 0,
                "weighted_rank_sum": 0.0,
                "commercial_count": 0,
            },
        )
        entry["seen"] += 1
        entry["weighted_seen"] += weight
        entry["best_rank"] = min(entry["best_rank"], rank)
        entry["rank_sum"] += rank
        entry["weighted_rank_sum"] += rank * weight
        if weight < 1:
            entry["commercial_count"] += 1
        if not entry.get("link") and item.get("link"):
            entry["link"] = item["link"]

    for index, item in enumerate(current_items, start=1):
        add_item(item, index)

    if os.path.exists(HOT_ARCHIVE_FILE):
        with open(HOT_ARCHIVE_FILE, "r", encoding="utf-8") as archive:
            for line in archive:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("date") != target_date:
                    continue
                for item in record.get("items", []):
                    add_item(item, int(item.get("rank") or 50))

    ranked = rank_hot_events(scores.values())
    result = []
    for item in ranked[:20]:
        result.append(
            {
                "feed_title": "微博热搜",
                "title": item["title"],
                "description": item.get("description", ""),
                "link": item.get("link", ""),
                "pub_date": "",
                "seen": item.get("seen", 0),
                "weighted_seen": item.get("weighted_seen", item.get("seen", 0)),
                "best_rank": item.get("best_rank", 50),
                "rank_sum": item.get("rank_sum", 0),
                "commercial_count": item.get("commercial_count", 0),
                "hot_score": item.get("hot_score", 0),
                "related_titles": item.get("related_titles", []),
                "commercial_related_titles": item.get("commercial_related_titles", []),
            }
        )
    log_progress(f"hot aggregate events={len(result)} titles={len(scores)} samples_file={HOT_ARCHIVE_FILE}")
    return result or current_items


def aggregate_hot_items_for_records(records):
    scores = {}

    def add_item(item, rank):
        title = item.get("title", "").strip()
        if not title or is_hard_ad_hot_item(item):
            return
        weight = hot_item_weight(item)
        entry = scores.setdefault(
            title,
            {
                "feed_title": "微博热搜",
                "title": title,
                "description": item.get("description", ""),
                "link": item.get("link", ""),
                "pub_date": "",
                "seen": 0,
                "weighted_seen": 0.0,
                "best_rank": rank,
                "rank_sum": 0,
                "weighted_rank_sum": 0.0,
                "commercial_count": 0,
            },
        )
        entry["seen"] += 1
        entry["weighted_seen"] += weight
        entry["best_rank"] = min(entry["best_rank"], rank)
        entry["rank_sum"] += rank
        entry["weighted_rank_sum"] += rank * weight
        if weight < 1:
            entry["commercial_count"] += 1
        if not entry.get("link") and item.get("link"):
            entry["link"] = item["link"]

    for record in records:
        for item in record.get("items", []):
            add_item(item, int(item.get("rank") or 50))
    return rank_hot_events(scores.values()) if scores else []


def load_hot_archive_records_for_day(day):
    if not os.path.exists(HOT_ARCHIVE_FILE):
        return []
    target_date = day.strftime("%Y-%m-%d")
    records = []
    with open(HOT_ARCHIVE_FILE, "r", encoding="utf-8") as archive:
        for line in archive:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("date") == target_date:
                records.append(record)
    return records


def parse_archive_ts(record):
    try:
        parsed = datetime.fromisoformat((record.get("ts") or "").replace("Z", "+00:00"))
        if not parsed.tzinfo:
            parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
        return parsed.astimezone(timezone(timedelta(hours=8)))
    except Exception:
        return None


def nightly_hot_supplement_items(start, end, limit=5):
    records = load_hot_archive_records_for_day(start.date())
    before_records = []
    after_records = []
    for record in records:
        ts = parse_archive_ts(record)
        if not ts:
            continue
        if ts < start:
            before_records.append(record)
        elif start <= ts <= end:
            after_records.append(record)
    before_titles = {
        item.get("title", "").strip()
        for record in before_records
        for item in record.get("items", [])
        if item.get("title")
    }
    after_events = aggregate_hot_items_for_records(after_records)
    result = []
    for event in after_events:
        titles = [event.get("title", "")] + (event.get("related_titles") or [])
        if any(title and title not in before_titles for title in titles):
            result.append(event)
        if len(result) >= limit:
            break
    return result


def clean_official_hot_brief_text(value):
    value = value or ""
    value = re.sub(r"<think>[\s\S]*?</think>", " ", value)
    value = re.sub(r"```wbCustomBlock[\s\S]*?```", " ", value)
    value = re.sub(r"<media-block>[\s\S]*?</media-block>", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return truncate(value.strip(), HOT_OFFICIAL_BRIEF_LIMIT)


def load_official_hot_brief():
    if not HOT_OFFICIAL_BRIEF_ENABLED or not WEIBO_COOKIE or not HOT_OFFICIAL_BRIEF_QUERY:
        return {}
    request_time = str(int(time.time() * 1000))
    params = {
        "query": HOT_OFFICIAL_BRIEF_QUERY,
        "content_type": "loop",
        "request_id": str(int(time.time())),
        "request_time": "0",
        "search_source": "default_init",
        "sid": "pc_search",
        "vstyle": "1",
        "cot": "1",
        "speed": "full",
        "loop_num": "1",
    }
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        "https://ai.s.weibo.com/api/wis/show.json",
        data=data,
        headers={
            "User-Agent": DESKTOP_UA,
            "Referer": "https://s.weibo.com/aisearch?q=" + urllib.parse.quote(HOT_OFFICIAL_BRIEF_QUERY),
            "Origin": "https://s.weibo.com",
            "Cookie": WEIBO_COOKIE,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log_progress(f"official hot brief fetch failed: {exc}")
        return {}
    text = clean_official_hot_brief_text(body.get("msg", ""))
    if not text:
        log_progress("official hot brief empty")
        return {}
    return {
        "query": HOT_OFFICIAL_BRIEF_QUERY,
        "version": body.get("version", ""),
        "status": body.get("status", ""),
        "current_time": body.get("current_time", request_time),
        "text": text,
    }


def context_snippet(text, needle, radius=90):
    if not text or not needle:
        return ""
    index = text.find(needle)
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    snippet = text[start:end].strip()
    snippet = re.sub(r"^[,，。；;、\s]+|[,，。；;、\s]+$", "", snippet)
    return snippet


def hot_event_text_candidates(item):
    titles = [item.get("title", "")]
    titles.extend(item.get("related_titles") or [])
    candidates = []
    seen = set()
    for title in titles:
        title = compact_text(title)
        if not title:
            continue
        variants = [title]
        variants.extend(re.findall(r"《([^》]{2,30})》", title))
        variants.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{3,20}", title))
        for variant in variants:
            variant = variant.strip()
            if len(variant) < 2 or variant in seen:
                continue
            seen.add(variant)
            candidates.append(variant)
    return candidates


def official_context_for_event(item, official_text):
    for candidate in hot_event_text_candidates(item):
        snippet = context_snippet(official_text, candidate)
        if snippet:
            return snippet
    event_tokens = hot_title_tokens(item.get("title", ""))
    if not event_tokens:
        return ""
    sentences = re.split(r"(?<=[。！？；;])\s*", official_text)
    best = ""
    best_overlap = 0
    for sentence in sentences:
        if not sentence:
            continue
        overlap = len(event_tokens & hot_title_tokens(sentence))
        if overlap > best_overlap:
            best_overlap = overlap
            best = sentence
    return truncate(best, 220) if best_overlap >= 3 else ""


def extract_official_event_candidates(official_text):
    if not official_text:
        return []
    candidates = []
    patterns = [
        r"\*\*([^*]{2,36})\*\*",
        r"《([^》]{2,30})》",
        r"(?:^|\s)(?:\d{1,2})[.、]\s*([^：:，。；;]{2,36})",
        r"“([^”]{2,30})”",
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, official_text))

    result = []
    seen = set()
    for raw_title in candidates:
        title = compact_text(raw_title)
        title = re.sub(r"^(话题|事件|热搜|更新)[:：]\s*", "", title).strip()
        book_titles = re.findall(r"《([^》]{2,20})》", title)
        if book_titles:
            title = book_titles[0] + ("开播" if "开播" in title and not book_titles[0].endswith("开播") else "")
        if len(title) < 2 or len(title) > 36:
            continue
        if any(keyword in title for keyword in HOT_AD_KEYWORDS):
            continue
        key = normalize_hot_title(title)
        if not key or key in seen:
            continue
        seen.add(key)
        snippet = context_snippet(official_text, title) or truncate(official_text, 220)
        result.append({"event": title, "official_context": truncate(snippet, 260)})
        if len(result) >= 12:
            break
    return result


def event_matches_official_candidate(item, candidate):
    official_tokens = hot_title_tokens(candidate.get("event", ""))
    if not official_tokens:
        return False
    for title in hot_event_text_candidates(item):
        title_tokens = hot_title_tokens(title)
        if not title_tokens:
            continue
        overlap = len(title_tokens & official_tokens)
        union = len(title_tokens | official_tokens)
        if normalize_hot_title(title) in normalize_hot_title(candidate.get("event", "")):
            return True
        if normalize_hot_title(candidate.get("event", "")) in normalize_hot_title(title):
            return True
        if overlap >= 2 and union and overlap / union >= 0.28:
            return True
    return False


def official_chunk_matches_hot_item(chunk, item):
    chunk_key = normalize_hot_title(chunk)
    chunk_tokens = hot_title_tokens(chunk)
    if not chunk_tokens:
        return False
    for title in hot_event_text_candidates(item):
        title_key = normalize_hot_title(title)
        title_tokens = hot_title_tokens(title)
        if not title_key or not title_tokens:
            continue
        if title_key in chunk_key or chunk_key in title_key:
            return True
        overlap = len(title_tokens & chunk_tokens)
        union = len(title_tokens | chunk_tokens)
        if overlap >= 3 and union and overlap / union >= 0.18:
            return True
    return False


def official_unmatched_context(official_text, hot_items):
    if not official_text:
        return ""
    prepared = re.sub(r"\s*(#{2,3}\s*)", r"\n\1", official_text)
    chunks = re.split(r"\n+|(?<=[。！？；;])\s+", prepared)
    kept = []
    seen = set()
    for chunk in chunks:
        chunk = compact_text(chunk)
        chunk = re.sub(r"^#{2,3}\s*", "", chunk).strip()
        if len(chunk) < 24:
            continue
        if any(keyword in chunk for keyword in HOT_AD_KEYWORDS):
            continue
        if any(official_chunk_matches_hot_item(chunk, item) for item in hot_items):
            continue
        key = normalize_hot_title(chunk[:80])
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(chunk)
        if sum(len(item) for item in kept) >= 1800:
            break
    return truncate(" ".join(kept), 1800)


def merge_hot_events_with_official_brief(hot_items, official_brief):
    official_text = (official_brief or {}).get("text", "")
    primary_events = []
    for item in hot_items:
        official_context = official_context_for_event(item, official_text)
        primary_events.append(
            {
                "event": item["title"],
                "source": "self_collected+official_brief" if official_context else "self_collected",
                "hot_score": item.get("hot_score", 0),
                "seen": item.get("seen", 0),
                "weighted_seen": item.get("weighted_seen", item.get("seen", 0)),
                "best_rank": item.get("best_rank", 50),
                "commercial_count": item.get("commercial_count", 0),
                "commercial_signal": bool(item.get("commercial_count", 0)),
                "related_titles": item.get("related_titles", []),
                "commercial_related_titles": item.get("commercial_related_titles", []),
                "official_context": official_context,
            }
        )

    return {
        "official_brief_meta": {
            "query": (official_brief or {}).get("query", ""),
            "version": (official_brief or {}).get("version", ""),
            "status": (official_brief or {}).get("status", ""),
        },
        "primary_events": primary_events,
        "official_unmatched_context": official_unmatched_context(official_text, hot_items),
    }


HOT_EVENT_RULES = [
    ("world_cup", "2026美加墨世界杯", ("世界杯", "美加墨", "梅西第6次征战")),
    ("moli_live", "莫离开播", ("莫离",)),
]


def normalize_hot_title(value):
    value = compact_text(value)
    value = re.sub(r"[#【】\\[\\]（）()《》“”\"'·,，。.!！?？:：;；\\s-]+", "", value)
    return value


def hot_event_rule(title):
    for key, label, keywords in HOT_EVENT_RULES:
        if any(keyword in title for keyword in keywords):
            return key, label
    return "", ""


def hot_title_tokens(title):
    value = normalize_hot_title(title)
    tokens = set()
    for length in (4, 3):
        for index in range(0, max(0, len(value) - length + 1)):
            token = value[index : index + length]
            if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", token):
                tokens.add(token)
    return tokens


def similar_hot_event(title, clusters):
    tokens = hot_title_tokens(title)
    if not tokens:
        return None
    best_key = None
    best_score = 0
    for key, cluster in clusters.items():
        cluster_tokens = cluster.get("tokens") or set()
        if not cluster_tokens:
            continue
        overlap = len(tokens & cluster_tokens)
        union = len(tokens | cluster_tokens)
        score = overlap / union if union else 0
        if overlap >= 3 and score > best_score:
            best_key = key
            best_score = score
    if best_score >= 0.22:
        return best_key
    return None


def representative_hot_title(items, preferred_label=""):
    if preferred_label:
        return preferred_label
    ranked = sorted(items, key=lambda item: (-item["seen"], item["best_rank"], item["rank_sum"], len(item["title"])))
    return ranked[0]["title"] if ranked else ""


def rank_hot_events(title_items):
    clusters = {}
    for item in sorted(title_items, key=lambda item: (-item["seen"], item["best_rank"], item["rank_sum"])):
        title = item["title"]
        rule_key, rule_label = hot_event_rule(title)
        key = rule_key or similar_hot_event(title, clusters) or f"title:{normalize_hot_title(title)}"
        cluster = clusters.setdefault(
            key,
            {
                "items": [],
                "tokens": set(),
                "label": rule_label,
            },
        )
        if rule_label and not cluster.get("label"):
            cluster["label"] = rule_label
        cluster["items"].append(item)
        cluster["tokens"].update(hot_title_tokens(title))

    events = []
    for cluster in clusters.values():
        items = cluster["items"]
        related = sorted(items, key=lambda item: (-item["seen"], item["best_rank"], item["rank_sum"]))
        seen = sum(item["seen"] for item in items)
        weighted_seen = sum(float(item.get("weighted_seen", item.get("seen", 0))) for item in items)
        best_rank = min(item["best_rank"] for item in items)
        rank_sum = sum(item["rank_sum"] for item in items)
        weighted_rank_sum = sum(float(item.get("weighted_rank_sum", item.get("rank_sum", 0))) for item in items)
        commercial_count = sum(int(item.get("commercial_count", 0)) for item in items)
        avg_rank = weighted_rank_sum / weighted_seen if weighted_seen else (rank_sum / seen if seen else 50)
        score = weighted_seen * 4 + max(0, 21 - best_rank) * 3 + max(0, 21 - avg_rank)
        if commercial_count and commercial_count == seen:
            score *= 0.55
        title = representative_hot_title(items, cluster.get("label", ""))
        leader = related[0]
        events.append(
            {
                "feed_title": "微博热搜",
                "title": title,
                "description": leader.get("description", ""),
                "link": leader.get("link", ""),
                "pub_date": "",
                "seen": seen,
                "weighted_seen": round(weighted_seen, 2),
                "best_rank": best_rank,
                "rank_sum": rank_sum,
                "commercial_count": commercial_count,
                "hot_score": round(score, 2),
                "related_titles": [item["title"] for item in related[:8] if item["title"] != title],
                "commercial_related_titles": [
                    item["title"]
                    for item in related[:8]
                    if item["title"] != title and int(item.get("commercial_count", 0)) > 0
                ],
            }
        )
    return sorted(events, key=lambda item: (-item["hot_score"], -item["seen"], item["best_rank"], item["rank_sum"]))


def is_today_text(created_at):
    if not created_at:
        return False
    target = digest_day()
    if created_at.startswith("今天") or "分钟前" in created_at or "刚刚" in created_at:
        return target == shanghai_now().date()
    month_day = f"{target.month:02d}-{target.day:02d}"
    loose_month_day = f"{target.month}-{target.day}"
    if created_at.startswith(month_day) or created_at.startswith(loose_month_day):
        return True
    return target.strftime("%b %d") in created_at or target.strftime("%b  %d") in created_at


def parse_weibo_time(created_at, target_date=None):
    if not created_at:
        return None
    target = target_date or digest_day()
    text = str(created_at).strip()
    now = shanghai_now()
    if text.startswith("刚刚"):
        return now if target == now.date() else None
    match = re.search(r"(\d+)\s*分钟前", text)
    if match:
        return now - timedelta(minutes=int(match.group(1))) if target == now.date() else None
    match = re.search(r"今天\s*(\d{1,2}):(\d{2})", text)
    if match and target == now.date():
        return datetime(target.year, target.month, target.day, int(match.group(1)), int(match.group(2)), tzinfo=timezone(timedelta(hours=8)))
    match = re.search(r"(?:(\d{4})[-/])?(\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})", text)
    if match:
        year = int(match.group(1) or target.year)
        return datetime(year, int(match.group(2)), int(match.group(3)), int(match.group(4)), int(match.group(5)), tzinfo=timezone(timedelta(hours=8)))
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%a %b %d %H:%M:%S %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            if not parsed.tzinfo:
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
            return parsed.astimezone(timezone(timedelta(hours=8)))
        except ValueError:
            pass
    return None


def in_time_window(created_at, start, end):
    parsed = parse_weibo_time(created_at, start.date())
    return bool(parsed and start <= parsed <= end)


def load_user_direct(uid, item_filter=None, include_empty=True):
    try:
        data = fetch_json(
            f"https://weibo.com/ajax/statuses/mymblog?uid={uid}&page=1&feature=0",
            referer=f"https://weibo.com/u/{uid}",
            cookie=WEIBO_COOKIE or None,
            desktop=True,
        )
        items = parse_desktop_user_items(uid, data, item_filter=item_filter, include_empty=include_empty)
        if items:
            return items
    except Exception:
        pass

    params = urllib.parse.urlencode(
        {
            "type": "uid",
            "value": uid,
            "containerid": f"107603{uid}",
            "page": "1",
        }
    )
    url = f"https://m.weibo.cn/api/container/getIndex?{params}"
    data = fetch_json(url, referer=f"https://weibo.com/u/{uid}", cookie=WEIBO_COOKIE or None)
    cards = data.get("data", {}).get("cards", [])
    items = []
    for card in cards:
        mblog = card.get("mblog") or {}
        if not mblog:
            continue
        created_at = mblog.get("created_at", "")
        if item_filter:
            if not item_filter(created_at):
                continue
        elif not is_today_text(created_at):
            continue
        user = mblog.get("user") or {}
        actual_uid = str(user.get("idstr") or user.get("id") or "")
        if actual_uid and actual_uid != uid:
            continue
        author = user.get("screen_name") or data.get("data", {}).get("userInfo", {}).get("screen_name") or f"UID {uid}"
        text = text_from_html(mblog.get("text", ""))
        repost = mblog.get("retweeted_status") or {}
        repost_user = repost.get("user") or {}
        repost_author = repost_user.get("screen_name", "")
        repost_text = text_from_html(repost.get("text", ""))
        mid = mblog.get("mid") or mblog.get("id") or ""
        link = card.get("scheme") or (f"https://m.weibo.cn/detail/{mid}" if mid else f"https://m.weibo.cn/u/{uid}")
        items.append(
            {
                "feed_title": author,
                "source_uid": uid,
                "title": truncate(text, 80),
                "description": text,
                "repost_author": repost_author,
                "repost_description": repost_text,
                "link": link,
                "pub_date": created_at,
            }
        )
    if not items and include_empty:
        author = data.get("data", {}).get("userInfo", {}).get("screen_name") or f"UID {uid}"
        items.append(
            {
                "feed_title": author,
                "source_uid": uid,
                "title": "今日无新动态",
                "description": "",
                "link": f"https://m.weibo.cn/u/{uid}",
                "pub_date": "",
            }
        )
    return items


def parse_desktop_user_items(uid, data, item_filter=None, include_empty=True):
    if data.get("ok") != 1:
        raise RuntimeError(f"weibo.com 返回 ok={data.get('ok')}，需要登录态")
    statuses = data.get("data", {}).get("list", [])
    items = []
    author = f"UID {uid}"
    for status in statuses:
        created_at = status.get("created_at", "")
        if item_filter:
            if not item_filter(created_at):
                continue
        elif not is_today_text(created_at):
            continue
        user = status.get("user") or {}
        actual_uid = str(user.get("idstr") or user.get("id") or "")
        if actual_uid and actual_uid != uid:
            continue
        author = user.get("screen_name") or author
        text = text_from_html(status.get("text_raw") or status.get("text") or "")
        repost = status.get("retweeted_status") or {}
        repost_user = repost.get("user") or {}
        repost_author = repost_user.get("screen_name", "")
        repost_text = text_from_html(repost.get("text_raw") or repost.get("text") or "")
        mid = status.get("mid") or status.get("mblogid") or status.get("idstr") or ""
        link = f"https://weibo.com/{uid}/{mid}" if mid else f"https://weibo.com/u/{uid}"
        items.append(
            {
                "feed_title": author,
                "source_uid": uid,
                "title": truncate(text, 80),
                "description": text,
                "repost_author": repost_author,
                "repost_description": repost_text,
                "link": link,
                "pub_date": created_at,
            }
        )
    if not items and include_empty:
        user = data.get("data", {}).get("user") or {}
        author = user.get("screen_name") or author
        items.append(
            {
                "feed_title": author,
                "source_uid": uid,
                "title": "今日无新动态",
                "description": "",
                "link": f"https://weibo.com/u/{uid}",
                "pub_date": "",
            }
        )
    return items


def load_blogger_items(item_filter=None, include_empty=True):
    blogger_items = []
    uid_order = {uid: index for index, uid in enumerate(UNIQUE_UIDS)}

    def normalize_items(uid, items):
        label = UID_LABELS.get(uid)
        for item in items:
            item["source_uid"] = uid
            if label:
                item["feed_title"] = label
        return items

    def load_uid(uid):
        homepage = f"https://weibo.com/u/{uid}"
        if WEIBO_COOKIE:
            try:
                return uid, normalize_items(uid, load_user_direct(uid, item_filter=item_filter, include_empty=include_empty))
            except Exception as direct_exc:
                return uid, normalize_items(uid, [
                    {
                        "feed_title": f"UID {uid}",
                        "title": "抓取失败",
                        "description": str(direct_exc),
                        "link": "",
                        "pub_date": "",
                    }
                ])

        try:
            return uid, normalize_items(uid, parse_rss(fetch(rss_url(f"/weibo/user/{uid}")), limit=5))
        except Exception as rss_exc:
            try:
                return uid, normalize_items(uid, load_user_direct(uid))
            except Exception as direct_exc:
                reason = str(direct_exc) or str(rss_exc)
                reason = f"{reason}；可能需要设置 WEIBO_COOKIE 登录态"
                return uid, normalize_items(uid, [
                    {
                        "feed_title": f"UID {uid}",
                        "title": "抓取失败",
                        "description": reason,
                        "link": "",
                        "pub_date": "",
                    }
                ])

    results = []
    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as executor:
        futures = [executor.submit(load_uid, uid) for uid in UNIQUE_UIDS]
        for future in as_completed(futures):
            results.append(future.result())

    for _, items in sorted(results, key=lambda result: uid_order[result[0]]):
        blogger_items.extend(items)

    blogger_items = [
        item
        for item in blogger_items
        if item["feed_title"].replace("的微博", "").strip() not in EXCLUDED_AUTHORS
    ]
    return blogger_items


def load_digest():
    hot_items = aggregate_hot_items(load_hot_items())
    blogger_items = load_blogger_items()
    return hot_items, blogger_items


def truncate(value, limit):
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1] + "..."


def compact_text(value):
    value = text_from_html(value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"转发微博|//@", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -:：")


def first_complete_sentence(value):
    value = compact_text(value)
    if not value:
        return ""
    parts = re.split(r"(?<=[。！？!?])", value, maxsplit=1)
    sentence = parts[0].strip()
    return sentence or value


def sentence_boundary_summary(value, limit=90):
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


def fallback_nightly_author_summary(author, items):
    snippets = []
    for item in items:
        text = compact_text(item.get("description") or item.get("title") or "")
        repost_text = compact_text(item.get("repost_description", ""))
        if repost_text and len(repost_text) > len(text):
            text = repost_text
        snippet = sentence_boundary_summary(text, 70)
        if snippet:
            snippets.append(snippet)
    if not snippets:
        return ""
    return f"{author}：{snippets[0]}"


def markdown_escape(value):
    return (
        value.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("`", "\\`")
    )


def markdown_link(text, href):
    return f"[{markdown_escape(text)}]({href})"


def openai_response_text(prompt):
    if not OPENAI_API_KEY:
        return ""
    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
    }
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
                    "你是中文微博日报主编，擅长把零散微博整理成高信息密度、"
                    "自然中文、适合飞书阅读的简报。你必须只输出 JSON。"
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


HOT_CATEGORIES = [
    ("高考教育", ("高考", "数学", "作文", "考生", "考场", "录取", "学校", "教育")),
    ("社会民生", ("车祸", "事故", "医院", "医生", "牙医", "中产", "市值", "耐克", "阿迪达斯", "民生", "警方")),
    ("文娱综艺", ("浪姐", "排名", "淘汰", "张月", "陈瑶", "安崎", "代斯", "黄子韬", "张慧雯", "曾沛慈", "唱歌")),
    ("国际科技财经", ("中国逐日", "AI", "Anthropic", "朝鲜", "平壤", "五星红旗", "科技", "突破", "工程")),
    ("体育赛事", ("F1", "足球", "篮球", "网球", "赛事", "冠军")),
]


def summarize_hot_items(hot_items):
    grouped = {name: [] for name, _ in HOT_CATEGORIES}
    grouped["其他"] = []
    for item in hot_items:
        title = item["title"]
        related = item.get("related_titles") or []
        display_title = title if not related else f"{title}（相关：{'、'.join(related[:3])}）"
        matched = False
        for name, keywords in HOT_CATEGORIES:
            if any(keyword in title for keyword in keywords):
                grouped[name].append(display_title)
                matched = True
                break
        if not matched:
            grouped["其他"].append(display_title)

    parts = []
    for name, titles in grouped.items():
        if not titles:
            continue
        sample = "、".join(titles[:4])
        parts.append(f"{name}：{sample}")
    if not parts:
        return "暂无可归纳热点。"
    return "今日热搜主要集中在" + "；".join(parts) + "。"


def item_for_llm(item):
    text = compact_text(item.get("description") or item.get("title") or "")
    repost_text = compact_text(item.get("repost_description", ""))
    repost_author = compact_text(item.get("repost_author", ""))
    if repost_text and repost_author not in EXCLUDED_REPOST_AUTHORS:
        text = f"{text}\n转发自：{repost_author}\n被转发内容：{repost_text}"
    text = truncate(text, 1800)
    return {
        "time": post_time_label(item.get("pub_date", "")),
        "text": text,
    }


def build_llm_summaries(hot_items, blogger_items):
    groups = {
        author: items
        for author, items in group_by_author(blogger_items).items()
        if has_reportable_items(items)
    }
    if not groups:
        return {}, ""
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return {}, ""
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return {}, ""

    model_name = DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else OPENAI_MODEL
    date_text = digest_day().strftime("%Y-%m-%d")

    def summarize_hot_with_llm():
        official_brief = load_official_hot_brief()
        merged_hot_events = merge_hot_events_with_official_brief(hot_items, official_brief)
        payload = {
            "date": date_text,
            "hot_events": merged_hot_events,
        }
        cached = get_cached_summary("hot_summary", payload)
        if cached:
            return cached
        prompt = (
            "你是中文微博日报编辑。请综合当天微博热搜事件生成热点概览。\n"
            "只输出 JSON：{\"hot_summary\":\"...\"}。\n"
            "要求：\n"
            "1. hot_events.primary_events 是全天自采集并聚类后的主事件列表，排序和取舍以它为主。\n"
            "2. primary_events 中 source= self_collected+official_brief 表示官方简报也提到该事件；official_context 只作为背景补充。\n"
            "3. hot_events.official_unmatched_context 是官方简报中未匹配到主事件的剩余内容，只能在结尾作为一小段补充观察，不要逐条列标题。\n"
            "4. 用 5-8 句总结热点主题、事件走向和舆论关注点，重要事件可适当多写半句背景；最后可用 1 句补充官方简报体现的额外领域。\n"
            "5. 如果多个标题属于同一事件，要合并解释；需要点名重要赛事、社会事件、国际局势、文娱争议、公共政策或科技财经动态。\n"
            "6. 不要编造输入中没有的信息，不要输出广告或营销解读；赞助、发布会、带货、优惠促销、联名新品等硬广告内容要忽略。\n"
            "7. 消费/商业现象如果反映了当天热点，例如赛事带动周边销量，可以作为次要观察一句带过，不要写成品牌宣传。\n"
            "8. 官方补充内容价值不高时可以不写。\n"
            "输入 JSON：\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        parsed = json_llm_response(prompt, "{\"hot_summary\":\"...\"}")
        value = parsed.get("hot_summary", "")
        summary = value if isinstance(value, str) else ""
        set_cached_summary("hot_summary", payload, summary)
        return summary

    def summarize_blogger_batch(batch):
        payload = {
            "date": date_text,
            "bloggers": {
                author: [
                    item_for_llm(item)
                    for item in items
                    if is_real_post_item(item)
                ]
                for author, items in batch
            },
        }
        cached = get_cached_summary("blogger_batch", payload)
        if cached:
            return cached
        prompt = (
            "你是中文微博日报编辑。请根据输入 JSON 为每位博主生成当天整体摘要。\n"
            "只输出 JSON：{\"blogger_summaries\":{\"博主名\":\"...\"}}。\n"
            "要求：\n"
            "1. 每个博主通常 2-4 句，先说核心动向，再补充具体事实。\n"
            "2. 如果多为转发，要总结其关注/转发的议题，并尽量纳入被转发微博内容。\n"
            "3. 不要机械写“发了 N 条”“转发微博”；不要粘贴原文；不要用分号硬串。\n"
            "4. 不要出现省略号，不要编造输入中没有的信息。\n"
            "5. 内容跨度杂时按主题合并，例如行程见闻、汽车内容、社会评论、科技产品、生活日常。\n"
            "输入 JSON：\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        parsed = json_llm_response(prompt, "{\"blogger_summaries\":{\"博主名\":\"摘要\"}}")
        value = parsed.get("blogger_summaries", {})
        summaries = value if isinstance(value, dict) else {}
        set_cached_summary("blogger_batch", payload, summaries)
        return summaries

    hot_summary = ""
    blogger_summaries = {}
    group_items = list(groups.items())
    batch_size = max(1, LLM_BATCH_SIZE)
    batches = [
        group_items[index : index + batch_size]
        for index in range(0, len(group_items), batch_size)
    ]

    log_progress(
        f"calling llm in batches provider={LLM_PROVIDER} model={model_name} batches={len(batches)}"
    )
    tasks = [("hot", None)]
    tasks.extend(("bloggers", batch) for batch in batches)
    with ThreadPoolExecutor(max_workers=max(1, LLM_BATCH_WORKERS)) as executor:
        future_map = {}
        for kind, batch in tasks:
            if kind == "hot":
                future_map[executor.submit(summarize_hot_with_llm)] = (kind, batch)
            else:
                future_map[executor.submit(summarize_blogger_batch, batch)] = (kind, batch)

        for future in as_completed(future_map):
            kind, batch = future_map[future]
            try:
                result = future.result()
                if kind == "hot":
                    hot_summary = result
                else:
                    blogger_summaries.update(result)
            except Exception as exc:
                if kind == "hot":
                    log_progress(f"hot llm summary failed, fallback to rule summary: {exc}")
                else:
                    names = ", ".join(author for author, _ in batch)
                    log_progress(
                        f"blogger batch llm summary failed ({names}), fallback to rule summary: {exc}"
                    )

    return blogger_summaries, hot_summary


def post_time_label(pub_date):
    if not pub_date:
        return ""
    match = re.search(r"(\d{2}):(\d{2}):\d{2}", pub_date)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    match = re.search(r"(\d{1,2}:\d{2})", pub_date)
    return match.group(1) if match else ""


def summarize_post(item):
    if item["title"] == "今日无新动态":
        return "今日无新动态"
    if item["title"] == "抓取失败":
        return "抓取失败：" + compact_text(item["description"])
    text = compact_text(item["description"] or item["title"])
    if not text:
        return "转发了一条微博。"
    if text in {"转发", "微博"} or len(text) <= 4:
        return "转发了一条微博。"
    sentence = first_complete_sentence(text)
    if not re.search(r"[。！？!?]$", sentence):
        sentence += "。"
    return sentence


def summarize_author_items(items):
    failures = [item for item in items if item["title"] == "抓取失败"]
    if failures:
        return "抓取失败：" + compact_text(failures[0]["description"])

    posts = [item for item in items if item["title"] != "今日无新动态"]
    if not posts:
        return "今日无新动态"

    originals = []
    reposts = []
    pure_repost_count = 0
    for item in posts:
        own_text = compact_text(item["description"] or item["title"])
        repost_text = compact_text(item.get("repost_description", ""))
        repost_author = compact_text(item.get("repost_author", ""))

        if repost_text and repost_author not in EXCLUDED_REPOST_AUTHORS:
            pure = own_text in {"转发", "微博"} or len(own_text) <= 4
            if pure:
                pure_repost_count += 1
                lead = f"转发了 {repost_author} 的内容" if repost_author else "转发了一条内容"
            else:
                lead = f"转发并评论：{own_text}"
            detail = first_complete_sentence(repost_text)
            reposts.append(f"{lead}，被转发内容为：{detail}")
        elif own_text:
            originals.append(first_complete_sentence(own_text))

    points = []
    if originals:
        points.append("原创/自发内容：" + "；".join(dict.fromkeys(originals[:4])) + "。")
    if reposts:
        points.append("转发关注：" + "；".join(dict.fromkeys(reposts[:4])) + "。")
    if not points and pure_repost_count:
        points.append(f"今日共 {pure_repost_count} 条动态，主要为纯转发。")
    if not points:
        return "今日无可总结正文。"

    if pure_repost_count and reposts:
        points.append(f"其中 {pure_repost_count} 条为纯转发。")
    return f"今日共 {len(posts)} 条动态。" + "".join(points)


def group_by_author(items):
    groups = {}
    for item in items:
        author = item["feed_title"].replace("的微博", "").strip() or "未知博主"
        groups.setdefault(author, []).append(item)
    return groups


def is_failure_item(item):
    return item.get("title") == "抓取失败"


def is_real_post_item(item):
    return item.get("title") not in {"今日无新动态", "抓取失败"}


def has_reportable_items(items):
    return any(is_real_post_item(item) for item in items)


def reportable_links(items):
    return [
        item["link"]
        for item in items
        if item.get("link") and is_real_post_item(item)
    ]


def failed_authors(blogger_items):
    names = []
    for author, items in group_by_author(blogger_items).items():
        if any(is_failure_item(item) for item in items) and not has_reportable_items(items):
            names.append(author)
    return names


def build_nightly_supplement_lines():
    if not NIGHTLY_SUPPLEMENT_ENABLED:
        return []
    start, end = previous_supplement_window()
    hot_items = nightly_hot_supplement_items(start, end)
    blogger_items = load_blogger_items(
        item_filter=lambda created_at: in_time_window(created_at, start, end),
        include_empty=False,
    )
    blogger_items = [item for item in blogger_items if is_real_post_item(item)]
    if not hot_items and not blogger_items:
        return []

    payload = {
        "version": "weibo-nightly-v3",
        "date": digest_day().strftime("%Y-%m-%d"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hot_events": [
            {
                "event": item.get("title", ""),
                "seen": item.get("seen", 0),
                "best_rank": item.get("best_rank", 50),
                "related_titles": item.get("related_titles", []),
            }
            for item in hot_items[:8]
        ],
        "bloggers": {
            author: [
                item_for_llm(item)
                for item in items[:3]
                if is_real_post_item(item)
            ]
            for author, items in list(group_by_author(blogger_items).items())[:8]
        },
    }
    cached = get_cached_summary("nightly_supplement_v3", payload)
    if isinstance(cached, list):
        return cached
    if (LLM_PROVIDER == "deepseek" and DEEPSEEK_API_KEYS) or (LLM_PROVIDER != "deepseek" and OPENAI_API_KEY):
        try:
            prompt = (
                "请为微博日报生成“昨夜补遗”的简短摘要。\n"
                "只输出 JSON：{\"hot\":\"热搜补遗或空字符串\",\"bloggers\":\"博主补遗或空字符串\"}。\n"
                "要求：\n"
                "1. 这是昨日推送后到 24:00 的新增内容补充，不要写成完整日报。\n"
                "2. hot 最多 1 句，概括新增或升温热搜事件；没有就空字符串。\n"
                "3. bloggers 最多 2 句，按博主合并重点，不要列原文，不要出现省略号，不要机械写“今日共 N 条动态”。\n"
                "4. 文字要自然，避免截断感；只根据输入，不要编造。\n"
                "输入 JSON：\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            parsed = json_llm_response(prompt, "{\"hot\":\"...\",\"bloggers\":\"...\"}")
            lines = [
                "**昨夜补遗**",
                f"范围：昨日推送后至 24:00（{start.strftime('%H:%M')}-{end.strftime('%H:%M')}）新增内容。",
            ]
            hot_summary = compact_text(parsed.get("hot", "")) if isinstance(parsed, dict) else ""
            blogger_summary = compact_text(parsed.get("bloggers", "")) if isinstance(parsed, dict) else ""
            if hot_summary:
                lines.append("热搜：" + markdown_escape(hot_summary))
            if blogger_summary:
                lines.append("博主：" + markdown_escape(blogger_summary))
            if len(lines) > 2:
                set_cached_summary("nightly_supplement_v3", payload, lines)
                return lines
        except Exception as exc:
            log_progress(f"nightly supplement llm failed, fallback to rule summary: {exc}")

    lines = [
        "**昨夜补遗**",
        f"范围：昨日推送后至 24:00（{start.strftime('%H:%M')}-{end.strftime('%H:%M')}）新增内容。",
    ]
    if hot_items:
        titles = "、".join(item["title"] for item in hot_items[:5])
        lines.append(f"热搜：昨夜新增或升温事件包括 {markdown_escape(titles)}。")
    if blogger_items:
        parts = []
        for author, items in list(group_by_author(blogger_items).items())[:5]:
            text = fallback_nightly_author_summary(author, items)
            if text:
                parts.append(text)
        if len(group_by_author(blogger_items)) > 5:
            parts.append(f"另有 {len(group_by_author(blogger_items)) - 5} 位博主昨夜更新。")
        if parts:
            lines.append("博主：" + markdown_escape("；".join(parts)))
    return lines


def feishu_text_line(tag, text, href=None):
    if href:
        return [
            {"tag": "text", "text": tag},
            {"tag": "a", "text": text, "href": href},
        ]
    return [{"tag": "text", "text": f"{tag}{text}"}]


def build_daily_lines(hot_items, blogger_items):
    blogger_summaries, hot_summary = build_llm_summaries(hot_items, blogger_items)
    supplement_lines = build_nightly_supplement_lines()
    hot_lines = []
    if supplement_lines:
        hot_lines.extend(supplement_lines)
        hot_lines.append("")
    hot_lines.extend(["**热搜概览**", markdown_escape(hot_summary or summarize_hot_items(hot_items))])

    author_lines = ["**关注博主动态**"]
    shown_author_count = 0
    for author, items in group_by_author(blogger_items).items():
        if not has_reportable_items(items):
            continue
        shown_author_count += 1
        author_lines.append("")
        author_lines.append(f"<font color=\"blue\">**{markdown_escape(author)}**</font>")
        summary = blogger_summaries.get(author) or summarize_author_items(items)
        author_lines.append(f"重点：{markdown_escape(summary)}")
        links = reportable_links(items)
        if links:
            link_text = " ".join(markdown_link(str(index), link) for index, link in enumerate(links[:5], start=1))
            author_lines.append(f"原文：{link_text}")

    failures = failed_authors(blogger_items)
    if failures:
        shown = "、".join(markdown_escape(name) for name in failures[:12])
        more = f" 等 {len(failures)} 位博主" if len(failures) > 12 else ""
        author_lines.append("")
        author_lines.append(
            f"抓取异常：{shown}{more} 今日微博内容未获取，已跳过摘要。"
            "通常是微博登录态或接口限制导致。"
        )
    elif shown_author_count == 0:
        author_lines.append("")
        author_lines.append("今日暂无关注博主新动态。")

    return hot_lines, author_lines


def send_feishu_card(webhook, hot_lines, author_lines, today):
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": f"微博日报 {today}"},
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(hot_lines)},
                {"tag": "hr"},
                {"tag": "markdown", "content": "\n".join(author_lines)},
            ],
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        sys.stdout.write(resp.read().decode("utf-8"))


def build_feishu_image_key(title, sections):
    if not FEISHU_IMAGE_DAILY_ENABLED:
        return ""
    if not (FEISHU_APP_ID and FEISHU_APP_SECRET):
        return ""
    if not (render_daily_image and upload_feishu_image and send_feishu_image):
        raise RuntimeError("daily image renderer unavailable")
    image_path = os.path.join(APP_DATA_DIR, f"weibo_daily_{digest_day().strftime('%Y-%m-%d')}.png")
    render_daily_image(title, sections, image_path)
    log_progress(f"feishu image rendered path={image_path}")
    return upload_feishu_image(image_path, FEISHU_APP_ID, FEISHU_APP_SECRET)


def wechat_work_markdown(value):
    value = re.sub(r"</?font\b[^>]*>", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return value


def truncate_utf8(value, max_bytes):
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    suffix = "\n\n内容较长，已截断。"
    keep = max(0, max_bytes - len(suffix.encode("utf-8")))
    return data[:keep].decode("utf-8", errors="ignore").rstrip() + suffix


def truncate_utf8_plain(value, max_bytes):
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    return data[:max_bytes].decode("utf-8", errors="ignore").rstrip() + "..."


def wechat_line(value):
    value = wechat_work_markdown(value).strip()
    if not value or value.startswith("原文："):
        return ""
    value = value.replace("**", "")
    value = re.sub(r"\s+", " ", value)
    return truncate_utf8_plain(value, 520)


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
    content = build_wechat_content(title, sections)
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        sys.stdout.write(resp.read().decode("utf-8"))


def send_feishu(hot_items, blogger_items):
    today = digest_day().strftime("%Y-%m-%d")
    title = f"微博日报 {today}"
    hot_lines, author_lines = build_daily_lines(hot_items, blogger_items)
    sections = [hot_lines, author_lines]
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
                send_feishu_card(robot["url"], hot_lines, author_lines, today)
            sent += 1
        except Exception as exc:
            errors.append(f"feishu/{robot['name']}: {exc}")
            log_progress(f"feishu send failed robot={robot['name']}: {exc}")
            if image_key:
                try:
                    send_feishu_card(robot["url"], hot_lines, author_lines, today)
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
    if COLLECT_HOT_ONLY:
        log_progress("start hot collect")
        collect_hot_snapshot()
        log_progress("hot collect done")
        return

    log_progress("start loading digest")
    hot_items, blogger_items = load_digest()
    log_progress("digest loaded")
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        today = digest_day().strftime("%Y-%m-%d")
        title = f"微博日报 {today}"
        hot_lines, author_lines = build_daily_lines(hot_items, blogger_items)
        output_path = RENDER_OUTPUT or os.path.join(APP_DATA_DIR, f"weibo_daily_render_only_{today}.png")
        render_daily_image(title, [hot_lines, author_lines], output_path)
        log_progress(f"render only output={output_path}")
        return
    if PRECOMPUTE_ONLY:
        log_progress("precompute only: building llm cache")
        build_llm_summaries(hot_items, blogger_items)
        log_progress("precompute done")
        return
    wait_until_send_time()
    log_progress("sending notifications")
    send_feishu(hot_items, blogger_items)
    log_progress("done")


if __name__ == "__main__":
    main()
