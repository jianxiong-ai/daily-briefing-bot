# CCTV 朝闻天下日报

每天抓取央视《朝闻天下》当天节目列表，按新闻早报格式总结后推送到飞书和企业微信机器人。

- 正式定时：08:20 启动，08:30 推送。
- 正式推送：`PUSH_TARGETS=all`。
- 测试推送：工作区 `.env` 默认为 `PUSH_TARGETS=primary`。
- 数据源：`https://api.cntv.cn/NewVideo/getVideoListByColumn`，栏目 ID `TOPC1451558496100826`。
