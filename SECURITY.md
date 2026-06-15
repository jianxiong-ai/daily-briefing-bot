# Security Policy

This project works with cookies, webhooks, LLM API keys, and third-party data
API keys. Treat all local configuration as sensitive.

## Supported Versions

Security fixes are accepted for the current `main` branch.

## Reporting a Vulnerability

Please open a private security advisory if GitHub advisories are enabled for the
repository. Otherwise, contact the maintainer privately and do not disclose
working credentials or exploit details in a public issue.

## Secret Handling Rules

- Do not commit `.env` files.
- Do not commit cookie files.
- Do not commit generated caches or logs.
- Rotate any key that was ever committed to a public repository.
- Prefer `.env.example` files with placeholder values.

Before publishing this repository, run a secret scan and manually search for:

```bash
rg -n --hidden -g '!**/.git/**' \
  -g '!examples/env/**' \
  -g '!work/**/*.env.example' \
  'sk-|ak_|open-apis/bot|qyapi\\.weixin|SUB=|WBPSESS|XSRF|cookie|APP_SECRET|/Users/'
```
