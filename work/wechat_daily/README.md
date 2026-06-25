# 昨日公众号信息汇总

第一版使用 RedFox `hotArticle` 接口抓取公众号热门文章：

- 数据源：`POST https://redfox.hk/story/api/gzh/search/hotArticle`
- 默认范围：`DIGEST_DATE` 当天到次日
- 默认内容：一次请求 50 条候选文章，本地重排后展示 Top 10
- 选文策略：宏观议题优先，尽量覆盖国际、宏观经济、科技产业、社会公共、文化体育等不同领域；娱乐八卦、装修纠纷、强商业消费内容会降权。
- 成本策略：历史日期的 RedFox 原始响应会缓存到本地；当天数据测试时 1 小时内复用缓存，正式推送可通过 `DAILY_RUN_MODE=formal` 强制刷新当天数据。
- 板块：昨日概览、昨日热门、关注作者。
- 推送：复用现有飞书图片版、飞书文本兜底、企业微信 Markdown

## 常用命令

```bash
WECHAT_DAILY_ENV=work/wechat_daily/.env PUSH_TARGETS=primary SEND_AT_LOCAL= python3 work/wechat_daily/wechat_daily.py
```

指定日期测试：

```bash
WECHAT_DAILY_ENV=work/wechat_daily/.env DIGEST_DATE=2026-06-12 PUSH_TARGETS=primary SEND_AT_LOCAL= python3 work/wechat_daily/wechat_daily.py
```

## 主要配置

- `REDFOX_API_KEY`：RedFox API Key。
- `WECHAT_DAILY_KEYWORD`：关键词，留空为全站热门。
- `WECHAT_HOT_REPORT_LIMIT`：日报展示文章数，默认 10。
- `WECHAT_HOT_CANDIDATE_LIMIT`：本地候选文章数，默认 50。
- `WECHAT_FOLLOW_AUTHORS`：关注作者列表，分号分隔；格式为 `公众号账号|展示名`，只有一个字段时同时作为账号和展示名。
- `WECHAT_FOLLOW_ARTICLE_LIMIT`：关注作者文章候选数，默认 30。
- `WECHAT_FOLLOW_AUTHOR_LIMIT`：最多查询的关注作者数，默认 20。
- `WECHAT_FOLLOW_FETCH_WORKERS`：关注作者抓取并发数，默认 4。
- `WECHAT_FOLLOW_MAX_PAGES`：关注作者每人最多翻页数，默认 2。第一页 `hasMore=1` 或 `total > list` 时才请求第二页。
- `WECHAT_DIGEST_OFFSET_DAYS`：未显式传 `DIGEST_DATE` 时的日期偏移；设为 1 表示默认抓昨天。
- `WECHAT_MIN_READS`：最低阅读量，默认 5000。
- `WECHAT_MIN_HOT_ARTICLES`：完整日报要求的最低热门文章数，默认 6。
- `WECHAT_REQUIRE_FOLLOW_CONTENT`：配置关注作者时是否要求至少抓到一篇文章，默认开启。
- `WECHAT_SOURCE_RETRY_ATTEMPTS`：数据源不完整时最多抓取次数，默认 3 次。
- `WECHAT_SOURCE_RETRY_DELAY_SECONDS`：不完整数据重试间隔，默认 600 秒。
- `WECHAT_DAILY_TITLE`：日报标题，默认 `昨日公众号信息汇总`。
- `REDFOX_PAGE_SIZE`：RedFox 单次请求条数，默认不低于 50。
- `REDFOX_RAW_CACHE_FILE`：RedFox 原始响应缓存路径，默认 `work/wechat_daily/redfox_raw_cache.json`。
- `REDFOX_FORCE_REFRESH=1`：强制绕过 RedFox 缓存，重新请求接口。
- `REDFOX_TODAY_CACHE_TTL_SECONDS`：当天测试缓存有效期，默认 3600 秒。
- `REDFOX_TIMEOUT_SECONDS`：RedFox 接口请求超时，默认 90 秒。
- `DAILY_RUN_MODE=formal`：正式推送模式。当天数据会绕过缓存重新请求 RedFox，历史日期仍可用缓存。

正式任务会先检查数据完整度。热门数量不足时不会立即查询全部关注作者，
而是等待 RedFox 完成昨日数据更新后重试；关注作者全部返回 0 时也会强制
刷新。多次重试后仍不完整则退出并触发失败告警，不发送残缺日报。

默认只读取 `work/wechat_daily/.env`，公众号日报的 RedFox、LLM、飞书、企业微信配置都放在这个文件里。若临时需要共享其他日报配置，可显式设置 `SHARED_DAILY_ENV=/path/to/.env`。
