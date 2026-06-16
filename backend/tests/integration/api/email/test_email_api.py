"""Integration tests for email/drive API endpoints."""
import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_gmail_auth_url_requires_owner(client: AsyncClient, manager_token: str):
    resp = await client.get(
        "/api/v1/integrations/gmail/auth-url",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_gmail_auth_url_returns_google_url(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/integrations/gmail/auth-url",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    url = resp.json()["data"]["url"]
    assert "accounts.google.com" in url
    assert "gmail.readonly" in url


@pytest.mark.asyncio
async def test_outlook_auth_url_requires_owner(client: AsyncClient, manager_token: str):
    resp = await client.get(
        "/api/v1/integrations/outlook/auth-url",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_outlook_auth_url_returns_microsoft_url(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/integrations/outlook/auth-url",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    url = resp.json()["data"]["url"]
    assert "login.microsoftonline.com" in url


@pytest.mark.asyncio
async def test_gdrive_auth_url_requires_owner(client: AsyncClient, manager_token: str):
    resp = await client.get(
        "/api/v1/integrations/gdrive/auth-url",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_gdrive_auth_url_returns_google_url(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/integrations/gdrive/auth-url",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    url = resp.json()["data"]["url"]
    assert "accounts.google.com" in url
    assert "drive.readonly" in url


@pytest.mark.asyncio
async def test_gmail_status_empty_before_connect(client: AsyncClient, owner_token: str):
    resp = await client.get(
        "/api/v1/integrations/gmail/status",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_viewer_cannot_trigger_gmail_sync(client: AsyncClient, viewer_token: str):
    resp = await client.post(
        f"/api/v1/integrations/gmail/sync?config_id={uuid.uuid4()}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client: AsyncClient):
    for path in [
        "/api/v1/integrations/gmail/status",
        "/api/v1/integrations/outlook/status",
        "/api/v1/integrations/gdrive/status",
    ]:
        resp = await client.get(path)
        assert resp.status_code == 401, f"Expected 401 for {path}"


@pytest.mark.asyncio
async def test_gmail_status_tenant_isolated(
    client: AsyncClient,
    owner_token: str,
    other_tenant_owner_token: str,
    db_session,
    tenant,
):
    """Gmail configs registered under tenant A must not appear for tenant B."""
    from app.db.models.integration import IntegrationCredential
    from app.db.repositories.email_repo import EmailSyncRepository
    from app.core.security import encrypt_value

    cred = IntegrationCredential(
        tenant_id=tenant.id,
        provider="gmail",
        access_token_encrypted=encrypt_value("tok"),
        refresh_token_encrypted=encrypt_value("ref"),
    )
    db_session.add(cred)
    await db_session.flush()

    repo = EmailSyncRepository(db_session)
    await repo.upsert_config(
        tenant_id=tenant.id,
        provider="gmail",
        email_address="owner@tahinis.com",
        integration_credential_id=cred.id,
    )
    await db_session.commit()

    # Tenant A sees it
    resp_a = await client.get(
        "/api/v1/integrations/gmail/status",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert len(resp_a.json()["data"]) == 1

    # Tenant B sees nothing
    resp_b = await client.get(
        "/api/v1/integrations/gmail/status",
        headers={"Authorization": f"Bearer {other_tenant_owner_token}"},
    )
    assert resp_b.json()["data"] == []
