"""Tests for the keyless GET /demo endpoint.

These assert the structure and the keyless, no-model-call contract, not the
specific verdicts (those come from a real grounding run and may vary when the
fixture is regenerated). The tests skip until the fixture has been generated
(scripts/generate_demo.py); once it exists they run for real.
"""

from __future__ import annotations

from importlib.resources import files

import pytest
from fastapi.testclient import TestClient


def _fixture_present() -> bool:
    try:
        return files("app").joinpath("demo_data/demo.json").is_file()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _fixture_present(),
    reason="demo fixture not generated yet (run scripts/generate_demo.py)",
)


def test_demo_is_keyless_and_well_formed(client: TestClient) -> None:
    response = client.get("/demo")  # no X-Anthropic-Key header
    assert response.status_code == 200

    body = response.json()
    assert set(body) == {"example", "grounding", "meta"}

    assert body["example"]["source_text"]
    assert body["example"]["data"]

    grounding = body["grounding"]
    assert grounding["available"] is True
    assert set(grounding["summary"]) == {
        "checked",
        "supported",
        "unsupported",
        "unclear",
    }
    assert grounding["verdicts"], "expected at least one verdict"
    for verdict in grounding["verdicts"]:
        assert {"triple", "verdict", "justification"} <= set(verdict)
        assert verdict["verdict"] in {"supported", "unsupported", "unclear"}

    meta = body["meta"]
    assert meta["model"]
    assert meta["generated_at"]
    assert "ground" in meta["note"].lower()


def test_demo_makes_no_model_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If /demo ever tried a live call, instantiating this gateway would fail.
    class ExplodingClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("/demo must not instantiate the ClaudeClient")

    monkeypatch.setattr("app.grounding.ClaudeClient", ExplodingClient)
    assert client.get("/demo").status_code == 200
