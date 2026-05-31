"""Service configuration.

A single place for the grounding model name, the hard input bounds, and the
environment key lookup. Phase 1 only defines these; the grounding layer reads
them in Phase 5. Kept as a plain dataclass to avoid pulling in a settings
dependency that is not in pyproject. Override any field via the environment.

pydantic-settings is deliberately not used: the dependency set in pyproject
does not include it, and a handful of os.environ reads is enough here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Immutable service settings, sourced from the environment with defaults."""

    # The grounding model. A Haiku-class model is sufficient (see PLAN.md).
    # Set in exactly one place so it is not hardcoded across the codebase.
    grounding_model: str = "claude-haiku-4-5-20251001"

    # Combined byte cap on the request inputs (data + shapes). Enforced in
    # Phase 4 to protect the public scale-to-zero endpoint. Roughly 1 MB.
    max_input_bytes: int = 1_000_000

    # Hard bounds on the grounding call. max_triples caps how many triples are
    # checked; max_source_chars caps the source text sent to the model (the
    # field that drives prompt size and cost). Both are enforced in app.grounding.
    max_triples: int = 200
    max_source_chars: int = 50_000
    # How many triples per batched model call, the output-token cap per call,
    # the per-run token budget (input + output), and the transient-error retry
    # ceiling. Tunable via the environment.
    grounding_batch_size: int = 50
    grounding_max_output_tokens: int = 2048
    grounding_token_budget: int = 100_000
    grounding_max_retries: int = 3

    # OpenTelemetry trace/log sampling ratio (0.0-1.0). Moderate by default to
    # bound Application Insights ingestion. Only matters once a connection
    # string is configured.
    otel_sampling_ratio: float = 0.2

    # The environment fallback key. BYOK header takes precedence per request
    # and is never read from here. None means grounding needs a header key.
    anthropic_api_key: str | None = None


def load_settings() -> Settings:
    """Build Settings from the environment, falling back to the defaults."""

    defaults = Settings()
    return Settings(
        grounding_model=os.environ.get("GROUNDING_MODEL", defaults.grounding_model),
        max_input_bytes=int(
            os.environ.get("MAX_INPUT_BYTES", defaults.max_input_bytes)
        ),
        max_triples=int(os.environ.get("MAX_TRIPLES", defaults.max_triples)),
        max_source_chars=int(
            os.environ.get("MAX_SOURCE_CHARS", defaults.max_source_chars)
        ),
        grounding_batch_size=int(
            os.environ.get("GROUNDING_BATCH_SIZE", defaults.grounding_batch_size)
        ),
        grounding_max_output_tokens=int(
            os.environ.get(
                "GROUNDING_MAX_OUTPUT_TOKENS", defaults.grounding_max_output_tokens
            )
        ),
        grounding_token_budget=int(
            os.environ.get("GROUNDING_TOKEN_BUDGET", defaults.grounding_token_budget)
        ),
        grounding_max_retries=int(
            os.environ.get("GROUNDING_MAX_RETRIES", defaults.grounding_max_retries)
        ),
        otel_sampling_ratio=float(
            os.environ.get("OTEL_SAMPLING_RATIO", defaults.otel_sampling_ratio)
        ),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
