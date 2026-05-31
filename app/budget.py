"""Per-run token budget, enforced via a ContextVar.

A hard backstop against runaway cost on the public grounding endpoint: set the
budget at the start of a request, charge it after each model call, and stop if
it goes negative. ContextVar keeps the budget per-request without threading it
through every call, and isolates concurrent requests from each other.
"""

from __future__ import annotations

from contextvars import ContextVar

# None means "no budget configured" (charging is then a no-op).
_remaining: ContextVar[int | None] = ContextVar(
    "grounding_budget_remaining", default=None
)


class BudgetExceeded(Exception):
    """The per-run token budget was exhausted."""


def set_budget(tokens: int) -> None:
    """Start a run with `tokens` available."""

    _remaining.set(int(tokens))


def remaining() -> int | None:
    """Tokens left in the current run, or None if no budget is set."""

    return _remaining.get()


def charge(tokens: int) -> None:
    """Deduct `tokens` from the run budget; raise BudgetExceeded if it goes negative."""

    left = _remaining.get()
    if left is None:
        return
    left -= int(tokens)
    _remaining.set(left)
    if left < 0:
        raise BudgetExceeded(f"Token budget exceeded by {-left} tokens.")
