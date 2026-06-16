"""Integration tests for P&L API endpoints."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.db.models.expense import Expense
from app.db.models.toast import ToastOrder
from app.db.models.tenant import Tenant


async def _create_order(
    db_session,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    *,
    net_amount: Decimal = Decimal("1000.00"),
    discount_amount: Decimal = Decimal("0.00"),
    is_void: bool = False,
) -> ToastOrder:
    order = ToastOrder(
        tenant_id=tenant_id,
        location_id=location_id,
        toast_order_id=f"order_{uuid.uuid4().hex[:8]}",
        net_amount=net_amount,
        discount_amount=discount_amount,
        is_void=is_void,
        closed_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        business_date="20240615",
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _create_expense(
    db_session,
    tenant_id: uuid.UUID,
    *,
    category: str = "Food Cost",
    amount: Decimal = Decimal("300.00"),
) -> Expense:
    expense = Expense(
        tenant_id=tenant_id,
        vendor_name="Sysco",
        amount=amount,
        currency_code="CAD",
        category=category,
        is_ai_categorized=False,
        user_overridden=False,
    )
    db_session.add(expense)
    await db_session.commit()
    await db_session.refresh(expense)
    return expense


# ---------------------------------------------------------------------------
# GET /pnl/report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pnl_report_empty_period(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "2020-01-01", "period_end": "2020-01-31"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["line_items"]["net_revenue"] is None
    assert data["order_count"] == 0
    assert data["expense_count"] == 0


@pytest.mark.asyncio
async def test_pnl_report_with_orders_and_expenses(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant, location_id: uuid.UUID
):
    await _create_order(db_session, tenant.id, location_id, net_amount=Decimal("2000.00"))
    await _create_expense(db_session, tenant.id, category="Food Cost", amount=Decimal("500.00"))

    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "2024-06-01", "period_end": "2024-06-30"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    li = resp.json()["data"]["line_items"]
    assert li["net_revenue"] == "2000.00"
    assert li["cogs"] == "500.00"
    assert li["gross_profit"] == "1500.00"


@pytest.mark.asyncio
async def test_pnl_report_viewer_allowed(client: AsyncClient, viewer_token: str):
    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "2024-06-01", "period_end": "2024-06-30"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_pnl_report_unauthenticated(client: AsyncClient):
    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "2024-06-01", "period_end": "2024-06-30"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pnl_report_invalid_date_format(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "not-a-date", "period_end": "2024-06-30"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_pnl_report_missing_required_params(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/pnl/report",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pnl_report_tenant_isolation(
    client: AsyncClient,
    db_session,
    tenant: Tenant,
    location_id: uuid.UUID,
    owner_token: str,
    other_tenant_owner_token: str,
):
    await _create_order(db_session, tenant.id, location_id, net_amount=Decimal("9999.00"))

    # Other tenant's report should show 0, not 9999
    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "2024-06-01", "period_end": "2024-06-30"},
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["line_items"]["net_revenue"] is None


# ---------------------------------------------------------------------------
# GET /pnl/snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pnl_snapshots_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/pnl/snapshots",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_list_pnl_snapshots_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/pnl/snapshots")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Percentage calculations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pnl_report_percentage_fields(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant, location_id: uuid.UUID
):
    await _create_order(db_session, tenant.id, location_id, net_amount=Decimal("1000.00"))
    await _create_expense(db_session, tenant.id, category="Food Cost", amount=Decimal("300.00"))

    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "2024-06-01", "period_end": "2024-06-30"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    li = resp.json()["data"]["line_items"]
    # COGS = 300 / 1000 = 30%
    assert li["cogs_pct"] == "30.00"


@pytest.mark.asyncio
async def test_pnl_report_expense_breakdown_present(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_expense(db_session, tenant.id, category="Utilities", amount=Decimal("150.00"))
    await _create_expense(db_session, tenant.id, category="Utilities", amount=Decimal("50.00"))

    resp = await client.get(
        "/api/v1/pnl/report",
        params={"period_start": "2024-01-01", "period_end": "2026-12-31"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    breakdown = resp.json()["data"]["expense_breakdown"]
    utilities = next((b for b in breakdown if b["category"] == "Utilities"), None)
    assert utilities is not None
    assert utilities["expense_count"] == 2
