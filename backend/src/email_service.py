"""Email service for sending magic link authentication emails."""

import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

logger = logging.getLogger(__name__)


def _get_mail_config() -> tuple[str, int, str, str, str, bool]:
    """Get mail configuration from environment."""
    return (
        os.getenv("MAIL_SERVER", "localhost"),
        int(os.getenv("MAIL_PORT", "587")),
        os.getenv("MAIL_USERNAME", ""),
        os.getenv("MAIL_PASSWORD", ""),
        os.getenv("MAIL_FROM", "noreply@archon.local"),
        os.getenv("MAIL_USE_TLS", "true").lower() == "true",
    )


async def send_magic_link_email(
    to_email: str, magic_link: str, purpose: str = "signup"
) -> bool:
    """Send a magic link email for signup or password reset.

    Args:
        to_email: Recipient email address
        magic_link: Full URL for the magic link
        purpose: "signup" for new accounts, "reset" for password reset

    Returns:
        True if email was sent successfully, False otherwise
    """
    server, port, username, password, from_addr, use_tls = _get_mail_config()

    # Content based on purpose
    if purpose == "reset":
        subject = "Reset your Archon password"
        heading = "Reset your password"
        description = "Click the button below to reset your password."
        button_text = "Reset Password"
    elif purpose == "invite":
        subject = "You've been invited to Archon"
        heading = "Welcome to Archon!"
        description = "You've been registered as a VEKN member. Click the button below to set your password and activate your account."
        button_text = "Activate Account"
    else:
        subject = "Complete your Archon signup"
        heading = "Complete your signup"
        description = "Click the button below to set your password and complete your account setup."
        button_text = "Set Password"

    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    # Plain text version
    text_content = f"""
{heading}

{description}

{magic_link}

This link will expire in 15 minutes.

If you didn't request this email, you can safely ignore it.
"""

    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #1a1a1a; color: #e5e5e5; padding: 40px 20px; margin: 0;">
    <div style="max-width: 480px; margin: 0 auto; background-color: #262626; border-radius: 8px; padding: 40px; border: 1px solid #404040;">
        <h1 style="color: #dc2626; font-size: 28px; font-weight: 300; margin: 0 0 24px 0; text-align: center;">Archon</h1>
        <h2 style="color: #e5e5e5; font-size: 18px; font-weight: 500; margin: 0 0 16px 0; text-align: center;">{heading}</h2>
        <p style="color: #a3a3a3; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0; text-align: center;">
            {description}
        </p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{magic_link}" style="display: inline-block; background-color: #dc2626; color: white; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-weight: 500; font-size: 14px;">
                {button_text}
            </a>
        </div>
        <p style="color: #737373; font-size: 12px; line-height: 1.5; margin: 24px 0 0 0; text-align: center;">
            This link will expire in 15 minutes.<br>
            If you didn't request this email, you can safely ignore it.
        </p>
    </div>
</body>
</html>
"""

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        if username and password:
            # Authenticated SMTP
            await aiosmtplib.send(
                msg,
                hostname=server,
                port=port,
                username=username,
                password=password,
                start_tls=use_tls,
            )
        else:
            # Local/dev SMTP (no auth)
            await aiosmtplib.send(
                msg,
                hostname=server,
                port=port,
                start_tls=False,
            )
        logger.info(f"Magic link email ({purpose}) sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send magic link email to {to_email}: {e}")
        return False
