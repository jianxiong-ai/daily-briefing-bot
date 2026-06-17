# Development Guide

This repository is script-first, but new work should use the shared CLI and
runtime helpers where possible.

## Local Checks

Run the full local check before committing:

```bash
make check
```

This compiles Python files, runs smoke tests, lists registered reports, and runs
a lightweight secret scan.

For focused checks:

```bash
make compile
make test
make secret-scan
python3 -m daily_briefing.cli list
```

## Render-Only Workflow

Use render-only mode before sending any robot message:

```bash
python3 -m daily_briefing.cli run wechat \
  --env work/wechat_daily/.env \
  --render-only \
  --date 2026-06-13 \
  --output /tmp/wechat_daily.png
```

Useful flags:

| Flag | Environment effect | Purpose |
| --- | --- | --- |
| `--env path` | Sets the report-specific env var, such as `WECHAT_DAILY_ENV` | Use a private env file |
| `--render-only` | `RENDER_ONLY=1` | Generate image output without pushing |
| `--output path` | `RENDER_OUTPUT=path` | Choose image output path |
| `--date YYYY-MM-DD` | `DIGEST_DATE=YYYY-MM-DD` | Rebuild a historical report |
| `--push-targets primary` | `PUSH_TARGETS=primary` | Send only to primary robots |
| `--send-at ""` | `SEND_AT_LOCAL=` | Skip schedule waiting in manual tests |

## Adding a Report

1. Add a script under `work/<report_name>/<report_name>.py`.
2. Add an example env file under `examples/env/`.
3. Register the report in `daily_briefing/reports.py`.
4. Prefer helpers from `daily_briefing.runtime` for env loading, robot parsing,
   target selection, and send-time waiting.
5. Add smoke-test coverage for imports, registry entries, and new CLI behavior.
6. Document the report in `docs/report-matrix.md`.

## Commit Shape

Prefer small, natural commits:

- `feat:` for a new module or user-visible capability.
- `refactor:` for behavior-preserving cleanup.
- `docs:` for documentation-only updates.
- `test:` for test-only changes.
- `chore:` for maintenance tasks such as Makefile or CI updates.

Before pushing, check:

```bash
git status --short
make check
```

## Secret Hygiene

Never commit real `.env` files, cookies, caches, generated images, logs, or robot
webhooks. Use files under `examples/env/` as templates and keep private runtime
files outside git.
