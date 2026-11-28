"""Alert emails always arrive (spec 21, ADR-0020).

Raising any of the four alerts (Token Budget exhausted, Evaluation budget spent, Block rate
alert, Live score drop alert) writes, in the same transaction that raises it, one row per Owner
of the Organisation holding the email rendered for them (``raise_alert``). Once that commits,
the raiser sends them (``send_alert_emails``); the sweeper sends any still unsent, so a process
that died between raising and sending, or a send that failed for some Owners, is completed by
the next sweep.

Each row is sent under a row lock taken with ``SKIP LOCKED``, and marked sent in the same
transaction, so two senders never send the same row. A second email to one Owner happens only
when the process dies after the send and before the mark commits.
"""

import logging
import uuid
from collections.abc import Callable, Collection
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alert_emails.models import Alert, AlertEmail
from app.mail.port import Email, Mailer
from app.tenancy.models import Member, Membership, Role

logger = logging.getLogger(__name__)

# Renders the email for one Owner, from their name and address.
Render = Callable[[str, str], Email]


async def raise_alert(
    session: AsyncSession,
    alert: Alert,
    *,
    organisation_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    raised_at: datetime,
    render: Render,
) -> list[uuid.UUID]:
    """Records the alert's email to every Owner of the Organisation, unsent, in the caller's
    transaction (the one that raises the alert); the rows' IDs, for ``send_alert_emails``."""
    owners = await session.execute(
        select(Member.id, Member.name, Member.email)
        .join(Membership, Membership.member_id == Member.id)
        .where(Membership.organisation_id == organisation_id, Membership.role == Role.OWNER)
        .order_by(Member.email)
    )
    rows = []
    for member_id, name, address in owners:
        email = render(name, address)
        rows.append(
            AlertEmail(
                id=uuid.uuid4(),
                organisation_id=organisation_id,
                agent_id=agent_id,
                alert=alert,
                raised_at=raised_at,
                member_id=member_id,
                to=email.to,
                subject=email.subject,
                body=email.text,
            )
        )
    session.add_all(rows)
    await session.flush()
    return [row.id for row in rows]


async def send_alert_emails(
    session: AsyncSession,
    mailer: Mailer,
    *,
    now: datetime,
    ids: Collection[uuid.UUID] | None = None,
) -> int:
    """Sends the unsent alert emails (of ``ids``, or all of them, oldest first), each in its own
    transaction, and marks each sent as of ``now``; how many it sent. The session must have no
    transaction of its own open. One another sender holds is left to it; one the mailer refuses
    is logged and left for the next sweep."""
    only = [] if ids is None else [AlertEmail.id.in_(ids)]
    refused: list[uuid.UUID] = []
    sent = 0
    while True:
        row = await session.scalar(
            select(AlertEmail)
            .where(AlertEmail.sent_at.is_(None), AlertEmail.id.not_in(refused), *only)
            .order_by(AlertEmail.raised_at, AlertEmail.to)
            .limit(1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if row is None:
            await session.rollback()
            return sent
        try:
            await mailer.send(Email(to=row.to, subject=row.subject, text=row.body))
        except Exception:
            logger.exception("Alert email %s not sent; the sweeper will try again", row.id)
            refused.append(row.id)
            await session.rollback()
            continue
        row.sent_at = now
        await session.commit()
        sent += 1
