# Private Subscription Dashboard

This private branch adds a web dashboard and an in-process scheduler for Daily
Briefing Bot. It is intentionally separate from the open-source CLI-first
project because it stores personal subscription preferences, webhook targets,
and local deployment assumptions.

## Architecture

- `apps/api`: FastAPI service.
  - Stores subscriptions in SQLite.
  - Generates per-subscription env files under `data/subscriptions/env`.
  - Runs reports through `python -m daily_briefing.cli run`.
  - Schedules active subscriptions with APScheduler.
- `apps/web`: Next.js dashboard.
  - Create/edit/delete daily report subscriptions.
  - Configure report-specific fields such as Weibo blogger UIDs, WeChat
    followed accounts, ZSXQ group IDs, and push time.
  - Trigger render-only test runs and inspect generated images.
- `docker-compose.private.yml`: local/Tailscale-oriented deployment.

The dashboard does not use macOS `launchd`. A long-running API process owns the
schedule, similar to `astock-watchtower`.

## Local Development

```bash
cp .env.private.example .env
python3 -m pip install -r requirements.txt -r apps/api/requirements.txt
PYTHONPATH="$PWD:$PWD/apps/api" uvicorn app.main:app --reload --port 8000 --app-dir apps/api
```

In another terminal:

```bash
cd apps/web
npm install
npm run dev
```

Open:

- Web: <http://localhost:3000>
- API: <http://localhost:8000/docs>

## Docker Compose

```bash
cp .env.private.example .env
docker compose -f docker-compose.private.yml up --build
```

The private compose file is intentionally mapped away from `astock-watchtower`:

- Web: <http://localhost:3010>
- API: <http://localhost:8010>

For Tailscale access, leave `NEXT_PUBLIC_API_BASE_URL` empty. The browser will
use the same hostname as the page and API port `8010`, for example
`http://100.108.43.1:8010`.

```env
NEXT_PUBLIC_API_BASE_URL=""
API_CORS_ORIGINS="http://localhost:3010,http://127.0.0.1:3010,http://100.108.43.1:3010"
API_CORS_ORIGIN_REGEX="^http://(localhost|127\\.0\\.0\\.1|100\\.\\d+\\.\\d+\\.\\d+)(:3010)$"
```

For local development, keep `localhost` and `127.0.0.1` origins in
`API_CORS_ORIGINS`; otherwise opening the same page with the other hostname can
look like an API connection failure in the browser.

## Data And Secrets

Generated subscription data is ignored by git:

- `data/subscriptions/subscriptions.sqlite3`
- `data/subscriptions/env/*.env`
- `data/subscriptions/outputs/*.png`

Real `.env` files and cookies remain local only. Do not push this branch to a
public repository.
