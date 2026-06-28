from daily_briefing.reports import REPORTS


LLM_FIELDS = [
    {
        "key": "DEEPSEEK_API_KEYS",
        "label": "DeepSeek API Keys",
        "type": "password",
        "placeholder": "请输入",
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
            "help": "优先填写公众号名称；如已知 account，可用 公众号名称|account。多个用分号或换行分隔。",
        },
    ],
    "weibo": [
        *LLM_FIELDS,
        {
            "key": "WEIBO_COOKIE",
            "label": "微博 Cookie",
            "type": "textarea",
            "placeholder": "请输入",
            "help": "直接粘贴微博登录态；后台会保存成私密 cookie 文件供脚本读取。",
        },
        {
            "key": "WEIBO_BLOGGER_IDS",
            "label": "关注博主 UID",
            "type": "textarea",
            "placeholder": "请输入",
            "help": "多个 UID 用英文逗号、分号或换行分隔。",
        },
    ],
    "zsxq": [
        *LLM_FIELDS,
        {
            "key": "ZSXQ_COOKIE",
            "label": "知识星球 Cookie",
            "type": "textarea",
            "placeholder": "请输入",
            "help": "直接粘贴知识星球登录态；后台会保存成私密 cookie 文件供脚本读取。",
        },
        {"key": "ZSXQ_GROUP_ID", "label": "圈子 ID", "type": "text", "placeholder": "请输入"},
        {"key": "ZSXQ_GROUP_NAME", "label": "圈子名称", "type": "text", "placeholder": "请输入"},
        {
            "key": "ZSXQ_INCLUDE_USER_IDS",
            "label": "额外精选用户 ID",
            "type": "textarea",
            "placeholder": "请输入",
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
                "title": REPORT_TITLES.get(name, report.title),
                "default_env": str(report.default_env),
                "fields": REPORT_FIELDS.get(name, []),
            }
        )
    return items
