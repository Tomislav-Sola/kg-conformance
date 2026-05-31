"""SHACL conformance validation.

The deterministic layer: parse the data and shapes Turtle into rdflib graphs,
run pyshacl, and translate the SHACL validation report into the wire model
(ConformanceReport). No model call here; that is the grounding layer (Phase 5).

Kept separate from the FastAPI handler so the handler stays thin and this logic
is testable on its own.
"""

from __future__ import annotations

import pyshacl
from rdflib import Graph, Namespace, RDF

from app.models import ConformanceReport

SH = Namespace("http://www.w3.org/ns/shacl#")

# The validation-result fields pulled from the SHACL report, in a stable order
# (also used as the sort key so the violations list is deterministic).
_RESULT_FIELDS: tuple[tuple[str, object], ...] = (
    ("focus_node", SH.focusNode),
    ("path", SH.resultPath),
    ("source_shape", SH.sourceShape),
    ("constraint_component", SH.sourceConstraintComponent),
    ("severity", SH.resultSeverity),
    ("message", SH.resultMessage),
)


class TurtleParseError(ValueError):
    """A Turtle input could not be parsed.

    `which` is "data" or "shapes", so the caller can tell the client exactly
    which input was malformed.
    """

    def __init__(self, which: str, original: Exception) -> None:
        self.which = which
        super().__init__(f"Could not parse {which} as Turtle: {original}")


def _parse_turtle(text: str, which: str) -> Graph:
    graph = Graph()
    try:
        graph.parse(data=text, format="turtle")
    except Exception as exc:  # rdflib raises various parser-specific errors
        raise TurtleParseError(which, exc) from exc
    return graph


def _extract_violations(results_graph: Graph) -> list[dict]:
    """Translate the SHACL results graph into a list of violation dicts."""

    violations: list[dict] = []
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        violation = {}
        for key, predicate in _RESULT_FIELDS:
            value = results_graph.value(result, predicate)
            violation[key] = str(value) if value is not None else None
        violations.append(violation)

    violations.sort(key=lambda v: tuple(v[key] or "" for key, _ in _RESULT_FIELDS))
    return violations


def validate_conformance(data: str, shapes: str) -> ConformanceReport:
    """Validate the data graph against the shapes graph.

    Raises TurtleParseError if either input is not valid Turtle.
    """

    data_graph = _parse_turtle(data, "data")
    shapes_graph = _parse_turtle(shapes, "shapes")

    # inference="none" in v0.1: no RDFS/OWL entailment. A later flag may enable
    # it, but the deterministic baseline validates the asserted triples as-is.
    conforms, results_graph, _ = pyshacl.validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
    )

    return ConformanceReport(
        conforms=bool(conforms),
        violations=_extract_violations(results_graph),
    )
