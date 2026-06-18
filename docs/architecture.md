# Architecture

Daily Briefing Bot is organized as a thin CLI, report-specific scripts, and a
small shared core for runtime helpers and image rendering.

## Layers

1. **Schedule Layer**
   - macOS `launchd` can call `python3 -m daily_briefing.cli run <report>`.
   - The CLI sets report-specific env paths and common runtime flags.
   - Reports can still wait until `SEND_AT_LOCAL` before pushing.

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

## Shared Core

- `daily_briefing.cli`: the recommended command-line entrypoint for listing and
  running reports.
- `daily_briefing.reports`: registry of report names, scripts, default env files,
  and example env templates.
- `daily_briefing.runtime`: shared helpers for `.env` loading, robot list parsing,
  primary-target selection, boolean parsing, and local send-time waiting.
- `daily_briefing.push`: shared Feishu card/image message helpers, WeCom markdown
  formatting, truncation, and push-result aggregation primitives.
- `daily_briefing.llm`: shared LLM primitives for API key rotation, cache keys,
  JSONL summary cache, and OpenAI-compatible chat-completion requests.
- `daily_briefing.redfox`: shared RedFox POST helper, public-payload filtering,
  stable raw-cache keys, and bounded JSON cache storage.
- `work/daily_image.py`: shared image report renderer and Feishu image helpers.

## Report Modules

- `work/weibo_daily`: Weibo hot-topic and blogger digest.
- `work/zsxq_daily`: Knowledge Planet group digest.
- `work/cctv_daily`: CCTV `朝闻天下` digest.
- `work/wechat_daily`: WeChat official account hot and followed-author digest.
- `work/douyin_daily`: Douyin hot works digest.
- `work/ai_daily`: AI-industry digest from RedFox-backed feeds.

## Current Refactor Opportunities

The scripts intentionally started independently. CLI routing, runtime helpers,
push helpers, LLM primitives, and RedFox request/cache helpers have now been
extracted. The remaining cleanup opportunities are:

- Continue adopting shared LLM primitives in the larger WeChat, Weibo, and ZSXQ
  scripts where it can be done without changing report output.
- Further reduce duplicated notification-loop error handling.
- launchd template generation
- report section data model
