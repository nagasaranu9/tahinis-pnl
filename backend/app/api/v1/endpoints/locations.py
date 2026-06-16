import hashlib
import secrets
import uuid

from fastapi import APIRouter
from sqlalchemy import select, update

from app.core.config import settings
from app.core.deps import CurrentUserDep, ManagerDep, OwnerDep
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import hash_password
from app.db.models.location import Location
from app.db.models.user import User
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse
from app.schemas.location import (
    AcceptInviteRequest,
    CreateLocationRequest,
    InviteLocationOwnerRequest,
    InviteLocationOwnerResponse,
    LocationResponse,
    UpdateLocationRequest,
)
from app.services.email_service import send_email

router = APIRouter()


def _assert_tenant(location: Location | None, tenant_id: uuid.UUID) -> Location:
    if location is None or location.tenant_id != tenant_id:
        raise NotFoundError("Location not found")
    return location


@router.get("", response_model=APIResponse[list[LocationResponse]])
async def list_locations(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    conditions = [Location.tenant_id == user.tenant_id, Location.is_active == True]  # noqa: E712
    # Scoped (invited) owners only ever see their own location; tenant-wide users see all.
    if user.location_id is not None:
        conditions.append(Location.id == user.location_id)
    result = await db.execute(select(Location).where(*conditions))
    locations = result.scalars().all()
    return {"data": [LocationResponse.model_validate(l) for l in locations], "errors": None}


@router.post("/invite", response_model=APIResponse[InviteLocationOwnerResponse], status_code=201)
async def invite_location_owner(
    body: InviteLocationOwnerRequest, user: OwnerDep, db: AsyncSessionDep
) -> dict:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    location = Location(
        tenant_id=user.tenant_id,
        name=body.name,
        store_id=body.store_id,
        invite_email=body.invite_email,
        invite_token_hash=token_hash,
        invite_status="pending",
    )
    db.add(location)
    await db.flush()

    invite_url = f"{settings.FRONTEND_URL}/invite/{location.id}?token={raw_token}"
    send_email(
        body.invite_email,
        "You're invited to set up your Tahini's location",
        f"You've been invited to onboard store #{body.store_id} ({body.name}).\n\n"
        f"Set your password here: {invite_url}\n\nThis link is single-use.",
    )

    return {
        "data": InviteLocationOwnerResponse(
            location=LocationResponse.model_validate(location), invite_url=invite_url
        ),
        "errors": None,
    }


@router.get("/invite/{location_id}", response_model=APIResponse[LocationResponse])
async def get_invite(location_id: uuid.UUID, token: str, db: AsyncSessionDep) -> dict:
    location = await db.get(Location, location_id)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if (
        location is None
        or location.invite_status != "pending"
        or location.invite_token_hash != token_hash
    ):
        raise UnauthorizedError("Invalid or expired invite link")
    return {"data": LocationResponse.model_validate(location), "errors": None}


@router.post("/invite/{location_id}/accept", response_model=APIResponse[None])
async def accept_invite(
    location_id: uuid.UUID, body: AcceptInviteRequest, db: AsyncSessionDep
) -> dict:
    location = await db.get(Location, location_id)
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    if (
        location is None
        or location.invite_status != "pending"
        or location.invite_token_hash != token_hash
    ):
        raise UnauthorizedError("Invalid or expired invite link")

    owner = User(
        tenant_id=location.tenant_id,
        email=location.invite_email.lower(),
        hashed_password=hash_password(body.password),
        role="owner",
        location_id=location.id,
    )
    db.add(owner)
    await db.execute(
        update(Location)
        .where(Location.id == location.id)
        .values(invite_status="accepted", invite_token_hash=None)
    )
    return {"data": None, "errors": None}


@router.post("", response_model=APIResponse[LocationResponse], status_code=201)
async def create_location(body: CreateLocationRequest, user: ManagerDep, db: AsyncSessionDep) -> dict:
    location = Location(tenant_id=user.tenant_id, **body.model_dump())
    db.add(location)
    await db.flush()
    return {"data": LocationResponse.model_validate(location), "errors": None}


@router.get("/{location_id}", response_model=APIResponse[LocationResponse])
async def get_location(location_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    location = _assert_tenant(await db.get(Location, location_id), user.tenant_id)
    user.require_location_access(location.id)
    return {"data": LocationResponse.model_validate(location), "errors": None}


@router.patch("/{location_id}", response_model=APIResponse[LocationResponse])
async def update_location(
    location_id: uuid.UUID, body: UpdateLocationRequest, user: ManagerDep, db: AsyncSessionDep
) -> dict:
    location = _assert_tenant(await db.get(Location, location_id), user.tenant_id)
    updates = body.model_dump(exclude_none=True)
    if updates:
        await db.execute(update(Location).where(Location.id == location_id).values(**updates))
        await db.refresh(location)
    return {"data": LocationResponse.model_validate(location), "errors": None}


@router.delete("/{location_id}", response_model=APIResponse[None])
async def delete_location(location_id: uuid.UUID, user: OwnerDep, db: AsyncSessionDep) -> dict:
    location = _assert_tenant(await db.get(Location, location_id), user.tenant_id)
    await db.execute(update(Location).where(Location.id == location_id).values(is_active=False))
    return {"data": None, "errors": None}
