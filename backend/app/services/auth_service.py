import uuid
from uuid import UUID

import structlog

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    verify_password,
)
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import AsyncSessionLocal
from app.schemas.auth import TokenResponse

logger = structlog.get_logger(__name__)


class AuthService:
    def __init__(self, user_repo: UserRepository, audit_repo: AuditRepository) -> None:
        self._users = user_repo
        self._audit = audit_repo

    async def login(
        self,
        tenant_id: UUID,
        email: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenResponse:
        user = await self._users.get_by_email(tenant_id, email.lower())
        if user is None or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid credentials")

        access_token = create_access_token(
            str(user.id),
            str(user.tenant_id),
            user.role,
            str(user.location_id) if user.location_id else None,
        )
        raw_refresh, _ = create_refresh_token(str(user.id), str(user.tenant_id))
        await self._users.create_refresh_token(user.id, raw_refresh)
        await self._users.update_last_login(user.id)

        await self._audit.log(
            tenant_id=user.tenant_id,
            action="LOGIN",
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info("user_login", user_id=str(user.id), tenant_id=str(user.tenant_id))

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh(self, raw_refresh_token: str) -> TokenResponse:
        token = await self._users.get_refresh_token(raw_refresh_token)

        # Rotate: revoke old, issue new
        await self._users.revoke_refresh_token(raw_refresh_token)

        user_result = await self._users._db.get(
            __import__("app.db.models.user", fromlist=["User"]).User, token.user_id
        )
        if user_result is None or not user_result.is_active:
            raise UnauthorizedError("User not found or inactive")

        access_token = create_access_token(
            str(user_result.id),
            str(user_result.tenant_id),
            user_result.role,
            str(user_result.location_id) if user_result.location_id else None,
        )
        new_raw, _ = create_refresh_token(str(user_result.id), str(user_result.tenant_id))
        await self._users.create_refresh_token(user_result.id, new_raw)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_raw,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(self, raw_refresh_token: str) -> None:
        await self._users.revoke_refresh_token(raw_refresh_token)
