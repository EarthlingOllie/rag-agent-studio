"""TOTP MFA: enrol, confirm, verify, replace recovery codes and disable.

RFC 6238 TOTP (SHA-1, six digits, 30-second steps) with a window of one step either side.
A code is accepted once: the step it was accepted for is stored, and that step and earlier
ones are refused afterwards. The secret is envelope-encrypted, bound to the Member's ID.
Ten single-use recovery codes are stored as SHA-256 hashes.

Every successful enrolment, disabling, recovery-code use and recovery-code replacement is
recorded as an Audit Event in each Organisation the Member belongs to.
"""

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

import pyotp
import segno
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import Target, record
from app.auth.models import MfaFactor, RecoveryCode
from app.auth.passwords import verify_password
from app.core.clock import Clock
from app.crypto.envelope import EnvelopeEncryption
from app.tenancy.models import Member, Membership

ISSUER = "RAG Agent Studio"
STEP_SECONDS = 30
WINDOW_STEPS = 1
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_TOTP_CODE = re.compile(r"\d{6}")
_RECOVERY_CODE = re.compile(r"[A-Z2-7]{16}")


class MfaAlreadyEnabledError(Exception):
    pass


class MfaNotEnabledError(Exception):
    pass


class NoPendingEnrolmentError(Exception):
    pass


class CodeIncorrectError(Exception):
    pass


@dataclass(frozen=True)
class MfaStatus:
    enabled: bool
    recovery_codes_remaining: int


@dataclass(frozen=True)
class Enrolment:
    secret: str
    otpauth_uri: str
    qr_code: str


def _context(member_id: uuid.UUID) -> bytes:
    return b"mfa-totp:" + member_id.bytes


def _hash_recovery_code(normalised: str) -> str:
    return hashlib.sha256(normalised.encode()).hexdigest()


def _new_recovery_code() -> str:
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


