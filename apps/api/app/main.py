from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.report_metadata import report_options
from app.schemas import (
    RunOut,
    RunRequest,
    SchedulerStatus,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
    ValidationResult,
)
from app.services.report_runner import run_subscription
from app.services.scheduler import scheduler_status, start_scheduler, stop_scheduler, sync_jobs
from app.services.validation import errors_only, format_errors, validate_subscription
from app.store import (
    create_subscription,
    delete_subscription,
    get_subscription,
    init_db,
    list_run_logs,
    list_subscriptions,
    update_subscription,
)


settings = get_settings()
app = FastAPI(title="Daily Briefing Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
settings.output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=settings.output_dir, check_dir=False), name="outputs")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "daily-briefing-dashboard-api"}


@app.get("/api/reports")
def reports() -> list[dict]:
    return report_options()


@app.get("/api/subscriptions", response_model=list[SubscriptionOut])
def subscriptions() -> list[dict]:
    return list_subscriptions()


@app.post("/api/subscriptions/validate", response_model=ValidationResult)
def validate(payload: SubscriptionCreate) -> dict:
    return {"issues": validate_subscription(payload.model_dump())}


@app.post("/api/subscriptions", response_model=SubscriptionOut)
def create(payload: SubscriptionCreate) -> dict:
    data = payload.model_dump()
    issues = validate_subscription(data)
    if errors_only(issues):
        raise HTTPException(status_code=400, detail=format_errors(issues))
    try:
        item = create_subscription(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sync_jobs()
    return item | {"warnings": [issue["message"] for issue in issues]}


@app.put("/api/subscriptions/{subscription_id}", response_model=SubscriptionOut)
def update(subscription_id: int, payload: SubscriptionUpdate) -> dict:
    existing = get_subscription(subscription_id)
    if not existing:
        raise HTTPException(status_code=404, detail="subscription not found")
    data = payload.model_dump(exclude_unset=True)
    merged = dict(existing)
    merged.update({key: value for key, value in data.items() if value is not None})
    issues = validate_subscription(merged)
    if errors_only(issues):
        raise HTTPException(status_code=400, detail=format_errors(issues))
    try:
        item = update_subscription(subscription_id, data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="subscription not found") from exc
    sync_jobs()
    return item | {"warnings": [issue["message"] for issue in issues]}


@app.delete("/api/subscriptions/{subscription_id}", status_code=204)
def delete(subscription_id: int) -> None:
    delete_subscription(subscription_id)
    sync_jobs()


@app.post("/api/subscriptions/{subscription_id}/run", response_model=RunOut)
def run(subscription_id: int, payload: RunRequest) -> dict:
    subscription = get_subscription(subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="subscription not found")
    result = run_subscription(subscription, render_only=payload.render_only or not payload.send, digest_date=payload.digest_date)
    log = list_run_logs(limit=1)[0]
    return log | {"message": result.get("message", log.get("message", ""))[:4000]}


@app.get("/api/runs", response_model=list[RunOut])
def runs(limit: int = 50) -> list[dict]:
    return list_run_logs(limit=limit)


@app.get("/api/scheduler/status", response_model=SchedulerStatus)
def scheduler() -> dict:
    return scheduler_status()


@app.post("/api/scheduler/reload", response_model=SchedulerStatus)
def reload_scheduler() -> dict:
    sync_jobs()
    return scheduler_status()
