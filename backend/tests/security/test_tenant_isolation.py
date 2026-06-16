"""
Critical: cross-tenant data isolation tests.
Every test here is a security test — failures are critical defects.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models.location import Location
from app.db.models.tenant import Tenant
from app.db.models.user import User


@pytest.mark.asyncio
class TestCrossTenantIsolation:
    async def _create_tenant_with_owner(self, db: AsyncSession, slug_suffix: str) -> tuple[Tenant, User, str]:
        tenant = Tenant(
            slug=f"tenant-{slug_suffix}",
            name=f"Tenant {slug_suffix}",
            timezone="UTC",
            currency_code="CAD",
        )
        db.add(tenant)
        await db.flush()

        user = User(
            tenant_id=tenant.id,
            email=f"owner-{slug_suffix}@test.com",
            hashed_password=hash_password("testpass123"),
            role="owner",
        )
        db.add(user)
        await db.flush()
        return tenant, user, f"owner-{slug_suffix}@test.com"

    async def _get_token(self, client: AsyncClient, tenant: Tenant, email: str) -> str:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "testpass123"},
            headers={"X-Tenant-ID": str(tenant.id)},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        return resp.json()["data"]["access_token"]

    async def test_cannot_read_other_tenant(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Tenant A token cannot read Tenant B data."""
        suffix_a = uuid.uuid4().hex[:6]
        suffix_b = uuid.uuid4().hex[:6]
        tenant_a, _, email_a = await self._create_tenant_with_owner(db, suffix_a)
        tenant_b, _, _ = await self._create_tenant_with_owner(db, suffix_b)
        await db.commit()

        token_a = await self._get_token(client, tenant_a, email_a)

        # Tenant A token hits /tenants/me — must return Tenant A, not B
        resp = await client.get(
            "/api/v1/tenants/me",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == str(tenant_a.id)
        assert resp.json()["data"]["id"] != str(tenant_b.id)

    async def test_cannot_read_other_tenant_locations(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Tenant A token cannot see Tenant B locations."""
        suffix_a = uuid.uuid4().hex[:6]
        suffix_b = uuid.uuid4().hex[:6]
        tenant_a, _, email_a = await self._create_tenant_with_owner(db, suffix_a)
        tenant_b, _, _ = await self._create_tenant_with_owner(db, suffix_b)

        loc_b = Location(tenant_id=tenant_b.id, name="B Location", timezone="UTC")
        db.add(loc_b)
        await db.commit()

        token_a = await self._get_token(client, tenant_a, email_a)

        # List locations — must not include Tenant B's location
        resp = await client.get(
            "/api/v1/locations",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200
        ids = [l["id"] for l in resp.json()["data"]]
        assert str(loc_b.id) not in ids

    async def test_cannot_fetch_other_tenant_location_by_id(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """GET /locations/{id} with Tenant B's ID under Tenant A token returns 404."""
        suffix_a = uuid.uuid4().hex[:6]
        suffix_b = uuid.uuid4().hex[:6]
        tenant_a, _, email_a = await self._create_tenant_with_owner(db, suffix_a)
        tenant_b, _, _ = await self._create_tenant_with_owner(db, suffix_b)

        loc_b = Location(tenant_id=tenant_b.id, name="B Only Location", timezone="UTC")
        db.add(loc_b)
        await db.commit()

        token_a = await self._get_token(client, tenant_a, email_a)

        resp = await client.get(
            f"/api/v1/locations/{loc_b.id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404
