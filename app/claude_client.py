"""The single gateway for all Claude API calls.

This is the only place the Anthropic SDK is instantiated (global rule). In
Phase 1 it is an unused seam: nothing calls it yet. The grounding layer in
Phase 5 wires the endpoint to `ground` and this class gains a real batched
entailment call with structured, schema-validated verdicts.

BYOK: the key is resolved per request, the optional header taking precedence
over the environment fallback. The header key is never logged or stored.
"""

from __future__ import annotations

from app.config import Settings


class ClaudeClient:
    """Gateway to the grounding model. Not yet wired into any endpoint."""

    def __init__(self, settings: Settings, api_key: str | None = None) -> None:
        """Hold config and the resolved key.

        `api_key` is the per-request BYOK header value when present; it wins
        over the environment key in `settings`. The actual SDK client is built
        lazily in Phase 5 so importing this module stays cheap and key-free.
        """

        self._settings = settings
        self._api_key = api_key or settings.anthropic_api_key

    @property
    def model(self) -> str:
        """The configured grounding model name."""

        return self._settings.grounding_model

    def ground(self, claims: list[str], source_text: str) -> object:
        """Check claims against the source text in one batched call.

        Returns schema-validated grounding verdicts. Implemented in Phase 5;
        the signature is fixed now so the report assembler can be built
        against it without churn.
        """

        raise NotImplementedError("Grounding lands in Phase 5 (feat/grounding).")
