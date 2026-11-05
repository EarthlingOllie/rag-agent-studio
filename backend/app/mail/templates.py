"""The emails the Studio sends. Each template renders an ``Email`` from its variables."""

from datetime import timedelta
from urllib.parse import urlencode

from app.mail.port import Email

PRODUCT = "RAG Agent Studio"


def _minutes(duration: timedelta) -> str:
    minutes = int(duration.total_seconds() // 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def _duration(duration: timedelta) -> str:
    """Whole days when the duration is whole days, otherwise minutes."""
    if duration.days >= 1 and duration % timedelta(days=1) == timedelta(0):
        return "1 day" if duration.days == 1 else f"{duration.days} days"
    return _minutes(duration)


_ROLE_PHRASES = {"owner": "an Owner", "editor": "an Editor"}


def invite_link(studio_url: str, token: str) -> str:
    return f"{studio_url.rstrip('/')}/accept-invite?{urlencode({'token': token})}"


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


def invite(
    *,
    to: str,
    organisation_name: str,
    inviter_name: str,
    role: str,
    link: str,
    valid_for: timedelta,
) -> Email:
    return Email(
        to=to,
        subject=f"Join {organisation_name} on {PRODUCT}",
        text=(
            "Hello,\n\n"
            f"{inviter_name} has invited you to join {organisation_name} on {PRODUCT} "
            f"as {_ROLE_PHRASES[role]}. "
            "To accept, open this link:\n\n"
            f"{link}\n\n"
            "If you don't have an account yet, you can create one from the link. "
            f"The link works once and expires in {_duration(valid_for)}.\n\n"
            "If you weren't expecting this, you can ignore this email.\n"
        ),
    )
