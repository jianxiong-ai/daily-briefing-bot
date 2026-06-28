PYTHON ?= python3
PYCACHE ?= /tmp/daily_briefing_pycache
SECRET_PATTERN := (/Users/jasonjiang|open-apis/bot/[0-9a-f-]{20,}|qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[0-9a-f-]{20,}|SUB=|WBPSESS|XSRF-TOKEN|sk-[A-Za-z0-9]{12,}|ak_[A-Za-z0-9]{12,})

.PHONY: compile test dashboard-api-test dashboard-web-build dashboard-check secret-scan check list-reports

compile:
	PYTHONPYCACHEPREFIX="$(PYCACHE)" $(PYTHON) -m py_compile \
		daily_briefing/*.py \
		work/daily_image.py \
		work/astock_daily/astock_daily.py \
		work/ai_daily/ai_daily.py \
		work/cctv_daily/cctv_daily.py \
		work/douyin_daily/douyin_daily.py \
		work/wechat_daily/wechat_daily.py \
		work/weibo_daily/weibo_daily.py \
		work/zsxq_daily/zsxq_daily.py

test:
	PYTHONPYCACHEPREFIX="$(PYCACHE)" $(PYTHON) -m unittest discover -s tests

dashboard-api-test:
	PYTHONPYCACHEPREFIX="$(PYCACHE)" PYTHONPATH="$(PWD):$(PWD)/apps/api" $(PYTHON) -m unittest discover -s apps/api/tests

dashboard-web-build:
	cd apps/web && npm run build

dashboard-check: dashboard-api-test dashboard-web-build

secret-scan:
	@matches="$$(rg -n --hidden \
		--glob '!**/.git/**' \
		--glob '!examples/env/**' \
		--glob '!work/**/*.env.example' \
		--glob '!**/*.png' \
		--glob '!**/*.json' \
		--glob '!**/*.jsonl' \
		--glob '!**/*.cookie' \
		--glob '!**/.env' \
		--glob '!**/.DS_Store' \
		--glob '!Makefile' \
		'$(SECRET_PATTERN)' . \
		| rg -v '^(./)?(SECURITY.md|docs/security.md|docs/open-source-release-checklist.md):' || true)"; \
	if [ -n "$$matches" ]; then \
		printf '%s\n' "$$matches"; \
		echo "Potential secret detected."; \
		exit 1; \
	fi

list-reports:
	$(PYTHON) -m daily_briefing.cli list

check: compile test list-reports secret-scan
