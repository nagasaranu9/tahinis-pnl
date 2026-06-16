"""Integration tests for reconciliation API endpoints.

Covers RBAC enforcement, tenant isolation, and happy-path flows.
Celery tasks are patched so no worker is needed.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.db.models.reconciliation import ReconciliationFlag, ReconciliationRun
from app.db.models.tenant import Tenant
from app.db.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PERIOD_START = "2024-06-01T00:00:00Z"
_PERIOD_END = "2024-06-30T23:59:59Z"


async def _create_run(db_session, tenant_id: uuid.UUID, status: str = "complete") -> ReconciliationRun:
    run = ReconciliationRun(
        tenant_id=tenant_id,
        period_start=datetime(2024, 6, 1, tzinfo=timezone.utc),
        period_end=datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
        status=status,
        documents_checked=5,
        expenses_checked=3,
        toast_orders_checked=10,
        flags_raised=2,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def _create_flag(
    db_session,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    flag_type: str = "uncategorized_expense",
    severity: str = "medium",
    is_resolved: bool = False,
) -> ReconciliationFlag:
    flag = ReconciliationFlag(
        tenant_id=tenant_id,
        run_id=run_id,
        flag_type=flag_type,
        severity=severity,
        message="Test flag message.",
        is_resolved=is_resolved,
    )
    db_session.add(flag)
    await db_session.commit()
    await db_session.refresh(flag)
    return flag


# ---------------------------------------------------------------------------
# POST /reconciliation/runs  — trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_reconciliation_as_manager(
    client: AsyncClient, manager_token: str
):
    with patch("app.workers.tasks.reconciliation.run_reconciliation.apply_async"):
        resp = await client.post(
            "/api/v1/reconciliation/runs",
            json={"period_start": _PERIOD_START, "period_end": _PERIOD_END},
            headers={"Authorization": f"Bearer {manager_token}"},
        )
    assert resp.status_code == 202
    data = resp.json()["data"]
    assert data["status"] == "pending"
    assert data["period_start"].startswith("2024-06-01")


@pytest.mark.asyncio
async def test_trigger_reconciliation_as_owner(
    client: AsyncClient, owner_token: str
):
    with patch("app.workers.tasks.reconciliation.run_reconciliation.apply_async"):
        resp = await client.post(
            "/api/v1/reconciliation/runs",
            json={"period_start": _PERIOD_START, "period_end": _PERIOD_END},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_trigger_reconciliation_viewer_forbidden(
    client: AsyncClient, viewer_token: str
):
    resp = await client.post(
        "/api/v1/reconciliation/runs",
        json={"period_start": _PERIOD_START, "period_end": _PERIOD_END},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trigger_reconciliation_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/api/v1/reconciliation/runs",
        json={"period_start": _PERIOD_START, "period_end": _PERIOD_END},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trigger_reconciliation_invalid_period(
    client: AsyncClient, manager_token: str
):
    resp = await client.post(
        "/api/v1/reconciliation/runs",
        json={"period_start": "not-a-date", "period_end": _PERIOD_END},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /reconciliation/runs  — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/reconciliation/runs",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_list_runs_returns_tenant_runs(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    await _create_run(db_session, tenant.id)

    resp = await client.get(
        "/api/v1/reconciliation/runs",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["status"] == "complete"


@pytest.mark.asyncio
async def test_list_runs_viewer_allowed(client: AsyncClient, viewer_token: str):
    resp = await client.get(
        "/api/v1/reconciliation/runs",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_runs_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/reconciliation/runs")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /reconciliation/runs/{run_id}  — single run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_by_id(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    run = await _create_run(db_session, tenant.id)

    resp = await client.get(
        f"/api/v1/reconciliation/runs/{run.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == str(run.id)
    assert resp.json()["data"]["flags_raised"] == 2


@pytest.mark.asyncio
async def test_get_run_not_found(client: AsyncClient, owner_token: str):
    resp = await client.get(
        f"/api/v1/reconciliation/runs/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation — runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_isolation_runs(
    client: AsyncClient,
    db_session,
    tenant: Tenant,
    owner_token: str,
    other_tenant_owner_token: str,
):
    run = await _create_run(db_session, tenant.id)

    # Other tenant cannot see this run via list
    resp = await client.get(
        "/api/v1/reconciliation/runs",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp.status_code == 200
    run_ids = [r["id"] for r in resp.json()["data"]]
    assert str(run.id) not in run_ids

    # Other tenant cannot fetch run by id
    resp2 = await client.get(
        f"/api/v1/reconciliation/runs/{run.id}",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# GET /reconciliation/flags  — list flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_flags_empty(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/reconciliation/flags",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_list_flags_returns_data(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    run = await _create_run(db_session, tenant.id)
    await _create_flag(db_session, tenant.id, run.id)

    resp = await client.get(
        "/api/v1/reconciliation/flags",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["flag_type"] == "uncategorized_expense"


@pytest.mark.asyncio
async def test_list_flags_filter_by_run_id(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    run_a = await _create_run(db_session, tenant.id)
    run_b = await _create_run(db_session, tenant.id)
    await _create_flag(db_session, tenant.id, run_a.id)
    await _create_flag(db_session, tenant.id, run_b.id, flag_type="duplicate_invoice", severity="high")

    resp = await client.get(
        f"/api/v1/reconciliation/flags?run_id={run_a.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["data"][0]["flag_type"] == "uncategorized_expense"


@pytest.mark.asyncio
async def test_list_flags_unresolved_only_filter(
    client: AsyncClient, owner_token: str, db_session, tenant: Tenant
):
    run = await _create_run(db_session, tenant.id)
    await _create_flag(db_session, tenant.id, run.id, is_resolved=False)
    await _create_flag(db_session, tenant.id, run.id, flag_type="duplicate_invoice", severity="high", is_resolved=True)

    resp = await client.get(
        "/api/v1/reconciliation/flags?unresolved_only=true",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert all(not f["is_resolved"] for f in resp.json()["data"])


@pytest.mark.asyncio
async def test_list_flags_viewer_allowed(client: AsyncClient, viewer_token: str):
    resp = await client.get(
        "/api/v1/reconciliation/flags",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_flags_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/reconciliation/flags")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /reconciliation/flags/{id}/resolve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_flag_as_manager(
    client: AsyncClient, manager_token: str, db_session, tenant: Tenant
):
    run = await _create_run(db_session, tenant.id)
    flag = await _create_flag(db_session, tenant.id, run.id)

    resp = await client.post(
        f"/api/v1/reconciliation/flags/{flag.id}/resolve",
        json={"resolution_note": "Verified manually — correct amount."},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_resolved"] is True
    assert data["resolution_note"] == "Verified manually — correct amount."
    assert data["resolved_at"] is not None


@pytest.mark.asyncio
async def test_resolve_flag_viewer_forbidden(
    client: AsyncClient, viewer_token: str, db_session, tenant: Tenant
):
    run = await _create_run(db_session, tenant.id)
    flag = await _create_flag(db_session, tenant.id, run.id)

    resp = await client.post(
        f"/api/v1/reconciliation/flags/{flag.id}/resolve",
        json={"resolution_note": "Should not work."},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resolve_flag_not_found(client: AsyncClient, manager_token: str):
    resp = await client.post(
        f"/api/v1/reconciliation/flags/{uuid.uuid4()}/resolve",
        json={"resolution_note": "Doesn't exist."},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_flag_missing_note_rejected(
    client: AsyncClient, manager_token: str, db_session, tenant: Tenant
):
    run = await _create_run(db_session, tenant.id)
    flag = await _create_flag(db_session, tenant.id, run.id)

    resp = await client.post(
        f"/api/v1/reconciliation/flags/{flag.id}/resolve",
        json={},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_resolve_flag_unauthenticated(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/reconciliation/flags/{uuid.uuid4()}/resolve",
        json={"resolution_note": "Note"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tenant isolation — flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_isolation_flags(
    client: AsyncClient,
    db_session,
    tenant: Tenant,
    owner_token: str,
    other_tenant_owner_token: str,
):
    run = await _create_run(db_session, tenant.id)
    flag = await _create_flag(db_session, tenant.id, run.id)

    # Other tenant's list should not include this flag
    resp = await client.get(
        "/api/v1/reconciliation/flags",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp.status_code == 200
    flag_ids = [f["id"] for f in resp.json()["data"]]
    assert str(flag.id) not in flag_ids

    # Other tenant cannot resolve this flag
    resp2 = await client.post(
        f"/api/v1/reconciliation/flags/{flag.id}/resolve",
        json={"resolution_note": "Cross-tenant resolve attempt."},
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp2.status_code == 404
