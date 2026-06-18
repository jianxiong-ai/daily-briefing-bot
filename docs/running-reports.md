# Running Reports

The repository keeps each report as a standalone script, but the recommended
entry point is the lightweight CLI wrapper:

```bash
daily-briefing list
```

If the package is not installed, use `python3 -m daily_briefing.cli list` from
the repository root.

## Render Without Sending

Render-only mode is the safest way to inspect output before configuring robot
delivery:

```bash
daily-briefing run wechat \
  --env work/wechat_daily/.env \
  --render-only \
  --date 2026-06-13 \
  --output /tmp/wechat_daily.png
```

This sets `RENDER_ONLY=1` and should not send Feishu or WeCom messages.

## Run a Formal Report

After filling the env file:

```bash
daily-briefing run cctv \
  --env work/cctv_daily/.env \
  --push-targets primary
```

Use `--push-targets all` only after the primary robot output looks correct.

## Skip Waiting During Manual Tests

Some scripts support `SEND_AT_LOCAL` and wait until the configured delivery
time. To avoid waiting during a manual run:

```bash
daily-briefing run cctv \
  --env work/cctv_daily/.env \
  --send-at "" \
  --render-only \
  --output /tmp/cctv_daily.png
```

## Available Report Names

For data sources, env variables, and scheduling notes, see the
[Report Matrix](report-matrix.md).

| Name | Report |
| --- | --- |
| `ai` | AI industry briefing |
| `cctv` | CCTV `朝闻天下` briefing |
| `douyin` | Douyin hot works briefing |
| `wechat` | WeChat official account briefing |
| `weibo` | Weibo briefing |
| `zsxq` | Knowledge Planet briefing |

## Direct Script Execution

Direct script execution is still supported for compatibility:

```bash
WECHAT_DAILY_ENV=work/wechat_daily/.env \
RENDER_ONLY=1 \
python3 work/wechat_daily/wechat_daily.py
```

Prefer the CLI in documentation and examples because it keeps common flags
consistent across reports.
