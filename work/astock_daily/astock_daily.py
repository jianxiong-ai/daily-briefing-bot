#!/usr/bin/env python3
import html
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from multiprocessing import Process, Queue
from threading import BoundedSemaphore

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from daily_briefing.llm import JsonlSummaryCache, LlmClient, LlmSettings, cache_key as shared_cache_key
from daily_briefing.push import (
    build_wechat_content as push_build_wechat_content,
    send_feishu_card as push_send_feishu_card,
    send_wechat_work_markdown as push_send_wechat_work_markdown,
)
from daily_briefing.quality import dedupe_by_similarity
from daily_briefing.redfox import RawJsonCache, post_json as shared_redfox_post_json
from daily_briefing.runtime import (
    load_env_file,
    parse_webhook_robots,
    selected_robots as runtime_selected_robots,
    wait_until_local_time,
)
from daily_briefing.storage import runtime_storage

try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ENV_PATH = os.environ.get("ASTOCK_DAILY_ENV", os.path.join(ROOT_DIR, "work/astock_daily/.env"))
load_env_file(ENV_PATH, override=False)
STORAGE = runtime_storage("astock")

SH_TZ = timezone(timedelta(hours=8))
REDFOX_API_KEY = os.environ.get("REDFOX_API_KEY", "").strip()
REDFOX_STOCK_FEED_URL = os.environ.get(
    "REDFOX_STOCK_FEED_URL",
    "https://redfox.hk/story/api/multiPlatform/workSearch",
).strip()
REDFOX_ASTOCK_PUBLISH_URL = os.environ.get(
    "REDFOX_ASTOCK_PUBLISH_URL",
    "https://redfox.hk/story/api/gzh/search/dailyPublish",
).strip()
REDFOX_TIMEOUT_SECONDS = int(os.environ.get("REDFOX_TIMEOUT_SECONDS", "90"))
REDFOX_FORCE_REFRESH = os.environ.get("REDFOX_FORCE_REFRESH", "0").strip() == "1"
REDFOX_TODAY_CACHE_TTL_SECONDS = int(os.environ.get("REDFOX_TODAY_CACHE_TTL_SECONDS", "3600"))
REDFOX_RAW_CACHE_FILE = os.environ.get("REDFOX_RAW_CACHE_FILE", str(STORAGE.cache / "redfox_raw_cache.json"))

ASTOCK_DAILY_TITLE = os.environ.get("ASTOCK_DAILY_TITLE", "A股日报").strip()
ASTOCK_DIGEST_OFFSET_DAYS = int(os.environ.get("ASTOCK_DIGEST_OFFSET_DAYS", "1"))
ASTOCK_SOCIAL_LIMIT = int(os.environ.get("ASTOCK_SOCIAL_LIMIT", "45"))
ASTOCK_PUBLISH_LIMIT = int(os.environ.get("ASTOCK_PUBLISH_LIMIT", "36"))
ASTOCK_TOPIC_LIMIT = int(os.environ.get("ASTOCK_TOPIC_LIMIT", "7"))
ASTOCK_KEYWORDS = os.environ.get(
    "ASTOCK_KEYWORDS",
    "A股,A股市场,A股大盘,A股复盘,涨停,跌停,板块,行情,半导体,芯片,新能源,"
    "人工智能,机器人,医药,消费,银行,保险,地产,军工,有色,证券",
).strip()

OFFICIAL_ACCOUNTS = (
    "央视财经", "华夏基金", "金融时报", "中国基金报", "券商中国", "每日经济新闻",
    "财联社", "第一财经", "21世纪经济报道", "界面新闻", "中国证券报", "证券时报",
    "上海证券报", "e公司", "腾讯财经", "期货日报", "中新经纬", "天天基金网",
)
KOL_ACCOUNTS = (
    "好运哥2008", "雷立刚本人", "孥孥的大树", "财经作家雷立刚", "凯恩斯",
    "冷眼局中人", "毛有话说", "EarlETF", "研报号角", "齐俊杰看财经",
    "思哲与创富", "A股研报君", "价值成长", "唐老师笔记", "金成探市",
    "丹湖渔翁", "远行者与碎冰匠", "胡斐投资办公室",
)

