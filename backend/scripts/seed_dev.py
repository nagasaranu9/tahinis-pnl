"""
Dev seed: creates one tenant + owner/manager/viewer users.
Run: cd backend && python ../scripts/seed_dev.py
"""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models.location import Location
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.session import AsyncSessionLocal


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        tenant_id = uuid.uuid4()
        tenant = Tenant(
            id=tenant_id,
            slug="tahinis-dev",
            name="Tahinis Restaurant (Dev)",
            timezone="America/Toronto",
            currency_code="CAD",
            plan="starter",
        )
        db.add(tenant)

        location = Location(
            tenant_id=tenant_id,
            name="Main Location",
            address="123 King St W, Toronto, ON",
            timezone="America/Toronto",
            store_id="10001",
        )
        db.add(location)

        users = [
            User(
                tenant_id=tenant_id,
                email="owner@tahinis.dev",
                hashed_password=hash_password("devpassword123"),
                role="owner",
            ),
            User(
                tenant_id=tenant_id,
                email="manager@tahinis.dev",
                hashed_password=hash_password("devpassword123"),
                role="manager",
            ),
            User(
                tenant_id=tenant_id,
                email="viewer@tahinis.dev",
                hashed_password=hash_password("devpassword123"),
                role="viewer",
            ),
        ]
        for u in users:
            db.add(u)

        await db.commit()

        print(f"Tenant ID: {tenant_id}")
        print("Users seeded:")
        print("  owner@tahinis.dev   / devpassword123 / role=owner")
        print("  manager@tahinis.dev / devpassword123 / role=manager")
        print("  viewer@tahinis.dev  / devpassword123 / role=viewer")
        print(f"\nX-Tenant-ID header for API calls: {tenant_id}")


if __name__ == "__main__":
    asyncio.run(seed())
