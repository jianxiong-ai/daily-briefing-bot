#!/usr/bin/env python3
"""Scan tracked text files for credentials without flagging security docs."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


PATTERN = re.compile(
    r"(?:/Users/jasonjiang|open-apis/bot/[0-9a-f-]{20,}|"
    r"qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[0-9a-f-]{20,}|"
    r"SUB=|WBPSESS|XSRF-TOKEN|sk-[A-Za-z0-9]{12,}|ak_[A-Za-z0-9]{12,})"
)
EXCLUDED_PATHS = {
    "Makefile",
    "SECURITY.md",
    "docs/security.md",
    "docs/open-source-release-checklist.md",
    "scripts/secret_scan.py",
}
EXCLUDED_SUFFIXES = {".png", ".json", ".jsonl", ".cookie"}


def should_scan(path: str) -> bool:
    candidate = Path(path)
    return not (
        path in EXCLUDED_PATHS
        or path.startswith("examples/env/")
        or path.endswith(".env")
        or path.endswith(".env.example")
        or candidate.suffix in EXCLUDED_SUFFIXES
        or candidate.name == ".DS_Store"
    )


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], check=True, stdout=subprocess.PIPE
    ).stdout.split(b"\0")
    matches: list[str] = []
    for raw_path in tracked:
        if not raw_path:
            continue
        path = raw_path.decode("utf-8")
        if not should_scan(path):
            continue
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            if PATTERN.search(line):
                matches.append(f"{path}:{number}:{line}")

    if matches:
        print("\n".join(matches))
        print("Potential secret detected.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
