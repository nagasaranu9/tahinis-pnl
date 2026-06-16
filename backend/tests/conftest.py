import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models.location import Location
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.session import get_db
from app.main import app

# Use test DB (set via env in CI or Docker)
TEST_DATABASE_URL = str(settings.DATABASE_URL)

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine_test, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables() -> AsyncGenerator[None, None]:
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> Tenant:
    t = Tenant(
        slug=f"test-tenant-{uuid.uuid4().hex[:8]}",
        name="Test Tenant",
        timezone="UTC",
        currency_code="CAD",
    )
    db.add(t)
    await db.flush()
    return t


@pytest_asyncio.fixture
async def owner_user(db: AsyncSession, tenant: Tenant) -> User:
    u = User(
        tenant_id=tenant.id,
        email="owner@test.com",
        hashed_password=hash_password("testpass123"),
        role="owner",
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def manager_user(db: AsyncSession, tenant: Tenant) -> User:
    u = User(
        tenant_id=tenant.id,
        email="manager@test.com",
        hashed_password=hash_password("testpass123"),
        role="manager",
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def viewer_user(db: AsyncSession, tenant: Tenant) -> User:
    u = User(
        tenant_id=tenant.id,
        email="viewer@test.com",
        hashed_password=hash_password("testpass123"),
        role="viewer",
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def owner_token(client: AsyncClient, tenant: Tenant, owner_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@test.com", "password": "testpass123"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    return resp.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def manager_token(client: AsyncClient, tenant: Tenant, manager_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.com", "password": "testpass123"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    return resp.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def viewer_token(client: AsyncClient, tenant: Tenant, viewer_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@test.com", "password": "testpass123"},
        headers={"X-Tenant-ID": str(tenant.id)},
    )
    return resp.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def location_id(db: AsyncSession, tenant: Tenant) -> uuid.UUID:
    loc = Location(
        tenant_id=tenant.id,
        name="Test Location",
        timezone="America/Toronto",
    )
    db.add(loc)
    await db.flush()
    return loc.id


@pytest_asyncio.fixture
async def db_session(db: AsyncSession) -> AsyncSession:
    """Alias for db — used in repository tests."""
    return db


@pytest_asyncio.fixture
async def other_tenant_owner_token(client: AsyncClient, db: AsyncSession) -> str:
    other_tenant = Tenant(
        slug=f"other-tenant-{uuid.uuid4().hex[:8]}",
        name="Other Tenant",
        timezone="UTC",
        currency_code="CAD",
    )
    db.add(other_tenant)
    await db.flush()

    other_owner = User(
        tenant_id=other_tenant.id,
        email=f"other-owner-{uuid.uuid4().hex[:6]}@test.com",
        hashed_password=hash_password("testpass123"),
        role="owner",
    )
    db.add(other_owner)
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": other_owner.email, "password": "testpass123"},
        headers={"X-Tenant-ID": str(other_tenant.id)},
    )
    return resp.json()["data"]["access_token"]
