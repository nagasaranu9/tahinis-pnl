import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from celery import Task
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Sync engine for Celery task hooks (not async context)
_sync_engine = create_engine(
    str(settings.DATABASE_URL).replace("postgresql+asyncpg", "postgresql+psycopg2"),
    pool_size=5,
    max_overflow=2,
    pool_pre_ping=True,
)
_SyncSession = sessionmaker(bind=_sync_engine, autocommit=False, autoflush=False)


def _upsert_job(
    session: Session,
    celery_task_id: str,
    task_name: str,
    status: str,
    tenant_id: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_seconds: float | None = None,
    error_message: str | None = None,
    result_summary: dict | None = None,
) -> None:
    """Insert or update a job_runs record. Uses raw SQL to avoid model import cycles."""
    now = datetime.now(UTC)
    existing = session.execute(
        text("SELECT id FROM job_runs WHERE celery_task_id = :cid"),
        {"cid": celery_task_id},
    ).fetchone()

    if existing is None:
        session.execute(
            text(
                """
                INSERT INTO job_runs
                  (id, tenant_id, celery_task_id, task_name, status,
                   started_at, completed_at, duration_seconds,
                   error_message, result_summary, created_at)
                VALUES
                  (:id, :tenant_id, :cid, :task_name, :status,
                   :started_at, :completed_at, :dur,
                   :err, CAST(:res AS jsonb), :now)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "cid": celery_task_id,
                "task_name": task_name,
                "status": status,
                "started_at": started_at,
                "completed_at": completed_at,
                "dur": duration_seconds,
                "err": error_message,
                "res": __import__("json").dumps(result_summary) if result_summary else None,
                "now": now,
            },
        )
    else:
        updates: dict[str, Any] = {"status": status, "cid": celery_task_id}
        if started_at is not None:
            updates["started_at"] = started_at
        if completed_at is not None:
            updates["completed_at"] = completed_at
        if duration_seconds is not None:
            updates["dur"] = duration_seconds
        if error_message is not None:
            updates["err"] = error_message
        if result_summary is not None:
            updates["res"] = __import__("json").dumps(result_summary)

        set_clauses = ["status = :status"]
        if "started_at" in updates:
            set_clauses.append("started_at = :started_at")
        if "completed_at" in updates:
            set_clauses.append("completed_at = :completed_at")
        if "dur" in updates:
            set_clauses.append("duration_seconds = :dur")
        if "err" in updates:
            set_clauses.append("error_message = :err")
        if "res" in updates:
            set_clauses.append("result_summary = CAST(:res AS jsonb)")

        session.execute(
            text(f"UPDATE job_runs SET {', '.join(set_clauses)} WHERE celery_task_id = :cid"),
            updates,
        )
    session.commit()


def _extract_tenant_id(kwargs: dict, args: tuple = ()) -> str | None:
    """Resolve tenant_id from kwargs, else the first positional arg.

    Many tasks (email/ocr/reviews syncs) are dispatched with positional args —
    `apply_async(args=[tenant_id, ...])` — so a kwargs-only lookup returned None
    and their job_runs rows were written with tenant_id=NULL, making them
    invisible in the tenant-scoped Job Monitor."""
    tid = kwargs.get("tenant_id")
    if tid:
        return tid
    if args:
        first = args[0]
        if isinstance(first, str):
            try:
                uuid.UUID(first)
                return first
            except ValueError:
                pass
    return None


class TrackedTask(Task):
    """Base Celery task that writes job_runs records and structured logs."""

    abstract = True

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        structlog.contextvars.bind_contextvars(task_id=task_id, task_name=self.name)
        logger.info("task_start")
        tenant_id = _extract_tenant_id(kwargs, args)
        try:
            with _SyncSession() as session:
                _upsert_job(
                    session,
                    celery_task_id=task_id,
                    task_name=self.name,
                    status="running",
                    tenant_id=tenant_id,
                    started_at=datetime.now(UTC),
                )
        except Exception as exc:
            logger.warning("job_run_record_failed", error=str(exc))

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        logger.info("task_success")
        finished = datetime.now(UTC)
        tenant_id = _extract_tenant_id(kwargs, args)
        summary = retval if isinstance(retval, dict) else None
        try:
            with _SyncSession() as session:
                existing = session.execute(
                    text("SELECT started_at FROM job_runs WHERE celery_task_id = :cid"),
                    {"cid": task_id},
                ).fetchone()
                duration: float | None = None
                if existing and existing.started_at:
                    started = existing.started_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=UTC)
                    duration = (finished - started).total_seconds()
                _upsert_job(
                    session,
                    celery_task_id=task_id,
                    task_name=self.name,
                    status="success",
                    tenant_id=tenant_id,
                    completed_at=finished,
                    duration_seconds=duration,
                    result_summary=summary,
                )
        except Exception as exc:
            logger.warning("job_run_record_failed", error=str(exc))

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any
    ) -> None:
        logger.error("task_failure", error=str(exc), exc_info=True)
        tenant_id = _extract_tenant_id(kwargs, args)
        try:
            with _SyncSession() as session:
                _upsert_job(
                    session,
                    celery_task_id=task_id,
                    task_name=self.name,
                    status="failure",
                    tenant_id=tenant_id,
                    completed_at=datetime.now(UTC),
                    error_message=str(exc)[:2000],
                )
        except Exception as db_exc:
            logger.warning("job_run_record_failed", error=str(db_exc))

    def on_retry(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any
    ) -> None:
        logger.warning("task_retry", error=str(exc), retry_count=self.request.retries)
        tenant_id = _extract_tenant_id(kwargs, args)
        try:
            with _SyncSession() as session:
                _upsert_job(
                    session,
                    celery_task_id=task_id,
                    task_name=self.name,
                    status="retry",
                    tenant_id=tenant_id,
                    error_message=f"Retry {self.request.retries}: {exc}"[:2000],
                )
        except Exception as db_exc:
            logger.warning("job_run_record_failed", error=str(db_exc))
