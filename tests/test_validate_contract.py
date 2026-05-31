"""Tests for the /validate wire contract.

These pin the request/response shape rather than the validation logic (that is
in test_conformance.py): a well-formed request is accepted and the response
carries the conformance/grounding/cost structure, and a malformed request is
rejected by FastAPI request validation. The data here uses an empty shapes
graph, so validation conforms with no violations.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

# Valid Turtle. The shapes graph is empty (just a prefix), so any data graph
# conforms: there are no constraints to violate.
DATA_TTL = "@prefix ex: <http://example.org/> . ex:a ex:knows ex:b ."
SHAPES_TTL = "@prefix sh: <http://www.w3.org/ns/shacl#> ."


def test_validate_accepts_valid_request(client: TestClient) -> None:
    response = client.post(
        "/validate",
        json={
            "data": DATA_TTL,
            "shapes": SHAPES_TTL,
            "options": {"grounding": False, "max_triples": 50},
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert set(body) == {"conformance", "grounding", "cost"}
    assert body["conformance"]["conforms"] is True
    assert body["conformance"]["violations"] == []
    assert body["grounding"]["available"] is False
    assert body["cost"]["input_tokens"] == 0


def test_validate_defaults_options_when_omitted(client: TestClient) -> None:
    response = client.post(
        "/validate",
        json={"data": DATA_TTL, "shapes": SHAPES_TTL},
    )
    assert response.status_code == 200


def test_validate_rejects_missing_fields(client: TestClient) -> None:
    # `shapes` is required; omitting it is a 422 from request validation.
    response = client.post("/validate", json={"data": DATA_TTL})
    assert response.status_code == 422


def test_validate_rejects_malformed_body(client: TestClient) -> None:
    response = client.post("/validate", content="not json")
    assert response.status_code == 422
