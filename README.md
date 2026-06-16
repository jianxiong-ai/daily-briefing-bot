# Daily Briefing Bot

Daily Briefing Bot is a configurable AI-powered briefing system. It collects
signals from social media, creator communities, news programs, official feeds,
and third-party data APIs, summarizes them with an LLM, renders mobile-friendly
daily report images, and pushes the result to Feishu or WeCom robots.

This repository started as a personal automation project and is being cleaned up
into a reusable open-source tool. The current code is script-first and macOS
friendly; the roadmap is to extract more shared libraries and add more portable
deployment options.

## Features

- Multi-source daily reports:
  - Weibo hot topics and followed bloggers
  - Knowledge Planet group summaries
  - CCTV `朝闻天下`
  - WeChat official account hot articles and followed accounts
  - Douyin daily hot works
  - AI industry feed from public account and Xiaohongshu sources
- LLM summaries with cache, timeout handling, fallback summaries, and multi-key
  concurrency support.
- Image report rendering for Feishu image messages, with text-card fallback.
- Feishu and WeCom robot delivery.
- macOS `launchd` examples for scheduled local automation.
- Render-only mode for local visual QA before sending messages.

## Project Layout

```text
work/
  ai_daily/         AI industry briefing
  cctv_daily/       CCTV 朝闻天下 briefing
  douyin_daily/     Douyin hot works briefing
  wechat_daily/     WeChat official account briefing
  weibo_daily/      Weibo briefing and hot-topic collector
  zsxq_daily/       Knowledge Planet briefing
  daily_image.py    Shared image report renderer
docs/
  architecture.md
  configuration.md
  deployment-launchd.md
  report-matrix.md
  running-reports.md
  security.md
examples/
  env/
deploy/
  launchd/         Generic macOS launchd templates
```

## Quick Start

1. Clone the repository.
2. Install Python dependencies.
3. Copy an example env file for the report you want to run.
4. Fill in only the credentials required by that report.
5. Run in render-only mode first.

```bash
python3 -m pip install -r requirements.txt
```

Example:

```bash
cp examples/env/wechat_daily.env.example work/wechat_daily/.env
python3 -m daily_briefing.cli run wechat \
  --env work/wechat_daily/.env \
  --render-only \
  --output /tmp/wechat_daily.png
```

When the image looks correct, configure push targets and run without
`RENDER_ONLY=1`.

## Configuration

Configuration is environment-variable based. Real `.env` files, cookies, caches,
logs, and generated images are intentionally ignored by git.

Start with:

- [Configuration Guide](docs/configuration.md)
- [Running Reports](docs/running-reports.md)
- [Report Matrix](docs/report-matrix.md)
- [macOS launchd Deployment](docs/deployment-launchd.md)
- [Security Guide](docs/security.md)

## Push Channels

- Feishu custom bot webhook for text-card delivery.
- Feishu app credentials for image upload and image-card delivery.
- WeCom group robot webhook for markdown delivery.

If image delivery fails or is not configured, the scripts fall back to text-card
delivery where supported.

## Data Sources

Some reports depend on authenticated cookies or third-party paid APIs. The
project does not include credentials. You are responsible for complying with the
terms of service of every data source you configure.

## Local Checks

Run the same smoke checks used by CI:

```bash
make check
```

## Development Status

The current implementation is functional but still evolving. Near-term cleanup:

- Extract shared LLM, cache, robot, and scheduling helpers.
- Add tests around config parsing, cache keys, and render-only mode.
- Add Docker or cross-platform scheduler examples.
- Add clearer provider interfaces for new report types.

## License

MIT. See [LICENSE](LICENSE).
