# Architecture

Daily Briefing Bot is organized as a set of report-specific scripts plus a small
shared rendering layer.

## Layers

1. **Schedule Layer**
   - macOS `launchd` starts each report script a few minutes before the desired
     delivery time.
   - Each script can also wait until `SEND_AT_LOCAL` before pushing.

2. **Data Layer**
   - Source adapters fetch data from Weibo, Knowledge Planet, CCTV, RedFox, or
     other configured endpoints.
   - Paid or rate-limited APIs use raw-response caches where possible.

3. **Processing Layer**
   - Cleans HTML, markdown-like fragments, source metadata, and noisy records.
   - Deduplicates and ranks records.
   - Groups related items into topics or sections.
   - Builds fallback summaries when an LLM request fails.

4. **Summary Layer**
   - Calls an LLM provider, usually DeepSeek or OpenAI-compatible endpoints.
   - Supports multiple API keys, request timeouts, and summary caches.
   - Uses report-specific prompts to produce concise daily briefings.

5. **Delivery Layer**
   - Renders image reports with `work/daily_image.py`.
   - Sends images or markdown cards to Feishu.
   - Sends markdown text to WeCom.
   - Supports `PUSH_TARGETS=primary` for test or limited delivery.

## Report Modules

- `work/weibo_daily`: Weibo hot-topic and blogger digest.
- `work/zsxq_daily`: Knowledge Planet group digest.
- `work/cctv_daily`: CCTV `朝闻天下` digest.
- `work/wechat_daily`: WeChat official account hot and followed-author digest.
- `work/douyin_daily`: Douyin hot works digest.
- `work/ai_daily`: AI-industry digest from RedFox-backed feeds.

## Current Refactor Opportunities

The scripts intentionally started independently. The next cleanup step is to
extract duplicated code into shared modules:

- Env loading and validation
- LLM client and cache
- RedFox client and cache
- Feishu/WeCom push clients
- launchd template generation
- report section data model
