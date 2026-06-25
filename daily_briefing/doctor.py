import os
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import has_errors, validate_report_config
from .reports import REPORTS


ERROR_PATTERNS = (
    "Traceback",
    "Operation not permitted",
    "Unauthorized",
    "HTTP Error",
    "timed out",
    "timeout",
    "failed",
    "Error",
)


@dataclass(frozen=True)
class DoctorLine:
    level: str
    message: str


def _run(command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=8)
    except Exception as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def launchd_status(label, uid=None):
    uid = os.getuid() if uid is None else uid
    result = _run(["launchctl", "print", f"gui/{uid}/{label}"])
    if result.returncode != 0:
        return {"loaded": False, "summary": result.stderr.strip() or result.stdout.strip()}
    text = result.stdout
    state = re.search(r"state = ([^\n]+)", text)
    runs = re.search(r"runs = ([^\n]+)", text)
    last_exit = re.search(r"last exit code = ([^\n]+)", text)
    return {
        "loaded": True,
        "state": state.group(1).strip() if state else "unknown",
        "runs": runs.group(1).strip() if runs else "unknown",
        "last_exit": last_exit.group(1).strip() if last_exit else "unknown",
    }


def tail_log_findings(path, lines=80):
    path = Path(path).expanduser()
    if not path.exists():
        return [DoctorLine("warn", f"log missing: {path}")]
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return [DoctorLine("warn", f"log unreadable: {path}: {exc}")]
    findings = []
    for line in raw_lines[-lines:]:
        if any(pattern in line for pattern in ERROR_PATTERNS):
            findings.append(DoctorLine("warn", f"log: {line[-240:]}"))
    if not findings:
        findings.append(DoctorLine("ok", f"log has no obvious recent errors: {path}"))
    return findings


def check_hosts(hosts):
    findings = []
    for host in hosts:
        try:
            socket.getaddrinfo(host, 443)
            findings.append(DoctorLine("ok", f"network dns ok: {host}"))
        except Exception as exc:
            findings.append(DoctorLine("error", f"network dns failed: {host}: {exc}"))
    return findings


def doctor_report(report_name, env_path=None, check_network=False):
    report = REPORTS[report_name]
    env_path = Path(env_path).expanduser() if env_path else report.default_env
    app_dir = report.default_app_support_dir
    log_path = report.default_log_dir / report.log_file if report.log_file else report.default_log_dir / "report.log"
    findings = [
        DoctorLine("ok" if report.script.exists() else "error", f"script: {report.script}"),
        DoctorLine("ok" if env_path.exists() else "error", f"env: {env_path}"),
        DoctorLine("ok" if app_dir.exists() else "warn", f"app dir: {app_dir}"),
    ]

    status = launchd_status(report.default_launchd_label)
    if not status["loaded"]:
        findings.append(DoctorLine("warn", f"launchd not loaded: {report.default_launchd_label}: {status['summary']}"))
    else:
        exit_code = status.get("last_exit", "unknown")
        level = "ok" if exit_code in {"0", "(never exited)", "unknown"} else "warn"
        findings.append(
            DoctorLine(
                level,
                f"launchd {report.default_launchd_label}: state={status.get('state')} runs={status.get('runs')} last_exit={exit_code}",
            )
        )

    config_issues = validate_report_config(report.name, env_path, os.environ)
    if not config_issues:
        findings.append(DoctorLine("ok", "config validation passed"))
    else:
        for issue in config_issues:
            findings.append(DoctorLine(issue.level, f"config {issue.key}: {issue.message}"))

    findings.extend(tail_log_findings(log_path))
    if check_network:
        findings.extend(check_hosts(("open.feishu.cn", "qyapi.weixin.qq.com", "api.deepseek.com")))
    return findings


def doctor_reports(report_names=None, env_path=None, check_network=False):
    names = report_names or sorted(REPORTS)
    return {name: doctor_report(name, env_path=env_path if len(names) == 1 else None, check_network=check_network) for name in names}


def findings_have_errors(findings_by_report):
    for findings in findings_by_report.values():
        if any(line.level == "error" for line in findings):
            return True
    return False
