"""FastAPI application.

Two endpoints:

- GET /health  : liveness, no dependencies.
- POST /validate: runs real SHACL conformance validation (Phase 4) on the
  Turtle data and shapes and returns the report. Grounding stays unavailable
  until the AI core lands in Phase 5; the ClaudeClient seam is not touched
  here. The handler stays thin: parsing and validation live in app.validation.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.config import load_settings
from app.models import (
    CostReport,
    GroundingReport,
    ValidateRequest,
    ValidateResponse,
)
from app.validation import TurtleParseError, validate_conformance

app = FastAPI(
    title="kg-conformance",
    description="Conformance and source-grounding checks for extracted knowledge graphs.",
    version="0.1.0",
)

settings = load_settings()


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns ok when the process is serving."""

    return {"status": "ok"}


@app.post("/validate", response_model=ValidateResponse)
def validate(request: ValidateRequest) -> ValidateResponse:
    """Validate a graph against SHACL shapes.

    413 if the combined input exceeds the configured byte cap; 422 if either
    the data or the shapes is not valid Turtle (the message says which).
    Grounding is reported unavailable until Phase 5.
    """

    input_bytes = len(request.data.encode("utf-8")) + len(
        request.shapes.encode("utf-8")
    )
    if input_bytes > settings.max_input_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Input too large: {input_bytes} bytes (data + shapes) exceeds "
                f"the limit of {settings.max_input_bytes} bytes."
            ),
        )

    try:
        conformance = validate_conformance(request.data, request.shapes)
    except TurtleParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ValidateResponse(
        conformance=conformance,
        grounding=GroundingReport(available=False),
        cost=CostReport(),
    )
