from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import AsyncSessionDep

logger = structlog.get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(
        self, user_id: UUID, tenant_id: UUID, role: str, location_id: UUID | None = None
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        # NULL = tenant-wide access (admin/HQ). Set = scoped to exactly one location.
        self.location_id = location_id

    def require_role(self, *roles: str) -> None:
        if self.role not in roles:
            raise ForbiddenError(f"Role '{self.role}' not permitted. Required: {roles}")

    def require_location_access(self, location_id: UUID) -> None:
        if self.location_id is not None and self.location_id != location_id:
            raise ForbiddenError("Not permitted to access this location")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    if credentials is None:
        raise UnauthorizedError("No authorization header")

    payload = decode_access_token(credentials.credentials)

    try:
        raw_location_id = payload.get("location_id")
        return CurrentUser(
            user_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            role=payload["role"],
            location_id=UUID(raw_location_id) if raw_location_id else None,
        )
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Malformed token claims") from exc


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_owner(user: CurrentUserDep) -> CurrentUser:
    user.require_role("owner")
    return user


def require_manager_or_above(user: CurrentUserDep) -> CurrentUser:
    user.require_role("owner", "manager")
    return user


OwnerDep = Annotated[CurrentUser, Depends(require_owner)]
ManagerDep = Annotated[CurrentUser, Depends(require_manager_or_above)]
