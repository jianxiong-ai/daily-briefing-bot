# Open-Source Release Checklist

Use this checklist before creating the first public GitHub repository.

## Repository Hygiene

- [ ] Do not initialize git until `.gitignore` is present.
- [ ] Keep real `.env` files untracked.
- [ ] Keep cookies untracked.
- [ ] Keep generated reports, logs, and caches untracked.
- [ ] Review all screenshots before publishing.

## Secret Scan

Run:

```bash
rg -n --hidden -g '!**/.git/**' \
  -g '!examples/env/**' \
  -g '!work/**/*.env.example' \
  'sk-|ak_|open-apis/bot|qyapi\\.weixin|SUB=|WBPSESS|XSRF|APP_SECRET|/Users/'
```

Every match should either be:

- source code that reads env vars,
- documentation with placeholder values,
- or a local untracked file that will not be committed.

Also verify the actual files that would be committed:

```bash
git add --dry-run .
git ls-files --others --ignored --exclude-standard
```

## First Commits

Suggested commit sequence:

1. `chore: initialize open-source project metadata`
2. `docs: document architecture and configuration`
3. `chore: add example environment files`
4. `docs: add deployment and security guides`
5. `docs: add roadmap and contribution templates`

After that, start code cleanup commits:

1. `refactor: extract shared environment loading`
2. `refactor: extract LLM client and cache helpers`
3. `test: add config parsing tests`

## GitHub Project Setup

- [ ] Add repository description.
- [ ] Add topics: `daily-briefing`, `llm`, `feishu`, `wecom`, `automation`,
      `python`, `news-digest`.
- [ ] Enable secret scanning if available.
- [ ] Create `v0.1.0` release after docs and examples are stable.
- [ ] Open a few real roadmap issues from `ROADMAP.md`.
