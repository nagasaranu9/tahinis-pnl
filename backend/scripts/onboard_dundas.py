"""
Hardcoded onboarding for Tahinis Dundas (1955).
Run: cd backend && python -m scripts.onboard_dundas
"""
import asyncio
import os
import sys
import uuid

# Fix Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.security import create_access_token, hash_password
from app.db.models.location import Location
from app.db.models.tenant import Tenant
from app.db.models.user import User


async def onboard():
    # Hardcoded values
    tenant_uuid = uuid.UUID("00000000-0000-0000-0000-000007a70000")
    store_name = "Tahinis Dundas"
    email = "tahinisdundas@gmail.com"
    password = "Bhanu1955$"
    role = "owner"
    address = "#6, 690 Dundas St E, Toronto"
    timezone = "America/Toronto"
    store_id = "1955"

    # DB connection from environment
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://tahinis:tahinis@localhost:5432/tahinis_dev")
    engine = create_async_engine(db_url)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        # Phase 1: Tenant
        tenant = Tenant(
            id=tenant_uuid,
            slug="tahinis-dundas",
            name=store_name,
            timezone=timezone,
            currency_code="CAD",
            plan="starter",
            is_active=True,
        )
        db.add(tenant)
        print(f"✓ Tenant: {store_name}")

        # Phase 2: Location
        location = Location(
            id=uuid.uuid4(),
            tenant_id=tenant_uuid,
            name=store_name,
            address=address,
            timezone=timezone,
            store_id=store_id,
            is_active=True,
        )
        db.add(location)
        print(f"✓ Location: {store_name} (store_id={store_id})")

        # Phase 1: User
        hashed_pwd = hash_password(password)
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_uuid,
            email=email.lower(),
            hashed_password=hashed_pwd,
            role=role,
            is_active=True,
        )
        db.add(user)
        print(f"✓ User: {email} (role={role})")

        await db.commit()

        # JWT
        access_token = create_access_token(str(user.id), str(tenant_uuid), role, None)

        # Output
        print("\n" + "=" * 80)
        print("PHASE 1 & 2 COMPLETE")
        print("=" * 80)
        print(f"\nStore: {store_name} (id={store_id})")
        print(f"Tenant UUID: {tenant_uuid}")
        print(f"Email: {email}")
        print(f"Role: {role}")
        print(f"\nAccess Token:\n{access_token}")
        print(f"\nAPI Headers:\n  Authorization: Bearer {access_token}\n  X-Tenant-ID: {tenant_uuid}")
        print("\n⚠️  Password: ONE-WAY HASHED (bcrypt). Send securely to user.")
        print("✓ Ready for Phase 3: Toast, Gmail, Reconciliation sync")
        print("=" * 80)

        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(onboard())
