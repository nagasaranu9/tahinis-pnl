"""Integration tests for AI Insights API endpoints."""
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.db.models.ai_insight import AIInsight
from app.db.models.tenant import Tenant


async def _create_insight(
    db_session,
    tenant_id: uuid.UUID,
    *,
    insight_type: str = "pnl_summary",
    severity: str = "info",
    title: str = "Test Insight",
    is_dismissed: bool = False,
) -> AIInsight:
    insight = AIInsight(
        tenant_id=tenant_id,
        insight_type=insight_type,
        severity=severity,
        title=title,
        summary="This is a test summary.",
        explanation="Detailed explanation here.",
        confidence_score=Decimal("0.8500"),
        is_dismissed=is_dismissed,
    )
    db_session.add(insight)
    await db_session.commit()
    await db_session.refresh(insight)
    return insight


# ---------------------------------------------------------------------------
# GET /ai/insights
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_insights_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/ai/insights",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_list_insights_returns_data(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_insight(db_session, tenant.id, title="Revenue up 15%")

    resp = await client.get(
        "/api/v1/ai/insights",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["title"] == "Revenue up 15%"


@pytest.mark.asyncio
async def test_list_insights_excludes_dismissed_by_default(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_insight(db_session, tenant.id, is_dismissed=False)
    await _create_insight(db_session, tenant.id, is_dismissed=True)

    resp = await client.get(
        "/api/v1/ai/insights",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.json()["meta"]["total"] == 1


@pytest.mark.asyncio
async def test_list_insights_include_dismissed(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_insight(db_session, tenant.id, is_dismissed=False)
    await _create_insight(db_session, tenant.id, is_dismissed=True)

    resp = await client.get(
        "/api/v1/ai/insights",
        params={"include_dismissed": "true"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.json()["meta"]["total"] == 2


@pytest.mark.asyncio
async def test_list_insights_filter_by_type(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_insight(db_session, tenant.id, insight_type="pnl_summary")
    await _create_insight(db_session, tenant.id, insight_type="expense_anomaly")

    resp = await client.get(
        "/api/v1/ai/insights",
        params={"insight_type": "pnl_summary"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["insight_type"] == "pnl_summary"


@pytest.mark.asyncio
async def test_list_insights_viewer_allowed(client: AsyncClient, viewer_token: str):
    resp = await client.get(
        "/api/v1/ai/insights",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_insights_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/ai/insights")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /ai/insights/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_insight_by_id(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    insight = await _create_insight(db_session, tenant.id)

    resp = await client.get(
        f"/api/v1/ai/insights/{insight.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == str(insight.id)
    assert resp.json()["data"]["confidence_score"] == "0.8500"


@pytest.mark.asyncio
async def test_get_insight_not_found(client: AsyncClient, owner_token: str):
    resp = await client.get(
        f"/api/v1/ai/insights/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /ai/insights/generate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_insight_manager_allowed(client: AsyncClient, manager_token: str):
    with patch("app.workers.tasks.ai_insights.generate_insights_on_demand.apply_async"):
        resp = await client.post(
            "/api/v1/ai/insights/generate",
            json={
                "insight_type": "pnl_summary",
                "period_start": "2024-06-01",
                "period_end": "2024-06-30",
            },
            headers={"Authorization": f"Bearer {manager_token}"},
        )
    assert resp.status_code == 202
    assert resp.json()["data"]["status"] == "queued"


@pytest.mark.asyncio
async def test_generate_insight_viewer_forbidden(client: AsyncClient, viewer_token: str):
    resp = await client.post(
        "/api/v1/ai/insights/generate",
        json={
            "insight_type": "pnl_summary",
            "period_start": "2024-06-01",
            "period_end": "2024-06-30",
        },
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_generate_insight_invalid_type(client: AsyncClient, manager_token: str):
    resp = await client.post(
        "/api/v1/ai/insights/generate",
        json={
            "insight_type": "not_a_real_type",
            "period_start": "2024-06-01",
            "period_end": "2024-06-30",
        },
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_insight_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/api/v1/ai/insights/generate",
        json={"insight_type": "pnl_summary", "period_start": "2024-06-01", "period_end": "2024-06-30"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /ai/insights/{id}/dismiss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_insight(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    insight = await _create_insight(db_session, tenant.id)

    resp = await client.post(
        f"/api/v1/ai/insights/{insight.id}/dismiss",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_dismissed"] is True


@pytest.mark.asyncio
async def test_dismiss_insight_not_found(client: AsyncClient, owner_token: str):
    resp = await client.post(
        f"/api/v1/ai/insights/{uuid.uuid4()}/dismiss",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_insight_unauthenticated(client: AsyncClient):
    resp = await client.post(f"/api/v1/ai/insights/{uuid.uuid4()}/dismiss", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /ai/insights/{id}/feedback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_helpful(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    insight = await _create_insight(db_session, tenant.id)

    resp = await client.post(
        f"/api/v1/ai/insights/{insight.id}/feedback",
        json={"is_helpful": True},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_helpful"] is True


@pytest.mark.asyncio
async def test_feedback_not_helpful(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    insight = await _create_insight(db_session, tenant.id)

    resp = await client.post(
        f"/api/v1/ai/insights/{insight.id}/feedback",
        json={"is_helpful": False},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_helpful"] is False


@pytest.mark.asyncio
async def test_feedback_missing_field(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    insight = await _create_insight(db_session, tenant.id)
    resp = await client.post(
        f"/api/v1/ai/insights/{insight.id}/feedback",
        json={},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feedback_unauthenticated(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/ai/insights/{uuid.uuid4()}/feedback",
        json={"is_helpful": True},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insights_tenant_isolation(
    client: AsyncClient,
    db_session,
    tenant: Tenant,
    owner_token: str,
    other_tenant_owner_token: str,
):
    insight = await _create_insight(db_session, tenant.id, title="Private Insight")

    resp = await client.get(
        "/api/v1/ai/insights",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    titles = [i["title"] for i in resp.json()["data"]]
    assert "Private Insight" not in titles

    resp2 = await client.get(
        f"/api/v1/ai/insights/{insight.id}",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp2.status_code == 404
