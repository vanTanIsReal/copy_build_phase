import asyncio
import logging
import smtplib
from email.message import EmailMessage

from src.config import get_settings

logger = logging.getLogger(__name__)


def _send_password_reset_email(to_email: str, reset_url: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["Subject"] = "Reset your Orbit password"
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message.set_content(
        "We received a request to reset your Orbit password.\n\n"
        f"Open this link to choose a new password:\n{reset_url}\n\n"
        "This link expires soon and can only be used once."
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """Send a reset email when SMTP is configured; return False if unavailable."""
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        return False

    try:
        await asyncio.to_thread(_send_password_reset_email, to_email, reset_url)
    except (OSError, smtplib.SMTPException):
        logger.exception("Password reset email could not be sent")
        return False
    return True
