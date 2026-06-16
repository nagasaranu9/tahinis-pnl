"""
Google Business Profile Reviews endpoints.

OAuth flow:
  GET  /reviews/auth-url      → OAuth consent URL
  GET  /reviews/callback      → exchange code, store tokens, redirect
  GET  /reviews/status        → list connected configs
  GET  /reviews/summary       → aggregate rating + star breakdown + recent reviews
  GET  /reviews/list          → paginated reviews
  POST /reviews/sync          → manual sync trigger
  DELETE /reviews/disconnect  → deactivate config
"""
import secrets
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.core.deps import CurrentUserDep, ManagerDep, OwnerDep
from app.core.security import decrypt_value, encrypt_value
from app.db.models.integration import IntegrationCredential
from app.db.repositories.reviews_repo import ReviewsRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.google_reviews import (
    GoogleReviewConfigResponse,
    GoogleReviewLocationOverride,
    GoogleReviewResponse,
    ReviewsSummaryResponse,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


def _frontend_url(path: str) -> str:
    from app.core.config import settings
    return f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}{path}"


def _api_callback_url() -> str:
    from app.core.config import settings
    return f"{getattr(settings, 'API_BASE_URL', 'http://localhost:8000')}/api/v1/reviews/callback"


@router.get("/auth-url", response_model=APIResponse[dict])
async def reviews_auth_url(user: OwnerDep) -> dict:
    from app.services.google.reviews_client import build_reviews_auth_url
    state = f"{user.tenant_id}:{user.user_id}:{secrets.token_urlsafe(16)}"
    url = build_reviews_auth_url(redirect_uri=_api_callback_url(), state=state)
    return {"data": {"url": url}, "errors": None}


@router.get("/callback")
async def reviews_callback(code: str, state: str, db: AsyncSessionDep):
    from app.services.google.reviews_client import exchange_reviews_code

    try:
        parts = state.split(":")
        tenant_id = uuid.UUID(parts[0])

        token_data = await exchange_reviews_code(code, _api_callback_url())
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")

        # Account/location are no longer auto-discovered here — that lookup hits Google's
        # daily-quota-limited accounts/locations API and blocks indefinitely on 429.
        # The owner sets account_name/location_name via PATCH /reviews/config/location
        # (values copied from the business.google.com dashboard URL), and sync just uses
        # those directly. See set_review_location below.
        account_name = None
        location_name = None
        place_id = "pending"

        cred = IntegrationCredential(
            tenant_id=tenant_id,
            provider="google_business",
            access_token_encrypted=encrypt_value(access_token),
            refresh_token_encrypted=encrypt_value(refresh_token),
        )
        db.add(cred)
        await db.flush()

        # Use first location in DB for this tenant
        from sqlalchemy import select
        from app.db.models.location import Location
        loc_row = (await db.execute(
            select(Location).where(Location.tenant_id == tenant_id).limit(1)
        )).scalar_one_or_none()

        if loc_row:
            repo = ReviewsRepository(db)
            await repo.upsert_config(
                tenant_id=tenant_id,
                location_id=loc_row.id,
                place_id=place_id,
                account_name=account_name,
                location_name=location_name,
                integration_credential_id=cred.id,
            )

        await db.commit()
        logger.info("google_reviews_connected", tenant_id=str(tenant_id), account=account_name)

    except Exception as e:
        logger.error("google_reviews_callback_failed", error=str(e))
        return RedirectResponse(_frontend_url("/reviews?error=google_reviews_failed"))

    return RedirectResponse(_frontend_url("/reviews?connected=google"))


@router.get("/status", response_model=APIResponse[list[GoogleReviewConfigResponse]])
async def reviews_status(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = ReviewsRepository(db)
    configs = await repo.list_configs(user.tenant_id)
    return {"data": [GoogleReviewConfigResponse.model_validate(c) for c in configs], "errors": None}


@router.get("/summary", response_model=APIResponse[ReviewsSummaryResponse])
async def reviews_summary(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    repo = ReviewsRepository(db)
    summary = await repo.get_summary(user.tenant_id, location_id)
    recent, _ = await repo.list_reviews(user.tenant_id, location_id, page=1, limit=5)
    return {
        "data": ReviewsSummaryResponse(
            **summary,
            recent_reviews=[GoogleReviewResponse.model_validate(r) for r in recent],
        ),
        "errors": None,
    }


@router.get("/list", response_model=PaginatedResponse[GoogleReviewResponse])
async def reviews_list(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    repo = ReviewsRepository(db)
    rows, total = await repo.list_reviews(user.tenant_id, location_id, page=page, limit=limit)
    return {
        "data": [GoogleReviewResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.post("/sync", response_model=APIResponse[dict])
async def reviews_sync(
    user: ManagerDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    from app.workers.tasks.reviews_sync import sync_reviews

    repo = ReviewsRepository(db)
    configs = await repo.list_configs(user.tenant_id)
    if not configs:
        return {"data": {"queued": 0}, "errors": None}

    targets = [c for c in configs if not location_id or c.location_id == location_id]
    for cfg in targets:
        sync_reviews.apply_async(
            kwargs={"tenant_id": str(user.tenant_id), "location_id": str(cfg.location_id)},
            queue="sync",
        )

    return {"data": {"queued": len(targets)}, "errors": None}


@router.patch("/config/location", response_model=APIResponse[GoogleReviewConfigResponse])
async def set_review_location(
    user: OwnerDep,
    db: AsyncSessionDep,
    body: GoogleReviewLocationOverride,
) -> dict:
    """Manually pin account_name/location_name (e.g. 'accounts/123', 'accounts/123/locations/456')
    so sync can skip the accounts/locations discovery calls, which are gated by Google's daily
    API quota and can block discovery indefinitely. Get these from the business.google.com
    dashboard URL when discovery is quota-blocked."""
    repo = ReviewsRepository(db)
    config = await repo.set_manual_location(
        tenant_id=user.tenant_id,
        location_id=body.location_id,
        account_name=body.account_name,
        location_name=body.location_name,
    )
    await db.commit()
    return {"data": GoogleReviewConfigResponse.model_validate(config), "errors": None}


@router.delete("/disconnect", response_model=APIResponse[None])
async def reviews_disconnect(
    user: OwnerDep,
    db: AsyncSessionDep,
    config_id: uuid.UUID = Query(...),
) -> dict:
    repo = ReviewsRepository(db)
    await repo.deactivate_config(user.tenant_id, config_id)
    await db.commit()
    return {"data": None, "errors": None}