STOCK_TERMS = (
    "A股", "股票", "股市", "大盘", "指数", "板块", "行情", "涨停", "跌停", "成交",
    "财报", "业绩", "营收", "利润", "现金流", "估值", "分红", "回购", "增持", "减持",
    "并购", "重组", "IPO", "基金", "ETF", "券商", "银行", "保险", "地产", "半导体",
    "芯片", "新能源", "光伏", "锂电", "医药", "消费", "白酒", "汽车", "机器人",
    "人工智能", "AI", "军工", "有色", "铜", "稀土", "证监会", "央行", "降息", "降准",
)
NOISE_TERMS = ("美妆", "穿搭", "食谱", "旅游攻略", "追剧", "明星八卦", "萌宠")

DIGEST_DATE = os.environ.get("DIGEST_DATE", "").strip()
DAILY_RUN_MODE = os.environ.get("DAILY_RUN_MODE", "").strip().lower()
SEND_AT_LOCAL = os.environ.get("SEND_AT_LOCAL", "").strip()
RENDER_ONLY = os.environ.get("RENDER_ONLY", "").strip() == "1"
RENDER_OUTPUT = os.environ.get("RENDER_OUTPUT", "").strip()
LOG_PROGRESS = os.environ.get("LOG_PROGRESS", "1").strip() != "0"

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "").strip()
WECHAT_WORK_WEBHOOK = os.environ.get("WECHAT_WORK_WEBHOOK", "").strip()
PUSH_TARGETS = os.environ.get("PUSH_TARGETS", "all").strip().lower()
FEISHU_ROBOTS = parse_webhook_robots(os.environ.get("FEISHU_WEBHOOKS", ""), FEISHU_WEBHOOK, "主机器人")
WECHAT_WORK_ROBOTS = parse_webhook_robots(
    os.environ.get("WECHAT_WORK_WEBHOOKS", ""), WECHAT_WORK_WEBHOOK, "主机器人"
)
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "").strip()
FEISHU_IMAGE_DAILY_ENABLED = os.environ.get("FEISHU_IMAGE_DAILY_ENABLED", "1").strip() != "0"

LLM_SETTINGS = LlmSettings.from_env()
LLM_TIMEOUT_SECONDS = LLM_SETTINGS.timeout
LLM_MAX_CONCURRENT_REQUESTS = int(os.environ.get("LLM_MAX_CONCURRENT_REQUESTS", "2"))
LLM_PROMPT_VERSION = os.environ.get("ASTOCK_LLM_PROMPT_VERSION", "astock-v2").strip()
LLM_CACHE_TTL_SECONDS = int(os.environ.get("LLM_CACHE_TTL_SECONDS", "43200"))
LLM_CACHE_ENABLED = os.environ.get("LLM_CACHE_ENABLED", "1").strip() != "0"
LLM_CACHE_FILE = os.environ.get("ASTOCK_LLM_CACHE_FILE", str(STORAGE.cache / "llm_summary_cache.jsonl"))

REDFOX_CACHE = RawJsonCache(REDFOX_RAW_CACHE_FILE, max_entries=90)
LLM_CACHE = {}
LLM_CACHE_STORE = JsonlSummaryCache(LLM_CACHE_FILE, LLM_CACHE_TTL_SECONDS, LLM_CACHE_ENABLED, LLM_CACHE)
LLM_CLIENT = LlmClient(
    LLM_SETTINGS,
    semaphore=BoundedSemaphore(max(1, LLM_MAX_CONCURRENT_REQUESTS)),
)
APP_DATA_DIR = str(STORAGE.images)


def shanghai_now():
    return datetime.now(SH_TZ)


