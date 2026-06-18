#!/usr/bin/env python3
import html
import json
import os
import re
import sys
import time
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
    cache_key as shared_cache_key,
    chat_completion_text,
    split_api_keys,
)
from daily_briefing.redfox import (
    RawJsonCache,
    post_json as shared_redfox_post_json,
    redfox_cache_key as shared_redfox_cache_key,
)
try:
    from daily_image import render_daily_image, send_feishu_image, upload_feishu_image
except Exception:
    render_daily_image = None
    send_feishu_image = None
    upload_feishu_image = None


ENV_PATH = os.environ.get("DOUYIN_DAILY_ENV", os.path.join(ROOT_DIR, "work/douyin_daily/.env"))


def load_env_file(path, override=False):
    return runtime_load_env_file(path, override=override)


def parse_webhook_robots(value, primary_url="", primary_name="主机器人"):
    return runtime_parse_webhook_robots(value, primary_url, primary_name)


def selected_robots(robots):
    return runtime_selected_robots(robots, PUSH_TARGETS)


load_env_file(ENV_PATH, override=False)

REDFOX_API_KEY = os.environ.get("REDFOX_API_KEY", "").strip()
REDFOX_DOUYIN_LIKES_RANK_URL = os.environ.get(
    "REDFOX_DOUYIN_LIKES_RANK_URL",
    "https://redfox.hk/story/api/dy/search/likesRank",
).strip()
DOUYIN_DAILY_TITLE = os.environ.get("DOUYIN_DAILY_TITLE", "抖音日报").strip()
DOUYIN_CATEGORY = os.environ.get("DOUYIN_CATEGORY", "全部").strip() or "全部"
DOUYIN_REPORT_LIMIT = int(os.environ.get("DOUYIN_REPORT_LIMIT", "15"))
DOUYIN_LLM_INPUT_LIMIT = int(os.environ.get("DOUYIN_LLM_INPUT_LIMIT", "30"))
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
DOUYIN_DIGEST_OFFSET_DAYS = int(os.environ.get("DOUYIN_DIGEST_OFFSET_DAYS", "1"))
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
LLM_CACHE_FILE = os.environ.get("DOUYIN_LLM_CACHE_FILE", os.path.join(os.path.dirname(ENV_PATH), "llm_summary_cache.jsonl"))
LLM_PROMPT_VERSION = os.environ.get("DOUYIN_LLM_PROMPT_VERSION", "douyin-v4")

APP_DATA_DIR = os.path.dirname(ENV_PATH)
SH_TZ = timezone(timedelta(hours=8))
REDFOX_CACHE_LOCK = Lock()
REDFOX_CACHE_STORE = RawJsonCache(REDFOX_RAW_CACHE_FILE, max_entries=90)
LLM_SEMAPHORE = BoundedSemaphore(max(1, LLM_MAX_CONCURRENT_REQUESTS))
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
    return (shanghai_now() - timedelta(days=DOUYIN_DIGEST_OFFSET_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)


def is_today_digest():
    return digest_day().date() == shanghai_now().date()


def is_formal_run():
    return DAILY_RUN_MODE == "formal"


def compact_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def truncate(value, limit):
    value = compact_text(value)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def wait_until_send_time():
    wait_until_local_time(SEND_AT_LOCAL, shanghai_now, time.sleep, log_progress, strict=True)


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


def redfox_cache_key(payload):
    return shared_redfox_cache_key(payload)


def load_redfox_raw_cache():
    return REDFOX_CACHE_STORE.load()


def save_redfox_raw_cache(cache):
    REDFOX_CACHE_STORE.save(cache)


def get_redfox_raw_cache(payload, force_refresh=False):
    cache = load_redfox_raw_cache()
    record = cache.get(redfox_cache_key(payload))
    if not record or REDFOX_FORCE_REFRESH or force_refresh:
        return None
    cached_items = ((record.get("data") or {}).get("items") or [])
    if not cached_items:
        log_progress("redfox raw cache ignored empty items")
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
            "date": payload.get("startTime", ""),
            "type": payload.get("type", ""),
            "data": data,
        }
        save_redfox_raw_cache(cache)


def redfox_post_json(url, payload):
    return shared_redfox_post_json(
        url,
        payload,
        REDFOX_API_KEY,
        timeout=REDFOX_TIMEOUT_SECONDS,
        user_agent="Codex-DouyinDaily/0.1",
    )


