# Configuration

Each report is configured through environment variables. A script loads its
report-specific `.env` path when `*_DAILY_ENV` is set.

Do not commit real `.env` files. Use files under `examples/env/` as templates.

## Common Variables

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `deepseek` or `openai` |
| `DEEPSEEK_API_KEY` | Single DeepSeek API key |
| `DEEPSEEK_API_KEYS` | Comma-separated DeepSeek keys for concurrent calls |
| `DEEPSEEK_BASE_URL` | DeepSeek-compatible endpoint |
| `DEEPSEEK_MODEL` | Model name |
| `OPENAI_API_KEY` | OpenAI API key if using OpenAI |
| `OPENAI_MODEL` | OpenAI model name |
| `LLM_TIMEOUT_SECONDS` | Per-request timeout |
| `FEISHU_WEBHOOK` | Primary Feishu custom bot webhook |
| `FEISHU_WEBHOOKS` | Extra Feishu robots: `name|url|primary;name2|url2` |
| `WECHAT_WORK_WEBHOOK` | Primary WeCom robot webhook |
| `WECHAT_WORK_WEBHOOKS` | Extra WeCom robots |
| `PUSH_TARGETS` | `all` or `primary` |
| `FEISHU_APP_ID` | Feishu app ID for image upload |
| `FEISHU_APP_SECRET` | Feishu app secret for image upload |
| `FEISHU_IMAGE_DAILY_ENABLED` | `1` to send image reports where supported |
| `SEND_AT_LOCAL` | Local time to wait until before delivery |
| `DIGEST_DATE` | Force a report date, useful for testing |
| `RENDER_ONLY` | `1` renders an image without pushing |
| `RENDER_OUTPUT` | Output path for render-only image |

## AI Daily Deduplication

AI daily keeps a small local history file so repeated topics from RedFox-backed
feeds do not appear day after day. By default it looks back seven days and only
records reports that were actually pushed.

| Variable | Purpose |
| --- | --- |
| `AI_DEDUP_ENABLED` | `1` enables cross-day deduplication |
| `AI_DEDUP_LOOKBACK_DAYS` | Number of previous days to compare against |
| `AI_HISTORY_FILE` | Local JSON history file path |

## Report-Specific Env Files

- `AI_DAILY_ENV`
- `CCTV_DAILY_ENV`
- `DOUYIN_DAILY_ENV`
- `WECHAT_DAILY_ENV`
- `WEIBO_DAILY_ENV`
- `ZSXQ_DAILY_ENV`

## Credentials by Source

| Source | Required Credentials |
| --- | --- |
| Weibo blogger timelines | `WEIBO_COOKIE` or `WEIBO_COOKIE_FILE` |
| Knowledge Planet | `ZSXQ_COOKIE` or `ZSXQ_COOKIE_FILE` |
| RedFox-backed reports | `REDFOX_API_KEY` |
| Feishu image delivery | `FEISHU_APP_ID`, `FEISHU_APP_SECRET` |
| LLM summaries | DeepSeek or OpenAI-compatible key |

## Render-Only Testing

Render-only mode is the safest way to test formatting and content:

```bash
python3 -m daily_briefing.cli run cctv \
  --env work/cctv_daily/.env \
  --render-only \
  --date 2026-06-13 \
  --output /tmp/report.png
```

No robot message should be sent in render-only mode.
