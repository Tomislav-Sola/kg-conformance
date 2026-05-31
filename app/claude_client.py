"""The single gateway for all Claude API calls.

The only place the Anthropic SDK is instantiated. Given a batch of rendered
claims and the source text, it makes one structured (tool-use) grounding call
with a Haiku-class model and returns one verdict per claim plus token usage.

BYOK: the key is the per-request value passed in, never logged and never stored
beyond the lifetime of the client object. Transient failures are retried a
bounded number of times (tenacity); a rejected key and an exhausted-retry
failure are surfaced as two distinct exception types so the caller can tell a
caller error (4xx) from a fail-open degrade.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings

# Transient, worth retrying. AuthenticationError is deliberately excluded: a bad
# key will not fix itself, and the caller must be told.
_TRANSIENT = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)

_TOOL = {
    "name": "record_verdicts",
    "description": "Record exactly one grounding verdict per claim, by index.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "verdict": {
                            "type": "string",
                            "enum": ["supported", "unsupported", "unclear"],
                        },
                        "justification": {"type": "string"},
                    },
                    "required": ["index", "verdict", "justification"],
                },
            }
        },
        "required": ["verdicts"],
    },
}

_SYSTEM = (
    "You are a careful fact-checker. For each numbered claim, decide whether the "
    "SOURCE TEXT supports it: 'supported' if the source entails the claim, "
    "'unsupported' if the source contradicts it or offers no support, 'unclear' "
    "if the source is ambiguous. Give one short justification per claim. Respond "
    "only by calling the record_verdicts tool, with exactly one verdict per claim "
    "index."
)


@dataclass(frozen=True)
class Usage:
    """Token usage for one call."""

    input_tokens: int
    output_tokens: int


class GroundingAuthError(Exception):
    """The Anthropic key was rejected. A caller error, surfaced as 4xx."""


class GroundingUnavailable(Exception):
    """A transient/infra failure that survived retries. Fail-open, degrade."""


class ClaudeClient:
    """Gateway to the grounding model."""

    def __init__(self, settings: Settings, api_key: str | None = None) -> None:
        self._settings = settings
        # Per-request BYOK key wins; the env key is only a fallback for any
        # non-public use. Never logged, never persisted.
        self._api_key = api_key or settings.anthropic_api_key
        self._client: anthropic.Anthropic | None = None

    @property
    def model(self) -> str:
        return self._settings.grounding_model

    def _sdk(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete_grounding(
        self, claims: list[str], source_text: str
    ) -> tuple[list[dict], Usage]:
        """Check one batch of claims against the source text.

        Returns (verdicts, usage). Raises GroundingAuthError on a rejected key,
        GroundingUnavailable on a transient failure that survived retries.
        """

        try:
            message = self._send(claims, source_text)
        except anthropic.AuthenticationError as exc:
            raise GroundingAuthError("Anthropic rejected the provided key.") from exc
        except _TRANSIENT as exc:
            raise GroundingUnavailable(
                f"Grounding call failed after retries: {type(exc).__name__}"
            ) from exc

        usage = Usage(
            input_tokens=getattr(message.usage, "input_tokens", 0),
            output_tokens=getattr(message.usage, "output_tokens", 0),
        )
        return self._extract_verdicts(message), usage

    def _send(self, claims: list[str], source_text: str):
        numbered = "\n".join(f"[{i}] {claim}" for i, claim in enumerate(claims))
        user = f"SOURCE TEXT:\n{source_text}\n\nCLAIMS:\n{numbered}"

        retryer = Retrying(
            stop=stop_after_attempt(self._settings.grounding_max_retries),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(_TRANSIENT),
            reraise=True,
        )
        return retryer(
            lambda: self._sdk().messages.create(
                model=self._settings.grounding_model,
                max_tokens=self._settings.grounding_max_output_tokens,
                system=_SYSTEM,
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "record_verdicts"},
                messages=[{"role": "user", "content": user}],
            )
        )

    @staticmethod
    def _extract_verdicts(message) -> list[dict]:
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "record_verdicts":
                return list(block.input.get("verdicts", []))
        return []
