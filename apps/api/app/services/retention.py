from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from app.store import prune_run_logs_before


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_unlink(path_value: str, allowed_roots: list[Path]) -> bool:
    if not path_value:
        return False
    path = Path(path_value).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if not any(_is_under(resolved, root) for root in allowed_roots):
        return False
    if not resolved.is_file():
        return False
    resolved.unlink()
    return True


def _remove_old_pngs(root: Path, cutoff_ts: float) -> int:
    if not root.exists():
        return 0
    removed = 0
    for path in root.rglob("*.png"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime >= cutoff_ts:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def cleanup_old_run_records(retention_days: int | None = None) -> dict:
    settings = get_settings()
    days = settings.run_retention_days if retention_days is None else retention_days
    days = max(1, int(days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    output_root = settings.output_dir.resolve()
    runtime_root = settings.runtime_dir.resolve()
    allowed_roots = [output_root, runtime_root]

    referenced_paths = prune_run_logs_before(cutoff.isoformat())
    removed_referenced = sum(1 for path in referenced_paths if _safe_unlink(path, allowed_roots))
    cutoff_ts = cutoff.timestamp()
    removed_orphans = _remove_old_pngs(output_root, cutoff_ts) + _remove_old_pngs(runtime_root, cutoff_ts)

    return {
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "pruned_run_logs": len(referenced_paths),
        "removed_referenced_images": removed_referenced,
        "removed_orphan_images": removed_orphans,
    }
