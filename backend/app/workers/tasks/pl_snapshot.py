import structlog
from app.workers.celery_app import celery_app
from app.workers.base_task import TrackedTask

logger = structlog.get_logger(__name__)
