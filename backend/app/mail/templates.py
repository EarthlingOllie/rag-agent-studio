"""The emails the Studio sends. Each template renders an ``Email`` from its variables."""

from datetime import date, timedelta
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


def _project_link(studio_url: str, organisation_id: str, project_id: str) -> str:
    return f"{studio_url.rstrip('/')}/organisations/{organisation_id}/projects/{project_id}"


def version_comparison_link(
    studio_url: str, organisation_id: str, project_id: str, agent_id: str, a: str, b: str
) -> str:
    """Analytics for the Agent, comparing Version ``a`` with Version ``b``."""
    query = urlencode({"agent": agent_id, "a": a, "b": b})
    return f"{_project_link(studio_url, organisation_id, project_id)}/analytics?{query}"


def failed_live_verdicts_link(
    studio_url: str, organisation_id: str, project_id: str, agent_id: str
) -> str:
    """The Conversations viewer, filtered to the Agent's replies that failed their Live
    Verdict."""
    query = urlencode({"agent": agent_id, "live": "failed"})
    return f"{_project_link(studio_url, organisation_id, project_id)}/conversations?{query}"


def live_score_drop(
    *,
    to: str,
    name: str,
    agent_name: str,
    version: int,
    score: str,
    passed: int,
    judged: int,
    previous_version: int,
    previous_score: str,
    previous_passed: int,
    previous_judged: int,
    comparison_link: str,
    failed_link: str,
) -> Email:
    return Email(
        to=to,
        subject=f"{agent_name}'s Live score dropped",
        text=(
            f"Hello {name},\n\n"
            f"The Agent {agent_name} is answering worse since v{version} was made Live. "
            f"v{version}'s Live score is {score} ({passed} of {judged} judged replies); "
            f"v{previous_version}'s was {previous_score} ({previous_passed} of "
            f"{previous_judged}) over its last 30 days as Live.\n\n"
            "Compare the two Versions in the Studio:\n\n"
            f"{comparison_link}\n\n"
            "Read the replies that failed their Live Verdict:\n\n"
            f"{failed_link}\n\n"
            'The Agent shows a "Live score drop" badge until the drop is no longer clear or '
            "another Version is made Live. You get this email once per drop.\n"
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


def call_minutes_budget_spent(
    *, to: str, name: str, agent_name: str, budget: int, link: str
) -> Email:
    return Email(
        to=to,
        subject=f"{agent_name} has used its daily Call minutes budget",
        text=(
            f"Hello {name},\n\n"
            f"The Agent {agent_name} has used today's Call minutes budget of {budget:,} "
            "minutes, so Visitors who choose to call it now hear that it is unavailable and are "
            "offered messaging instead. Messaging still works. The budget resets at midnight "
            "UTC.\n\n"
            "To raise the budget, open the Agent's Operational Settings in the Studio:\n\n"
            f"{link}\n\n"
            "You get this email once per Agent per day.\n"
        ),
    )


def models_settings_link(studio_url: str, organisation_id: str) -> str:
    """Organisation settings, Models: where Owners set the Evaluation budget."""
    return f"{studio_url.rstrip('/')}/organisations/{organisation_id}/settings/models"


def evaluation_budget_spent(
    *, to: str, name: str, budget: str, resets_on: date, link: str
) -> Email:
    return Email(
        to=to,
        subject="Your Organisation's Evaluation budget is spent",
        text=(
            f"Hello {name},\n\n"
            f"Live Verdicts have spent this month's Evaluation budget of {budget}, so no more "
            "Visitor replies are judged until it is raised or a new month starts on "
            f"{resets_on:%-d %B %Y} (UTC). Judgements already under way still finish, so the "
            "spend can pass the budget slightly. Visitors' replies are not affected, and "
            "Evaluation Runs are never capped.\n\n"
            "To raise the budget, open Organisation settings in the Studio:\n\n"
            f"{link}\n\n"
            "You get this email once per month.\n"
        ),
    )
