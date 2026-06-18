import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.deps import CurrentUserDep, ManagerDep, OwnerDep
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import hash_password
from app.db.models.email_sync import EmailSyncConfig
from app.db.models.location import Location
from app.db.models.toast import ToastSyncConfig
from app.db.models.user import User
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse
from app.schemas.location import (
    AcceptInviteRequest,
    CreateLocationRequest,
    InviteLocationOwnerRequest,
    InviteLocationOwnerResponse,
    LocationResponse,
    OnboardingStatusResponse,
    OnboardingStepStatus,
    UpdateLocationRequest,
)
from app.services.email_service import send_email

router = APIRouter()
logger = structlog.get_logger(__name__)


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
    invite_email = body.invite_email.lower()

    # Email guard — block only live (non-deleted) pending/accepted invites.
    existing_email = await db.scalar(
        select(Location.id).where(
            Location.tenant_id == user.tenant_id,
            Location.invite_email == invite_email,
            Location.invite_status.in_(["pending", "accepted"]),
            Location.is_active == True,  # noqa: E712 — soft-deleted invites must not block re-invite
        )
    )
    if existing_email:
        raise ConflictError(f"An invite for {body.invite_email} already exists.")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    # store_id has a GLOBAL unique index (ignores is_active), so a soft-deleted
    # row with this store_id would crash an INSERT. Fetch the full row regardless
    # of is_active and reuse it: live row -> conflict, deleted row -> revive.
    existing = await db.scalar(
        select(Location).where(
            Location.tenant_id == user.tenant_id,
            Location.store_id == body.store_id,
        )
    )
    if existing is not None and existing.is_active:
        raise ConflictError(f"Store #{body.store_id} already exists.")

    if existing is not None:
        # Revive the soft-deleted row as a fresh pending invite.
        existing.is_active = True
        existing.name = body.name
        existing.invite_email = invite_email
        existing.invite_token_hash = token_hash
        existing.invite_status = "pending"
        existing.onboarding_completed_at = None
        location = existing
    else:
        location = Location(
            tenant_id=user.tenant_id,
            name=body.name,
            store_id=body.store_id,
            invite_email=invite_email,
            invite_token_hash=token_hash,
            invite_status="pending",
        )
        db.add(location)
    await db.flush()

    invite_url = f"{settings.FRONTEND_URL}/invite/{location.id}?token={raw_token}"
    email_sent = send_email(
        body.invite_email,
        "You're invited to set up your Tahini's location",
        f"You've been invited to onboard store #{body.store_id} ({body.name}).\n\n"
        f"Set your password here: {invite_url}\n\nThis link is single-use.",
    )
    logger.info(
        "location_invite_created",
        location_id=str(location.id),
        store_id=body.store_id,
        invite_email=body.invite_email.lower(),
        email_sent=email_sent,
    )

    return {
        "data": InviteLocationOwnerResponse(
            location=LocationResponse.model_validate(location),
            invite_url=invite_url,
            email_sent=email_sent,
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


async def _build_onboarding_status(
    location: Location, db: AsyncSessionDep
) -> OnboardingStatusResponse:
    """Derive wizard step completion from the same fields the integration UIs write."""
    gmail_count = await db.scalar(
        select(func.count())
        .select_from(EmailSyncConfig)
        .where(
            EmailSyncConfig.tenant_id == location.tenant_id,
            EmailSyncConfig.provider == "gmail",
        )
    )
    # Toast connect writes a ToastSyncConfig row (not location.toast_location_id),
    # so derive the step from that.
    toast_count = await db.scalar(
        select(func.count())
        .select_from(ToastSyncConfig)
        .where(ToastSyncConfig.location_id == location.id)
    )
    steps = OnboardingStepStatus(
        profile=bool(location.address),
        toast=bool(toast_count),
        gmail=bool(gmail_count),
        google=bool(location.google_place_id),
    )
    return OnboardingStatusResponse(
        location_id=location.id,
        steps=steps,
        completed=location.onboarding_completed_at is not None,
        completed_at=location.onboarding_completed_at,
    )


@router.get("/{location_id}/onboarding", response_model=APIResponse[OnboardingStatusResponse])
async def get_onboarding_status(
    location_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep
) -> dict:
    location = _assert_tenant(await db.get(Location, location_id), user.tenant_id)
    user.require_location_access(location.id)
    status = await _build_onboarding_status(location, db)
    return {"data": status, "errors": None}


@router.post("/{location_id}/onboarding/complete", response_model=APIResponse[OnboardingStatusResponse])
async def complete_onboarding(
    location_id: uuid.UUID, user: OwnerDep, db: AsyncSessionDep
) -> dict:
    location = _assert_tenant(await db.get(Location, location_id), user.tenant_id)
    user.require_location_access(location.id)
    await db.execute(
        update(Location)
        .where(Location.id == location.id)
        .values(onboarding_completed_at=datetime.now(timezone.utc))
    )
    await db.refresh(location)
    status = await _build_onboarding_status(location, db)
    return {"data": status, "errors": None}


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
