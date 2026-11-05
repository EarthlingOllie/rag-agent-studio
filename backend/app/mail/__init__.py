"""The mailer port: send a templated email through whichever adapter settings select.

Adapters: ``ses`` (AWS SES, switched on when a sending domain exists), ``smtp`` (Mailpit in
``docker compose``) and ``outbox`` (in memory, for tests).
"""
