"""Request and response models for the /validate endpoint.

These define the wire contract from PLAN.md (Request and response, v0.1). In
Phase 1 they back a dummy report only; the conformance and grounding layers
fill them with real content in later phases. Keeping the contract fixed now
means the endpoint and tests do not have to change when the logic lands.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ValidateOptions(BaseModel):
    """Per-request switches and bounds."""

    grounding: bool = False
    max_triples: int = Field(default=200, ge=1)


class ValidateRequest(BaseModel):
    """The input payload: an RDF data graph, SHACL shapes, optional source."""

    data: str = Field(description="The extracted triples, as Turtle.")
    shapes: str = Field(description="The SHACL shapes, as Turtle.")
    source_text: str | None = Field(
        default=None,
        description="Source text the triples were extracted from. Required to enable grounding.",
    )
    options: ValidateOptions = Field(default_factory=ValidateOptions)


class ConformanceReport(BaseModel):
    """SHACL validation outcome. Phase 4 fills violations from pyshacl."""

    conforms: bool
    violations: list[dict] = Field(default_factory=list)


class GroundingReport(BaseModel):
    """Source-grounding outcome. Phase 5 fills the buckets from the AI core.

    `available` is False when grounding was not requested or the model call
    failed (fail-open): in that case the conformance report still stands.
    """

    available: bool = False
    checked: int = 0
    supported: list[dict] = Field(default_factory=list)
    unsupported: list[dict] = Field(default_factory=list)
    uncertain: list[dict] = Field(default_factory=list)


class CostReport(BaseModel):
    """Token and cost accounting for the request."""

    input_tokens: int = 0
    output_tokens: int = 0
    usd_estimate: float = 0.0


class ValidateResponse(BaseModel):
    """The merged report returned by /validate."""

    conformance: ConformanceReport
    grounding: GroundingReport
    cost: CostReport


# --- Grounding (POST /ground), Phase 5 -------------------------------------


class Verdict(str, Enum):
    """Whether the source text backs a triple."""

    supported = "supported"
    unsupported = "unsupported"
    unclear = "unclear"


class GroundRequest(BaseModel):
    """The /ground input: text to check against, and the triples to check."""

    source_text: str = Field(description="The source text the triples should be grounded in.")
    data: str = Field(description="The triples to check, as Turtle.")


class TripleVerdict(BaseModel):
    """One triple's grounding outcome."""

    triple: str
    verdict: Verdict
    justification: str


class GroundingSummary(BaseModel):
    """Verdict counts for the request."""

    checked: int = 0
    supported: int = 0
    unsupported: int = 0
    unclear: int = 0


class GroundingResult(BaseModel):
    """The grounding outcome. `available` is False when the check degraded
    (fail-open): the caller gets a 200 with no verdicts and a reason."""

    available: bool = True
    unavailable_reason: str | None = None
    summary: GroundingSummary = Field(default_factory=GroundingSummary)
    verdicts: list[TripleVerdict] = Field(default_factory=list)


class GroundResponse(BaseModel):
    """The response returned by /ground."""

    grounding: GroundingResult
    cost: CostReport
