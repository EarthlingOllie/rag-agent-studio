"""Audit Events stay append-only, except when their whole Organisation is erased (ticket 10-01).

``make seed-reset`` deletes the demo Organisation and recreates it. Its Audit Events go with it:
the trigger now lets a DELETE through when the transaction has set
``app.erasing_organisation`` to the row's Organisation ID (``app.tenancy.erasure``). Every
other UPDATE, DELETE and TRUNCATE is still refused.

Revision ID: 0019_erase_organisation
Revises: 0018_document_failures
Create Date: 2026-11-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_erase_organisation"
down_revision: str | None = "0018_document_failures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE'
                AND OLD.organisation_id::text = current_setting('app.erasing_organisation', true)
            THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