def log_progress(message):
    if LOG_PROGRESS:
        print(f"[{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def digest_day():
    if DIGEST_DATE:
        return datetime.strptime(DIGEST_DATE, "%Y-%m-%d").replace(tzinfo=SH_TZ)
    return (shanghai_now() - timedelta(days=ASTOCK_DIGEST_OFFSET_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def compact_text(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def int_value(value):
    if isinstance(value, str):
        text = value.lower().replace(",", "").replace("+", "").strip()
        try:
            if "w" in text:
                return int(float(text.replace("w", "")) * 10000)
            if text.endswith("万"):
                return int(float(text[:-1]) * 10000)
        except ValueError:
            return 0
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def truncate(value, limit):
    value = compact_text(value)
    return value if len(value) <= limit else value[:limit].rstrip() + "..."


def parse_publish_date(value):
    text = compact_text(value)
    if not text:
        return None
    if text.isdigit():
        try:
            timestamp = int(text)
            if timestamp > 10**12:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, SH_TZ).date()
        except (OSError, ValueError):
            return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(), "%Y-%m-%d").date()
    except ValueError:
        return None


def selected_robots(robots):
    return runtime_selected_robots(robots, PUSH_TARGETS)


def is_today_digest():
    return digest_day().date() == shanghai_now().date()


def is_formal_run():
    return DAILY_RUN_MODE == "formal"


def redfox_post(url, payload):
    if not REDFOX_API_KEY:
        raise RuntimeError("missing REDFOX_API_KEY")
    return shared_redfox_post_json(
        url,
        payload,
        REDFOX_API_KEY,
        timeout=REDFOX_TIMEOUT_SECONDS,
        user_agent="DailyBriefing-AStock/0.1",
    )


def cached_redfox(payload):
    if REDFOX_FORCE_REFRESH:
        return None
    value = REDFOX_CACHE.get(payload)
    if value is None:
        return None
    if is_today_digest():
        if is_formal_run():
            return None
        value = REDFOX_CACHE.get(payload, ttl_seconds=REDFOX_TODAY_CACHE_TTL_SECONDS)
    return value


def fetch_stock_feed():
    day = digest_day()
    payload = {
        "keyword": ASTOCK_KEYWORDS,
        "source": "A股日报-DailyBriefingBot",
        "startDate": day.strftime("%Y-%m-%d"),
        "endDate": (day + timedelta(days=1)).strftime("%Y-%m-%d"),
        "_cache_url": REDFOX_STOCK_FEED_URL,
    }
    cached = cached_redfox(payload)
    if cached is not None:
        log_progress("astock social cache hit")
        return cached
    body = redfox_post(REDFOX_STOCK_FEED_URL, payload)
    if body.get("code") not in {200, 2000}:
        raise RuntimeError(f"RedFox stock feed error: {body.get('msg') or body.get('code')}")
    data = body.get("data") or {}
    REDFOX_CACHE.set(payload, data)
    return data


def fetch_astock_publish():
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "accountNames": list(KOL_ACCOUNTS + OFFICIAL_ACCOUNTS),
        "source": "A股日报-DailyBriefingBot",
        "_cache_url": REDFOX_ASTOCK_PUBLISH_URL,
    }
    cached = cached_redfox(payload)
    if cached is not None:
        log_progress("astock publish cache hit")
        return cached
    body = redfox_post(REDFOX_ASTOCK_PUBLISH_URL, payload)
    if body.get("code") not in {200, 2000}:
        raise RuntimeError(f"RedFox A-stock publish error: {body.get('msg') or body.get('code')}")
    data = body.get("data") or {}
    REDFOX_CACHE.set(payload, data)
    return data


def normalize_social_item(raw, platform):
    title = compact_text(raw.get("title") or raw.get("workTitle") or raw.get("displayTitle"))
    summary = compact_text(
        raw.get("summary") or raw.get("desc") or raw.get("workDesc") or raw.get("displayDesc") or raw.get("content")
    )
    author = compact_text(
        raw.get("author") or raw.get("accountName") or raw.get("accountNickname") or raw.get("nickname")
    )
    published = compact_text(
        raw.get("publicTime") or raw.get("publishTime") or raw.get("workPublishTime") or raw.get("createTime")
    )
    return {
        "id": compact_text(raw.get("workUuid") or raw.get("workId") or raw.get("id") or raw.get("url")),
        "platform": platform,
        "title": title or truncate(summary, 90),
        "summary": summary,
        "author": author or "未知作者",
        "published_at": published,
        "url": compact_text(raw.get("workUrl") or raw.get("url") or raw.get("shareInfoLink")),
        "engagement": sum(
            int_value(raw.get(key))
            for key in (
                "clicksCount", "readCount", "likeCount", "likedCount", "workLikedCount",
                "commentCount", "commentsCount", "workCommentsCount", "collectCount",
                "collectedCount", "workCollectedCount", "shareCount", "sharedCount", "workSharedCount",
            )
        ),
        "relevance": float(raw.get("relevanceScore") or 0),
        "popularity": float(raw.get("popularityScore") or 0),
    }


def normalize_social_data(data):
    mapping = (("小红书", "xhsResult"), ("抖音", "dyResult"), ("公众号", "gzhResult"))
    items = []
    expected = digest_day().date()
    for platform, key in mapping:
        values = data.get(key) or []
        if isinstance(values, dict):
            values = values.get("articles") or values.get("list") or []
        for raw in values if isinstance(values, list) else []:
            item = normalize_social_item(raw, platform)
            item_date = parse_publish_date(item["published_at"])
            if item_date and item_date != expected:
                continue
            text = f"{item['title']} {item['summary']}"
            if item["title"] and any(term.lower() in text.lower() for term in STOCK_TERMS) and not any(
                term in text for term in NOISE_TERMS
            ):
                items.append(item)
    items = dedupe_by_similarity(items, lambda item: item["title"] + " " + item["summary"], threshold=0.82)
    items.sort(
        key=lambda item: (
            item["relevance"] * 1.5 + item["popularity"] + math.log1p(item["engagement"]),
            item["engagement"],
        ),
        reverse=True,
    )
    return items[:ASTOCK_SOCIAL_LIMIT]


def normalize_publish_data(data):
    items = []
    expected = digest_day().date()
    official = set(OFFICIAL_ACCOUNTS)
    for account in data.get("accounts") or []:
        author = compact_text(account.get("accountName"))
        category = "机构/媒体" if author in official else "个人大V"
        for raw in account.get("works") or []:
            published = compact_text(raw.get("publishTime"))
            item_date = parse_publish_date(published)
            if item_date and item_date != expected:
                continue
            title = compact_text(raw.get("title"))
            if not title:
                continue
            summary = compact_text(raw.get("summary") or raw.get("memo") or raw.get("content"))
            text = f"{title} {summary}"
            if not any(term.lower() in text.lower() for term in STOCK_TERMS) or any(
                term in text for term in NOISE_TERMS
            ):
                continue
            items.append(
                {
                    "id": compact_text(raw.get("workUuid") or raw.get("workUrl") or title),
                    "category": category,
                    "author": author,
                    "title": title,
                    "summary": summary,
                    "url": compact_text(raw.get("workUrl")),
                    "published_at": published,
                    "reads": int_value(raw.get("clicksCount")),
                    "likes": int_value(raw.get("likeCount")),
                    "comments": int_value(raw.get("commentCount")),
                }
            )
    items = dedupe_by_similarity(items, lambda item: item["title"], threshold=0.9)
    items.sort(key=lambda item: (item["reads"], item["likes"], item["comments"]), reverse=True)
    return items[:ASTOCK_PUBLISH_LIMIT]


def load_llm_cache():
    try:
        LLM_CACHE_STORE.load()
    except OSError:
        pass


load_llm_cache()


def current_model():
    return LLM_SETTINGS.model


def llm_cache_key(payload):
    return shared_cache_key("astock_daily_digest", payload, LLM_SETTINGS.provider, current_model(), LLM_PROMPT_VERSION)


def compact_for_llm(item):
    return {
        "source": item.get("platform") or item.get("category"),
        "author": truncate(item.get("author"), 30),
        "title": truncate(item.get("title"), 120),
        "summary": truncate(item.get("summary"), 260),
        "engagement": item.get("engagement") or item.get("reads") or 0,
    }


def fallback_digest(social_items, publish_items):
    titles = [item["title"] for item in social_items[:8]]
    views = [f"{item['author']}：{item['title']}" for item in publish_items[:6]]
    return {
        "overview": (
            f"昨日共收集 {len(social_items)} 条跨平台市场讨论及 {len(publish_items)} 条机构/大V文章。"
            f"较受关注的话题包括：{'；'.join(titles[:4]) or '暂无可归纳主题'}。"
        ),
        "topics": [{"title": "市场热点扫描", "summary": "；".join(titles[:8])}] if titles else [],
        "views": [{"title": "机构与大V观点", "summary": "；".join(views)}] if views else [],
        "risks": ["社交平台热度不等于基本面变化，未交叉验证的信息应视为待确认。"],
    }


def run_llm_worker(prompt, queue):
    try:
        result = LLM_CLIENT.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的A股市场信息编辑。只归纳输入，不提供个股买卖建议，不把大V观点当事实，"
                        "不编造指数涨跌、资金流或公司数据。输出有效JSON。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        queue.put(("ok", result))
    except Exception as exc:
        queue.put(("error", repr(exc)))


def request_digest(payload):
    key = llm_cache_key(payload)
    cached = LLM_CACHE_STORE.get(key)
    if cached is not None:
        log_progress("astock llm cache hit")
        return cached
    prompt = (
        "请将昨日A股相关跨平台讨论和机构/大V文章整理成投资者可快速阅读的信息日报。\n"
        "输出JSON：{\"overview\":\"...\",\"topics\":[{\"title\":\"...\",\"summary\":\"...\"}],"
        "\"views\":[{\"title\":\"...\",\"summary\":\"...\"}],\"risks\":[\"...\"]}。\n"
        "要求：\n"
        "1. overview 2-3段，概括主线、市场关注方向与信息分歧；不得写输入没有的行情数字。\n"
        f"2. topics 生成4-{ASTOCK_TOPIC_LIMIT}个跨来源主题，优先宏观政策、产业趋势、公司事件和市场结构，"
        "同一事件合并，不按平台罗列；每条100-180字。\n"
        "3. views 只能根据 publish 数组生成，严禁用 social 数组补充观点。按作者归纳，"
        "最多生成 min(5, publish中的不同作者数) 条；若 publish 只有1位作者，就只能生成1条。"
        "标题要具体，明确使用“机构文章关注”“某大V认为”等措辞，不得包装成事实或投资建议；每条90-160字。\n"
        "4. risks 输出2-4条信息风险或待验证事项，包括来源单一、情绪过热、事实与观点混杂等。\n"
        "5. 过滤荐股口号、仓位指令、纯技术喊单、无事实依据的涨跌预测和非A股内容。\n"
        "6. 不出现“建议买入、卖出、加仓、减仓”，不做收益承诺；不输出缺少数据源等流程说明。\n"
        "输入：\n" + json.dumps(payload, ensure_ascii=False)
    )
    queue = Queue()
    process = Process(target=run_llm_worker, args=(prompt, queue))
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
    parsed = json.loads(value)
    result = {
        "overview": compact_text(parsed.get("overview")),
        "topics": parsed.get("topics") if isinstance(parsed.get("topics"), list) else [],
        "views": parsed.get("views") if isinstance(parsed.get("views"), list) else [],
        "risks": parsed.get("risks") if isinstance(parsed.get("risks"), list) else [],
    }
    distinct_publish_authors = {
        compact_text(item.get("author"))
        for item in payload.get("publish", [])
        if compact_text(item.get("author"))
    }
    result["views"] = result["views"][: min(5, len(distinct_publish_authors))]
    LLM_CACHE_STORE.set(
        key,
        "astock_daily_digest",
        result,
        metadata={"date": digest_day().strftime("%Y-%m-%d"), "model": current_model()},
    )
    return result


def build_digest(social_items, publish_items):
    if not LLM_SETTINGS.api_keys:
        return fallback_digest(social_items, publish_items)
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "social": [compact_for_llm(item) for item in social_items],
        "publish": [compact_for_llm(item) for item in publish_items],
    }
    try:
        return request_digest(payload)
    except Exception as exc:
        log_progress(f"astock llm failed, fallback: {exc}")
        return fallback_digest(social_items, publish_items)


