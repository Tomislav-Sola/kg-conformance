# CLAUDE.md, kg-conformance

An HTTP service that checks an already-extracted knowledge graph on two axes: SHACL conformance (deterministic) and source-grounding (LLM). Full design in PLAN.md.

Follows the global CLAUDE.md (user-level) baseline. Only the project map, changelog, and the guardrails that go beyond the baseline are listed here.

## Map

Planned top-level layout, filled in as Phase 1 lands the package:

- app/ : the FastAPI service. Conformance layer (rdflib, pyshacl), grounding layer (ClaudeClient), report assembler, request and response models.
- tests/ : pytest suite.
- Dockerfile : container build.
- pyproject.toml, .gitignore : setup.
- PLAN.md : design record and phases.

## Changelog

Newest first.

- Setup: scaffolding created (PLAN.md, this file, README, pyproject, .gitignore). No code yet. Design settled: RDF-native input, deploy-early ordering, BYOK plus canned grounding on the public demo.

## Additional guardrails (beyond the global baseline)

- Input is RDF-native: Turtle for data, SHACL (Turtle) for shapes. JSON-LD is deferred. Do not add a generic JSON triple path without discussion.
- Deploy-early: a trivial container goes live on Azure Container Apps with CI/CD and monitoring before the domain logic is built. Do not reorder to core-first.
- Two layers, do not merge or drift: conformance is deterministic (rdflib plus pyshacl, no model call), grounding sits behind the single ClaudeClient with structured verdicts validated against a Pydantic schema before use. Keep orchestration minimal, no multi-agent setup.
- Grounding: a Haiku-class model, one batched call per request, with max_triples and a source-text length cap. Fail-open: on a failed call, return the conformance report and mark grounding unavailable.
- BYOK: the grounding key may come from an optional per-request header, falling back to the environment key. Never log or store the header key.
- Public demo: SHACL conformance is open and free. Grounding is offered via BYOK and a small set of cached canned examples.
- Azure: Container Apps Consumption plan, image on ghcr.io (not ACR), the key as a Container Apps secret, everything in one resource group so teardown is a single delete.
- Release tags: v0.1.0 after the SHACL layer is live, v0.2.0 after grounding, v0.3.0 after observability. Phases are in PLAN.md.
