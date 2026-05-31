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

POST /validate
- data: Turtle, the extracted triples
- shapes: Turtle, the SHACL shapes
- source_text: optional, enables grounding
- options: grounding on or off, and a cap on the number of triples checked

The response contains the SHACL conformance report, the grounding result (supported, unsupported, uncertain), and the token and cost figures for the request.

GET /health for a liveness check.

## Demo and keys

The public demo runs conformance for free, since it needs no model. For grounding there are two paths:

- Bring your own key: pass your own Anthropic key in a request header. Your key, your cost. The header key is never logged or stored.
- Canned examples: a few prepared documents and graphs with cached grounding results, so you can see grounding work without a key.

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

In active development, following a phased plan (see PLAN.md). The SHACL conformance layer is implemented and runs live on Azure Container Apps, deployed via GitHub Actions. The grounding layer (the LLM check) is not built yet; /validate currently returns conformance plus a grounding section marked unavailable. Expect rough edges.

## License

MIT
