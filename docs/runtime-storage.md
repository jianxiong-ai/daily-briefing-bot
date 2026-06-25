# Runtime Storage

The repository contains code and local `.env` files. Generated runtime data lives
outside the repository so normal runs do not dirty the Git worktree.

## Directory layout

```text
~/Library/Application Support/DailyBriefingBot/
  ai/
  cctv/
  douyin/
  wechat/
  weibo/
  zsxq/
    cache/   # API responses and LLM summary caches
    images/  # rendered daily report images
    state/   # cookies, histories, and durable archives

~/Library/Logs/DailyBriefingBot/
  ai/
  cctv/
  douyin/
  wechat/
  weibo/
  zsxq/
```

The paths can be overridden with:

- `DAILY_BRIEFING_DATA_ROOT`
- `DAILY_BRIEFING_LOG_ROOT`
- `DAILY_RUNTIME_DIR`
- `DAILY_CACHE_DIR`
- `DAILY_IMAGE_DIR`
- `DAILY_STATE_DIR`
- `DAILY_LOG_DIR`

## Cleanup policy

Run cleanup manually with:

```bash
python3 -m daily_briefing.cli cleanup wechat
```

Installed launchd wrappers run the same lightweight cleanup before generating a
daily report.

Default policy:

- rendered PNG images: 14 days
- temporary files: 2 days
- archived logs and backups: 30 days
- active log files: trimmed to the newest 2 MiB after reaching 10 MiB
- LLM JSONL cache: compacted to records from the latest 7 days
- raw JSON API caches: bounded by each cache's existing maximum entry count
- `state/`: never removed automatically

Cookies, collection histories, and durable archives belong in `state/`. They
must not be placed in `cache/`, because cache files may be compacted or rebuilt.
