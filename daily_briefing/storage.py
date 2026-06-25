import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeStorage:
    report: str
    root: Path
    cache: Path
    images: Path
    state: Path
    logs: Path

    def ensure(self):
        for path in (self.root, self.cache, self.images, self.state, self.logs):
            path.mkdir(parents=True, exist_ok=True)
        return self


def default_data_root():
    return Path.home() / "Library/Application Support/DailyBriefingBot"


def default_log_root():
    return Path.home() / "Library/Logs/DailyBriefingBot"


def runtime_storage(report, environ=None):
    environ = os.environ if environ is None else environ
    data_root = Path(environ.get("DAILY_BRIEFING_DATA_ROOT") or default_data_root()).expanduser()
    log_root = Path(environ.get("DAILY_BRIEFING_LOG_ROOT") or default_log_root()).expanduser()
    root = Path(environ.get("DAILY_RUNTIME_DIR") or data_root / report).expanduser()
    return RuntimeStorage(
        report=report,
        root=root,
        cache=Path(environ.get("DAILY_CACHE_DIR") or root / "cache").expanduser(),
        images=Path(environ.get("DAILY_IMAGE_DIR") or root / "images").expanduser(),
        state=Path(environ.get("DAILY_STATE_DIR") or root / "state").expanduser(),
        logs=Path(environ.get("DAILY_LOG_DIR") or log_root / report).expanduser(),
    ).ensure()


def _remove_older_than(directory, pattern, cutoff):
    removed = 0
    if not directory.exists():
        return removed
    for path in directory.glob(pattern):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed


def _trim_file_tail(path, max_bytes, keep_bytes):
    if not path.is_file() or path.stat().st_size <= max_bytes:
        return False
    with path.open("rb") as source:
        source.seek(-min(keep_bytes, path.stat().st_size), os.SEEK_END)
        tail = source.read()
    with path.open("wb") as target:
        target.write(tail)
    return True


def compact_jsonl_cache(path, ttl_seconds, now=None):
    if not path.is_file():
        return 0
    now = time.time() if now is None else now
    cutoff = now - max(0, int(ttl_seconds))
    retained = []
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            try:
                record = json.loads(line)
            except Exception:
                continue
            if float(record.get("created_at", 0) or 0) >= cutoff:
                retained.append(json.dumps(record, ensure_ascii=False))
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(("\n".join(retained) + "\n") if retained else "", encoding="utf-8")
    temp.replace(path)
    return len(retained)


def cleanup_runtime(
    storage,
    *,
    image_days=14,
    log_days=30,
    temp_days=2,
    max_log_bytes=10 * 1024 * 1024,
    keep_log_bytes=2 * 1024 * 1024,
    now=None,
):
    now = time.time() if now is None else now
    stats = {
        "images_removed": _remove_older_than(storage.images, "*.png", now - image_days * 86400),
        "temp_removed": 0,
        "logs_removed": 0,
        "logs_trimmed": 0,
    }
    for directory in (storage.cache, storage.images):
        stats["temp_removed"] += _remove_older_than(directory, "*.tmp", now - temp_days * 86400)
        stats["temp_removed"] += _remove_older_than(directory, "*.bak", now - log_days * 86400)
    stats["logs_removed"] += _remove_older_than(storage.logs, "*.log.*", now - log_days * 86400)
    for path in storage.logs.glob("*.log"):
        stats["logs_trimmed"] += int(_trim_file_tail(path, max_log_bytes, keep_log_bytes))
    return stats
