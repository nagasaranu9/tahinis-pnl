from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import AsyncSessionDep
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
from app.schemas.common import APIResponse
from app.services.auth_service import AuthService

router = APIRouter()
_limiter = Limiter(key_func=get_remote_address)


def _get_service(db: AsyncSessionDep) -> AuthService:
    return AuthService(UserRepository(db), AuditRepository(db))


@router.post("/login", response_model=APIResponse[TokenResponse])
@_limiter.limit("10/minute")
async def login(body: LoginRequest, request: Request, db: AsyncSessionDep) -> dict:
    from uuid import UUID
    from sqlalchemy import select
    from app.core.exceptions import UnauthorizedError
    from app.db.models.tenant import Tenant

    # Resolve tenant: store_id (on location) takes priority over X-Tenant-ID header
    if body.store_id:
        from app.db.models.location import Location
        result = await db.execute(
            select(Location).where(Location.store_id == body.store_id, Location.is_active == True)  # noqa: E712
        )
        location = result.scalar_one_or_none()
        if not location:
            raise UnauthorizedError("Invalid Store ID")
        # Verify tenant is active
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.id == location.tenant_id, Tenant.is_active == True)  # noqa: E712
        )
        if not tenant_result.scalar_one_or_none():
            raise UnauthorizedError("Invalid Store ID")
        tenant_id = location.tenant_id
    else:
        raw_tenant = request.headers.get("X-Tenant-ID", "")
        if not raw_tenant:
            raise UnauthorizedError("Store ID required")
        try:
            tenant_id = UUID(raw_tenant)
        except ValueError:
            raise UnauthorizedError("Invalid tenant identifier")

    svc = _get_service(db)
    tokens = await svc.login(
        tenant_id=tenant_id,
        email=body.email,
        password=body.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    return {"data": tokens, "errors": None}


@router.post("/refresh", response_model=APIResponse[TokenResponse])
@_limiter.limit("20/minute")
async def refresh(body: RefreshRequest, request: Request, db: AsyncSessionDep) -> dict:
    svc = _get_service(db)
    tokens = await svc.refresh(body.refresh_token)
    return {"data": tokens, "errors": None}


@router.post("/logout", response_model=APIResponse[None])
async def logout(body: LogoutRequest, db: AsyncSessionDep) -> dict:
    svc = _get_service(db)
    await svc.logout(body.refresh_token)
    return {"data": None, "errors": None}


@router.post("/reset-password", response_model=APIResponse[None])
async def reset_password(body: object) -> dict:
    # Phase 2 implementation: email-based reset flow
    return {"data": None, "errors": None}
