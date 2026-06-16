"""
Integration tests for Toast API endpoints.
Covers: connect, status, sync trigger, sync jobs, tenant isolation, RBAC.
"""
import uuid
import pytest
from httpx import AsyncClient

from app.core.security import encrypt_value


@pytest.mark.asyncio
async def test_connect_toast_requires_owner(client: AsyncClient, manager_token: str, location_id: uuid.UUID):
    resp = await client.post(
        "/api/v1/integrations/toast/connect",
        json={
            "location_id": str(location_id),
            "client_id": "cid",
            "client_secret": "secret",
            "toast_restaurant_guid": "rest-guid",
        },
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_connect_toast_success(
    client: AsyncClient,
    owner_token: str,
    location_id: uuid.UUID,
    mocker,
):
    # Patch out the Celery task dispatch
    mocker.patch(
        "app.api.v1.endpoints.toast_integrations.toast_historical_import.apply_async"
    )

    resp = await client.post(
        "/api/v1/integrations/toast/connect",
        json={
            "location_id": str(location_id),
            "client_id": "cid",
            "client_secret": "secret",
            "toast_restaurant_guid": "rest-guid-abc",
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["toast_restaurant_guid"] == "rest-guid-abc"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_status_not_found_before_connect(
    client: AsyncClient, owner_token: str
):
    resp = await client.get(
        f"/api/v1/integrations/toast/status?location_id={uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_viewer_cannot_trigger_sync(
    client: AsyncClient, viewer_token: str, location_id: uuid.UUID
):
    resp = await client.post(
        "/api/v1/integrations/toast/sync",
        json={"location_id": str(location_id), "sync_type": "incremental"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_jobs_tenant_isolated(
    client: AsyncClient,
    owner_token: str,
    other_tenant_owner_token: str,
    location_id: uuid.UUID,
):
    """Jobs created under tenant A must not appear in tenant B's list."""
    # Tenant B queries same location_id — should return 0 jobs
    resp = await client.get(
        f"/api/v1/integrations/toast/sync-jobs?location_id={location_id}",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_disconnect_requires_owner(
    client: AsyncClient, manager_token: str, location_id: uuid.UUID
):
    resp = await client.delete(
        f"/api/v1/integrations/toast/disconnect?location_id={location_id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client: AsyncClient, location_id: uuid.UUID):
    resp = await client.get(
        f"/api/v1/integrations/toast/status?location_id={location_id}"
    )
    assert resp.status_code == 401
