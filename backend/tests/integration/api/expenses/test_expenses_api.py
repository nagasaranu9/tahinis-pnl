"""Integration tests for expenses API endpoints."""
import uuid
import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.db.models.expense import Expense


async def _create_expense(db_session, tenant_id: uuid.UUID) -> Expense:
    expense = Expense(
        tenant_id=tenant_id,
        vendor_name="Sysco Canada",
        amount=Decimal("500.00"),
        currency_code="CAD",
        category=None,
        is_ai_categorized=False,
        user_overridden=False,
    )
    db_session.add(expense)
    await db_session.commit()
    await db_session.refresh(expense)
    return expense


@pytest.mark.asyncio
async def test_list_expenses_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_list_expenses_returns_tenant_data(
    client: AsyncClient, owner_token: str, db_session, tenant
):
    await _create_expense(db_session, tenant.id)

    resp = await client.get(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["vendor_name"] == "Sysco Canada"


@pytest.mark.asyncio
async def test_get_expense_by_id(client: AsyncClient, owner_token: str, db_session, tenant):
    expense = await _create_expense(db_session, tenant.id)

    resp = await client.get(
        f"/api/v1/expenses/{expense.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == str(expense.id)


@pytest.mark.asyncio
async def test_get_expense_not_found(client: AsyncClient, owner_token: str):
    resp = await client.get(
        f"/api/v1/expenses/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_override_category_manager(
    client: AsyncClient, manager_token: str, db_session, tenant
):
    expense = await _create_expense(db_session, tenant.id)

    resp = await client.patch(
        f"/api/v1/expenses/{expense.id}/category",
        json={"category": "Food Cost"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["category"] == "Food Cost"
    assert data["user_overridden"] is True


@pytest.mark.asyncio
async def test_override_category_invalid(
    client: AsyncClient, manager_token: str, db_session, tenant
):
    expense = await _create_expense(db_session, tenant.id)

    resp = await client.patch(
        f"/api/v1/expenses/{expense.id}/category",
        json={"category": "Office Supplies"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_viewer_cannot_override_category(
    client: AsyncClient, viewer_token: str, db_session, tenant
):
    expense = await _create_expense(db_session, tenant.id)

    resp = await client.patch(
        f"/api/v1/expenses/{expense.id}/category",
        json={"category": "Food Cost"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_expense_tenant_isolation(
    client: AsyncClient,
    owner_token: str,
    other_tenant_owner_token: str,
    db_session,
    tenant,
):
    await _create_expense(db_session, tenant.id)

    resp_a = await client.get(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp_a.json()["meta"]["total"] == 1

    resp_b = await client.get(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp_b.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_filter_uncategorized_only(
    client: AsyncClient, owner_token: str, db_session, tenant
):
    # One uncategorized, one categorized
    await _create_expense(db_session, tenant.id)
    categorized = Expense(
        tenant_id=tenant.id,
        vendor_name="Rogers",
        amount=Decimal("200.00"),
        currency_code="CAD",
        category="Utilities",
        is_ai_categorized=True,
        user_overridden=False,
    )
    db_session.add(categorized)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/expenses?uncategorized_only=true",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["category"] is None


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client: AsyncClient):
    resp = await client.get("/api/v1/expenses")
    assert resp.status_code == 401
