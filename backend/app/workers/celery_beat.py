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
    # Every 6h (not once-daily): survives beat restarts, self-heals a missed
    # slot, and guarantees a run lands inside the Job Monitor's visible window.
    # Stagger gmail/outlook by 30min to avoid hammering the sync queue together.
    "gmail-sync-6h": {
        "task": "email.gmail_sync_all",
        "schedule": crontab(hour="*/6", minute=0),
    },
    "outlook-sync-6h": {
        "task": "email.outlook_sync_all",
        "schedule": crontab(hour="*/6", minute=30),
    },
    "external-sync-daily": {
        # Covers Google Reviews + Google Ads for all tenants
        "task": "external.daily_external_sync_all_tenants",
        "schedule": crontab(hour=7, minute=0),
    },
    "reviews-sync-hourly": {
        # Near-realtime Google reviews: Business Profile API has no push/webhook
        # and a hard daily quota, so hourly polling is the closest safe cadence.
        # Runs alongside the manual "Sync now" button and the daily external sweep
        # above. Dispatches one per-tenant sync_reviews job per active config.
        "task": "reviews.daily_sync_all_tenants",
        "schedule": crontab(minute=0),  # top of every hour
    },
    "reviews-places-refresh-hourly": {
        # Places API (New) fallback — key-only, no GBP allowlisting. Keeps reviews
        # dynamic (rating + count + recent) for any config with a stored Place ID,
        # offset 15 min from the GBP poll above. This is the source that actually
        # refreshes while Business Profile API access is pending.
        "task": "reviews.places_refresh_all_tenants",
        "schedule": crontab(minute=15),  # top+15 of every hour
    },
    "pipeboard-sync-daily": {
        # Covers Pipeboard (Google Ads, Meta Ads, TikTok Ads) for all tenants
        "task": "pipeboard.daily_sync_all_tenants",
        "schedule": crontab(hour=7, minute=30),
    },
    "google-ads-optimization-daily": {
        # Auto-optimize Google Ads campaigns daily (1 hour after Pipeboard sync)
        "task": "google_ads.optimize_all_tenants",
        "schedule": crontab(hour=8, minute=30),
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