def load_douyin_rank(force_refresh=False):
    if not REDFOX_API_KEY:
        raise RuntimeError("missing REDFOX_API_KEY")
    day = digest_day()
    payload = {
        "source": "抖音每日热门作品榜-GitHub",
        "startTime": day.strftime("%Y-%m-%d"),
        "endTime": day.strftime("%Y-%m-%d"),
        "_cache_url": REDFOX_DOUYIN_LIKES_RANK_URL,
    }
    if DOUYIN_CATEGORY != "全部":
        payload["type"] = DOUYIN_CATEGORY
    cached = get_redfox_raw_cache(payload, force_refresh=force_refresh)
    if cached is not None:
        items = cached.get("items", []) or []
        log_progress(f"redfox douyin cache hit items={len(items)}")
        return [normalize_item(item, index) for index, item in enumerate(items, start=1)]

    body = redfox_post_json(REDFOX_DOUYIN_LIKES_RANK_URL, payload)
    if body.get("code") != 2000:
        raise RuntimeError(f"RedFox Douyin API error: {body.get('msg') or body.get('code')}")
    items = body.get("data") or []
    if not isinstance(items, list):
        items = []
    if items:
        set_redfox_raw_cache(payload, {"items": items})
    else:
        log_progress("redfox douyin returned empty items, skip raw cache")
    log_progress(f"redfox douyin loaded items={len(items)}")
    return [normalize_item(item, index) for index, item in enumerate(items, start=1)]


def normalize_item(raw, index):
    return {
        "rank": int_value(raw.get("rank")) or index,
        "title": compact_text(raw.get("title")),
        "content": compact_text(raw.get("content")),
        "accountName": compact_text(raw.get("accountName")),
        "followerCount": int_value(raw.get("followerCount")),
        "category": compact_text(raw.get("category")) or "未分类",
        "collectCount": int_value(raw.get("collectCount")),
        "commentCount": int_value(raw.get("commentCount")),
        "shareCount": int_value(raw.get("shareCount")),
        "likeCount": int_value(raw.get("likeCount")),
        "publishTime": compact_text(raw.get("publishTime")),
        "workId": compact_text(raw.get("workId")),
        "workUrl": compact_text(raw.get("workUrl")),
    }


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
    if LLM_PROVIDER == "deepseek":
        api_keys = DEEPSEEK_API_KEYS
        base_url = DEEPSEEK_BASE_URL
        model = DEEPSEEK_MODEL
    else:
        api_keys = [OPENAI_API_KEY] if OPENAI_API_KEY else []
        base_url = "https://api.openai.com/v1"
        model = OPENAI_MODEL
    if not api_keys:
        raise RuntimeError("missing LLM API key")
    key = api_keys[int(time.time() * 1000) % len(api_keys)]
    start = time.time()
    with LLM_SEMAPHORE:
        text = chat_completion_text(
            base_url=base_url,
            api_key=key,
            model=model,
            messages=[
            {"role": "system", "content": "你是严谨的信息摘要助手，只根据输入内容总结，输出有效 JSON。"},
            {"role": "user", "content": prompt},
            ],
            timeout=LLM_TIMEOUT_SECONDS,
            temperature=0.2,
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
        "rank": item["rank"],
        "title": truncate(item["title"], 120),
        "content": truncate(item["content"], 240),
        "author": truncate(item["accountName"], 40),
        "category": item["category"],
        "likes": item["likeCount"],
        "comments": item["commentCount"],
        "shares": item["shareCount"],
        "collects": item["collectCount"],
        "publish_time": item["publishTime"],
    }


def fallback_digest(items):
    by_category = {}
    for item in items:
        by_category.setdefault(item["category"], 0)
        by_category[item["category"]] += 1
    category_text = "、".join(f"{name}{count}条" for name, count in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)[:6])
    hot_topics = []
    for name, count in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)[:8]:
        examples = [i for i in items if i["category"] == name][:4]
        example_text = "；".join((i["title"] or i["content"]) for i in examples)
        hot_topics.append(
            {
                "topic": name,
                "summary": f"该话题入榜 {count} 条，代表内容包括：{example_text[:220]}",
            }
        )
    return {
        "overview": f"昨日抖音点赞榜共收集 {len(items)} 条作品，主要集中在{category_text or '多个赛道'}。",
        "hot_topics": hot_topics,
    }


