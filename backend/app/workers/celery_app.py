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
    task_default_queue="default",  # worker runs -Q default,sync,ocr,ai; without this, Celery uses "celery" queue which is not consumed
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
    # Beat scheduler — use /tmp (writable in containers) instead of current dir
    beat_schedule_filename="/tmp/celerybeat-schedule",
    # Route heavy AI/OCR tasks to dedicated queue
    task_routes={
        "app.workers.tasks.ocr_process.*": {"queue": "ocr"},
        "app.workers.tasks.ai_categorize.*": {"queue": "ai"},
        "app.workers.tasks.toast_sync.*": {"queue": "sync"},
        "app.workers.tasks.email_sync.*": {"queue": "sync"},
        "app.workers.tasks.external_platforms.*": {"queue": "sync"},
        "app.workers.tasks.reviews_sync.*": {"queue": "sync"},
    },
    # NOTE: beat_schedule lives solely in app.workers.celery_beat (single source of
    # truth). Launch beat with `-A app.workers.celery_beat beat`. Do not redefine the
    # schedule here — two schedules silently override each other depending on which
    # module beat is started with.
)


@celery_setup_logging.connect
def configure_logging(**kwargs: object) -> None:
    from app.core.logging import setup_logging
    setup_logging()
