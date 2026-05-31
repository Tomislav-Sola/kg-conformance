"""Tests for observability wiring and key scrubbing.

No telemetry is exported (no connection string is set). The span test installs
an in-memory exporter and asserts the BYOK key reaches no span; the redaction
helpers are unit-tested directly. Together with test_ground_never_logs_the_key
(logs, stdout, response), this covers every path the key could leak through.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.claude_client import Usage
from app.config import load_settings
from app.observability import KeyRedactingFilter, configure_observability, redact

SECRET = "sk-ant-SUPERSECRET-do-not-log-DEADBEEF0001"
SOURCE = "Paris is the capital of France."
DATA = "@prefix ex: <http://example.org/> . ex:France ex:capital ex:Paris ."
KEY_HEADER = {"X-Anthropic-Key": SECRET}


def test_redact_scrubs_anthropic_key() -> None:
    out = redact(f"calling with key={SECRET} now")
    assert SECRET not in out
    assert "REDACTED" in out


def test_key_redacting_filter_scrubs_log_record() -> None:
    flt = KeyRedactingFilter()
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="key is %s",
        args=(SECRET,),
        exc_info=None,
    )
    assert flt.filter(record) is True
    assert SECRET not in record.getMessage()


def test_app_starts_without_connection_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    fresh = FastAPI()
    # Must not raise and must not export, with or without the env var.
    configure_observability(fresh, load_settings())

    @fresh.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    assert TestClient(fresh).get("/ping").status_code == 200


def _install_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, settings, api_key=None) -> None:
            pass

        def complete_grounding(self, claims, source_text):
            return (
                [
                    {"index": i, "verdict": "supported", "justification": "t"}
                    for i, _ in enumerate(claims)
                ],
                Usage(input_tokens=10, output_tokens=5),
            )

    monkeypatch.setattr("app.grounding.ClaudeClient", FakeClient)


def test_ground_request_does_not_leak_key_into_spans(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("opentelemetry")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    exporter.clear()

    _install_fake(monkeypatch)
    response = client.post(
        "/ground", json={"source_text": SOURCE, "data": DATA}, headers=KEY_HEADER
    )
    assert response.status_code == 200

    spans = exporter.get_finished_spans()
    assert spans, "FastAPI instrumentation should have produced a span"

    blob: list[str] = []
    for span in spans:
        blob.append(span.name)
        for key, value in (span.attributes or {}).items():
            blob.append(str(key))
            blob.append(str(value))
        for event in span.events:
            blob.append(event.name)
            for key, value in (event.attributes or {}).items():
                blob.append(str(key))
                blob.append(str(value))
    assert SECRET not in "\n".join(blob)