def build_llm_digest(items):
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEYS:
        return fallback_digest(items)
    if LLM_PROVIDER != "deepseek" and not OPENAI_API_KEY:
        return fallback_digest(items)
    payload = {
        "date": digest_day().strftime("%Y-%m-%d"),
        "category": DOUYIN_CATEGORY,
        "items": [item_for_llm(item) for item in items[:DOUYIN_LLM_INPUT_LIMIT]],
    }
    cached = get_cached_summary("douyin_daily_digest", payload)
    if cached:
        return cached
    prompt = (
        "请根据 RedFox 返回的抖音每日点赞榜，生成一份抖音日报摘要。你需要把热门作品聚合成读者真正关心的热点话题，而不是逐条罗列作品。\n"
        "只输出 JSON：{\"overview\":\"...\",\"hot_topics\":[{\"topic\":\"...\",\"summary\":\"...\",\"representative_ranks\":[1,2]}]}。\n"
        "要求：\n"
        "1. overview 用 2-3 句概括昨日抖音爆款内容主线，说明真正值得关注的社会情绪、公共事件或个人爆款。\n"
        "2. hot_topics 聚合 4-6 个热点话题，每条 110-190 字；话题名必须具体、通顺，像日报标题，不要只写原始赛道名。\n"
        "3. 话题优先级：宏观/公共事件、体育赛事、电竞赛事、教育/校园/就业等社会议题、个人情绪共鸣类爆款。\n"
        "4. 不要把明星个人营业、粉丝应援、纯搞笑、萌宠、日常情侣、低信息量模仿视频单独作为话题；它们只能在能说明平台情绪或传播机制时一笔带过。\n"
        "5. 每个话题要说明：包含哪些代表作品或共同内容、为什么容易传播、互动强度如何。提到具体作品时必须写明作者名，例如“基本祐利记录世界杯现场”，不要写“博主记录”“用户发布”这种空泛主体。只在 summary 自然表达，不要出现“代表：1,2”这种内部标注。\n"
        "6. 话题应尽量覆盖不同领域，不要把同一类娱乐/情绪内容占满全部位置。\n"
        "7. representative_ranks 填入该话题对应的输入 rank，最多 5 个，仅用于程序内部，不要在 summary 里展示。\n"
        "8. 不要编造输入以外的信息，不要写运营建议，不要逐条列出热门作品。\n"
        "输入 JSON：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    parsed = json_llm_response(
        prompt,
        "{\"overview\":\"...\",\"hot_topics\":[{\"topic\":\"...\",\"summary\":\"...\",\"representative_ranks\":[1,2]}]}",
    )
    result = {
        "overview": parsed.get("overview") if isinstance(parsed.get("overview"), str) else "",
        "hot_topics": parsed.get("hot_topics") if isinstance(parsed.get("hot_topics"), list) else [],
    }
    set_cached_summary("douyin_daily_digest", payload, result)
    return result


def markdown_escape(value):
    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def markdown_link(text, href):
    return f"[{markdown_escape(text)}]({href})"


def item_summary_by_rank(digest):
    result = {}
    for item in digest.get("items") or []:
        if not isinstance(item, dict):
            continue
        rank = int_value(item.get("rank"))
        summary = compact_text(item.get("summary"))
        if rank and summary:
            result[rank] = summary
    return result


def build_daily_lines(items):
    try:
        digest = build_llm_digest(items)
    except Exception as exc:
        log_progress(f"douyin llm summary failed, fallback to rule summary: {exc}")
        digest = fallback_digest(items)

    overview_lines = ["**昨日概览**", markdown_escape(digest.get("overview") or "暂无概览。")]

    topic_lines = ["**热点话题**"]
    topics = digest.get("hot_topics") or []
    skipped_topic_keywords = ("明星个人", "明星趣味", "粉丝应援", "明星营业")
    for topic in topics[:8]:
        if not isinstance(topic, dict):
            continue
        topic_name = compact_text(topic.get("topic"))
        summary = compact_text(topic.get("summary"))
        if any(keyword in topic_name for keyword in skipped_topic_keywords):
            continue
        if topic_name and summary:
            topic_lines.append("")
            topic_lines.append(f"<font color=\"blue\">**{markdown_escape(topic_name)}**</font>")
            topic_lines.append(markdown_escape(summary))
    if len(topic_lines) == 1:
        topic_lines.append("暂无可归纳热点话题。")

    return overview_lines, topic_lines


def send_feishu_card(webhook, sections, today):
    return push_send_feishu_card(webhook, f"{DOUYIN_DAILY_TITLE} {today}", sections)


def build_feishu_image_key(title, sections):
    if not FEISHU_IMAGE_DAILY_ENABLED:
        return ""
    if not (FEISHU_APP_ID and FEISHU_APP_SECRET):
        return ""
    if not (render_daily_image and upload_feishu_image and send_feishu_image):
        raise RuntimeError("daily image renderer unavailable")
    image_path = os.path.join(APP_DATA_DIR, f"douyin_daily_{digest_day().strftime('%Y-%m-%d')}.png")
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
    title = f"{DOUYIN_DAILY_TITLE} {today}"
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
    log_progress("start loading douyin daily rank")
    items = load_douyin_rank()
    log_progress(f"douyin rank loaded count={len(items)}")
    if RENDER_ONLY:
        if not render_daily_image:
            raise RuntimeError("daily image renderer unavailable")
        today = digest_day().strftime("%Y-%m-%d")
        title = f"{DOUYIN_DAILY_TITLE} {today}"
        sections = build_daily_lines(items)
        output_path = RENDER_OUTPUT or os.path.join(APP_DATA_DIR, f"douyin_daily_render_only_{today}.png")
        render_daily_image(title, sections, output_path)
        log_progress(f"render only output={output_path}")
        return
    if not items:
        wait_until_send_time()
        log_progress("douyin rank empty before send, force refresh")
        items = load_douyin_rank(force_refresh=True)
        log_progress(f"douyin rank refreshed count={len(items)}")
    else:
        wait_until_send_time()
    log_progress("sending notifications")
    send_notifications(items)
    log_progress("done")


if __name__ == "__main__":
    main()
