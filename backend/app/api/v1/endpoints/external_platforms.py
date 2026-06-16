"""External platform data endpoints (Google Reviews + Google Ads)."""
import uuid
from decimal import Decimal

import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentUserDep, OwnerDep
from app.core.security import encrypt_value
from app.db.models.integration import IntegrationCredential
from app.db.repositories.external_platform_repo import ExternalPlatformRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.external_platform import (
    GoogleAdsDailyMetricResponse,
    GoogleAdsSummaryResponse,
    GoogleReviewSnapshotResponse,
    GoogleAdsCampaignResponse,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


# -------------------------------------------------------- ad connectors
# Google Ads and Meta Ads use long-lived API credentials (no interactive OAuth
# redirect flow here, unlike Gmail/Outlook/Reviews) — owner pastes the
# customer/account ID + token from their ad account dashboard.

class AdConnectorStatus(BaseModel):
    connected: bool
    account_id: str | None = None


class GoogleAdsConnectRequest(BaseModel):
    customer_id: str
    developer_token: str
    refresh_token: str


class MetaAdsConnectRequest(BaseModel):
    ad_account_id: str
    access_token: str


async def _connector_status(db: AsyncSessionDep, tenant_id: uuid.UUID, provider: str) -> AdConnectorStatus:
    cred = (await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.tenant_id == tenant_id,
            IntegrationCredential.provider == provider,
            IntegrationCredential.is_active == True,
        ).order_by(IntegrationCredential.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if not cred:
        return AdConnectorStatus(connected=False)
    account_id = (cred.extra_config or {}).get("account_id")
    return AdConnectorStatus(connected=True, account_id=account_id)


async def _connector_disconnect(db: AsyncSessionDep, tenant_id: uuid.UUID, provider: str) -> None:
    rows = (await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.tenant_id == tenant_id,
            IntegrationCredential.provider == provider,
        )
    )).scalars().all()
    for row in rows:
        row.is_active = False


@router.get("/google-ads/status", response_model=APIResponse[AdConnectorStatus])
async def google_ads_status(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    return {"data": await _connector_status(db, user.tenant_id, "google_ads"), "errors": None}


@router.post("/google-ads/connect", response_model=APIResponse[AdConnectorStatus])
async def google_ads_connect(
    user: OwnerDep, db: AsyncSessionDep, body: GoogleAdsConnectRequest
) -> dict:
    await _connector_disconnect(db, user.tenant_id, "google_ads")
    cred = IntegrationCredential(
        tenant_id=user.tenant_id,
        provider="google_ads",
        refresh_token_encrypted=encrypt_value(body.refresh_token),
        access_token_encrypted=encrypt_value(body.developer_token),
        extra_config={"account_id": body.customer_id},
    )
    db.add(cred)
    await db.commit()
    logger.info("google_ads_connected", tenant_id=str(user.tenant_id), customer_id=body.customer_id)
    return {"data": AdConnectorStatus(connected=True, account_id=body.customer_id), "errors": None}


@router.delete("/google-ads/disconnect", response_model=APIResponse[None])
async def google_ads_disconnect(user: OwnerDep, db: AsyncSessionDep) -> dict:
    await _connector_disconnect(db, user.tenant_id, "google_ads")
    await db.commit()
    return {"data": None, "errors": None}


@router.get("/meta-ads/status", response_model=APIResponse[AdConnectorStatus])
async def meta_ads_status(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    return {"data": await _connector_status(db, user.tenant_id, "meta_ads"), "errors": None}


@router.post("/meta-ads/connect", response_model=APIResponse[AdConnectorStatus])
async def meta_ads_connect(
    user: OwnerDep, db: AsyncSessionDep, body: MetaAdsConnectRequest
) -> dict:
    await _connector_disconnect(db, user.tenant_id, "meta_ads")
    cred = IntegrationCredential(
        tenant_id=user.tenant_id,
        provider="meta_ads",
        access_token_encrypted=encrypt_value(body.access_token),
        extra_config={"account_id": body.ad_account_id},
    )
    db.add(cred)
    await db.commit()
    logger.info("meta_ads_connected", tenant_id=str(user.tenant_id), account_id=body.ad_account_id)
    return {"data": AdConnectorStatus(connected=True, account_id=body.ad_account_id), "errors": None}


@router.delete("/meta-ads/disconnect", response_model=APIResponse[None])
async def meta_ads_disconnect(user: OwnerDep, db: AsyncSessionDep) -> dict:
    await _connector_disconnect(db, user.tenant_id, "meta_ads")
    await db.commit()
    return {"data": None, "errors": None}


# ------------------------------------------------------------------ reviews

@router.get("/reviews/snapshots", response_model=PaginatedResponse[GoogleReviewSnapshotResponse])
async def list_review_snapshots(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    limit: int = Query(90, ge=1, le=365),
) -> dict:
    repo = ExternalPlatformRepository(db)
    rows, total = await repo.list_review_snapshots(
        tenant_id=user.tenant_id,
        location_id=location_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        limit=limit,
    )
    return {
        "data": [GoogleReviewSnapshotResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


# ------------------------------------------------------------------ ads

@router.get("/ads/campaigns", response_model=APIResponse[list[GoogleAdsCampaignResponse]])
async def list_campaigns(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    repo = ExternalPlatformRepository(db)
    campaigns = await repo.list_campaigns(tenant_id=user.tenant_id, location_id=location_id)
    return {
        "data": [GoogleAdsCampaignResponse.model_validate(c) for c in campaigns],
        "errors": None,
    }


@router.get("/ads/metrics", response_model=PaginatedResponse[GoogleAdsDailyMetricResponse])
async def list_ads_metrics(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    campaign_id: uuid.UUID | None = Query(None),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    limit: int = Query(90, ge=1, le=365),
) -> dict:
    repo = ExternalPlatformRepository(db)
    rows, total = await repo.list_daily_metrics(
        tenant_id=user.tenant_id,
        campaign_id=campaign_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        limit=limit,
    )
    return {
        "data": [GoogleAdsDailyMetricResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.get("/ads/summary", response_model=APIResponse[GoogleAdsSummaryResponse])
async def ads_summary(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    repo = ExternalPlatformRepository(db)
    campaigns = await repo.list_campaigns(tenant_id=user.tenant_id, location_id=location_id)
    rows, _ = await repo.list_daily_metrics(
        tenant_id=user.tenant_id,
        start_date=start_date,
        end_date=end_date,
        limit=9999,
    )

    total_spend = sum((r.spend or Decimal("0") for r in rows), Decimal("0"))
    total_impressions = sum(r.impressions for r in rows)
    total_clicks = sum(r.clicks for r in rows)
    total_conversions = sum((r.conversions or Decimal("0") for r in rows), Decimal("0"))
    avg_roas: Decimal | None = None
    roas_values = [r.roas for r in rows if r.roas is not None]
    if roas_values:
        avg_roas = sum(roas_values, Decimal("0")) / len(roas_values)

    summary = GoogleAdsSummaryResponse(
        period_start=start_date,
        period_end=end_date,
        total_spend=total_spend,
        total_impressions=total_impressions,
        total_clicks=total_clicks,
        total_conversions=total_conversions,
        average_roas=avg_roas,
        campaigns=[GoogleAdsCampaignResponse.model_validate(c) for c in campaigns],
        daily_metrics=[GoogleAdsDailyMetricResponse.model_validate(r) for r in rows],
    )
    return {"data": summary, "errors": None}