class Mfa:
    """The MFA operations for one request: a database session, the envelope and the clock."""

    def __init__(self, session: AsyncSession, envelope: EnvelopeEncryption, clock: Clock) -> None:
        self._session = session
        self._envelope = envelope
        self._clock = clock

    async def status(self, member_id: uuid.UUID) -> MfaStatus:
        factor = await self._session.get(MfaFactor, member_id)
        enabled = factor is not None and factor.confirmed_at is not None
        remaining = await self._session.scalar(
            select(func.count())
            .select_from(RecoveryCode)
            .where(RecoveryCode.member_id == member_id, RecoveryCode.used_at.is_(None))
        )
        return MfaStatus(enabled=enabled, recovery_codes_remaining=remaining or 0)

    async def is_enabled(self, member_id: uuid.UUID) -> bool:
        return (await self.status(member_id)).enabled

    async def start_enrolment(self, member: Member) -> Enrolment:
        """A new secret for the Member's authenticator; replaces any unconfirmed one."""
        factor = await self._session.get(MfaFactor, member.id)
        if factor is not None and factor.confirmed_at is not None:
            raise MfaAlreadyEnabledError
        secret = pyotp.random_base32()
        sealed = self._envelope.seal(secret.encode(), context=_context(member.id))
        if factor is None:
            self._session.add(MfaFactor(member_id=member.id, secret_sealed=sealed))
        else:
            factor.secret_sealed = sealed
            factor.last_used_step = None
        await self._session.commit()
        uri = pyotp.TOTP(secret).provisioning_uri(name=member.email, issuer_name=ISSUER)
        qr_code = segno.make(uri, error="m").svg_data_uri(scale=4, border=4, light="#fff")
        return Enrolment(secret=secret, otpauth_uri=uri, qr_code=qr_code)

    async def confirm_enrolment(self, member: Member, code: str) -> list[str]:
        """Turns MFA on once the authenticator's code checks out; returns the recovery codes."""
        factor = await self._session.get(MfaFactor, member.id)
        if factor is None:
            raise NoPendingEnrolmentError
        if factor.confirmed_at is not None:
            raise MfaAlreadyEnabledError
        if not await self._accept_totp(factor, code):
            raise CodeIncorrectError
        factor.confirmed_at = self._clock.now()
        codes = self._issue_recovery_codes(member.id)
        await self._audit(member.id, "mfa.enrolled", {"mfa_enabled": False}, {"mfa_enabled": True})
        await self._session.commit()
        return codes

    async def verify(self, member_id: uuid.UUID, code: str) -> bool:
        """Checks a TOTP or recovery code for an enabled Member, using it up if it is good."""
        factor = await self._enabled_factor(member_id)
        accepted = await self._accept_code(factor, code)
        await self._session.commit()
        return accepted

    async def replace_recovery_codes(self, member: Member, code: str) -> list[str]:
        factor = await self._enabled_factor(member.id)
        if not await self._accept_code(factor, code):
            await self._session.commit()
            raise CodeIncorrectError
        await self._session.execute(delete(RecoveryCode).where(RecoveryCode.member_id == member.id))
        codes = self._issue_recovery_codes(member.id)
        await self._audit(
            member.id, "mfa.recovery_codes_replaced", None, {"recovery_codes_remaining": len(codes)}
        )
        await self._session.commit()
        return codes

    async def disable(self, member: Member, *, password: str, code: str) -> None:
        """Turns MFA off; needs the password and a code. The password is checked first, so a
        wrong password doesn't use up a code."""
        factor = await self._enabled_factor(member.id)
        if not verify_password(member.password_hash, password):
            raise CodeIncorrectError
        if not await self._accept_code(factor, code):
            await self._session.commit()
            raise CodeIncorrectError
        await self._session.execute(delete(RecoveryCode).where(RecoveryCode.member_id == member.id))
        await self._session.delete(factor)
        await self._audit(member.id, "mfa.disabled", {"mfa_enabled": True}, {"mfa_enabled": False})
        await self._session.commit()

    async def _enabled_factor(self, member_id: uuid.UUID) -> MfaFactor:
        factor = await self._session.get(MfaFactor, member_id)
        if factor is None or factor.confirmed_at is None:
            raise MfaNotEnabledError
        return factor

    async def _accept_code(self, factor: MfaFactor, code: str) -> bool:
        code = code.strip()
        if _TOTP_CODE.fullmatch(code):
            return await self._accept_totp(factor, code)
        return await self._accept_recovery_code(factor.member_id, code)

    async def _accept_totp(self, factor: MfaFactor, code: str) -> bool:
        secret = self._envelope.open(factor.secret_sealed, context=_context(factor.member_id))
        totp = pyotp.TOTP(secret.decode())
        current = int(self._clock.now().timestamp()) // STEP_SECONDS
        last_used = factor.last_used_step
        for step in range(current - WINDOW_STEPS, current + WINDOW_STEPS + 1):
            if last_used is not None and step <= last_used:
                continue
            if hmac.compare_digest(totp.generate_otp(step), code):
                # Conditional, so two requests racing with one code can't both succeed.
                result = await self._session.execute(
                    update(MfaFactor)
                    .where(
                        MfaFactor.member_id == factor.member_id,
                        or_(MfaFactor.last_used_step.is_(None), MfaFactor.last_used_step < step),
                    )
                    .values(last_used_step=step)
                    .returning(MfaFactor.member_id),
                    execution_options={"synchronize_session": "fetch"},
                )
                return result.first() is not None
        return False

    async def _accept_recovery_code(self, member_id: uuid.UUID, code: str) -> bool:
        normalised = re.sub(r"[\s-]", "", code).upper()
        if not _RECOVERY_CODE.fullmatch(normalised):
            return False
        used = await self._session.scalar(
            update(RecoveryCode)
            .where(
                RecoveryCode.member_id == member_id,
                RecoveryCode.code_hash == _hash_recovery_code(normalised),
                RecoveryCode.used_at.is_(None),
            )
            .values(used_at=self._clock.now())
            .returning(RecoveryCode.id)
        )
        if used is None:
            return False
        remaining = (await self.status(member_id)).recovery_codes_remaining
        await self._audit(
            member_id, "mfa.recovery_code_used", None, {"recovery_codes_remaining": remaining}
        )
        return True

    def _issue_recovery_codes(self, member_id: uuid.UUID) -> list[str]:
        codes = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        self._session.add_all(
            RecoveryCode(member_id=member_id, code_hash=_hash_recovery_code(code.replace("-", "")))
            for code in codes
        )
        return codes

    async def _audit(
        self,
        member_id: uuid.UUID,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        organisation_ids = await self._session.scalars(
            select(Membership.organisation_id).where(Membership.member_id == member_id)
        )
        for organisation_id in organisation_ids:
            record(
                self._session,
                organisation_id=organisation_id,
                actor_member_id=member_id,
                action=action,
                target=Target("member", member_id),
                before=before,
                after=after,
            )
