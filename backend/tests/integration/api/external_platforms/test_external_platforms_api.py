"""Integration tests for external platform API endpoints."""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.db.models.external_platform import (
    GoogleAdsCampaign,
    GoogleAdsDailyMetric,
    GoogleReviewSnapshot,
)
from app.db.models.tenant import Tenant


async def _create_review_snapshot(
    db_session,
    tenant_id: uuid.UUID,
    *,
    snapshot_date: str = "2024-06-15",
    rating_average: Decimal = Decimal("4.5"),
    review_count_total: int = 100,
    new_reviews_count: int = 2,
) -> GoogleReviewSnapshot:
    snap = GoogleReviewSnapshot(
        tenant_id=tenant_id,
        snapshot_date=snapshot_date,
        rating_average=rating_average,
        review_count_total=review_count_total,
        new_reviews_count=new_reviews_count,
        positive_count=1,
        neutral_count=1,
        negative_count=0,
    )
    db_session.add(snap)
    await db_session.commit()
    await db_session.refresh(snap)
    return snap


async def _create_campaign(
    db_session, tenant_id: uuid.UUID, *, name: str = "Test Campaign"
) -> GoogleAdsCampaign:
    campaign = GoogleAdsCampaign(
        tenant_id=tenant_id,
        google_campaign_id=f"cmp_{uuid.uuid4().hex[:8]}",
        google_customer_id="cust_001",
        name=name,
        status="ENABLED",
        campaign_type="SEARCH",
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


async def _create_metric(
    db_session,
    tenant_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    metric_date: str = "2024-06-15",
    spend: Decimal = Decimal("50.00"),
) -> GoogleAdsDailyMetric:
    metric = GoogleAdsDailyMetric(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        metric_date=metric_date,
        spend=spend,
        impressions=400,
        clicks=20,
        conversions=Decimal("2.5"),
        roas=Decimal("3.0000"),
        currency_code="CAD",
    )
    db_session.add(metric)
    await db_session.commit()
    await db_session.refresh(metric)
    return metric


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_review_snapshots_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/external/reviews/snapshots",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_list_review_snapshots_returns_data(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_review_snapshot(db_session, tenant.id)

    resp = await client.get(
        "/api/v1/external/reviews/snapshots",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["rating_average"] == "4.50"


@pytest.mark.asyncio
async def test_list_review_snapshots_date_filter(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_review_snapshot(db_session, tenant.id, snapshot_date="2024-06-01")
    await _create_review_snapshot(db_session, tenant.id, snapshot_date="2024-07-15")

    resp = await client.get(
        "/api/v1/external/reviews/snapshots",
        params={"start_date": "2024-07-01", "end_date": "2024-07-31"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["snapshot_date"] == "2024-07-15"


@pytest.mark.asyncio
async def test_list_review_snapshots_viewer_allowed(client: AsyncClient, viewer_token: str):
    resp = await client.get(
        "/api/v1/external/reviews/snapshots",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_review_snapshots_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/external/reviews/snapshots")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tenant isolation — reviews
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_snapshots_tenant_isolation(
    client: AsyncClient,
    db_session,
    tenant: Tenant,
    owner_token: str,
    other_tenant_owner_token: str,
):
    snap = await _create_review_snapshot(db_session, tenant.id)

    resp = await client.get(
        "/api/v1/external/reviews/snapshots",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    ids = [s["id"] for s in resp.json()["data"]]
    assert str(snap.id) not in ids


# ---------------------------------------------------------------------------
# Ads campaigns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_campaigns_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/external/ads/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_list_campaigns_returns_data(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_campaign(db_session, tenant.id, name="Brand Search")

    resp = await client.get(
        "/api/v1/external/ads/campaigns",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
    assert resp.json()["data"][0]["name"] == "Brand Search"


@pytest.mark.asyncio
async def test_list_campaigns_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/external/ads/campaigns")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Ads metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ads_metrics_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/external/ads/metrics",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_list_ads_metrics_returns_data(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    campaign = await _create_campaign(db_session, tenant.id)
    await _create_metric(db_session, tenant.id, campaign.id, spend=Decimal("75.00"))

    resp = await client.get(
        "/api/v1/external/ads/metrics",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["spend"] == "75.00"


@pytest.mark.asyncio
async def test_list_ads_metrics_filter_by_campaign(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    camp_a = await _create_campaign(db_session, tenant.id, name="Camp A")
    camp_b = await _create_campaign(db_session, tenant.id, name="Camp B")
    await _create_metric(db_session, tenant.id, camp_a.id, metric_date="2024-06-01")
    await _create_metric(db_session, tenant.id, camp_b.id, metric_date="2024-06-02")

    resp = await client.get(
        "/api/v1/external/ads/metrics",
        params={"campaign_id": str(camp_a.id)},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["campaign_id"] == str(camp_a.id)


@pytest.mark.asyncio
async def test_list_ads_metrics_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/external/ads/metrics")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Ads summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ads_summary_aggregates_totals(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    campaign = await _create_campaign(db_session, tenant.id)
    await _create_metric(db_session, tenant.id, campaign.id, metric_date="2024-06-01", spend=Decimal("50.00"))
    await _create_metric(db_session, tenant.id, campaign.id, metric_date="2024-06-02", spend=Decimal("70.00"))

    resp = await client.get(
        "/api/v1/external/ads/summary",
        params={"start_date": "2024-06-01", "end_date": "2024-06-30"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert float(data["total_spend"]) == pytest.approx(120.0)
    assert data["total_impressions"] == 800  # 400 × 2 rows


@pytest.mark.asyncio
async def test_ads_summary_missing_params(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/external/ads/summary",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ads_summary_unauthenticated(client: AsyncClient):
    resp = await client.get(
        "/api/v1/external/ads/summary",
        params={"start_date": "2024-06-01", "end_date": "2024-06-30"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tenant isolation — ads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ads_campaigns_tenant_isolation(
    client: AsyncClient,
    db_session,
    tenant: Tenant,
    owner_token: str,
    other_tenant_owner_token: str,
):
    campaign = await _create_campaign(db_session, tenant.id, name="Private Campaign")

    resp = await client.get(
        "/api/v1/external/ads/campaigns",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    names = [c["name"] for c in resp.json()["data"]]
    assert "Private Campaign" not in names
