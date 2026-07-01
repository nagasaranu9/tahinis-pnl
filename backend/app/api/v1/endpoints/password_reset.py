"""Password reset endpoints."""
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, status

from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password, hash_refresh_token
from app.db.repositories.password_reset_repo import PasswordResetRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db
from app.services.email.resend_client import ResendClient
from app.core.config import settings

router = APIRouter(tags=["password-reset"])


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    password: str


class PasswordResetResponse(BaseModel):
    message: str


@router.post("/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(
    req: PasswordResetRequest, db=Depends(get_db)
) -> PasswordResetResponse:
    """Request password reset. Sends email with reset link."""
    user_repo = UserRepository(db)
    reset_repo = PasswordResetRepository(db)

    # Note: we don't have tenant_id in this context, so we'll find user by email
    # For security, we still return success even if email not found (prevent email enumeration)
    from sqlalchemy import select
    from app.db.models.user import User

    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()

    if user:
        raw_token, token_hash = await reset_repo.create_reset_token(user.id)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"

        client = ResendClient()
        await client.send_password_reset_email(
            to_email=user.email, reset_url=reset_url, user_name=user.email.split("@")[0]
        )
        await client.close()
        await db.commit()

    return PasswordResetResponse(message="If the email exists, a reset link has been sent.")


@router.post("/password-reset/confirm", response_model=PasswordResetResponse)
async def confirm_password_reset(
    req: PasswordResetConfirm, db=Depends(get_db)
) -> PasswordResetResponse:
    """Confirm password reset with token. Sets new password."""
    reset_repo = PasswordResetRepository(db)
    user_repo = UserRepository(db)

    # Hash the token to look it up
    token_hash = hash_refresh_token(req.token)

    try:
        token = await reset_repo.get_valid_token(token_hash)
    except Exception:
        raise UnauthorizedError("Invalid or expired reset token")

    # Get user and update password
    from sqlalchemy import update
    from app.db.models.user import User

    await db.execute(
        update(User).where(User.id == token.user_id).values(hashed_password=hash_password(req.password))
    )

    # Mark token as used
    await reset_repo.mark_token_used(token_hash)
    await db.commit()

    return PasswordResetResponse(message="Password reset successfully. You can now login.")
