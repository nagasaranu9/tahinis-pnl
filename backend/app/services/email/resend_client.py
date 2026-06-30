"""Resend email client for sending transactional emails."""
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class ResendClient:
    """Resend HTTP API client for sending emails."""

    BASE_URL = "https://api.resend.com"
    TIMEOUT = 30

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.RESEND_API_KEY
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.TIMEOUT,
        )

    async def send_password_reset_email(
        self, to_email: str, reset_url: str, user_name: str = "User"
    ) -> bool:
        """Send password reset email via Resend."""
        if not self.api_key:
            logger.warning("password_reset_email_skipped", reason="RESEND_API_KEY not configured")
            return False

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">Password Reset Request</h2>
            <p>Hello {user_name},</p>
            <p>We received a request to reset your password. Click the button below to set a new password:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 4px; display: inline-block;">
                    Reset Password
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">This link expires in 1 hour. If you didn't request this, you can ignore this email.</p>
            <p style="color: #999; font-size: 12px;">—<br>Tahinis Financial Platform</p>
        </div>
        """

        payload = {
            "from": settings.SMTP_FROM_EMAIL,
            "to": to_email,
            "subject": "Reset Your Password",
            "html": html,
        }

        try:
            response = await self.client.post("/emails", json=payload)
            response.raise_for_status()
            logger.info("password_reset_email_sent", to=to_email)
            return True
        except httpx.HTTPError as e:
            logger.error("password_reset_email_failed", to=to_email, error=str(e))
            return False

    async def send_onboarding_email(
        self, to_email: str, login_url: str, store_name: str = "Your Store"
    ) -> bool:
        """Send onboarding email with login link."""
        if not self.api_key:
            logger.warning("onboarding_email_skipped", reason="RESEND_API_KEY not configured")
            return False

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">Welcome to Tahinis!</h2>
            <p>Your account for <strong>{store_name}</strong> is ready.</p>
            <p>Log in to your dashboard:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{login_url}" style="background-color: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 4px; display: inline-block;">
                    Login to Dashboard
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">Use your email and the password we provided to access your account.</p>
            <p style="color: #999; font-size: 12px;">—<br>Tahinis Financial Platform</p>
        </div>
        """

        payload = {
            "from": settings.SMTP_FROM_EMAIL,
            "to": to_email,
            "subject": f"Welcome to Tahinis - {store_name}",
            "html": html,
        }

        try:
            response = await self.client.post("/emails", json=payload)
            response.raise_for_status()
            logger.info("onboarding_email_sent", to=to_email, store=store_name)
            return True
        except httpx.HTTPError as e:
            logger.error("onboarding_email_failed", to=to_email, error=str(e))
            return False

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
