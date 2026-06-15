# Weibo Daily Digest

Daily digest for Weibo hot search Top 20 and selected bloggers.

## Inputs

- `FEISHU_WEBHOOK`: Feishu custom bot webhook URL.
- `RSSHUB_BASE`: Optional RSSHub instance, default `https://rsshub.app`.
- `WEIBO_COOKIE`: Optional Weibo login cookie for blogger timelines.
- `WEIBO_COOKIE_FILE`: Optional path to a local file containing the Weibo login cookie.

## Bloggers

- `1906286443`
- `1111681197`
- `1747780592`
- `1192966660`
- `7827771738`
- `6420726021`
- `1775948951`
- `5167198527`
- `1044980795`
- `1989660417`
- `2803301701`

`6420726021` appeared twice in the original list and is deduplicated here.

## Run

```bash
FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/..." \
WEIBO_COOKIE_FILE="work/weibo_daily/weibo.cookie" \
python3 work/weibo_daily/weibo_daily.py
```

The script fetches RSSHub feeds and sends a Feishu rich-text message. For high-quality "summary of key points", run it from a Codex automation prompt that summarizes the fetched items before calling the sender, or extend the script with an LLM API call.

Weibo hot search can usually be fetched anonymously. Blogger timelines often require a logged-in Weibo cookie because public RSSHub instances and anonymous mobile APIs are frequently blocked by Weibo.
