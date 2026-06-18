import smtplib
from email.message import EmailMessage

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Best-effort send. Returns False (and logs) if no transport is configured or the
    send fails — callers must surface the content another way (e.g. invite_url in the
    API response).

    Prefers the Resend HTTP API (HTTPS:443) because Railway blocks outbound SMTP ports
    (25/465/587), which makes smtplib hang and time out. Falls back to SMTP only if no
    RESEND_API_KEY is set.
    """
    if settings.RESEND_API_KEY:
        return _send_via_resend(to_email, subject, body)
    if settings.SMTP_HOST:
        return _send_via_smtp(to_email, subject, body)
    logger.warning("email_not_configured", to=to_email, subject=subject)
    return False


def _send_via_resend(to_email: str, subject: str, body: str) -> bool:
    logger.info(
        "resend_send_start",
        to=to_email,
        subject=subject,
        from_email=settings.SMTP_FROM_EMAIL,
    )
    try:
        resp = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.SMTP_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
            timeout=15,
        )
    except Exception as exc:
        logger.exception(
            "resend_send_failed", to=to_email, error_type=type(exc).__name__, error=str(exc)
        )
        return False

    if resp.status_code >= 400:
        # Surface Resend's reason (e.g. unverified sender domain, bad key).
        logger.error(
            "resend_send_rejected",
            to=to_email,
            status_code=resp.status_code,
            response=resp.text[:500],
        )
        return False

    logger.info("resend_send_ok", to=to_email, subject=subject)
    return True


def _send_via_smtp(to_email: str, subject: str, body: str) -> bool:
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
        logger.exception(
            "smtp_send_failed",
            to=to_email,
            host=settings.SMTP_HOST,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return False
