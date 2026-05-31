# CLAUDE.md, kg-conformance

An HTTP service that checks an already-extracted knowledge graph on two axes: SHACL conformance (deterministic) and source-grounding (LLM). Full design in PLAN.md.

Follows the global CLAUDE.md (user-level) baseline. Only the project map, changelog, and the guardrails that go beyond the baseline are listed here.

## Map

Top-level layout. Phase 1 landed the skeleton; the conformance and grounding internals fill in during Phases 4 and 5.

- app/ : the FastAPI service.
  - main.py : the app. GET /health; POST /validate (SHACL, keyless); POST /ground (grounding, BYOK). Thin handlers: input-size and parse guards (413/422), delegate to app.validation and app.grounding.
  - validation.py : SHACL conformance. Parses Turtle into rdflib graphs, runs pyshacl (inference="none"), translates the results graph into ConformanceReport. Deterministic, no model call.
  - grounding.py : grounding orchestration. Renders triples to claims, batches them through the ClaudeClient, enforces the token budget, assembles the report. Defensive mapping, fail-open via GroundingUnavailable.
  - claude_client.py : the single ClaudeClient gateway, now active. One structured (tool-use) Haiku-class call per batch, tenacity retries, BYOK key. The only place the Anthropic SDK is instantiated.
  - budget.py : per-run token budget as a ContextVar (set, charge, BudgetExceeded).
  - models.py : Pydantic request and response models (validate and ground contracts).
  - config.py : Settings (grounding model, max_input_bytes, grounding batch/output-token/budget/retry bounds, env key lookup).
- tests/ : pytest suite. conftest.py (TestClient fixture), test_health.py, test_validate_contract.py, test_conformance.py, test_validation_mapping.py, test_grounding.py (mocked gateway), fixtures/ (Turtle and source-text examples).
- Dockerfile, .dockerignore : container build (python:3.12-slim, non-root, uvicorn on 0.0.0.0:8000).
- .github/workflows/deploy.yml : CI/CD. On push to main, test, build and push the image to ghcr (tagged with the commit SHA), then update the Azure Container App via OIDC.
- pyproject.toml, .gitignore : setup.
- PLAN.md : design record and phases.

## Changelog

Newest first.

- 2026-05-31, Phase 5 (feat/grounding): the grounding axis. New POST /ground checks whether each triple is supported by the supplied source text; /validate stays keyless, free and unchanged. The dormant ClaudeClient seam is now live: one structured tool-use call per batch with a Haiku-class model, tenacity retries on transient errors, verdicts (supported/unsupported/unclear) plus a short justification per triple, defensively parsed and deterministically ordered. BYOK via the X-Anthropic-Key header, read per request, passed only to the gateway, never logged or stored; missing key is 401, a rejected key is 401, transient/infra failure after retries degrades fail-open (200 with grounding unavailable) instead of 500. Per-run token budget enforced via a new ContextVar seam (app/budget.py). Same input guards as /validate (413 oversize, 422 malformed Turtle naming the input). max_source_chars now actually caps the source text sent to the model (was a dormant setting). Response is a grounding report (per-triple verdict + justification, plus verdict-count summary) and token cost. The key is protected by assertion, not just by omission: a test runs a /ground call and asserts the key value never appears in logs, stdout/stderr, or the response (it goes red in Phase 6 if observability ever logs the header). Tests mock the gateway (happy mixed verdicts, batching, source-text cap, fail-open, no-key-leak, 401, 422, 413); no real Anthropic call in CI. pyproject and app at 0.2.0. Tag v0.2.0 after the live endpoint is verified with a real key. Phase 6 note: key scrubbing must become active there, not by omission; the no-leak test keeps that honest.
- 2026-05-31, Phase 4 (feat/shacl-conformance): real SHACL validation. The /validate stub is replaced by deterministic pyshacl validation in app/validation.py: data and shapes are parsed as Turtle into rdflib graphs, pyshacl runs with inference="none" (no RDFS/OWL entailment in v0.1), and the results graph is translated into ConformanceReport violations (focus node, path, source shape, constraint component, severity, message), sorted for determinism. The handler stays thin and adds two guards: a configurable combined input-size cap (max_input_bytes, ~1 MB, 413 on exceed) and 422 on malformed Turtle naming which input failed. ClaudeClient seam still dormant (Phase 5). Fixtures and tests added (conforming/violating cases, 422 data, 422 shapes, 413 oversize), plus mapping tests for SHACL subtleties (node constraints with no path, multiple sorted violations, non-Violation severities); contract tests adapted to real behavior. README refreshed (working name dropped, status reflects live conformance). pyproject and the FastAPI app both at 0.1.0. Tag v0.1.0 after the live endpoint is verified against both fixtures.
- 2026-05-31, Phase 3 (feat/cicd): CI/CD. GitHub Actions workflow (.github/workflows/deploy.yml) that, on push to main (plus manual workflow_dispatch), tests the app (Python 3.12, pip install of the package plus dev extras, pytest), builds and pushes the image to ghcr tagged with the commit SHA, then updates the live Azure Container App (ca-kg-conformance) to that image via OIDC (azure/login@v2, no client secret). The public image needs no registry credentials on the Azure side. pytest gates the deploy. Tag still deferred (v0.1.0 follows Phase 4).
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
