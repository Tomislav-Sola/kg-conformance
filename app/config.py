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

    # Hard bounds on the grounding call. Enforced in Phase 5.
    max_triples: int = 200
    max_source_chars: int = 50_000

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
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
