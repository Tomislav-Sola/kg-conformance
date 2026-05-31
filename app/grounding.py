"""Grounding orchestration.

Render the triples to readable claims, batch them through the ClaudeClient,
enforce the per-run token budget, and assemble the grounding report. The single
model gateway is the ClaudeClient; this module never touches the SDK directly.

Defensive throughout: a triple the model returns no verdict for, or an
out-of-range or unknown verdict, degrades to 'unclear' rather than failing the
whole request. A transient failure or an exhausted budget raises
GroundingUnavailable, which the handler turns into a fail-open degrade.
"""

from __future__ import annotations

from collections import Counter

from app.budget import BudgetExceeded, charge, remaining, set_budget
from app.claude_client import ClaudeClient, GroundingUnavailable
from app.config import Settings
from app.models import (
    CostReport,
    GroundingResult,
    GroundingSummary,
    TripleVerdict,
    Verdict,
)
from app.validation import _parse_turtle

_VALID = {v.value for v in Verdict}


def _render(triple) -> str:
    subject, predicate, obj = triple
    return f"{subject} {predicate} {obj}"


def _assemble(triple, raw: dict | None) -> TripleVerdict:
    text = _render(triple)
    if raw is None:
        return TripleVerdict(
            triple=text,
            verdict=Verdict.unclear,
            justification="No verdict returned for this triple.",
        )
    verdict = raw.get("verdict")
    if verdict not in _VALID:
        verdict = Verdict.unclear.value
    return TripleVerdict(
        triple=text,
        verdict=Verdict(verdict),
        justification=str(raw.get("justification") or ""),
    )


def _summarize(verdicts: list[TripleVerdict]) -> GroundingSummary:
    counts = Counter(v.verdict for v in verdicts)
    return GroundingSummary(
        checked=len(verdicts),
        supported=counts[Verdict.supported],
        unsupported=counts[Verdict.unsupported],
        unclear=counts[Verdict.unclear],
    )


def ground_triples(
    data: str, source_text: str, api_key: str, settings: Settings
) -> tuple[GroundingResult, CostReport]:
    """Ground the triples in `data` against `source_text`.

    Raises TurtleParseError (from parsing) and GroundingAuthError /
    GroundingUnavailable (from the gateway / budget) for the handler to map.
    """

    graph = _parse_turtle(data, "data")
    triples = sorted(graph, key=lambda t: (str(t[0]), str(t[1]), str(t[2])))
    triples = triples[: settings.max_triples]
    if not triples:
        return GroundingResult(), CostReport()

    # Cap the source text sent to the model. This is the field that grows the
    # prompt (and the cost), so bound it independently of the byte-size guard.
    source_text = source_text[: settings.max_source_chars]
    claims = [_render(t) for t in triples]
    client = ClaudeClient(settings, api_key=api_key)
    set_budget(settings.grounding_token_budget)

    raw_by_index: dict[int, dict] = {}
    input_tokens = output_tokens = 0
    batch_size = settings.grounding_batch_size

    try:
        for start in range(0, len(claims), batch_size):
            if (left := remaining()) is not None and left <= 0:
                raise GroundingUnavailable("Per-run token budget exhausted.")
            chunk = claims[start : start + batch_size]
            verdicts, usage = client.complete_grounding(chunk, source_text)
            charge(usage.input_tokens + usage.output_tokens)
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
            for verdict in verdicts:
                index = verdict.get("index")
                if isinstance(index, int) and 0 <= index < len(chunk):
                    raw_by_index[start + index] = verdict
    except BudgetExceeded as exc:
        raise GroundingUnavailable("Per-run token budget exhausted.") from exc

    verdicts_out = [_assemble(triples[i], raw_by_index.get(i)) for i in range(len(triples))]
    result = GroundingResult(summary=_summarize(verdicts_out), verdicts=verdicts_out)
    cost = CostReport(input_tokens=input_tokens, output_tokens=output_tokens)
    return result, cost
