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


def agent_link(studio_url: str, organisation_id: str, project_id: str, agent_id: str) -> str:
    """The Agent's page in the Studio."""
    return (
        f"{studio_url.rstrip('/')}/organisations/{organisation_id}/projects/{project_id}"
        f"/agents/{agent_id}"
    )


def blocked_conversations_link(
    studio_url: str, organisation_id: str, project_id: str, agent_id: str
) -> str:
    """The Conversations viewer, filtered to the Agent's Conversations with a blocked message."""
    return (
        f"{studio_url.rstrip('/')}/organisations/{organisation_id}/projects/{project_id}"
        f"/conversations?agent={agent_id}&guardrail=blocked"
    )


def block_rate_spike(
    *,
    to: str,
    name: str,
    agent_name: str,
    blocks: int,
    replies: int,
    rate: str,
    baseline_rate: str,
    link: str,
) -> Email:
    return Email(
        to=to,
        subject=f"{agent_name} is blocking an unusual share of messages",
        text=(
            f"Hello {name},\n\n"
            f"The input Guardrail of the Agent {agent_name} blocked {blocks} of the last "
            f"hour's {replies} Visitor messages ({rate}), against {baseline_rate} over the "
            "week before. Someone may be attacking it.\n\n"
            "Review the blocked Conversations in the Studio:\n\n"
            f"{link}\n\n"
            'The Agent shows a "Block rate spike" badge until an hour\'s block rate is back '
            "to normal. You get this email once per spike.\n"
        ),
    )


def token_budget_exhausted(*, to: str, name: str, agent_name: str, budget: int, link: str) -> Email:
    return Email(
        to=to,
        subject=f"{agent_name} has used its daily Token Budget",
        text=(
            f"Hello {name},\n\n"
            f"The Agent {agent_name} has used today's Token Budget of {budget:,} tokens, so "
            "Visitors on your website now see its unavailable text instead of answers. "
            "The budget resets at midnight UTC.\n\n"
            "To raise the budget, open the Agent's Operational Settings in the Studio:\n\n"
            f"{link}\n\n"
            "You get this email once per Agent per day.\n"
        ),
    )
