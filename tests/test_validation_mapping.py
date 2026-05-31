"""Tests for the results-graph to ConformanceReport mapping.

These call validate_conformance directly (no HTTP) to pin the SHACL subtleties
that hide in the translation: node-level constraints carry no path, several
violations come back as a deterministic list, and non-Violation severities
are reported as-is.
"""

from __future__ import annotations

from app.validation import validate_conformance

EX = "http://example.org/"


def test_node_constraint_has_no_path() -> None:
    # sh:class on the node shape itself is a node constraint: the result has
    # no sh:resultPath, so the mapping must leave path as None (not crash).
    shapes = f"""
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <{EX}> .
    ex:PersonNodeShape a sh:NodeShape ;
        sh:targetNode ex:bob ;
        sh:class ex:Person ;
        sh:message "Node must be typed as ex:Person." .
    """
    data = f'@prefix ex: <{EX}> . ex:bob ex:name "Bob" .'

    report = validate_conformance(data, shapes)
    assert report.conforms is False
    assert len(report.violations) == 1
    violation = report.violations[0]
    assert violation["path"] is None
    assert violation["constraint_component"].endswith("ClassConstraintComponent")


def test_multiple_violations_are_listed_and_sorted() -> None:
    shapes = f"""
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <{EX}> .
    ex:PersonNodeShape a sh:NodeShape ;
        sh:targetNode ex:bob, ex:carol ;
        sh:class ex:Person ;
        sh:message "Node must be typed as ex:Person." .
    """
    data = f'@prefix ex: <{EX}> . ex:bob ex:name "Bob" . ex:carol ex:name "Carol" .'

    report = validate_conformance(data, shapes)
    assert report.conforms is False
    assert len(report.violations) == 2
    focus_nodes = [v["focus_node"] for v in report.violations]
    assert focus_nodes == sorted(focus_nodes)
    assert focus_nodes == [f"{EX}bob", f"{EX}carol"]


def test_warning_severity_is_reported() -> None:
    # A sh:Warning still produces a result; severity must pass through verbatim.
    shapes = f"""
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <{EX}> .
    ex:PersonShape a sh:NodeShape ;
        sh:targetClass ex:Person ;
        sh:property [
            sh:path ex:name ;
            sh:minCount 1 ;
            sh:severity sh:Warning ;
            sh:message "Name is recommended." ;
        ] .
    """
    data = f"@prefix ex: <{EX}> . ex:bob a ex:Person ."

    report = validate_conformance(data, shapes)
    assert len(report.violations) == 1
    assert report.violations[0]["severity"].endswith("Warning")
