from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Report:
    name: str
    title: str
    script: Path
    env_var: str
    example_env: Path
    default_env: Path


REPORTS = {
    "ai": Report(
        name="ai",
        title="AI industry daily",
        script=ROOT / "work/ai_daily/ai_daily.py",
        env_var="AI_DAILY_ENV",
        example_env=ROOT / "examples/env/ai_daily.env.example",
        default_env=ROOT / "work/ai_daily/.env",
    ),
    "cctv": Report(
        name="cctv",
        title="CCTV morning news daily",
        script=ROOT / "work/cctv_daily/cctv_daily.py",
        env_var="CCTV_DAILY_ENV",
        example_env=ROOT / "examples/env/cctv_daily.env.example",
        default_env=ROOT / "work/cctv_daily/.env",
    ),
    "douyin": Report(
        name="douyin",
        title="Douyin hot works daily",
        script=ROOT / "work/douyin_daily/douyin_daily.py",
        env_var="DOUYIN_DAILY_ENV",
        example_env=ROOT / "examples/env/douyin_daily.env.example",
        default_env=ROOT / "work/douyin_daily/.env",
    ),
    "wechat": Report(
        name="wechat",
        title="WeChat official account daily",
        script=ROOT / "work/wechat_daily/wechat_daily.py",
        env_var="WECHAT_DAILY_ENV",
        example_env=ROOT / "examples/env/wechat_daily.env.example",
        default_env=ROOT / "work/wechat_daily/.env",
    ),
    "weibo": Report(
        name="weibo",
        title="Weibo daily",
        script=ROOT / "work/weibo_daily/weibo_daily.py",
        env_var="WEIBO_DAILY_ENV",
        example_env=ROOT / "examples/env/weibo_daily.env.example",
        default_env=ROOT / "work/weibo_daily/.env",
    ),
    "zsxq": Report(
        name="zsxq",
        title="Knowledge Planet daily",
        script=ROOT / "work/zsxq_daily/zsxq_daily.py",
        env_var="ZSXQ_DAILY_ENV",
        example_env=ROOT / "examples/env/zsxq_daily.env.example",
        default_env=ROOT / "work/zsxq_daily/.env",
    ),
}


def get_report(name):
    try:
        return REPORTS[name]
    except KeyError as exc:
        choices = ", ".join(sorted(REPORTS))
        raise SystemExit(f"Unknown report '{name}'. Available reports: {choices}") from exc
