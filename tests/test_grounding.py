"""Tests for POST /ground with a mocked ClaudeClient.

No real Anthropic call happens in CI: every test patches app.grounding.ClaudeClient
with a fake. Cases: happy path with mixed verdicts, batching across multiple
calls, fail-open on a transient failure, missing key, and the input guards.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.claude_client import GroundingUnavailable, Usage
from app.config import Settings

SOURCE = "Paris is the capital of France. Berlin is the capital of Germany."
DATA_TWO = (
    "@prefix ex: <http://example.org/> .\n"
    "ex:France ex:capital ex:Paris .\n"
    "ex:Germany ex:capital ex:Paris .\n"
)
KEY_HEADER = {"X-Anthropic-Key": "sk-test-not-a-real-key"}


def _install_fake(monkeypatch: pytest.MonkeyPatch, behavior):
    """Patch the gateway with a fake; return a dict recording the batches sent."""

    recorded = {"batches": [], "source_texts": []}

    class FakeClient:
        def __init__(self, settings, api_key=None) -> None:
            pass

        def complete_grounding(self, claims, source_text):
            recorded["batches"].append(list(claims))
            recorded["source_texts"].append(source_text)
            return behavior(claims), Usage(input_tokens=10, output_tokens=5)

    monkeypatch.setattr("app.grounding.ClaudeClient", FakeClient)
    return recorded


def _verdict_by_country(claims):
    # The France triple is supported by the source; the Germany triple is not.
    return [
        {
            "index": i,
            "verdict": "supported" if "France" in claim else "unsupported",
            "justification": "test verdict",
        }
        for i, claim in enumerate(claims)
    ]


def test_ground_happy_path_maps_mixed_verdicts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake(monkeypatch, _verdict_by_country)

    response = client.post(
        "/ground", json={"source_text": SOURCE, "data": DATA_TWO}, headers=KEY_HEADER
    )
    assert response.status_code == 200

    body = response.json()
    grounding = body["grounding"]
    assert grounding["available"] is True
    assert grounding["summary"] == {
        "checked": 2,
        "supported": 1,
        "unsupported": 1,
        "unclear": 0,
    }

    by_triple = {v["triple"]: v["verdict"] for v in grounding["verdicts"]}
    assert by_triple["http://example.org/France http://example.org/capital http://example.org/Paris"] == "supported"
    assert by_triple["http://example.org/Germany http://example.org/capital http://example.org/Paris"] == "unsupported"
    # One batch -> one Usage record.
    assert body["cost"]["input_tokens"] == 10
    assert body["cost"]["output_tokens"] == 5


def test_ground_batches_multiple_triples(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.main.settings", Settings(grounding_batch_size=1))
    recorded = _install_fake(
        monkeypatch,
        lambda claims: [
            {"index": i, "verdict": "unclear", "justification": "t"}
            for i, _ in enumerate(claims)
        ],
    )

    response = client.post(
        "/ground", json={"source_text": SOURCE, "data": DATA_TWO}, headers=KEY_HEADER
    )
    assert response.status_code == 200
    # Two triples, batch size 1 -> two calls, one claim each.
    assert len(recorded["batches"]) == 2
    assert all(len(batch) == 1 for batch in recorded["batches"])
    assert response.json()["grounding"]["summary"]["checked"] == 2
    # Cost accumulates across batches.
    assert response.json()["cost"]["input_tokens"] == 20


def test_ground_caps_source_text_at_max_source_chars(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.main.settings", Settings(max_source_chars=10))
    recorded = _install_fake(monkeypatch, _verdict_by_country)

    response = client.post(
        "/ground",
        json={"source_text": "A" * 100, "data": DATA_TWO},
        headers=KEY_HEADER,
    )
    assert response.status_code == 200
    # The model only ever sees the capped source text.
    assert recorded["source_texts"]
    assert all(len(text) <= 10 for text in recorded["source_texts"])


def test_ground_fail_open_on_transient_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(claims):
        raise GroundingUnavailable("simulated transient failure")

    _install_fake(monkeypatch, boom)

    response = client.post(
        "/ground", json={"source_text": SOURCE, "data": DATA_TWO}, headers=KEY_HEADER
    )
    # Degrade, not a 500.
    assert response.status_code == 200
    grounding = response.json()["grounding"]
    assert grounding["available"] is False
    assert grounding["verdicts"] == []
    assert grounding["unavailable_reason"]


def test_ground_never_logs_the_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Guard the BYOK contract by assertion, not by "nobody logs it today": this
    # goes red in Phase 6 if observability ever logs the header or the key.
    secret = "sk-ant-SUPERSECRET-do-not-log-DEADBEEF"
    _install_fake(monkeypatch, _verdict_by_country)
    caplog.set_level(logging.DEBUG)

    response = client.post(
        "/ground",
        json={"source_text": SOURCE, "data": DATA_TWO},
        headers={"X-Anthropic-Key": secret},
    )
    assert response.status_code == 200

    captured = capsys.readouterr()
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
    assert secret not in response.text


def test_ground_missing_key_returns_401(client: TestClient) -> None:
    response = client.post("/ground", json={"source_text": SOURCE, "data": DATA_TWO})
    assert response.status_code == 401
    assert "X-Anthropic-Key" in response.json()["detail"]


def test_ground_malformed_turtle_returns_422(client: TestClient) -> None:
    response = client.post(
        "/ground",
        json={"source_text": SOURCE, "data": "this is not turtle <<<"},
        headers=KEY_HEADER,
    )
    assert response.status_code == 422
    assert "data" in response.json()["detail"]


def test_ground_oversized_input_returns_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.main.settings", Settings(max_input_bytes=50))
    response = client.post(
        "/ground",
        json={"source_text": "x" * 100, "data": DATA_TWO},
        headers=KEY_HEADER,
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()
