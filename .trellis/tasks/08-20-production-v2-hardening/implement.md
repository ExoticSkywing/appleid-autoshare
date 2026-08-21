# Production v2 implementation plan

1. Add focused failing tests for parser strictness, public DTO isolation, Redis freshness, Turnstile/session/ticket flows, rate limits, and headers.
2. Introduce configuration, typed models, generic errors, and logging redaction helpers.
3. Replace hard-coded adapters with injected source configuration; add the approved DOM adapter and strict source-A filtering.
4. Implement Redis store semantics: source slices with independent `valid_until`, request-time fresh-slice aggregation, session creation, atomic ticket consume, and rate limiting.
5. Implement independent pollers; failed refreshes must not extend prior slice freshness.
6. Replace the v1 FastAPI routes with v2 session/ticket/reveal routes, readiness/liveness endpoints, security middleware, and static SPA delivery.
7. Add safe local account rotation UI and explicit Turnstile integration/test mode.
8. Harden Docker/Compose and add environment/runbook documentation.
9. Run unit/integration/security-negative tests, static upstream-leak scan, live redacted ingestion smoke test, image build, and loopback Compose end-to-end verification.
10. Run independent specification and quality/security reviews, address findings, rerun verification, and report only remaining operator configuration.

## Validation commands

```bash
uv run --with-requirements requirements-dev.txt pytest -q
uv run --with-requirements requirements-dev.txt ruff check .
uv run --with-requirements requirements-dev.txt mypy app
python scripts/live_probe.py --redacted
python scripts/check_public_leaks.py
docker compose config
docker compose build
# Start with a generated local env/test mode, then run scripts/e2e_smoke.py
```

## Risk and rollback points

- Never print or fixture live credentials. Live probes report only counts, timestamps, and digests.
- Do not bake real source URLs or secrets into the Docker image.
- Bind test deployment to loopback and an unused port; do not alter existing 1Panel Redis or unrelated containers.
- The existing service is not currently running; no data migration is required.
- Keep each security decision fail-closed when Redis, Turnstile, freshness state, or ticket state is unavailable.
