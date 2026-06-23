import argparse
import os
import runpy
from pathlib import Path

from .alerts import send_failure_alert
from .config import has_errors, mask_value, parse_env_file, validate_report_config
from .doctor import doctor_reports, findings_have_errors
from .reports import REPORTS, get_report


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
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
