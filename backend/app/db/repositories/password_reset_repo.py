"""Password reset token repository."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.security import hash_refresh_token
from app.db.models.password_reset import PasswordResetToken


class PasswordResetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_reset_token(self, user_id: uuid.UUID, expires_in_hours: int = 1) -> tuple[str, str]:
        """
        Create password reset token.
        Returns (raw_token, token_hash) — raw sent to user, hash stored in DB.
        """
        import secrets

        raw = secrets.token_urlsafe(32)
        hashed = hash_refresh_token(raw)

        token = PasswordResetToken(
            user_id=user_id,
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(hours=expires_in_hours),
        )
        self._db.add(token)
        await self._db.flush()
        return raw, hashed

    async def get_valid_token(self, token_hash: str) -> PasswordResetToken:
        """Get unexpired, unused token."""
        result = await self._db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.expires_at > datetime.now(UTC),
                PasswordResetToken.used_at == None,  # noqa: E711
            )
        )
        token = result.scalar_one_or_none()
        if token is None:
            raise NotFoundError("Invalid or expired reset token")
        return token

    async def mark_token_used(self, token_hash: str) -> None:
        """Mark token as used."""
        await self._db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .values(used_at=datetime.now(UTC))
        )

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> None:
        """Revoke all reset tokens for user."""
        await self._db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at == None)  # noqa: E711
            .values(used_at=datetime.now(UTC))
        )
