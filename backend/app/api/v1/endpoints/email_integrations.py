"""
Email integration endpoints (Gmail + Outlook).

OAuth flow:
  GET  /integrations/gmail/auth-url   → redirect URL for consent
  GET  /integrations/gmail/callback   → exchange code, store tokens
  GET  /integrations/gmail/status     → list connected accounts
  POST /integrations/gmail/sync       → manual sync trigger
  DELETE /integrations/gmail/disconnect

Same pattern for /outlook.
"""
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.core.deps import CurrentUserDep, ManagerDep, OwnerDep
from app.core.exceptions import NotFoundError
from app.core.security import encrypt_value
from app.db.models.integration import IntegrationCredential
from app.db.repositories.email_repo import EmailSyncRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.email_sync import (
    EmailSyncConfigResponse,
    EmailSyncJobResponse,
)

router = APIRouter()
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frontend_url(path: str) -> str:
    from app.core.config import settings
    base = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    return f"{base}{path}"


def _api_callback_url(provider: str) -> str:
    from app.core.config import settings
    base = getattr(settings, "API_BASE_URL", "http://localhost:8000")
    return f"{base}/api/v1/integrations/{provider}/callback"


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

@router.get("/gmail/auth-url", response_model=APIResponse[dict])
async def gmail_auth_url(user: OwnerDep) -> dict:
    from app.services.email.gmail_client import build_gmail_auth_url
    state = f"{user.tenant_id}:{user.user_id}:{secrets.token_urlsafe(16)}"
    url = build_gmail_auth_url(redirect_uri=_api_callback_url("gmail"), state=state)
    return {"data": {"url": url}, "errors": None}


@router.get("/gmail/callback")
async def gmail_callback(
    code: str,
    state: str,
    db: AsyncSessionDep,
):
    """OAuth callback — exchanges code, stores encrypted tokens, redirects to frontend."""
    from app.services.email.gmail_client import exchange_gmail_code, GmailClient

    try:
        parts = state.split(":")
        tenant_id = uuid.UUID(parts[0])
        token_data = await exchange_gmail_code(code, _api_callback_url("gmail"))

        async with GmailClient(token_data["access_token"], token_data.get("refresh_token", "")) as client:
            email_address, _ = await client.get_profile()

        cred = IntegrationCredential(
            tenant_id=tenant_id,
            provider="gmail",
            access_token_encrypted=encrypt_value(token_data["access_token"]),
            refresh_token_encrypted=encrypt_value(token_data.get("refresh_token", "")),
        )
        db.add(cred)
        await db.flush()

        repo = EmailSyncRepository(db)
        await repo.upsert_config(
            tenant_id=tenant_id,
            provider="gmail",
            email_address=email_address,
            integration_credential_id=cred.id,
        )
        await db.commit()
        logger.info("gmail_connected", tenant_id=str(tenant_id), email=email_address)
    except Exception as e:
        logger.error("gmail_callback_failed", error=str(e))
        return RedirectResponse(_frontend_url("/integrations?error=gmail_failed"))

    return RedirectResponse(_frontend_url("/integrations?connected=gmail"))


@router.get("/gmail/status", response_model=APIResponse[list[EmailSyncConfigResponse]])
async def gmail_status(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = EmailSyncRepository(db)
    configs = await repo.list_configs(user.tenant_id, provider="gmail")
    return {"data": [EmailSyncConfigResponse.model_validate(c) for c in configs], "errors": None}


@router.post("/gmail/sync", response_model=APIResponse[EmailSyncJobResponse])
async def gmail_manual_sync(
    user: ManagerDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID = Query(...),
) -> dict:
    repo = EmailSyncRepository(db)
    config = await repo.get_config_by_id(user.tenant_id, config_id)
    if not config:
        raise NotFoundError("Gmail config not found")

    job = await repo.create_job(
        tenant_id=user.tenant_id,
        config_id=config.id,
        provider="gmail",
        triggered_by=user.user_id,
    )
    await db.commit()

    from app.workers.tasks.email_sync import gmail_sync_single
    gmail_sync_single.apply_async(
        args=[str(user.tenant_id), str(config_id), str(job.id)],
        queue="sync",
    )
    return {"data": EmailSyncJobResponse.model_validate(job), "errors": None}


@router.post("/gmail/historical-import", response_model=APIResponse[EmailSyncJobResponse])
async def gmail_historical_import(
    user: OwnerDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID = Query(...),
    after_date: str = Query(..., description="YYYY-MM-DD — scan emails received after this date"),
) -> dict:
    """Trigger a historical Gmail scan from a specific date. Imports all attachment emails since after_date."""
    try:
        from datetime import datetime as _dt
        _dt.fromisoformat(after_date)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="after_date must be YYYY-MM-DD")

    repo = EmailSyncRepository(db)
    config = await repo.get_config_by_id(user.tenant_id, config_id)
    if not config:
        raise NotFoundError("Gmail config not found")

    job = await repo.create_job(
        tenant_id=user.tenant_id,
        config_id=config.id,
        provider="gmail",
        triggered_by=user.user_id,
    )
    await db.commit()

    from app.workers.tasks.email_sync import gmail_historical_import_single
    gmail_historical_import_single.apply_async(
        args=[str(user.tenant_id), str(config_id), str(job.id), after_date],
        queue="sync",
    )
    return {"data": EmailSyncJobResponse.model_validate(job), "errors": None}


