# A股日报

数据来源：

- RedFox `multiPlatform/workSearch`：一次获取公众号、小红书和抖音的 A 股相关讨论。
- RedFox `gzh/search/dailyPublish`：一次批量获取固定官媒、机构和个人大 V 的目标日文章。

日报板块：

- 市场概览
- 热点主题
- 机构与大 V 观点
- 风险观察

默认只进行两次 RedFox 请求。`ai-intelligence-investigator` 不进入日常全量流程，
后续仅适合作为重大事件的按需交叉验证能力。

运行：

```bash
python3 -m daily_briefing.cli run astock --env work/astock_daily/.env \
  --date 2026-06-24 --render-only --output /tmp/astock.png
```

报告严格区分事实与观点，不生成买卖、仓位或收益建议。
