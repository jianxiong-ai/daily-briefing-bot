# Roadmap

## v0.1.0 - Open-Source Preview

- Publish a secret-safe repository.
- Provide setup documentation and `.env.example` files.
- Keep all current report scripts runnable from source.
- Support render-only verification before pushing.
- Document launchd deployment for macOS users.

## v0.2.0 - Shared Core

- Keep the unified CLI and runtime helpers stable.
- Adopt shared LLM primitives across report scripts, including retry, timeout,
  cache, and multi-key behavior.
- Continue consolidating Feishu and WeCom notification loops.
- Extract RedFox request and cache helpers.
- Normalize report section data before image rendering.
- Add unit tests for cache keys and fallback summaries.

## v0.3.0 - Deployment Options

- Add Docker examples.
- Add cron/systemd examples.
- Add sample GitHub Actions workflow for lint and tests.

## v0.4.0 - Extensibility

- Define a source-adapter interface.
- Define a push-provider interface.
- Add Telegram or email push provider.
- Add template themes for image reports.

## Later Ideas

- Small local web dashboard for configuration and preview.
- Report history browser.
- Better observability for failed fetches, LLM fallbacks, and push errors.
- Optional SQLite cache backend.
