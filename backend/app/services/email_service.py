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

    # Diagnostics — never log the password, only whether it's present.
    logger.info(
        "smtp_send_start",
        to=to_email,
        subject=subject,
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        use_tls=settings.SMTP_USE_TLS,
        user=settings.SMTP_USER or None,
        from_email=settings.SMTP_FROM_EMAIL,
        password_set=bool(settings.SMTP_PASSWORD),
    )

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("smtp_send_ok", to=to_email, subject=subject)
        return True
    except Exception as exc:
        # Surface the actual SMTP reason (auth, unverified sender, conn refused) in logs.
        logger.exception(
            "smtp_send_failed",
            to=to_email,
            host=settings.SMTP_HOST,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return False
