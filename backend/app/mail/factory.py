"""Chooses the mailer adapter from settings."""

import boto3

from app.core.settings import Settings
from app.mail.outbox import OutboxMailer
from app.mail.port import Mailer
from app.mail.ses import SesMailer
from app.mail.smtp import SmtpMailer


def build_mailer(settings: Settings) -> Mailer:
    if settings.mailer == "outbox":
        return OutboxMailer()
    if settings.mailer == "smtp":
        return SmtpMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.mail_from,
            timeout_seconds=settings.smtp_timeout_seconds,
        )
    # "ses": the only value left.
    return SesMailer(
        boto3.client("sesv2", region_name=settings.ses_region), sender=settings.mail_from
    )
