import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .reports import get_report


@dataclass(frozen=True)
class LaunchdInstallResult:
    app_dir: Path
    wrapper_path: Path
    plist_path: Path
    label: str
    loaded: bool = False


def default_app_dir(report_name):
    return Path.home() / "Library/Application Support/DailyBriefingBot" / f"{report_name}_daily"


def default_label(report_name):
    return f"com.daily-briefing.{report_name}"


def render_wrapper(*, app_dir, project_dir, report_name, env_file, python_bin):
    return f"""#!/bin/zsh
set -eu

APP_DIR="${{APP_DIR:-{app_dir}}}"
PROJECT_DIR="${{PROJECT_DIR:-{project_dir}}}"
PYTHON_BIN="${{PYTHON_BIN:-{python_bin}}}"
REPORT_NAME="${{REPORT_NAME:-{report_name}}}"
ENV_FILE="${{ENV_FILE:-{env_file}}}"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"
REPORT_LOG="$LOG_DIR/report.log"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

set +e
"$PYTHON_BIN" -m daily_briefing.cli run "$REPORT_NAME" --env "$ENV_FILE" >> "$REPORT_LOG" 2>&1
run_status=$?
set -e
if [[ "$run_status" -ne 0 ]]; then
  "$PYTHON_BIN" -m daily_briefing.cli alert "$REPORT_NAME" \\
    --env "$ENV_FILE" \\
    --message "launchd report command failed" \\
    --exit-code "$run_status" \\
    --log "$REPORT_LOG" \\
    --push-targets primary >> "$LOG_DIR/alert.log" 2>&1 || true
fi
exit "$run_status"
"""


def render_plist(*, label, app_dir, hour=None, minute=None, interval_seconds=None):
    if interval_seconds:
        trigger = f"""  <key>StartInterval</key>
  <integer>{int(interval_seconds)}</integer>"""
    else:
        trigger = f"""  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>{int(hour)}</integer>
    <key>Minute</key>
    <integer>{int(minute)}</integer>
  </dict>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{app_dir}/run_report.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{app_dir}</string>
{trigger}
  <key>StandardOutPath</key>
  <string>{app_dir}/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>{app_dir}/logs/launchd.err.log</string>
</dict>
</plist>
"""


def install_launchd_report(
    *,
    report_name,
    project_dir,
    app_dir=None,
    env_file=None,
    label=None,
    hour=None,
    minute=None,
    interval_seconds=None,
    python_bin="python3",
    load=False,
):
    report = get_report(report_name)
    if interval_seconds is None and (hour is None or minute is None):
        raise ValueError("hour and minute are required unless interval_seconds is set")
    if interval_seconds is not None and (hour is not None or minute is not None):
        raise ValueError("use either interval_seconds or hour/minute, not both")

    app_dir = Path(app_dir).expanduser() if app_dir else default_app_dir(report_name)
    project_dir = Path(project_dir).expanduser().resolve()
    env_file = Path(env_file).expanduser() if env_file else app_dir / ".env"
    label = label or default_label(report_name)
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "logs").mkdir(exist_ok=True)

    wrapper_path = app_dir / "run_report.sh"
    wrapper_path.write_text(
        render_wrapper(
            app_dir=app_dir,
            project_dir=project_dir,
            report_name=report.name,
            env_file=env_file,
            python_bin=python_bin,
        ),
        encoding="utf-8",
    )
    wrapper_path.chmod(0o755)

    plist_path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(
        render_plist(
            label=label,
            app_dir=app_dir,
            hour=hour,
            minute=minute,
            interval_seconds=interval_seconds,
        ),
        encoding="utf-8",
    )

    if load:
        uid = os.getuid()
        subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(plist_path)], capture_output=True, text=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)], check=True)
    return LaunchdInstallResult(app_dir=app_dir, wrapper_path=wrapper_path, plist_path=plist_path, label=label, loaded=load)


def copy_example_env(report_name, app_dir, overwrite=False):
    report = get_report(report_name)
    app_dir = Path(app_dir).expanduser()
    target = app_dir / ".env"
    if target.exists() and not overwrite:
        return target
    shutil.copyfile(report.example_env, target)
    target.chmod(0o600)
    return target
