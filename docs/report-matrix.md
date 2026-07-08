# Report Matrix

This project currently contains seven report modules. Each module can be run with
the unified CLI:

```bash
python3 -m daily_briefing.cli run <report-name> --env path/to/.env
```

Use render-only mode before enabling robot delivery:

```bash
python3 -m daily_briefing.cli run <report-name> \
  --env path/to/.env \
  --render-only \
  --output /tmp/report.png
```

## Reports

| Report | CLI name | Script | Main inputs | Typical output |
| --- | --- | --- | --- | --- |
| AI Industry Daily | `ai` | `work/ai_daily/ai_daily.py` | AIHot selected feed, RedFox AI Xiaohongshu feed, LLM | AI topic clusters and source highlights |
| CCTV Morning News Daily | `cctv` | `work/cctv_daily/cctv_daily.py` | CCTV program page, article pages, LLM | Morning news overview, key stories, section summaries |
| Douyin Hot Works Daily | `douyin` | `work/douyin_daily/douyin_daily.py` | RedFox Douyin hot works feed, LLM | Hot-topic clusters from daily viral videos |
| A-Share Market Daily | `astock` | `work/astock_daily/astock_daily.py` | RedFox multi-platform A-share search, A-share publisher feed, LLM | Market themes, institution/KOL viewpoints, and information-risk flags |
| WeChat Official Account Daily | `wechat` | `work/wechat_daily/wechat_daily.py` | RedFox public account APIs, configured followed accounts, LLM | Hot public-account articles and followed-account summaries |
| Weibo Daily | `weibo` | `work/weibo_daily/weibo_daily.py` | Weibo hot search feeds, followed bloggers, optional cookie, LLM | Hot-search overview and followed blogger activity |
| Knowledge Planet Daily | `zsxq` | `work/zsxq_daily/zsxq_daily.py` | Knowledge Planet group APIs, cookie, LLM | Digest posts, selected authors, topic clusters |

## Configuration Files

| Report | Env var | Example template |
| --- | --- | --- |
| `ai` | `AI_DAILY_ENV` | `examples/env/ai_daily.env.example` |
| `cctv` | `CCTV_DAILY_ENV` | `examples/env/cctv_daily.env.example` |
| `douyin` | `DOUYIN_DAILY_ENV` | `examples/env/douyin_daily.env.example` |
| `wechat` | `WECHAT_DAILY_ENV` | `examples/env/wechat_daily.env.example` |
| `weibo` | `WEIBO_DAILY_ENV` | `examples/env/weibo_daily.env.example` |
| `zsxq` | `ZSXQ_DAILY_ENV` | `examples/env/zsxq_daily.env.example` |

The CLI also accepts `--env`, which sets the correct report-specific env var for
the current process.

## Runtime Modes

| Mode | How to run | Purpose |
| --- | --- | --- |
| Render only | `--render-only --output /tmp/report.png` | Generate an image without sending robot messages |
| Historical date | `--date YYYY-MM-DD` | Rebuild a report for a specific local date |
| Primary robots | `--push-targets primary` | Send only to targets marked as primary, useful for tests |
| All robots | `--push-targets all` | Send to all configured targets |

## Scheduling Status

The repository supports two scheduling styles:

- The subscription dashboard runs schedules inside the FastAPI process and
  stores encrypted subscription config in SQLite.
- macOS `launchd` templates are available for users who prefer local
  script-first automation.

Real credentials, cookies, and robot targets should stay in local `.env` files,
dashboard subscriptions, or host-level secret storage outside git.

Suggested schedule conventions:

| Report | Suggested time | Notes |
| --- | --- | --- |
| `ai` | Morning | Uses prior-day public feed data |
| `wechat` | Morning | RedFox public-account data may update after source processing completes |
| `cctv` | Morning | Depends on CCTV page availability |
| `zsxq` | Evening | Best after the group has accumulated most daily activity |
| `weibo` | Evening or disabled | Hot-search collection can be run separately from final delivery |
| `douyin` | Optional | Enable only when source data quality is stable for your use case |

## Adding a Report

1. Add the report script under `work/<name>/`.
2. Add an env template under `examples/env/`.
3. Register it in `daily_briefing/reports.py`.
4. Add smoke-test coverage for the script and env template.
5. Document required credentials in `docs/configuration.md`.
