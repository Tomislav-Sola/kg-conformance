"""FastAPI application: the walking skeleton.

Phase 1 wires two endpoints into a running shell:

- GET /health  : liveness, no dependencies.
- POST /validate: accepts the real request contract and returns a fixed dummy
  report. No rdflib, no pyshacl, no model call yet. The conformance layer
  (Phase 4) and the grounding layer (Phase 5) grow into this shell, replacing
  the dummy with real reports while the wire contract stays put.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.models import (
    ConformanceReport,
    CostReport,
    GroundingReport,
    ValidateRequest,
    ValidateResponse,
)

app = FastAPI(
    title="kg-conformance",
    description="Conformance and source-grounding checks for extracted knowledge graphs.",
    version="0.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns ok when the process is serving."""

    return {"status": "ok"}


@app.post("/validate", response_model=ValidateResponse)
def validate(request: ValidateRequest) -> ValidateResponse:
    """Validate a graph. Phase 1 stub: returns a fixed dummy report.

    The request is parsed and validated against the real contract, so callers
    and tests already exercise the wire shape. The body is otherwise ignored
    until the conformance and grounding layers land.
    """

    return ValidateResponse(
        conformance=ConformanceReport(conforms=True, violations=[]),
        grounding=GroundingReport(available=False),
        cost=CostReport(),
    )
