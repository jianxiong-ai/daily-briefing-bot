# Subscription Dashboard

Daily Briefing Bot includes a lightweight web dashboard for configuring and
scheduling reports without macOS `launchd`.

The dashboard is intended for a self-hosted personal or small-team deployment:
you choose a report type, fill in the required credentials and followed sources,
set a delivery time, and provide the Feishu webhook that should receive the
report.

![Subscription dashboard](assets/dashboard-subscriptions.png)

## What It Provides

- Create, edit, pause, and delete report subscriptions.
- Configure credentials per subscription, including RedFox keys, LLM keys, and
  source cookies.
- Configure report-specific followed sources, such as Weibo blogger UIDs,
  WeChat official account names, and Knowledge Planet group IDs.
- Run render-only tests from the UI and inspect generated report images.
- Run schedules inside the API process with APScheduler.
- Store subscription secrets encrypted at rest in SQLite.

The dashboard calls the same report implementation as the CLI:

```text
dashboard subscription
  -> generated per-subscription env file
  -> python -m daily_briefing.cli run <report>
  -> image/text report delivery
```

## Architecture

- `apps/api`: FastAPI service.
  - Stores subscriptions in SQLite.
  - Encrypts secret-looking subscription config values.
  - Generates per-subscription env files under `SUBSCRIPTION_ENV_DIR`.
  - Runs reports through `python -m daily_briefing.cli run`.
  - Schedules active subscriptions with APScheduler.
- `apps/web`: Next.js dashboard.
  - Calls the API over HTTP.
  - Uses the current page hostname with API port `8010` when
    `NEXT_PUBLIC_API_BASE_URL` is empty, which is convenient for Tailscale.
- `docker-compose.dashboard.yml`: local/Tailscale-oriented deployment.

## Docker Compose Deployment

Create a local env file:

```bash
cp .env.dashboard.example .env
```

Edit `.env` and set at least:

```env
LLM_PROVIDER="deepseek"
DEEPSEEK_API_KEYS="sk-..."
REDFOX_API_KEY="ak_..."
FEISHU_APP_ID="cli_..."
FEISHU_APP_SECRET="..."
```

Then start the stack:

```bash
docker compose -f docker-compose.dashboard.yml up --build -d
```

Check status:

```bash
docker compose -f docker-compose.dashboard.yml ps
docker compose -f docker-compose.dashboard.yml logs -f
```

Default ports:

- Web: <http://localhost:3010>
- API: <http://localhost:8010>

For Tailscale access, leave `NEXT_PUBLIC_API_BASE_URL` empty. The browser will
derive the API endpoint from the page hostname and port `8010`, for example:

```text
http://100.x.y.z:3010 -> http://100.x.y.z:8010
```

Allow local and Tailscale origins with:

```env
API_CORS_ORIGINS="http://localhost:3010,http://127.0.0.1:3010,http://100.108.43.1:3010"
API_CORS_ORIGIN_REGEX="^http://(localhost|127\\.0\\.0\\.1|100\\.\\d+\\.\\d+\\.\\d+)(:3010)$"
```

## Subscription Fields

Every subscription needs:

- Report type
- Delivery time
- Feishu webhook
- Credentials required by that report
- Followed sources required by that report

Typical report fields:

| Report | Credentials | Followed-source config |
| --- | --- | --- |
| AI daily | `REDFOX_API_KEY`, LLM key | none |
| A-share daily | `REDFOX_API_KEY`, LLM key | none |
| CCTV daily | LLM key | none |
| Douyin daily | `REDFOX_API_KEY`, LLM key | none |
| WeChat daily | `REDFOX_API_KEY`, LLM key | followed official account names |
| Weibo daily | LLM key, Weibo cookie | blogger UIDs |
| ZSXQ daily | LLM key, Knowledge Planet cookie | group ID and extra selected user IDs |

For Weibo and Knowledge Planet cookies, paste the cookie value directly into
the dashboard. The API writes it to a local private file and passes
`WEIBO_COOKIE_FILE` or `ZSXQ_COOKIE_FILE` to the original report script.

## Render-Only Tests

Use the `渲染测试` button to run a subscription without sending the report to a
robot. Generated images are served from the API's output directory and linked in
the run log.

Example rendered report:

![Rendered daily report](assets/report-image-cctv.png)

## Data And Secret Storage

The Docker deployment stores runtime state in the named volume
`daily_briefing_dashboard_data`:

```text
/data/
  subscriptions.sqlite3
  secret.key
  env/
  outputs/
  runtime/
```

Secret-looking subscription values are encrypted before they are written to
SQLite. The encryption key comes from `DASHBOARD_SECRET_KEY` when set; otherwise
the API generates `/data/secret.key` on first run.

Back up `DASHBOARD_SECRET_KEY` or `secret.key` separately from the database.
If the key is lost, encrypted subscription values cannot be recovered.

## Local Development

API:

```bash
cp .env.dashboard.example .env
python3 -m pip install -r requirements.txt -r apps/api/requirements.txt
PYTHONPATH="$PWD:$PWD/apps/api" uvicorn app.main:app --reload --port 8000 --app-dir apps/api
```

Web:

```bash
cd apps/web
npm install
npm run dev
```

Open:

- Web: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>

## Migrating From launchd

If you previously used the macOS launchd deployment, run a dry migration first:

```bash
python3 scripts/migrate_launchd_to_dashboard.py
```

Create paused subscriptions:

```bash
python3 scripts/migrate_launchd_to_dashboard.py --apply
```

Create active subscriptions:

```bash
python3 scripts/migrate_launchd_to_dashboard.py --apply --active
```
