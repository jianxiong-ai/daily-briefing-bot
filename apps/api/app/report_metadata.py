from daily_briefing.reports import REPORTS


REPORT_FIELDS = {
    "ai": [
        {"key": "AI_XHS_KEYWORD", "label": "小红书关键词", "type": "text", "placeholder": "AI"},
        {"key": "AI_TOPIC_LIMIT", "label": "主题数量", "type": "number", "placeholder": "8"},
    ],
    "astock": [
        {"key": "ASTOCK_TOPIC_LIMIT", "label": "主题数量", "type": "number", "placeholder": "7"},
        {"key": "ASTOCK_SOCIAL_LIMIT", "label": "社媒候选数量", "type": "number", "placeholder": "45"},
    ],
    "cctv": [
        {"key": "CCTV_DIGEST_OFFSET_DAYS", "label": "日期偏移天数", "type": "number", "placeholder": "0"},
    ],
    "douyin": [
        {"key": "DOUYIN_CATEGORY", "label": "抖音分类", "type": "text", "placeholder": "全部"},
        {"key": "DOUYIN_REPORT_LIMIT", "label": "作品候选数量", "type": "number", "placeholder": "15"},
    ],
    "wechat": [
        {
            "key": "WECHAT_FOLLOW_AUTHORS",
            "label": "关注公众号",
            "type": "textarea",
            "placeholder": "都市快报|dskbdskb;财联社|cls-telegraph",
            "help": "格式：公众号名称|account；多个用分号分隔。",
        },
        {"key": "WECHAT_DAILY_KEYWORD", "label": "热门文章关键词", "type": "text", "placeholder": "可留空"},
        {"key": "WECHAT_HOT_REPORT_LIMIT", "label": "热门文章数量", "type": "number", "placeholder": "10"},
    ],
    "weibo": [
        {
            "key": "WEIBO_BLOGGER_IDS",
            "label": "关注博主 UID",
            "type": "textarea",
            "placeholder": "1763864272,1906286443",
            "help": "多个 UID 用英文逗号分隔。",
        },
        {"key": "WEIBO_COOKIE_FILE", "label": "微博 Cookie 文件", "type": "text", "placeholder": "work/weibo_daily/weibo.cookie"},
        {"key": "WEIBO_FETCH_WORKERS", "label": "抓取并发数", "type": "number", "placeholder": "8"},
    ],
    "zsxq": [
        {"key": "ZSXQ_GROUP_ID", "label": "圈子 ID", "type": "text", "placeholder": "458522225218"},
        {"key": "ZSXQ_GROUP_NAME", "label": "圈子名称", "type": "text", "placeholder": "知识星球"},
        {"key": "ZSXQ_COOKIE_FILE", "label": "知识星球 Cookie 文件", "type": "text", "placeholder": "work/zsxq_daily/zsxq.cookie"},
        {
            "key": "ZSXQ_INCLUDE_USER_IDS",
            "label": "额外精选用户 ID",
            "type": "textarea",
            "placeholder": "145548258122,844188812841442",
            "help": "多个 user id 用英文逗号分隔。",
        },
    ],
}


def report_options():
    items = []
    for name, report in REPORTS.items():
        items.append(
            {
                "name": name,
                "title": report.title,
                "default_env": str(report.default_env),
                "fields": REPORT_FIELDS.get(name, []),
            }
        )
    return items