@router.delete("/gmail/disconnect", response_model=APIResponse[None])
async def gmail_disconnect(
    user: OwnerDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID = Query(...),
) -> dict:
    repo = EmailSyncRepository(db)
    await repo.deactivate_config(user.tenant_id, config_id)
    await db.commit()
    return {"data": None, "errors": None}


@router.get("/gmail/sync-jobs", response_model=PaginatedResponse[EmailSyncJobResponse])
async def gmail_sync_jobs(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    repo = EmailSyncRepository(db)
    offset = (page - 1) * limit
    jobs, total = await repo.list_jobs(user.tenant_id, config_id=config_id, limit=limit, offset=offset)
    return {
        "data": [EmailSyncJobResponse.model_validate(j) for j in jobs],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


# ---------------------------------------------------------------------------
# Outlook
# ---------------------------------------------------------------------------

@router.get("/outlook/auth-url", response_model=APIResponse[dict])
async def outlook_auth_url(user: OwnerDep) -> dict:
    from app.services.email.outlook_client import build_outlook_auth_url
    state = f"{user.tenant_id}:{user.user_id}:{secrets.token_urlsafe(16)}"
    url = build_outlook_auth_url(redirect_uri=_api_callback_url("outlook"), state=state)
    return {"data": {"url": url}, "errors": None}


@router.get("/outlook/callback")
async def outlook_callback(code: str, state: str, db: AsyncSessionDep):
    from app.services.email.outlook_client import exchange_outlook_code, OutlookClient

    try:
        parts = state.split(":")
        tenant_id = uuid.UUID(parts[0])
        token_data = await exchange_outlook_code(code, _api_callback_url("outlook"))

        async with OutlookClient(token_data["access_token"], token_data.get("refresh_token", "")) as client:
            email_address, _ = await client.get_me()

        cred = IntegrationCredential(
            tenant_id=tenant_id,
            provider="outlook",
            access_token_encrypted=encrypt_value(token_data["access_token"]),
            refresh_token_encrypted=encrypt_value(token_data.get("refresh_token", "")),
        )
        db.add(cred)
        await db.flush()

        repo = EmailSyncRepository(db)
        await repo.upsert_config(
            tenant_id=tenant_id,
            provider="outlook",
            email_address=email_address,
            integration_credential_id=cred.id,
        )
        await db.commit()
        logger.info("outlook_connected", tenant_id=str(tenant_id), email=email_address)
    except Exception as e:
        logger.error("outlook_callback_failed", error=str(e))
        return RedirectResponse(_frontend_url("/integrations?error=outlook_failed"))

    return RedirectResponse(_frontend_url("/integrations?connected=outlook"))


@router.get("/outlook/status", response_model=APIResponse[list[EmailSyncConfigResponse]])
async def outlook_status(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = EmailSyncRepository(db)
    configs = await repo.list_configs(user.tenant_id, provider="outlook")
    return {"data": [EmailSyncConfigResponse.model_validate(c) for c in configs], "errors": None}


@router.post("/outlook/sync", response_model=APIResponse[EmailSyncJobResponse])
async def outlook_manual_sync(
    user: ManagerDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID = Query(...),
) -> dict:
    repo = EmailSyncRepository(db)
    config = await repo.get_config_by_id(user.tenant_id, config_id)
    if not config:
        raise NotFoundError("Outlook config not found")

    job = await repo.create_job(
        tenant_id=user.tenant_id,
        config_id=config.id,
        provider="outlook",
        triggered_by=user.user_id,
    )
    await db.commit()

    from app.workers.tasks.email_sync import outlook_sync_single
    outlook_sync_single.apply_async(
        args=[str(user.tenant_id), str(config_id), str(job.id)],
        queue="sync",
    )
    return {"data": EmailSyncJobResponse.model_validate(job), "errors": None}


@router.delete("/outlook/disconnect", response_model=APIResponse[None])
async def outlook_disconnect(
    user: OwnerDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID = Query(...),
) -> dict:
    repo = EmailSyncRepository(db)
    await repo.deactivate_config(user.tenant_id, config_id)
    await db.commit()
    return {"data": None, "errors": None}
