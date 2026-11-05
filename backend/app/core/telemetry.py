"""OpenTelemetry through the Logfire SDK, shared by the API, the worker and Beat.

Spans go to Logfire when a token is configured and to the console otherwise. Every exporter sits
behind Logfire's scrubbing processor, which these settings extend so that Message bodies are
redacted along with cookies, authorisation headers and secret-like attributes.
"""

import functools
import re
import string
import sys
from collections.abc import Sequence
from typing import Any

import logfire
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.settings import Settings

# Fields that carry Message text: a key named like these, at any depth, has its value redacted.
# ``input`` is where validation errors echo a rejected request value back.
_MESSAGE_FIELD_NAMES = r"(?:content|messages?|prompt|input)"
MESSAGE_FIELD_PATTERN = rf"(?:^|[._ -]){_MESSAGE_FIELD_NAMES}\Z"
# The same names as keys inside a JSON-encoded attribute, so the scrubber parses and walks it.
_MESSAGE_FIELD_IN_JSON = rf'"{_MESSAGE_FIELD_NAMES}"\s*:'
MESSAGE_PATTERNS = (MESSAGE_FIELD_PATTERN, _MESSAGE_FIELD_IN_JSON)
_MESSAGE_FIELD_RE = re.compile(MESSAGE_FIELD_PATTERN, re.IGNORECASE)


def _keep_prose_mentioning_messages(match: logfire.ScrubMatch) -> Any:
    """Redact every match except a plain value that merely ends with a word like "message".

    Logfire matches each pattern against keys and values alike. A Message field is identified
    by its key, so a value such as "Visitor sent a message" is kept. The scrubber reports the
    leftmost match, so a value kept here contains no other sensitive pattern.
    """
    matched_text = match.pattern_match.string
    on_key = bool(match.path) and matched_text == match.path[-1]
    if not on_key and _MESSAGE_FIELD_RE.fullmatch(match.pattern_match.group(0)):
        return match.value
    return None


SCRUBBING = logfire.ScrubbingOptions(
    extra_patterns=MESSAGE_PATTERNS, callback=_keep_prose_mentioning_messages
)

_SCRUBBED_MARK = "[Scrubbed due to "
_FIELD_NAME_END = re.compile(r"[.\[!:=]")


def _template_fields(template: str) -> set[str]:
    return {
        _FIELD_NAME_END.split(field)[0]
        for _, field, _, _ in string.Formatter().parse(template)
        if field
    }


def _hide_scrubbed_values_in_message(span: ReadableSpan) -> ReadableSpan:
    """Fall back to the bare message template when a value it formats was scrubbed.

    Logfire formats a log's message from its arguments and, by design, does not scrub a value
    that the template names explicitly, e.g. ``logfire.info("sent {content}", content=...)``.
    """
    attributes = dict(span.attributes or {})
    template = attributes.get("logfire.msg_template")
    if not isinstance(template, str):
        return span
    # A scrubbed value may be nested, e.g. a model argument whose ``content`` was redacted.
    if not any(
        _SCRUBBED_MARK in str(attributes.get(field, "")) for field in _template_fields(template)
    ):
        return span
    attributes["logfire.msg"] = template
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class ScrubbedMessageProcessor(SpanProcessor):
    """Passes Logfire-scrubbed spans on to ``inner`` with formatted messages made safe too."""

    def __init__(self, inner: SpanProcessor) -> None:
        self._inner = inner

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        self._inner.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        self._inner.on_end(_hide_scrubbed_values_in_message(span))

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def _span_exporter(settings: Settings) -> SpanExporter:
    """Logfire when a token is configured, otherwise one JSON object per span on stdout."""
    if settings.logfire_token is None:
        return ConsoleSpanExporter(
            out=sys.stdout, formatter=lambda span: span.to_json(indent=None) + "\n"
        )
    token = settings.logfire_token.get_secret_value()
    configured_base_url = str(settings.logfire_base_url) if settings.logfire_base_url else None
    base_url = logfire.AdvancedOptions(base_url=configured_base_url).generate_base_url(token)
    return OTLPSpanExporter(
        endpoint=f"{base_url.rstrip('/')}/v1/traces", headers={"Authorization": token}
    )


def configure_telemetry(
    settings: Settings,
    service_name: str,
    *,
    extra_span_processors: Sequence[SpanProcessor] = (),
) -> None:
    """Configure the process-wide tracer and instrument Celery and HTTP clients.

    ``extra_span_processors`` receive the same scrubbed spans as the configured exporter.
    """
    logfire.configure(
        service_name=service_name,
        environment=settings.environment,
        send_to_logfire=False,
        console=False,
        scrubbing=SCRUBBING,
        # Trace context travels with Celery tasks so worker spans join the request that queued them.
        distributed_tracing=True,
        additional_span_processors=[
            ScrubbedMessageProcessor(processor)
            for processor in (BatchSpanProcessor(_span_exporter(settings)), *extra_span_processors)
        ],
    )
    _instrument_process_wide_libraries()


@functools.cache
def _instrument_process_wide_libraries() -> None:
    """Instrumentors are process-wide singletons; configuring again only swaps the exporters."""
    logfire.instrument_celery()
    logfire.instrument_httpx()


def instrument_engine(engine: AsyncEngine) -> None:
    """Trace queries on ``engine``, the process's database engine."""
    instrumentor = SQLAlchemyInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        # Only one engine is traced at a time; an app rebuilt in the same process replaces it.
        instrumentor.uninstrument()
    # The instrumentation declares support for SQLAlchemy < 2.1; it works with 2.1 (the telemetry
    # tests assert real query spans), so the declared-range check is skipped.
    logfire.instrument_sqlalchemy(engine=engine, skip_dep_check=True)


def flush_telemetry() -> None:
    """Export buffered spans now; a server stopped by a signal exits without atexit hooks."""
    logfire.force_flush()
