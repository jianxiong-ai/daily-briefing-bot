# ZSXQ Daily Digest

Daily digest for one Knowledge Planet group, pushed to a Feishu custom bot.

## Output

- `精选内容`: each selected/essence item is summarized separately.
- `话题总结`: all daily items are grouped by tags or inferred themes, then summarized by topic instead of by author.

## Performance

- Topic list pagination is controlled by `ZSXQ_FETCH_PAGES` and `ZSXQ_PAGE_SIZE`.
- Topic detail backfill runs concurrently with `ZSXQ_DETAIL_WORKERS`.
- DeepSeek/OpenAI summaries are split into batches using `LLM_BATCH_SIZE`.
- LLM batches run concurrently with `LLM_BATCH_WORKERS`.
- Each LLM request is limited by `LLM_TIMEOUT_SECONDS`; failed batches fall back to rule summaries.

## Required Config

Create `.env` from `.env.example`:

```bash
cp work/zsxq_daily/.env.example work/zsxq_daily/.env
```

Then set:

- `FEISHU_WEBHOOK`
- `ZSXQ_GROUP_ID`
- `ZSXQ_COOKIE_FILE` or `ZSXQ_COOKIE`
- `DEEPSEEK_API_KEY`

## Run

```bash
ZSXQ_DAILY_ENV="work/zsxq_daily/.env" python3 work/zsxq_daily/zsxq_daily.py
```

For a fixed date:

```bash
DIGEST_DATE="2026-06-11" ZSXQ_DAILY_ENV="work/zsxq_daily/.env" python3 work/zsxq_daily/zsxq_daily.py
```
