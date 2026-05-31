"""FastAPI application.

Two endpoints:

- GET /health  : liveness, no dependencies.
- POST /validate: runs real SHACL conformance validation (Phase 4) on the
  Turtle data and shapes and returns the report. Deterministic, keyless, free.
- POST /ground: checks whether each triple is supported by the source text
  (Phase 5, the AI core). BYOK via the X-Anthropic-Key header, fail-open.

The handlers stay thin: validation lives in app.validation, grounding
orchestration in app.grounding, the single SDK gateway in app.claude_client.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from app import observability
from app.claude_client import GroundingAuthError, GroundingUnavailable
from app.config import load_settings
from app.grounding import ground_triples
from app.models import (
    CostReport,
    GroundingReport,
    GroundingResult,
    GroundRequest,
    GroundResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.validation import TurtleParseError, validate_conformance

app = FastAPI(
    title="kg-conformance",
    description="Conformance and source-grounding checks for extracted knowledge graphs.",
    version="0.3.0",
)

settings = load_settings()

# Install key redaction, instrument FastAPI, and export to Azure Monitor when a
# connection string is set. Safe (and a no-op for export) without one.
observability.configure_observability(app, settings)


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

    observability.record_validate(conformance.conforms, len(conformance.violations))
    return ValidateResponse(
        conformance=conformance,
        grounding=GroundingReport(available=False),
        cost=CostReport(),
    )


@app.post("/ground", response_model=GroundResponse)
def ground(
    request: GroundRequest,
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
) -> GroundResponse:
    """Check whether each triple is supported by the source text.

    BYOK: the Anthropic key comes from the X-Anthropic-Key header, is used only
    for this request, and is never logged or stored. Guards mirror /validate:
    413 on oversized input, 422 on malformed Turtle. 401 if the key is missing
    or rejected. Transient upstream failures degrade fail-open: a 200 with the
    grounding section marked unavailable, never a 500.
    """

    input_bytes = len(request.source_text.encode("utf-8")) + len(
        request.data.encode("utf-8")
    )
    if input_bytes > settings.max_input_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Input too large: {input_bytes} bytes (source_text + data) "
                f"exceeds the limit of {settings.max_input_bytes} bytes."
            ),
        )

    if not x_anthropic_key:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing X-Anthropic-Key header. Grounding requires a per-request "
                "Anthropic key (BYOK)."
            ),
        )

    try:
        result, cost = ground_triples(
            request.data, request.source_text, x_anthropic_key, settings
        )
    except TurtleParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GroundingAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GroundingUnavailable:
        # Fail-open: valid key, transient/infra failure. Degrade, do not 500.
        observability.record_grounding_degraded()
        return GroundResponse(
            grounding=GroundingResult(
                available=False,
                unavailable_reason="Grounding is temporarily unavailable (upstream error).",
            ),
            cost=CostReport(),
        )

    observability.record_grounding(result.summary, cost)
    return GroundResponse(grounding=result, cost=cost)
