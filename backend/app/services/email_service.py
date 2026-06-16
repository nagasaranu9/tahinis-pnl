import smtplib
from email.message import EmailMessage

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Best-effort send. Returns False (and logs the body) if SMTP isn't configured —
    callers must surface the content another way (e.g. invite_url in the API response)."""
    if not settings.SMTP_HOST:
        logger.warning("smtp_not_configured", to=to_email, subject=subject)
        return False

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("smtp_send_failed", to=to_email)
        return False
