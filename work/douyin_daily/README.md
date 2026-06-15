# 抖音日报

基于 RedFox `douyin-daily-hot` skill 的抖音每日点赞榜数据生成日报。

## 数据来源

- 接口：`POST https://redfox.hk/story/api/dy/search/likesRank`
- 默认日期：昨日数据，RedFox 文档说明每日 06:00 更新昨日榜单
- 默认赛道：`全部`
- 默认推送：每日 08:15

## 推送内容

- 昨日概览：总结全榜内容主线和传播特点
- 赛道趋势：按赛道归纳热门内容方向
- 热门作品：展示 Top 作品、作者、赛道、互动数据和摘要

## 成本控制

- 同一日期、同一赛道的 RedFox 原始结果会写入 `redfox_raw_cache.json`
- 测试当天重复执行优先复用 1 小时内缓存
- 正式任务查询当天日期时会跳过今日缓存；默认查询昨日，不影响正式推送
- LLM 摘要写入 `llm_summary_cache.jsonl`

## 手动测试

```bash
PYTHONPYCACHEPREFIX=/private/tmp/douyin_pycache \
DOUYIN_DAILY_ENV=work/douyin_daily/.env \
DIGEST_DATE=2026-06-12 \
PUSH_TARGETS=primary \
SEND_AT_LOCAL= \
python3 work/douyin_daily/douyin_daily.py
```
