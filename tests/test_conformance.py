"""Tests for real SHACL conformance validation on /validate.

Cases: a conforming graph, a violating graph (with the expected violation
content), malformed data, malformed shapes, and oversized input.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


SHAPES = _fixture("shapes.ttl")
CONFORMING = _fixture("conforming_data.ttl")
VIOLATING = _fixture("violating_data.ttl")


def test_conforming_graph(client: TestClient) -> None:
    response = client.post(
        "/validate", json={"data": CONFORMING, "shapes": SHAPES}
    )
    assert response.status_code == 200

    conformance = response.json()["conformance"]
    assert conformance["conforms"] is True
    assert conformance["violations"] == []


def test_violating_graph(client: TestClient) -> None:
    response = client.post(
        "/validate", json={"data": VIOLATING, "shapes": SHAPES}
    )
    assert response.status_code == 200

    conformance = response.json()["conformance"]
    assert conformance["conforms"] is False
    assert len(conformance["violations"]) == 1

    violation = conformance["violations"][0]
    assert violation["focus_node"] == "http://example.org/bob"
    assert violation["path"] == "http://example.org/name"
    assert violation["message"] == "A person must have exactly one name (a string)."
    # The missing-name violation is a minCount constraint.
    assert violation["constraint_component"].endswith("MinCountConstraintComponent")


def test_malformed_data_returns_422(client: TestClient) -> None:
    response = client.post(
        "/validate", json={"data": "this is not turtle <<<", "shapes": SHAPES}
    )
    assert response.status_code == 422
    assert "data" in response.json()["detail"]


def test_malformed_shapes_returns_422(client: TestClient) -> None:
    response = client.post(
        "/validate", json={"data": CONFORMING, "shapes": "@prefix broken <<<"}
    )
    assert response.status_code == 422
    assert "shapes" in response.json()["detail"]


def test_oversized_input_returns_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Shrink the cap rather than build a megabyte payload.
    monkeypatch.setattr("app.main.settings", Settings(max_input_bytes=100))
    big = "@prefix ex: <http://example.org/> .\n" + "ex:a ex:b ex:c .\n" * 50

    response = client.post("/validate", json={"data": big, "shapes": SHAPES})
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()
