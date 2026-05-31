"""OpenTelemetry wiring for Azure Application Insights.

configure_observability() runs once at app startup. It always installs the
key-redaction log filter and (when OpenTelemetry is installed) instruments
FastAPI WITHOUT capturing request headers, so the BYOK X-Anthropic-Key header
can never become a span attribute. Telemetry is exported to Azure Monitor only
when APPLICATIONINSIGHTS_CONNECTION_STRING is set, so local runs and tests
neither export nor crash.

The whole module is a no-op when the observability extra is not installed: the
app still serves, just without telemetry. Production gets the extra via the
Docker image.

Custom metrics are deliberately few: validate conforms/violations, ground
verdict counts, grounding token usage, and fail-open degradations.
"""

from __future__ import annotations

import logging
import os
import re

from app.config import Settings

# Real Anthropic keys start with this prefix. Redact anything matching it from
# log records, as defence in depth on top of "headers are never captured".
_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")
_REDACTION = "***REDACTED-ANTHROPIC-KEY***"


def redact(text: str) -> str:
    """Replace anything that looks like an Anthropic key with a marker."""

    return _KEY_RE.sub(_REDACTION, text)


class KeyRedactingFilter(logging.Filter):
    """Scrub Anthropic keys from log records before any handler emits them."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        if "sk-ant-" in message:
            record.msg = redact(message)
            record.args = None
        return True


# --- Metrics ---------------------------------------------------------------
# Built against the global meter (a proxy that is a no-op until a meter provider
# is configured). If OpenTelemetry is not installed at all, fall back to a stub
# so the import and the record_* calls stay harmless.


class _NoopInstrument:
    def add(self, *args, **kwargs) -> None:
        pass


try:
    from opentelemetry import metrics as _otel_metrics

    _meter = _otel_metrics.get_meter("kg-conformance")
    _validate_requests = _meter.create_counter(
        "kgc.validate.requests", description="validate calls, by conforms flag"
    )
    _validate_violations = _meter.create_counter(
        "kgc.validate.violations", description="SHACL violations reported"
    )
    _ground_verdicts = _meter.create_counter(
        "kgc.ground.verdicts", description="grounding verdicts, by verdict"
    )
    _ground_tokens = _meter.create_counter(
        "kgc.ground.tokens", description="grounding token usage, by kind"
    )
    _ground_degraded = _meter.create_counter(
        "kgc.ground.degraded", description="fail-open grounding degradations"
    )
except ImportError:  # observability extra not installed
    _validate_requests = _NoopInstrument()
    _validate_violations = _NoopInstrument()
    _ground_verdicts = _NoopInstrument()
    _ground_tokens = _NoopInstrument()
    _ground_degraded = _NoopInstrument()


def record_validate(conforms: bool, violations: int) -> None:
    _validate_requests.add(1, {"conforms": str(conforms).lower()})
    if violations:
        _validate_violations.add(violations)


def record_grounding(summary, cost) -> None:
    _ground_verdicts.add(summary.supported, {"verdict": "supported"})
    _ground_verdicts.add(summary.unsupported, {"verdict": "unsupported"})
    _ground_verdicts.add(summary.unclear, {"verdict": "unclear"})
    if cost.input_tokens:
        _ground_tokens.add(cost.input_tokens, {"kind": "input"})
    if cost.output_tokens:
        _ground_tokens.add(cost.output_tokens, {"kind": "output"})


def record_grounding_degraded() -> None:
    _ground_degraded.add(1)


# --- Setup -----------------------------------------------------------------

_redaction_installed = False


def _install_log_redaction() -> None:
    global _redaction_installed
    if _redaction_installed:
        return
    flt = KeyRedactingFilter()
    root = logging.getLogger()
    root.addFilter(flt)
    for handler in root.handlers:
        handler.addFilter(flt)
    _redaction_installed = True


def configure_observability(app, settings: Settings) -> None:
    """Install key redaction, instrument FastAPI, and export only if configured."""

    _install_log_redaction()

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        # Observability extra not installed: serve without telemetry.
        return

    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=connection_string,
            sampling_ratio=settings.otel_sampling_ratio,
        )
        # configure_azure_monitor just attached its log-export handler to the
        # root logger; redact on that handler too.
        for handler in logging.getLogger().handlers:
            handler.addFilter(KeyRedactingFilter())

    # Instrument FastAPI. Request headers are NOT captured (the default), so the
    # X-Anthropic-Key header never reaches a span. Do not enable
    # OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST.
    FastAPIInstrumentor.instrument_app(app)
