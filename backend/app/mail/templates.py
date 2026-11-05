"""The emails the Studio sends. Each template renders an ``Email`` from its variables."""

from datetime import timedelta
from urllib.parse import urlencode

from app.mail.port import Email

PRODUCT = "RAG Agent Studio"


def _minutes(duration: timedelta) -> str:
    minutes = int(duration.total_seconds() // 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def password_reset(
    *, to: str, name: str, studio_url: str, token: str, valid_for: timedelta
) -> Email:
    link = f"{studio_url.rstrip('/')}/reset-password?{urlencode({'token': token})}"
    return Email(
        to=to,
        subject=f"Reset your {PRODUCT} password",
        text=(
            f"Hello {name},\n\n"
            f"Someone asked to reset the password for your {PRODUCT} account. "
            "To choose a new password, open this link:\n\n"
            f"{link}\n\n"
            f"The link works once and expires in {_minutes(valid_for)}. Resetting your password "
            "signs you out everywhere else.\n\n"
            "If you didn't ask for this, you can ignore this email. Your password stays the same.\n"
        ),
    )
