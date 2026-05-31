# kg-conformance

Conformance and source-grounding checks for LLM-extracted knowledge graphs, served as a small HTTP API.

## What it does

Given a knowledge graph that was already extracted from some text, this service answers two separate questions:

- Conformance: is the graph well-formed against an ontology expressed as SHACL shapes. This runs locally with no model call.
- Source-grounding: can each asserted statement be traced back to the source text, or was it hallucinated. This uses a language model.

The two checks are independent. You can run conformance alone, or both.

## What it is not

It does not extract the graph for you. It consumes triples produced elsewhere (a graph builder, GraphRAG, or your own pipeline) and tells you whether you can trust them. It is also not a general guardrail framework, it is shaped specifically around knowledge-graph conformance and grounding.

## API

POST /validate (keyless, free, deterministic)
- data: Turtle, the extracted triples
- shapes: Turtle, the SHACL shapes

Returns the SHACL conformance report (conforms plus violations).

POST /ground (the LLM check, bring your own key)
- source_text: the text the triples should be grounded in
- data: Turtle, the triples to check
- X-Anthropic-Key header: your Anthropic key (BYOK)

Returns a verdict per triple (supported, unsupported, unclear) with a short justification, a verdict-count summary, and the token cost. Fail-open: on a transient upstream error the grounding section comes back marked unavailable rather than failing the request.

GET /health for a liveness check.

## Demo and keys

Conformance runs for free, since it needs no model. Grounding is bring-your-own-key: pass your Anthropic key in the X-Anthropic-Key header. Your key, your cost. The header key is used only for that request and is never logged or stored. A keyless demo with a few cached grounding examples is planned.

## Quickstart (local)

```
git clone <repo>
cd kg-conformance
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...   # only needed for grounding
uvicorn app.main:app --reload
```

Then POST a Turtle data graph and SHACL shapes to /validate.

## Stack

Python 3.12, FastAPI, rdflib and pyshacl for the deterministic conformance layer, the Anthropic SDK behind a single client gateway for grounding, pydantic, structlog, tenacity. Designed to run containerized on Azure Container Apps.

## Status

In active development, following a phased plan (see PLAN.md). Both layers are implemented and run live on Azure Container Apps, deployed via GitHub Actions: SHACL conformance (/validate, keyless) and source-grounding (/ground, BYOK). Still to come: a keyless cached-example demo and observability. Expect rough edges.

## License

MIT
