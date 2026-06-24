import re


def normalize_text(value):
    value = re.sub(r"\s+", "", value or "")
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "", value)
    return value.lower()


def char_ngrams(value, n=2):
    text = normalize_text(value)
    if not text:
        return set()
    if len(text) <= n:
        return {text}
    return {text[index : index + n] for index in range(len(text) - n + 1)}


def text_similarity(left, right):
    left_tokens = char_ngrams(left)
    right_tokens = char_ngrams(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def text_containment(left, right):
    left_tokens = char_ngrams(left)
    right_tokens = char_ngrams(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def is_similar_event(left_title, left_text, right_title, right_text):
    left_title_tokens = char_ngrams(left_title)
    right_title_tokens = char_ngrams(right_title)
    shared_title_tokens = left_title_tokens & right_title_tokens
    title_containment = text_containment(left_title, right_title)
    if title_containment >= 0.38 and len(shared_title_tokens) >= 3:
        return True

    body_containment = text_containment(
        f"{left_title} {left_text}",
        f"{right_title} {right_text}",
    )
    return len(shared_title_tokens) >= 3 and body_containment >= 0.15


def dedupe_by_similarity(items, key, threshold=0.72):
    kept = []
    seen_values = []
    for item in items:
        value = key(item) if callable(key) else item.get(key, "")
        if any(text_similarity(value, old) >= threshold for old in seen_values):
            continue
        kept.append(item)
        seen_values.append(value)
    return kept


BROAD_WEATHER_TERMS = (
    "全国",
    "中央气象",
    "中国天气",
    "华北",
    "华东",
    "华南",
    "华中",
    "西南",
    "西北",
    "东北",
    "江南",
    "长江",
    "黄淮",
    "气候",
    "台风",
    "厄尔尼诺",
    "拉尼娜",
)

LOCAL_WEATHER_TERMS = (
    "天气",
    "暴雨",
    "强降雨",
    "大暴雨",
    "雷雨",
    "降水",
    "洪水",
    "地质灾害",
    "列车停运",
    "高温",
)


def is_local_weather_noise(text, allowed_regions=()):
    value = text or ""
    if not any(term in value for term in LOCAL_WEATHER_TERMS):
        return False
    if any(term in value for term in BROAD_WEATHER_TERMS):
        return False
    if any(region and region in value for region in allowed_regions):
        return False
    return True


LOW_PRIORITY_TOPIC_TERMS = (
    "多领域问答",
    "问答汇总",
    "音频合集",
    "文章音频合集",
    "过往帖子",
    "索引",
)


def low_priority_topic_sort_key(item):
    topic = item.get("topic", "") if isinstance(item, dict) else str(item or "")
    return 1 if any(term in topic for term in LOW_PRIORITY_TOPIC_TERMS) else 0
