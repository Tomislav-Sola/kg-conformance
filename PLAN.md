# kg-conformance, design plan

Working name. See README for renaming. This document is the design record. Implementation follows the phases below, one feature branch per phase.

## Decisions (settled)

- Tool: a conformance and source-grounding checker for already-extracted knowledge graphs, served as an HTTP API. Not an extractor, not a general guardrail library.
- Input is RDF-native: Turtle for the data graph and SHACL (Turtle) for the shapes. JSON-LD is deferred.
- Deployment ordering is deploy-early (walking skeleton): a trivial container goes live on Azure Container Apps with CI/CD and monitoring before the domain logic is built, then the logic grows into the running shell.
- Public demo: SHACL conformance is open and free (no model call). Grounding is offered via BYOK (the caller supplies their own Anthropic key per request) and via a small set of cached canned examples for keyless viewing.
- Target platform: Azure Container Apps, Consumption plan. Image on GitHub Container Registry (ghcr.io), not ACR.

## What it is (and is not)

Two orthogonal checks on an extracted knowledge graph:

1. Conformance: is the graph well-formed against an ontology expressed as SHACL shapes. Deterministic, no model call.
2. Source-grounding: can each asserted statement be traced to the source text, or is it hallucinated. This is the AI core.

Deliberately out of scope: extracting the graph (this consumes triples produced elsewhere, it does not compete with GraphRAG or graph builders), a generic guardrail framework, JSON-LD input, provenance-span grounding, async handling of large graphs, auth and multi-tenant.

## Architecture

A small FastAPI service with three layers:

- Conformance layer: rdflib plus pyshacl. Validates the data graph against the shapes graph and returns the standard SHACL validation report.
- Grounding layer (the AI core): behind a single ClaudeClient gateway. Renders each triple to a readable claim and checks the claims against the source text in one batched entailment call. Verdicts come back as structured output, validated against a Pydantic schema before use. Fail-open: if the call fails, the conformance report is still returned and grounding is marked unavailable.
- Report assembler: merges both reports plus cost and token usage into one response.

### Request and response (v0.1)

POST /validate
- data: Turtle, the extracted triples
- shapes: Turtle, the SHACL shapes
- source_text: optional, enables grounding
- options: { grounding: bool, max_triples: int }

Response
- conformance: { conforms: bool, violations: [...] }
- grounding: { checked: int, supported: [...], unsupported: [...], uncertain: [...] }
- cost: { input_tokens, output_tokens, usd_estimate }

Plus GET /health.

### The AI core, in detail

- One batched model call per request, not one per triple.
- A Haiku-class model is sufficient. Entailment is not a hard reasoning task, so cost per request stays low. The exact model string is a config constant set in the ClaudeClient, not hardcoded across the codebase.
- The grounding verdicts are themselves structured model output, validated against a Pydantic schema before use.
- Hard bounds: max_triples and a source-text length cap, plus a per-run budget cap via ContextVar.
- BYOK: the grounding key is read from an optional per-request header and falls back to the environment key. The header key is never logged or stored.

## Tradeoffs

- RDF-native over generic JSON triples: more authentic and distinctive, pyshacl carries the conformance work, at the cost of a narrower caller audience. Accepted.
- Deploy-early over core-first: maximizes operational learning time and de-risks deployment, at the cost of deploying a stub first. Accepted.
- Grounding against the full source text over provenance spans: simpler and needs no provenance from the caller, at the cost of growing with text length, bounded by the caps. Span mode is a later refinement.
- Synchronous request-response with capped inputs over an async job pattern: matches the shape and stays simple. Large graphs are out of scope.
- Scale-to-zero over a minimum replica: cheap, at the cost of a cold start on the first request. A minimum replica can be set temporarily for a demo window.

## Cost and abuse control

- Anthropic Console spend limit as the hard backstop.
- Per-IP rate limit at the application edge.
- max_triples and source-text length caps.
- Content-hash caching so identical inputs are not billed twice.
- Azure side: demo traffic stays within the Container Apps free grant, so the model call is the only real cost exposure.

## Phases

One feature branch per phase, conventional commits, PR with self-merge, annotated tags at milestones.

1. feat/skeleton: setup and a local walking skeleton. .gitignore first, pyproject.toml, CLAUDE.md, FastAPI with /health and a /validate stub, Dockerfile, runs locally in the container. ClaudeClient gateway as an unused seam. pytest scaffold.
2. feat/azure-deploy: push the image to ghcr.io, deploy to Container Apps by hand (resource group, container app, ingress, secret placeholder). Stub live. Verify scale-to-zero. Practice teardown and redeploy. This is the central operations phase, done by hand.
3. feat/cicd: GitHub Actions, build, push, deploy on merge or tag.
4. feat/shacl-conformance: real pyshacl validation, Turtle data plus shapes, example fixtures, tests. Tag v0.1.0.
5. feat/grounding: the AI core. Tests. Tag v0.2.0.
6. feat/observability: OpenTelemetry with the Azure Monitor exporter, custom metrics (latency, cost per request, conformance pass rate, grounding supported rate, token usage), sampling, a small dashboard. Tag v0.3.0.

Optional later: a minimal frontend for a clickable demo link.

## Stack

Python 3.12, FastAPI and uvicorn, rdflib and pyshacl, anthropic via a single ClaudeClient (Haiku-class for grounding), pydantic, structlog, tenacity, OpenTelemetry with the Azure Monitor exporter, Docker. pip with pyproject.toml. Tests with pytest.

## Security and conventions

- ANTHROPIC_API_KEY in the shell environment locally, as a Container Apps secret in Azure, never in repo files.
- .gitignore covers .env, .env.*, .coverage, outputs/, data/, *.db, .venv/ before any matching file exists.
- All Claude calls behind the single ClaudeClient gateway.
- All code artifacts in English. No em-dashes. Honest senior voice, no hype, no performance claims without measurement.
