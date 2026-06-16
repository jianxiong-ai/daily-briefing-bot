import argparse
import os
import runpy
from pathlib import Path

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
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
