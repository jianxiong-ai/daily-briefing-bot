PYTHON ?= python3
PYCACHE ?= /tmp/daily_briefing_pycache

.PHONY: compile test check list-reports

compile:
	PYTHONPYCACHEPREFIX="$(PYCACHE)" $(PYTHON) -m py_compile \
		daily_briefing/*.py \
		work/daily_image.py \
		work/ai_daily/ai_daily.py \
		work/cctv_daily/cctv_daily.py \
		work/douyin_daily/douyin_daily.py \
		work/wechat_daily/wechat_daily.py \
		work/weibo_daily/weibo_daily.py \
		work/zsxq_daily/zsxq_daily.py

test:
	PYTHONPYCACHEPREFIX="$(PYCACHE)" $(PYTHON) -m unittest discover -s tests

list-reports:
	$(PYTHON) -m daily_briefing.cli list

check: compile test list-reports
