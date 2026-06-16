import pytest
from httpx import AsyncClient

from app.db.models.tenant import Tenant
from app.db.models.user import User


@pytest.mark.asyncio
class TestLogin:
    async def test_login_success(self, client: AsyncClient, tenant: Tenant, owner_user: User) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "testpass123"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, tenant: Tenant, owner_user: User) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "wrongpassword"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
        assert resp.status_code == 401

    async def test_login_unknown_user(self, client: AsyncClient, tenant: Tenant) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@test.com", "password": "testpass123"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
        assert resp.status_code == 401

    async def test_login_missing_tenant_header(self, client: AsyncClient, owner_user: User) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "testpass123"},
        )
        assert resp.status_code == 401

    async def test_login_cross_tenant_blocked(
        self, client: AsyncClient, tenant: Tenant, owner_user: User, db: object
    ) -> None:
        """User from Tenant A cannot login under Tenant B header."""
        import uuid
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.db.models.tenant import Tenant as T

        other_tenant = T(slug=f"other-{uuid.uuid4().hex[:6]}", name="Other", timezone="UTC", currency_code="CAD")
        assert isinstance(db, AsyncSession)
        db.add(other_tenant)
        await db.flush()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "testpass123"},
            headers={"X-Tenant-ID": str(other_tenant.id)},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestRefreshAndLogout:
    async def test_refresh_issues_new_tokens(self, client: AsyncClient, tenant: Tenant, owner_user: User) -> None:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "testpass123"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
        refresh_token = login.json()["data"]["refresh_token"]

        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"]

    async def test_refresh_token_rotation_old_rejected(
        self, client: AsyncClient, tenant: Tenant, owner_user: User
    ) -> None:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "testpass123"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
        refresh_token = login.json()["data"]["refresh_token"]

        # Use once
        await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        # Reuse old → rejected
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401

    async def test_logout_revokes_token(self, client: AsyncClient, tenant: Tenant, owner_user: User) -> None:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "testpass123"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
        refresh_token = login.json()["data"]["refresh_token"]

        await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestProtectedEndpoints:
    async def test_no_token_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/tenants/me")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/tenants/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401

    async def test_viewer_cannot_delete_location(
        self, client: AsyncClient, viewer_token: str
    ) -> None:
        import uuid
        resp = await client.delete(
            f"/api/v1/locations/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_owner_can_read_tenant(
        self, client: AsyncClient, owner_token: str, tenant: Tenant
    ) -> None:
        resp = await client.get(
            "/api/v1/tenants/me",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == str(tenant.id)
