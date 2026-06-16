from celery import Celery
from celery.signals import setup_logging as celery_setup_logging

from app.core.config import settings

celery_app = Celery(
    "tahinis",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
    include=[
        "app.workers.tasks.toast_sync",
        "app.workers.tasks.email_sync",
        "app.workers.tasks.ocr_process",
        "app.workers.tasks.ai_categorize",
        "app.workers.tasks.reconciliation",
        "app.workers.tasks.pnl",
        "app.workers.tasks.external_platforms",
        "app.workers.tasks.ai_insights",
        "app.workers.tasks.reviews_sync",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Retry config
    task_max_retries=3,
    task_default_retry_delay=60,
    # Result expiry
    result_expires=86400,
    # Route heavy AI/OCR tasks to dedicated queue
    task_routes={
        "app.workers.tasks.ocr_process.*": {"queue": "ocr"},
        "app.workers.tasks.ai_categorize.*": {"queue": "ai"},
        "app.workers.tasks.toast_sync.*": {"queue": "sync"},
        "app.workers.tasks.email_sync.*": {"queue": "sync"},
        "app.workers.tasks.external_platforms.*": {"queue": "sync"},
        "app.workers.tasks.reviews_sync.*": {"queue": "sync"},
    },
    beat_schedule={
        "monthly-pnl-snapshots": {
            "task": "pnl.monthly_pnl_all_tenants",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(
                hour=2, minute=0, day_of_month=1
            ),
        },
        "weekly-reconciliation": {
            "task": "reconciliation.weekly_reconciliation_all_tenants",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(
                hour=3, minute=0, day_of_week=1
            ),
        },
        "daily-external-sync": {
            "task": "external.daily_external_sync_all_tenants",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(
                hour=4, minute=30
            ),
        },
        "hourly-toast-sync": {
            "task": "toast.daily_sync_all_locations",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(
                minute=0
            ),
        },
    },
)


@celery_setup_logging.connect
def configure_logging(**kwargs: object) -> None:
    from app.core.logging import setup_logging
    setup_logging()
