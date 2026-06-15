# Contributing

Thanks for considering a contribution. This project is useful when it remains
easy to configure, safe to run, and honest about data-source limitations.

## Good First Contributions

- Improve docs or setup examples.
- Add a small test for config parsing, cache behavior, or rendering.
- Add a new push provider behind a clean environment-variable interface.
- Improve error messages for missing credentials or failed data fetches.
- Extract duplicated helpers into shared modules.

## Development Workflow

1. Create a branch from `main`.
2. Keep changes focused on one report or one shared capability.
3. Run at least render-only mode for affected reports.
4. Make sure no credentials, cookies, generated images, or caches are committed.
5. Open a pull request with a short description and verification notes.

## Commit Style

Use concise conventional-style prefixes when practical:

- `feat:` user-visible functionality
- `fix:` bug fixes
- `docs:` documentation
- `test:` tests
- `refactor:` code structure without behavior changes
- `chore:` maintenance

## Security

Never include real API keys, cookies, webhooks, tokens, or private group IDs in
issues, pull requests, screenshots, or logs.
