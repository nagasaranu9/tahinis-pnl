"""
Onboard new store (Phase 1 & 2): Create tenant, location, user.
Run: cd backend && python ../scripts/onboard_store.py

Usage example:
  python onboard_store.py \
    --tenant-id 1955 \
    --store-name "Tahinis Dundas" \
    --email "tahinisdundas@gmail.com" \
    --password "Bhanu1955$" \
    --role owner \
    --address "#6, 690 Dundas St E, Toronto" \
    --timezone "America/Toronto"
"""
import argparse
import asyncio
import uuid
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.db.models.location import Location
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.session import AsyncSessionLocal


async def onboard_store(
    tenant_id_numeric: int,
    store_name: str,
    email: str,
    password: str,
    role: str,
    address: str,
    timezone: str = "America/Toronto",
) -> None:
    """Create tenant, location, user. Output secure credentials."""
    async with AsyncSessionLocal() as db:
        # Generate UUID from numeric tenant_id (deterministic for reproducibility)
        tenant_uuid = uuid.UUID(f"00000000-0000-0000-0000-{tenant_id_numeric:012d}")

        # Phase 1: Create Tenant
        tenant_slug = store_name.lower().replace(" ", "-")
        tenant = Tenant(
            id=tenant_uuid,
            slug=tenant_slug,
            name=store_name,
            timezone=timezone,
            currency_code="CAD",
            plan="starter",
            is_active=True,
        )
        db.add(tenant)
        print(f"✓ Tenant created: {store_name} (id={tenant_uuid})")

        # Phase 2: Create Location
        location = Location(
            id=uuid.uuid4(),
            tenant_id=tenant_uuid,
            name=store_name,
            address=address,
            timezone=timezone,
            store_id=str(tenant_id_numeric),
            is_active=True,
        )
        db.add(location)
        print(f"✓ Location created: {store_name} (store_id={tenant_id_numeric})")

        # Phase 1: Create User
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
        print(f"✓ User created: {email} (role={role})")

        await db.commit()

        # Generate JWT token
        access_token = create_access_token(
            user_id=str(user.id),
            tenant_id=str(tenant_uuid),
            role=role,
            location_id=None,
        )

        # Output credentials (do NOT log plaintext password)
        print("\n" + "=" * 80)
        print("ONBOARDING COMPLETE — PHASE 1 & 2")
        print("=" * 80)
        print(f"\nStore Information:")
        print(f"  Store Name:      {store_name}")
        print(f"  Store ID:        {tenant_id_numeric}")
        print(f"  Tenant UUID:     {tenant_uuid}")
        print(f"  Address:         {address}")
        print(f"  Timezone:        {timezone}")

        print(f"\nUser Account:")
        print(f"  Email:           {email}")
        print(f"  Role:            {role}")
        print(f"  ⚠️  Password:     [HASHED — never log plaintext]")

        print(f"\nAccess Token (valid for API calls):")
        print(f"  {access_token}")

        print(f"\nAPI Headers Required:")
        print(f"  Authorization: Bearer {access_token}")
        print(f"  X-Tenant-ID: {tenant_uuid}")

        print(f"\n⚠️  SECURITY NOTES:")
        print(f"  1. Password is ONE-WAY HASHED with bcrypt (cannot be recovered)")
        print(f"  2. Send credentials securely to user (NOT via email/Slack)")
        print(f"  3. User should change password on first login")
        print(f"  4. Access token expires in 15 minutes")
        print(f"  5. Refresh token needed for long-lived sessions")
        print(f"\n✓ Ready for Phase 3: Initial Data Sync (Toast, Gmail, etc)")
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Onboard new store")
    parser.add_argument("--tenant-id", type=int, required=True, help="Numeric tenant ID (e.g., 1955)")
    parser.add_argument("--store-name", type=str, required=True, help="Store name (e.g., 'Tahinis Dundas')")
    parser.add_argument("--email", type=str, required=True, help="Owner email")
    parser.add_argument("--password", type=str, required=True, help="Owner password (will be hashed)")
    parser.add_argument("--role", type=str, default="owner", choices=["owner", "manager", "viewer"])
    parser.add_argument("--address", type=str, required=True, help="Store address")
    parser.add_argument("--timezone", type=str, default="America/Toronto", help="Timezone (default: America/Toronto)")

    args = parser.parse_args()

    asyncio.run(
        onboard_store(
            tenant_id_numeric=args.tenant_id,
            store_name=args.store_name,
            email=args.email,
            password=args.password,
            role=args.role,
            address=args.address,
            timezone=args.timezone,
        )
    )


if __name__ == "__main__":
    main()
