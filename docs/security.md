# Security Guide

This project can contain several types of high-risk secrets:

- LLM API keys
- RedFox API keys
- Feishu and WeCom webhooks
- Feishu app secrets
- Weibo cookies
- Knowledge Planet cookies
- Private group IDs, user IDs, and followed-account lists

## Before Publishing

1. Ensure `.gitignore` is present.
2. Do not initialize git until real secrets are ignored or moved outside the
   repository.
3. Search the working tree:

   ```bash
   rg -n --hidden -g '!**/.git/**' \
     -g '!examples/env/**' \
     -g '!work/**/*.env.example' \
     'sk-|ak_|open-apis/bot|qyapi\\.weixin|SUB=|WBPSESS|XSRF|APP_SECRET|/Users/'
   ```

4. Review all screenshots and generated images before sharing.
5. Rotate any key that was exposed in a public commit, issue, or screenshot.

## Recommended Local Layout

Keep credentials outside the repository when possible:

```text
~/Library/Application Support/DailyBriefingBot/
  ai_daily/.env
  wechat_daily/.env
  cookies/
```

Then point each script at the env file with `*_DAILY_ENV`.

## Dashboard Secrets at Rest

The subscription dashboard stores per-subscription credentials (LLM keys, RedFox
keys, cookies, etc.) encrypted at rest:

- Secret-looking config values are encrypted before being written to the SQLite
  database and decrypted transparently when read back.
- The encryption key comes from the `DASHBOARD_SECRET_KEY` environment variable
  when set. Otherwise a key is generated once at `data/subscriptions/secret.key`
  (chmod 600). Set `DASHBOARD_SECRET_KEY` explicitly for reproducible deploys and
  so the database is unreadable without it.
- Back up `DASHBOARD_SECRET_KEY` (or `secret.key`) separately from the database;
  losing it makes encrypted values unrecoverable.
- Generated subscription env files never inherit secret-looking keys from the
  repo's `work/<report>/.env`; each subscription must provide its own credentials,
  so a developer's personal keys never bleed into a subscription.
