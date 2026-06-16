import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import hash_refresh_token
from app.db.models.user import RefreshToken, User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        result = await self._db.execute(
            select(User).where(User.tenant_id == tenant_id, User.email == email, User.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User:
        result = await self._db.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == user_id, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        await self._db.execute(
            update(User).where(User.id == user_id).values(last_login_at=datetime.now(UTC))
        )

    async def create_refresh_token(self, user_id: uuid.UUID, raw_token: str) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_refresh_token(self, raw_token: str) -> RefreshToken:
        token_hash = hash_refresh_token(raw_token)
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked == False,  # noqa: E712
                RefreshToken.expires_at > datetime.now(UTC),
            )
        )
        token = result.scalar_one_or_none()
        if token is None:
            raise UnauthorizedError("Invalid or expired refresh token")
        return token

    async def revoke_refresh_token(self, raw_token: str) -> None:
        token_hash = hash_refresh_token(raw_token)
        await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> None:
        await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
            .values(revoked=True)
        )
