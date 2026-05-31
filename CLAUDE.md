# CLAUDE.md, kg-conformance

An HTTP service that checks an already-extracted knowledge graph on two axes: SHACL conformance (deterministic) and source-grounding (LLM). Full design in PLAN.md.

Follows the global CLAUDE.md (user-level) baseline. Only the project map, changelog, and the guardrails that go beyond the baseline are listed here.

## Map

Top-level layout. Phase 1 landed the skeleton; the conformance and grounding internals fill in during Phases 4 and 5.

- app/ : the FastAPI service.
  - main.py : the app, GET /health and the POST /validate stub (dummy report).
  - models.py : Pydantic request and response models (the v0.1 wire contract).
  - config.py : Settings (grounding model name, input bounds, env key lookup).
  - claude_client.py : the single ClaudeClient gateway. Unused seam in Phase 1, wired in Phase 5. The only place the Anthropic SDK is instantiated.
- tests/ : pytest suite. conftest.py (TestClient fixture), test_health.py, test_validate_stub.py.
- Dockerfile, .dockerignore : container build (python:3.12-slim, non-root, uvicorn on 0.0.0.0:8000).
- pyproject.toml, .gitignore : setup.
- PLAN.md : design record and phases.

## Changelog

Newest first.

- 2026-05-31, Phase 2 (operational, no code branch): Azure deployment. The Phase 1 skeleton image went live on Azure Container Apps, provisioned by hand via the Azure CLI. No application code changed, so by the branch-per-phase rule (code phases only) there is no feat/azure-deploy branch and no PR; this entry is the only artifact and lands as a docs commit on main. Live at the FQDN recorded in PLAN.md (Phase 2 deployment). Scale-to-zero verified, /health and /docs reachable. Infrastructure stays up (idle cost near zero); teardown deferred to project end. No tag (v0.1.0 follows Phase 4).
- 2026-05-30, Phase 1 (feat/skeleton): local walking skeleton. FastAPI with GET /health and a POST /validate stub returning a fixed dummy report against the real v0.1 contract. Pydantic models, Settings, ClaudeClient gateway as an unused seam (NotImplementedError). Dockerfile (python:3.12-slim, non-root, uvicorn on 0.0.0.0:8000) and .dockerignore. pytest scaffold (5 tests). Verified: pytest green, docker build and container smoke test (/health and /validate return 200) passing. Merged to main, branch deleted. No tag (v0.1.0 follows Phase 4).
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
