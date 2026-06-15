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
