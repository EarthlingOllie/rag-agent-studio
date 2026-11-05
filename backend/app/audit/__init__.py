"""The audit module: one ``record`` operation for writing Audit Events, and Owner-only reads.

Every security- or configuration-relevant change calls ``record`` in the same transaction as
the change itself, so the change and its Audit Event commit or roll back together.
"""

from app.audit.service import AuditTarget, record

__all__ = ["AuditTarget", "record"]
