import argparse
import os
import runpy
from pathlib import Path

from .alerts import send_failure_alert
from .config import has_errors, mask_value, parse_env_file, validate_report_config
from .doctor import doctor_reports, findings_have_errors
from .launchd import copy_example_env, install_launchd_report
from .reports import REPORTS, get_report
from .storage import cleanup_runtime, compact_jsonl_cache, runtime_storage


def list_reports(_args):
    for report in REPORTS.values():
        print(f"{report.name:8} {report.title}")
    return 0


def run_report(args):
    report = get_report(args.report)
    env_path = Path(args.env).expanduser() if args.env else report.default_env

    if args.require_env and not env_path.exists():
        raise SystemExit(
            f"Env file not found: {env_path}\n"
            f"Copy the example first: cp {report.example_env} {env_path}"
        )

    os.environ[report.env_var] = str(env_path)
    if args.render_only:
        os.environ["RENDER_ONLY"] = "1"
    if args.output:
        os.environ["RENDER_OUTPUT"] = str(Path(args.output).expanduser())
    if args.date:
        os.environ["DIGEST_DATE"] = args.date
    if args.push_targets:
        os.environ["PUSH_TARGETS"] = args.push_targets
    if args.send_at is not None:
        os.environ["SEND_AT_LOCAL"] = args.send_at

    runpy.run_path(str(report.script), run_name="__main__")
    return 0


def validate_report(args):
    report = get_report(args.report)
    env_path = Path(args.env).expanduser() if args.env else report.default_env
    issues = validate_report_config(report.name, env_path, os.environ)
    values = parse_env_file(env_path)
    print(f"report: {report.name}")
    print(f"env: {env_path}")
    for key in sorted(values):
        if args.show_values:
            print(f"env[{key}]={mask_value(key, values[key])}")
    if not issues:
        print("ok: config looks usable")
        return 0
    for issue in issues:
        print(f"{issue.level}: {issue.key}: {issue.message}")
    return 1 if has_errors(issues) else 0


def doctor_command(args):
    report_names = None if args.report == "all" else [args.report]
    findings = doctor_reports(report_names, env_path=args.env, check_network=args.network)
    for report_name, lines in findings.items():
        print(f"report: {report_name}")
        for line in lines:
            print(f"{line.level}: {line.message}")
    return 1 if findings_have_errors(findings) else 0


def alert_command(args):
    result = send_failure_alert(
        report=args.report,
        message=args.message,
        env_path=args.env,
        exit_code=args.exit_code,
        log_path=args.log,
        push_targets=args.push_targets,
    )
    if result.sent:
        print(f"sent: {result.sent}")
        if result.errors:
            for error in result.errors:
                print(f"warn: {error}")
        return 0
    if not result.errors:
        print("error: no push target configured")
        return 1
    for error in result.errors:
        print(f"error: {error}")
    return 1


def launchd_install_command(args):
    result = install_launchd_report(
        report_name=args.report,
        project_dir=args.project_dir,
        app_dir=args.app_dir,
        env_file=args.env,
        label=args.label,
        hour=args.hour,
        minute=args.minute,
        interval_seconds=args.interval_seconds,
        python_bin=args.python_bin,
        load=args.load,
    )
    if args.copy_env:
        env_path = copy_example_env(args.report, result.app_dir, overwrite=args.overwrite_env)
        print(f"env: {env_path}")
    print(f"app_dir: {result.app_dir}")
    print(f"log_dir: {result.log_dir}")
    print(f"wrapper: {result.wrapper_path}")
    print(f"plist: {result.plist_path}")
    print(f"label: {result.label}")
    print(f"loaded: {result.loaded}")
    return 0


