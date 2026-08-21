# Production v2 hardening implementation

## Goal

Turn the existing proof-of-concept Apple ID aggregator into a deployable v2 service that polls the two approved Tier-1 sources, publishes only fresh normalized accounts, requires a verified browser session before revealing credentials, and supports client-side instant account rotation without leaking upstream identifiers.

## Background and confirmed facts

- The implementation repository is `/root/data/private_repo/appleid-autoshare`; it currently has a FastAPI proof of concept with an in-memory cache, a five-minute scheduler, permissive CORS, no downstream authorization, no Redis, and no source-B adapter.
- The authoritative product input is `/root/data/private_repo/appleid-aggregator-spec/prd_production_v2.md`.
- Live redacted probes on 2026-08-20 confirmed source A responds with structured JSON and seven candidate records, and source B responds with HTML containing seven username/password clipboard pairs and seven normal-status markers.
- Source URLs and source-specific field names are ingestion-only secrets. They must never appear in public API responses, browser assets, public logs, or public health endpoints.
- A browser-held HMAC secret cannot prove that a client is a legitimate browser; shipped client secrets are extractable. The v2 implementation therefore uses server-side Turnstile verification followed by an HttpOnly session cookie and a one-time Redis-backed reveal ticket. This preserves the anti-replay goal without claiming impossible “unextractable frontend HMAC” security.

## Requirements

### R1 — Dual-source ingestion and normalization

- Poll the approved JSON source at the configured 45-second interval and the approved DOM clipboard source at the configured 90-second interval.
- Enforce TLS verification, bounded timeouts, response-size limits, and no redirect following by default.
- Source A records are eligible only when `status is true`, `message == "正常"`, and `last_check_success == 1`.
- Source B records are eligible only when a syntactically valid email and non-empty paired password are present on a card whose status is exactly normal and whose text has no configured unhealthy marker.
- Normalize into a typed internal account model. Public IDs must be stable keyed HMACs, not raw usernames or source IDs.
- Deduplicate case-insensitively by username, preferring the freshest eligible record.

### R2 — Fresh fail-closed Redis pool

- Redis is the production cache and anti-replay state store.
- Store each source slice independently with `fetched_at` and an absolute `valid_until`; Redis key TTL is storage cleanup, not evidence of freshness.
- A successful source refresh replaces only that source’s slice. A failed refresh must not mark stale data fresh. A refresh of source A must never extend source B's freshness.
- Credential reveal re-evaluates every slice against its own configured `valid_until`, aggregates only fresh slices, and fails closed when Redis is unavailable or no fresh slice remains.
- The default 45/90-second polling targets cannot both prove a universal 60-second maximum age. If the operator requires a hard 60-second SLO, each poll interval must include timeout/jitter margin (normally 30–40 seconds or less) and be permitted by the upstream.
- `/readyz` reports not-ready when Redis is unavailable or the pool is stale/empty. `/healthz` only reports process liveness.

### R3 — Human-verification session and one-time reveal

- `POST /api/v2/session/verify` verifies a Cloudflare Turnstile token server-side and binds the resulting short-lived session to an HttpOnly, Secure-in-production, SameSite=Strict cookie.
- Turnstile test mode is allowed only when explicitly enabled for local/test use; production startup rejects missing production secrets.
- `POST /api/v2/reveal-ticket` requires the verified session and creates a random, single-use, short-lived reveal ticket in Redis.
- `POST /api/v2/accounts/reveal` atomically consumes that ticket, applies IP/session rate limits, and returns the full current batch once. Reuse, expiry, session mismatch, and stale pool all fail closed.
- API errors use generic codes/messages and never include upstream exceptions, URLs, response bodies, usernames, or passwords.

### R4 — Delivery contract and instant rotation UI

- The reveal response contains only normalized public fields: opaque `id`, `username`, `password`, `region`, `status`, `last_synced_at`, and generic `features`; it contains no source name, source-specific status text, source URL, raw upstream key, or raw upstream HTML.
- Accounts are ordered by newest heartbeat and delivered as one batch so the browser can rotate locally with no additional backend request.
- The SPA shows one active account, copy controls, position/freshness, and an explicit “password wrong / verification required / app missing — switch” action.
- Browser code must use text nodes/textContent instead of injecting upstream values through `innerHTML`.
- Static browser assets contain no upstream domains or ingestion credentials.

### R5 — Transport and application hardening

- Default-deny CORS; same-origin works without CORS and optional allowed origins are explicit.
- Add CSP, Referrer-Policy, X-Content-Type-Options, frame-ancestors, Permissions-Policy, no-store, and noindex headers.
- Rate limits are Redis-backed and keyed by trusted client IP plus session. Proxy headers are used only when trusted-proxy mode is explicitly enabled.
- Disable public API docs in production by default.
- Logs are structured enough for operations but contain only public source aliases and exception classes/reason codes, never credential content or upstream locations.
- Headless heuristics and JavaScript obfuscation are optional defense-in-depth only; they are not treated as an authorization boundary or a production-readiness blocker.

### R6 — Deployment and operation

- Provide a non-root multi-stage Docker image with a health check and no source secrets baked into image layers.
- Provide Docker Compose services for the API and a private Redis with persistence disabled for this ephemeral credential cache, resource/health settings, and a host bind configurable via environment variables.
- Provide `.env.example`, source configuration examples, startup validation, and a Chinese operator runbook. Real source URLs are configured at deployment time and are not committed in runtime code or browser assets.
- Do not deploy to a public hostname or change external DNS/Cloudflare settings without the user’s explicit configuration.

## Acceptance Criteria

- [ ] `pytest` passes unit and integration tests for both parsers, strict health filtering, deduplication, stale fail-closed behavior, Turnstile verification, ticket replay rejection, rate limiting, error redaction, security headers, and no upstream metadata in public responses.
- [ ] A live redacted ingestion smoke test obtains non-empty eligible results from both configured sources without printing credentials.
- [ ] Static scans find no approved upstream host/path/key in tracked browser assets, public responses, or runtime logs.
- [ ] `docker compose config` validates and `docker compose build` succeeds.
- [ ] The Compose stack starts on a loopback-only test port; Redis becomes healthy, `/healthz` returns 200, `/readyz` becomes 200 after refresh, and the Turnstile test-mode verify → ticket → reveal flow succeeds.
- [ ] A second reveal with the same ticket is rejected, and the returned pool can be rotated entirely in the browser without another reveal request.
- [ ] Documentation states the residual-risk boundary: after the authorized browser receives the full batch, the operator cannot technically prevent that client from inspecting/copying it; the controls raise scraping cost and bound abuse rather than provide DRM or absolute anti-crawl protection.
- [ ] Stopping Redis or expiring/removing the pool causes readiness/reveal to fail closed rather than serving in-process stale credentials.
- [ ] The final repository diff receives an independent specification review and code-quality/security review with no unresolved critical finding.

## Out of scope

- Automated discovery or promotion of new upstream origins.
- Circumventing Apple 2FA, changing passwords, or independently logging into Apple accounts for credential validation.
- Claims that client-side HMAC, code obfuscation, fingerprinting, or headless detection can “completely block” extraction after plaintext credentials are intentionally delivered to a user-controlled browser.
- Public production rollout, Cloudflare zone changes, domain/DNS creation, or acquisition of production secrets.