def markdown_escape(value):
    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def paragraph_lines(value):
    return [compact_text(part) for part in re.split(r"\n+", str(value or "")) if compact_text(part)]


def build_daily_lines(social_items, publish_items):
    digest = build_digest(social_items, publish_items)
    overview = ["**市场概览**"]
    overview.extend(
        markdown_escape(part)
        for part in paragraph_lines(digest.get("overview") or "昨日暂无可归纳A股信息。")
    )

    topics = ["**热点主题**"]
    for item in (digest.get("topics") or [])[:ASTOCK_TOPIC_LIMIT]:
        title = compact_text(item.get("title")) if isinstance(item, dict) else ""
        summary = compact_text(item.get("summary")) if isinstance(item, dict) else ""
        if title and summary:
            topics.extend(["", f'<font color="blue">**{markdown_escape(title)}**</font>'])
            topics.extend(markdown_escape(part) for part in paragraph_lines(summary))
    if len(topics) == 1:
        topics.append("昨日暂无可归纳热点主题。")

    views = ["**机构与大V观点**"]
    for item in (digest.get("views") or [])[:5]:
        title = compact_text(item.get("title")) if isinstance(item, dict) else ""
        summary = compact_text(item.get("summary")) if isinstance(item, dict) else ""
        if title and summary:
            views.extend(["", f'<font color="blue">**{markdown_escape(title)}**</font>'])
            views.extend(markdown_escape(part) for part in paragraph_lines(summary))
    if len(views) == 1:
        views.append("昨日暂无可归纳机构与大V观点。")

    risks = ["**风险观察**"]
    for item in (digest.get("risks") or [])[:4]:
        text = compact_text(item)
        if text:
            risks.append(f"- {markdown_escape(text)}")
    risks.append("- 本日报仅作公开信息整理，不构成投资建议。")
    return overview, topics, views, risks


