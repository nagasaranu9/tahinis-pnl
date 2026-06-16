from sqlalchemy import select, update

from app.core.deps import CurrentUserDep, OwnerDep
from app.core.exceptions import NotFoundError
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse
from app.schemas.tenant import TenantResponse, UpdateTenantRequest
from fastapi import APIRouter

router = APIRouter()


@router.get("/me", response_model=APIResponse[TenantResponse])
async def get_tenant(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    tenant = await db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    return {"data": TenantResponse.model_validate(tenant), "errors": None}


@router.patch("/me", response_model=APIResponse[TenantResponse])
async def update_tenant(body: UpdateTenantRequest, user: OwnerDep, db: AsyncSessionDep) -> dict:
    tenant = await db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        await db.execute(
            update(Tenant).where(Tenant.id == user.tenant_id).values(**updates)
        )
        await db.refresh(tenant)

    return {"data": TenantResponse.model_validate(tenant), "errors": None}
