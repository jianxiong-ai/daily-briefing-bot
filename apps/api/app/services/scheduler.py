from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from app.config import get_settings
from app.report_metadata import REPORT_WINDOWS
from app.services.report_runner import run_hot_collector, run_subscription
from app.store import get_subscription, list_subscriptions


settings = get_settings()
scheduler = BackgroundScheduler(
    timezone=settings.scheduler_timezone,
    executors={"default": ThreadPoolExecutor(max_workers=3)},
)

_MANAGED_PREFIXES = ("subscription-", "collector-")


def _job(subscription_id: int) -> None:
    subscription = get_subscription(subscription_id)
    if not subscription or not subscription["is_active"]:
        return
    run_subscription(subscription, render_only=False)


def _collector_job(subscription_id: int) -> None:
    subscription = get_subscription(subscription_id)
    if not subscription or not subscription["is_active"]:
        return
    run_hot_collector(subscription)


def sync_jobs() -> None:
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(_MANAGED_PREFIXES):
            scheduler.remove_job(job.id)
    for subscription in list_subscriptions():
        if not subscription["is_active"]:
            continue
        hour, minute = [int(part) for part in subscription["push_time"].split(":")]
        scheduler.add_job(
            _job,
            "cron",
            id=f"subscription-{subscription['id']}",
            name=f"{subscription['name']} ({subscription['report_type']})",
            hour=hour,
            minute=minute,
            args=[subscription["id"]],
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=15 * 60,
        )

        window = REPORT_WINDOWS.get(subscription["report_type"], {})
        if window.get("needs_hot_collector"):
            interval = max(5, int(window.get("collector_interval_minutes", 30)))
            scheduler.add_job(
                _collector_job,
                "interval",
                id=f"collector-{subscription['id']}",
                name=f"{subscription['name']} 采集 ({subscription['report_type']})",
                minutes=interval,
                args=[subscription["id"]],
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=10 * 60,
            )


def start_scheduler() -> None:
    if not settings.scheduler_enabled:
        return
    if not scheduler.running:
        scheduler.start()
    sync_jobs()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def scheduler_status() -> dict:
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )
    return {
        "enabled": settings.scheduler_enabled,
        "timezone": settings.scheduler_timezone,
        "jobs": jobs,
    }