def send_notifications(social_items, publish_items):
    date_text = digest_day().strftime("%Y-%m-%d")
    title = f"{ASTOCK_DAILY_TITLE} {date_text}"
    sections = build_daily_lines(social_items, publish_items)
    image_key = ""
    image_error = ""
    if selected_robots(FEISHU_ROBOTS) and FEISHU_IMAGE_DAILY_ENABLED:
        try:
            if not (render_daily_image and upload_feishu_image and FEISHU_APP_ID and FEISHU_APP_SECRET):
                raise RuntimeError("image renderer or Feishu app credentials unavailable")
            image_path = os.path.join(APP_DATA_DIR, f"astock_daily_{date_text}.png")
            render_daily_image(title, sections, image_path)
            image_key = upload_feishu_image(image_path, FEISHU_APP_ID, FEISHU_APP_SECRET)
        except Exception as exc:
            image_error = str(exc)
            log_progress(f"astock image unavailable, fallback to card: {exc}")
    sent = 0
    errors = []
    for robot in selected_robots(FEISHU_ROBOTS):
        try:
            if image_key:
                send_feishu_image(robot["url"], image_key)
            else:
                push_send_feishu_card(robot["url"], title, sections)
            sent += 1
        except Exception as exc:
            errors.append(f"feishu/{robot['name']}: {exc}")
    for robot in selected_robots(WECHAT_WORK_ROBOTS):
        try:
            push_send_wechat_work_markdown(robot["url"], title, sections)
            sent += 1
        except Exception as exc:
            errors.append(f"wechat-work/{robot['name']}: {exc}")
    if sent == 0:
        if image_error:
            errors.append(f"image: {image_error}")
        raise RuntimeError("all notification channels failed: " + "; ".join(errors))


def wait_until_send_time():
    wait_until_local_time(SEND_AT_LOCAL, shanghai_now, time.sleep, log_progress, strict=True)


def main():
    log_progress("loading A-stock social feed")
    social_items = normalize_social_data(fetch_stock_feed())
    log_progress(f"A-stock social items={len(social_items)}")
    log_progress("loading A-stock publisher feed")
    publish_items = normalize_publish_data(fetch_astock_publish())
    log_progress(f"A-stock publisher items={len(publish_items)}")
    date_text = digest_day().strftime("%Y-%m-%d")
    title = f"{ASTOCK_DAILY_TITLE} {date_text}"
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        output = RENDER_OUTPUT or os.path.join(APP_DATA_DIR, f"astock_daily_render_only_{date_text}.png")
        render_daily_image(title, build_daily_lines(social_items, publish_items), output)
        log_progress(f"render only output={output}")
        return
    wait_until_send_time()
    send_notifications(social_items, publish_items)
    log_progress("done")


if __name__ == "__main__":
    main()
