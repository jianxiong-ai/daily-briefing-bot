from daily_briefing.reports import REPORTS


LLM_FIELDS = [
    {
        "key": "DEEPSEEK_API_KEYS",
        "label": "DeepSeek API Keys",
        "type": "password",
        "placeholder": "请输入",
        "required": True,
        "help": "用于日报内容总结；配置多个 key 时，原脚本会轮询使用。",
    },
    {
        "key": "DEEPSEEK_MODEL",
        "label": "DeepSeek 模型",
        "type": "text",
        "placeholder": "请输入",
        "help": "可留空使用脚本默认值。",
    },
]

REDFOX_FIELD = {
    "key": "REDFOX_API_KEY",
    "label": "RedFox API Key",
    "type": "password",
    "placeholder": "请输入",
    "required": True,
    "help": "用于获取 RedFox 数据源内容。",
}


REPORT_TITLES = {
    "ai": "AI 领域日报",
    "astock": "A 股日报",
    "cctv": "朝闻天下日报",
    "douyin": "抖音日报",
    "wechat": "公众号日报",
    "weibo": "微博日报",
    "zsxq": "知识星球日报",
}


# 数据窗口模型：描述每个日报抓取的数据范围，以及与之匹配的推荐推送时段。
# 推送时间和数据窗口强相关，落在推荐区间外通常意味着数据为空或已过时。
WINDOW_PREV_DAY = {
    "model": "prev_day",
    "summary": "抓取前一天全天数据，建议早晨推送。",
    "recommended_start": "05:00",
    "recommended_end": "12:00",
}
WINDOW_TODAY_MORNING = {
    "model": "today_morning",
    "summary": "抓取当天早间节目内容，建议上午推送。",
    "recommended_start": "06:30",
    "recommended_end": "12:00",
}
WINDOW_TODAY_REALTIME = {
    "model": "today_realtime",
    "summary": "聚合当天实时数据，需等全天数据攒满，建议夜间推送。",
    "recommended_start": "20:00",
    "recommended_end": "23:59",
}


REPORT_WINDOWS = {
    "ai": dict(WINDOW_PREV_DAY),
    "astock": dict(WINDOW_PREV_DAY),
    "douyin": dict(WINDOW_PREV_DAY),
    "wechat": dict(WINDOW_PREV_DAY),
    "cctv": dict(WINDOW_TODAY_MORNING),
    "weibo": {
        **WINDOW_TODAY_REALTIME,
        "needs_hot_collector": True,
        "collector_interval_minutes": 30,
        "summary": "聚合当天热搜+关注博主，热搜依赖全天采集，建议夜间推送。",
    },
    "zsxq": dict(WINDOW_TODAY_REALTIME),
}


REPORT_FIELDS = {
    "ai": [
        REDFOX_FIELD,
        *LLM_FIELDS,
    ],
    "astock": [
        REDFOX_FIELD,
        *LLM_FIELDS,
    ],
    "cctv": [
        *LLM_FIELDS,
    ],
    "douyin": [
        REDFOX_FIELD,
        *LLM_FIELDS,
    ],
    "wechat": [
        REDFOX_FIELD,
        *LLM_FIELDS,
        {
            "key": "WECHAT_FOLLOW_AUTHORS",
            "label": "关注公众号",
            "type": "textarea",
            "placeholder": "请输入",
            "group": "follow",
            "help": "选填，留空则不展示关注作者模块。优先填写公众号名称；如已知 account，可用 公众号名称|account。多个用分号或换行分隔。",
        },
    ],
    "weibo": [
        *LLM_FIELDS,
        {
            "key": "WEIBO_COOKIE",
            "label": "微博 Cookie",
            "type": "textarea",
            "placeholder": "请输入",
            "group": "follow",
            "recommended": True,
            "help": "关注博主模块所需；留空则只输出热搜。后台会保存成私密 cookie 文件供脚本读取。",
        },
        {
            "key": "WEIBO_BLOGGER_IDS",
            "label": "关注博主 UID",
            "type": "textarea",
            "placeholder": "请输入",
            "group": "follow",
            "recommended": True,
            "help": "选填，留空则不展示关注博主模块。多个 UID 用英文逗号、分号或换行分隔。",
        },
    ],
    "zsxq": [
        *LLM_FIELDS,
        {
            "key": "ZSXQ_COOKIE",
            "label": "知识星球 Cookie",
            "type": "textarea",
            "placeholder": "请输入",
            "required": True,
            "help": "知识星球日报必需；直接粘贴登录态，后台会保存成私密 cookie 文件供脚本读取。",
        },
        {
            "key": "ZSXQ_GROUP_ID",
            "label": "圈子 ID",
            "type": "text",
            "placeholder": "请输入",
            "required": True,
        },
        {"key": "ZSXQ_GROUP_NAME", "label": "圈子名称", "type": "text", "placeholder": "请输入"},
        {
            "key": "ZSXQ_INCLUDE_USER_IDS",
            "label": "额外精选用户 ID",
            "type": "textarea",
            "placeholder": "请输入",
            "group": "follow",
            "help": "选填，留空则不额外精选用户。多个 user id 用英文逗号分隔。",
        },
    ],
}


def report_options():
    items = []
    for name, report in REPORTS.items():
        items.append(
            {
                "name": name,
                "title": REPORT_TITLES.get(name, report.title),
                "default_env": str(report.default_env),
                "fields": REPORT_FIELDS.get(name, []),
                "window": REPORT_WINDOWS.get(name, {}),
            }
        )
    return items
