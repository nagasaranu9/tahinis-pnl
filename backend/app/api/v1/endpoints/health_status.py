"""Dashboard system-status ("traffic light") endpoint.

One call returns the live state of every core system, credential-based
integration, and delivery revenue channel for the tenant, each as:

    active   — up and fresh (green)
    down     — enabled but unreachable / stale (red)
    disabled — not connected / no data (grey)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep
from app.db.session import AsyncSessionDep

router = APIRouter()
logger = structlog.get_logger(__name__)

# How stale before a daily integration flips red.
_STALE = timedelta(hours=36)
# Background jobs (worker/beat) should produce a run within this window.
_JOB_FRESH = timedelta(minutes=30)
_DELIVERY_LOOKBACK_DAYS = 14


def _item(key, label, group, state, detail=""):
    return {"key": key, "label": label, "group": group, "state": state, "detail": detail}


async def _last_success(db: AsyncSession, tenant_id, prefix: str):
    from sqlalchemy import or_

    from app.db.models.job_run import JobRun
    # Many syncs run as all-tenant dispatch jobs (tenant_id NULL), so accept
    # either this tenant's runs or the shared ones.
    return await db.scalar(
        select(func.max(JobRun.created_at)).where(and_(
            or_(JobRun.tenant_id == tenant_id, JobRun.tenant_id.is_(None)),
            JobRun.task_name.like(prefix),
            JobRun.status == "success",
        ))
    )


@router.get("/status")
async def system_status(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    now = datetime.now(timezone.utc)
    tid = user.tenant_id
    items: list[dict] = []

    # ---- Core ----
    items.append(_item("api", "API", "core", "active", "Responding"))

    try:
        await db.execute(select(1))
        items.append(_item("database", "Database", "core", "active", "Connected"))
    except Exception:
        items.append(_item("database", "Database", "core", "down", "Unreachable"))

    try:
        from app.workers.tasks.toast_sync import _get_redis
        rc = await _get_redis()
        ok = False
        if rc is not None:
            ok = await rc.ping()
            await rc.aclose()
        items.append(_item("cache", "Cache", "core", "active" if ok else "down",
                           "Connected" if ok else "No ping"))
    except Exception:
        items.append(_item("cache", "Cache", "core", "down", "Unreachable"))

    # Worker + scheduler liveness from recent job activity.
    from app.db.models.job_run import JobRun
    last_job = await db.scalar(select(func.max(JobRun.created_at)))
    job_fresh = last_job is not None and (now - last_job) <= _JOB_FRESH
    detail = f"Last run {last_job:%b %d %H:%M} UTC" if last_job else "No runs"
    items.append(_item("worker", "Worker", "core", "active" if job_fresh else "down", detail))
    items.append(_item("scheduler", "Scheduler", "core", "active" if job_fresh else "down", detail))

    from app.core.config import settings
    ocr_ok = bool(getattr(settings, "ANTHROPIC_API_KEY", None) or getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", None))
    items.append(_item("ocr", "OCR", "core", "active" if ocr_ok else "disabled",
                       "Ready" if ocr_ok else "No provider key"))

    # ---- Credential integrations ----
    from app.db.models.integration import IntegrationCredential
    active_providers = set((await db.execute(
        select(IntegrationCredential.provider).where(and_(
            IntegrationCredential.tenant_id == tid,
            IntegrationCredential.is_active.is_(True),
        ))
    )).scalars().all())

    def _from_last(key, label, last, fresh=_STALE):
        if last is None:
            return _item(key, label, "platform", "down", "No recent sync")
        if (now - last) > fresh:
            return _item(key, label, "platform", "down", f"Stale · {last:%b %d}")
        return _item(key, label, "platform", "active", f"Synced {last:%b %d %H:%M}")

    # Toast — freshness from actual order data (most reliable signal).
    if "toast" in active_providers:
        from app.db.models.toast import ToastOrder
        max_bd = await db.scalar(select(func.max(ToastOrder.business_date)).where(ToastOrder.tenant_id == tid))
        if max_bd:
            bd = datetime.strptime(max_bd, "%Y%m%d").replace(tzinfo=timezone.utc)
            state = "active" if (now - bd) <= timedelta(days=3) else "down"
            items.append(_item("toast", "Toast POS", "platform", state,
                               f"Orders to {bd:%b %d}" if state == "active" else f"Stale · {bd:%b %d}"))
        else:
            items.append(_item("toast", "Toast POS", "platform", "down", "No orders"))
    else:
        items.append(_item("toast", "Toast POS", "platform", "disabled", "Not connected"))

    # Gmail / Outlook — tracked sync jobs.
    for key, label, prefix in [("gmail", "Gmail", "email.gmail%"), ("outlook", "Outlook", "email.outlook%")]:
        if key not in active_providers:
            items.append(_item(key, label, "platform", "disabled", "Not connected"))
        else:
            items.append(_from_last(key, label, await _last_success(db, tid, prefix)))

    # Google Business — freshness from captured review snapshots.
    if "google_business" in active_providers:
        from app.db.models.external_platform import GoogleReviewSnapshot
        last = await db.scalar(select(func.max(GoogleReviewSnapshot.created_at)).where(
            GoogleReviewSnapshot.tenant_id == tid))
        items.append(_from_last("google_business", "Google Business", last, fresh=timedelta(days=7)))
    else:
        items.append(_item("google_business", "Google Business", "platform", "disabled", "Not connected"))

    # PushOperations — config-based; freshness from its sync cursor.
    try:
        from app.db.models.push_labor import PushSyncConfig
        cfg = (await db.execute(select(PushSyncConfig).where(and_(
            PushSyncConfig.tenant_id == tid, PushSyncConfig.is_active.is_(True),
        )).limit(1))).scalars().first()
        if cfg:
            items.append(_from_last("pushops", "PushOperations", cfg.last_synced_at))
        else:
            items.append(_item("pushops", "PushOperations", "platform", "disabled", "Not connected"))
    except Exception:
        items.append(_item("pushops", "PushOperations", "platform", "disabled", "Not connected"))

    # ---- Delivery channels (revenue, no credential) ----
    from app.db.models.toast import ToastOrder
    since_bd = (now - timedelta(days=_DELIVERY_LOOKBACK_DAYS)).strftime("%Y%m%d")
    delivery = [
        ("uber", "Uber Eats", "%uber%"),
        ("doordash", "DoorDash", "%doordash%"),
        ("skip", "Skip", "%skip%"),
        ("ritual", "Ritual", "%ritual%"),
    ]
    for key, label, pat in delivery:
        cnt = await db.scalar(select(func.count()).select_from(ToastOrder).where(and_(
            ToastOrder.tenant_id == tid,
            ToastOrder.business_date >= since_bd,
            ToastOrder.dining_option.ilike(pat),
        )))
        if cnt and cnt > 0:
            items.append(_item(key, label, "delivery", "active", f"{cnt} orders / 14d"))
        else:
            items.append(_item(key, label, "delivery", "disabled", "No recent orders"))

    return {"data": {"generated_at": now.isoformat(), "items": items}, "errors": None}
