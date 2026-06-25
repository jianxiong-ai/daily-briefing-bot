from dataclasses import dataclass
from pathlib import Path

from .storage import default_data_root, default_log_root


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Report:
    name: str
    title: str
    script: Path
    env_var: str
    example_env: Path
    default_env: Path
    launchd_label: str = ""
    app_support_name: str = ""
    log_file: str = ""

    @property
    def default_launchd_label(self):
        return self.launchd_label or f"com.jason.{self.name}-daily"

    @property
    def default_app_support_dir(self):
        return default_data_root() / self.name

    @property
    def default_log_dir(self):
        return default_log_root() / self.name


REPORTS = {
    "ai": Report(
        name="ai",
        title="AI industry daily",
        script=ROOT / "work/ai_daily/ai_daily.py",
        env_var="AI_DAILY_ENV",
        example_env=ROOT / "examples/env/ai_daily.env.example",
        default_env=ROOT / "work/ai_daily/.env",
        launchd_label="com.jason.ai-daily",
        app_support_name="CodexAIDaily",
        log_file="ai_daily.log",
    ),
    "cctv": Report(
        name="cctv",
        title="CCTV morning news daily",
        script=ROOT / "work/cctv_daily/cctv_daily.py",
        env_var="CCTV_DAILY_ENV",
        example_env=ROOT / "examples/env/cctv_daily.env.example",
        default_env=ROOT / "work/cctv_daily/.env",
        launchd_label="com.jason.cctv-daily",
        app_support_name="CodexCctvDaily",
        log_file="cctv_daily.log",
    ),
    "douyin": Report(
        name="douyin",
        title="Douyin hot works daily",
        script=ROOT / "work/douyin_daily/douyin_daily.py",
        env_var="DOUYIN_DAILY_ENV",
        example_env=ROOT / "examples/env/douyin_daily.env.example",
        default_env=ROOT / "work/douyin_daily/.env",
        launchd_label="com.jason.douyin-daily",
        app_support_name="CodexDouyinDaily",
        log_file="douyin_daily.log",
    ),
    "wechat": Report(
        name="wechat",
        title="WeChat official account daily",
        script=ROOT / "work/wechat_daily/wechat_daily.py",
        env_var="WECHAT_DAILY_ENV",
        example_env=ROOT / "examples/env/wechat_daily.env.example",
        default_env=ROOT / "work/wechat_daily/.env",
        launchd_label="com.jason.wechat-daily",
        app_support_name="CodexWechatDaily",
        log_file="wechat_daily.log",
    ),
    "weibo": Report(
        name="weibo",
        title="Weibo daily",
        script=ROOT / "work/weibo_daily/weibo_daily.py",
        env_var="WEIBO_DAILY_ENV",
        example_env=ROOT / "examples/env/weibo_daily.env.example",
        default_env=ROOT / "work/weibo_daily/.env",
        launchd_label="com.jason.weibo-daily",
        app_support_name="CodexWeiboDaily",
        log_file="weibo_daily.log",
    ),
    "zsxq": Report(
        name="zsxq",
        title="Knowledge Planet daily",
        script=ROOT / "work/zsxq_daily/zsxq_daily.py",
        env_var="ZSXQ_DAILY_ENV",
        example_env=ROOT / "examples/env/zsxq_daily.env.example",
        default_env=ROOT / "work/zsxq_daily/.env",
        launchd_label="com.jason.zsxq-daily",
        app_support_name="CodexZsxqDaily",
        log_file="zsxq_daily.log",
    ),
}


def get_report(name):
    try:
        return REPORTS[name]
    except KeyError as exc:
        choices = ", ".join(sorted(REPORTS))
        raise SystemExit(f"Unknown report '{name}'. Available reports: {choices}") from exc