def cleanup_command(args):
    storage = runtime_storage(args.report)
    stats = cleanup_runtime(
        storage,
        image_days=args.image_days,
        log_days=args.log_days,
        temp_days=args.temp_days,
    )
    cache_path = storage.cache / "llm_summary_cache.jsonl"
    retained = compact_jsonl_cache(cache_path, args.llm_cache_ttl) if cache_path.exists() else 0
    if not args.quiet:
        print(f"report: {args.report}")
        print(f"runtime: {storage.root}")
        print(f"logs: {storage.logs}")
        for key, value in stats.items():
            print(f"{key}: {value}")
        print(f"llm_cache_records: {retained}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="daily-briefing")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List available reports")
    list_parser.set_defaults(func=list_reports)

    run_parser = subparsers.add_parser("run", help="Run a report script")
    run_parser.add_argument("report", choices=sorted(REPORTS))
    run_parser.add_argument("--env", help="Path to the report .env file")
    run_parser.add_argument(
        "--require-env",
        action="store_true",
        help="Fail if the env file does not exist",
    )
    run_parser.add_argument(
        "--render-only",
        action="store_true",
        help="Render an image without sending robot messages",
    )
    run_parser.add_argument("--output", help="Render-only output image path")
    run_parser.add_argument("--date", help="Digest date, formatted as YYYY-MM-DD")
    run_parser.add_argument("--push-targets", choices=("all", "primary"))
    run_parser.add_argument(
        "--send-at",
        default=None,
        help="Override SEND_AT_LOCAL. Use an empty string to avoid waiting.",
    )
    run_parser.set_defaults(func=run_report)

    validate_parser = subparsers.add_parser("validate", help="Validate report configuration")
    validate_parser.add_argument("report", choices=sorted(REPORTS))
    validate_parser.add_argument("--env", help="Path to the report .env file")
    validate_parser.add_argument(
        "--show-values",
        action="store_true",
        help="Print env keys with secret values masked",
    )
    validate_parser.set_defaults(func=validate_report)

    doctor_parser = subparsers.add_parser("doctor", help="Check local report health")
    doctor_parser.add_argument("report", choices=sorted(REPORTS) + ["all"], nargs="?", default="all")
    doctor_parser.add_argument("--env", help="Env path, only valid when checking one report")
    doctor_parser.add_argument(
        "--network",
        action="store_true",
        help="Also check DNS resolution for common external services",
    )
    doctor_parser.set_defaults(func=doctor_command)

    alert_parser = subparsers.add_parser("alert", help="Send a failure alert to push targets")
    alert_parser.add_argument("report")
    alert_parser.add_argument("--message", required=True)
    alert_parser.add_argument("--env", help="Env file containing webhook settings")
    alert_parser.add_argument("--exit-code", type=int)
    alert_parser.add_argument("--log", help="Attach the tail of this log file")
    alert_parser.add_argument("--push-targets", choices=("all", "primary"), default="primary")
    alert_parser.set_defaults(func=alert_command)

    cleanup_parser = subparsers.add_parser("cleanup", help="Clean generated runtime files")
    cleanup_parser.add_argument("report", choices=sorted(REPORTS))
    cleanup_parser.add_argument("--image-days", type=int, default=14)
    cleanup_parser.add_argument("--log-days", type=int, default=30)
    cleanup_parser.add_argument("--temp-days", type=int, default=2)
    cleanup_parser.add_argument("--llm-cache-ttl", type=int, default=7 * 86400)
    cleanup_parser.add_argument("--quiet", action="store_true")
    cleanup_parser.set_defaults(func=cleanup_command)

    launchd_parser = subparsers.add_parser("launchd", help="Manage macOS launchd jobs")
    launchd_subparsers = launchd_parser.add_subparsers(dest="launchd_command", required=True)
    install_parser = launchd_subparsers.add_parser("install", help="Install or update a launchd report job")
    install_parser.add_argument("report", choices=sorted(REPORTS))
    install_parser.add_argument("--project-dir", default=str(Path.cwd()), help="Project directory to run")
    install_parser.add_argument("--app-dir", help="Application Support directory for env and logs")
    install_parser.add_argument("--env", help="Env file path. Defaults to the repository report .env")
    install_parser.add_argument("--label", help="launchd label")
    install_parser.add_argument("--hour", type=int, help="Daily schedule hour")
    install_parser.add_argument("--minute", type=int, help="Daily schedule minute")
    install_parser.add_argument("--interval-seconds", type=int, help="Run every N seconds instead of daily schedule")
    install_parser.add_argument("--python-bin", default="python3")
    install_parser.add_argument("--copy-env", action="store_true", help="Copy the example env into APP_DIR/.env")
    install_parser.add_argument("--overwrite-env", action="store_true", help="Overwrite APP_DIR/.env when copying env")
    install_parser.add_argument("--load", action="store_true", help="Load/reload the launchd job now")
    install_parser.set_defaults(func=launchd_install_command)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
