from celery.schedules import crontab

from app.workers.celery_app import celery_app

celery_app.conf.beat_schedule = {
    # ── Near-realtime Toast sync every minute ────────────────────────────────
    # Single entry — toast-sync-daily was a duplicate that fired at 2AM in the
    # same minute as this schedule, causing two dispatch tasks to race and create
    # two pending jobs per location (one stayed pending until the 60-min stale sweep).
    "toast-sync-1min": {
        "task": "toast.daily_sync_all_locations",
        "schedule": crontab(minute="*"),
    },
    # ── Daily syncs (UTC) ─────────────────────────────────────────────────────
    "gmail-sync-daily": {
        "task": "email.gmail_sync_all",
        "schedule": crontab(hour=3, minute=0),
    },
    "outlook-sync-daily": {
        "task": "email.outlook_sync_all",
        "schedule": crontab(hour=3, minute=30),
    },
    "external-sync-daily": {
        # Covers Google Reviews + Google Ads for all tenants
        "task": "external.daily_external_sync_all_tenants",
        "schedule": crontab(hour=7, minute=0),
    },
    "pipeboard-sync-daily": {
        # Covers Pipeboard (Google Ads, Meta Ads, TikTok Ads) for all tenants
        "task": "pipeboard.daily_sync_all_tenants",
        "schedule": crontab(hour=7, minute=30),
    },
    "reconciliation-daily": {
        # weekly_reconciliation_all_tenants builds its own (run_id, tenant_id,
        # period) per tenant — run_reconciliation itself requires those as
        # positional args and crashes every time if fired bare from beat.
        "task": "app.workers.tasks.reconciliation.weekly_reconciliation_all_tenants",
        "schedule": crontab(hour=6, minute=0),
    },
    # ── Weekly ────────────────────────────────────────────────────────────────
    "financial-consistency-check": {
        "task": "app.workers.tasks.reconciliation.weekly_reconciliation_all_tenants",
        "schedule": crontab(hour=8, minute=0, day_of_week=0),  # Sunday
    },
    # ── Monthly ───────────────────────────────────────────────────────────────
    "pl-snapshot-monthly": {
        "task": "pnl.monthly_pnl_all_tenants",
        "schedule": crontab(hour=9, minute=0, day_of_month=1),
    },
}
