# Production v2 architecture

## System boundaries

```text
Approved source A ─┐
                   ├─> isolated pollers -> strict parser/normalizer -> Redis source slices
Approved source B ─┘                                           │
                                                               v
Browser -> Turnstile -> verified HttpOnly session -> one-time ticket -> fresh aggregate reveal
                                                               │
                                                               v
                                                   local in-browser rotation
```

The application has three trust boundaries:

1. **Untrusted upstream input**: both external sources may return malformed, hostile, or unexpectedly large content. Adapters own network policy and strict parsing. They return typed internal records or a generic failure reason.
2. **Trusted ephemeral state**: Redis owns source slices, aggregate freshness, verified sessions, reveal tickets, nonces, and rate counters. No in-process fallback is allowed in production because separate workers and replicas must make the same security decision.
3. **Untrusted browser**: once credentials are deliberately revealed, a motivated user can inspect them. Turnstile, tickets, rate limits, and optional heuristics raise extraction cost and prevent blind unauthenticated API reuse; they cannot make plaintext secret delivery non-extractable.

## Modules

- `app/config.py`: environment parsing and production-mode validation.
- `app/models.py`: typed internal/public data contracts.
- `app/adapters/`: base client policy plus JSON and DOM adapters. Source URLs stay here only as injected configuration, never constants.
- `app/services/store.py`: Redis serialization, source-slice replacement, aggregate freshness, session/ticket state, atomic consume, and rate limiting.
- `app/services/aggregator.py`: independent per-source polling loops, deduplication, and aggregate publication.
- `app/services/turnstile.py`: Cloudflare siteverify client with explicit local test mode.
- `app/security.py`: client-IP policy, cookies, response headers, generic errors, and keyed public IDs.
- `app/api.py` / `main.py`: lifespan wiring and public routes.
- `static/`: safe SPA assets using DOM APIs and local rotation.

## Data contracts

### Internal account

```json
{
  "id": "acc_<keyed digest>",
  "username": "full email",
  "password": "secret",
  "region": "US",
  "status": "active",
  "last_synced_at": 1787244000,
  "features": ["shadowrocket_purchased"]
}
```

`source_alias` exists only in the internal source-slice envelope, not the account public DTO. The keyed ID prevents offline reversal of a public deterministic username hash.

### Redis keys

- `<prefix>:source:<alias>` — source slice JSON `{fetched_at, valid_until, accounts[]}`; Redis TTL is slightly longer than `valid_until` for storage cleanup, and reads exclude stale slices.
- `<prefix>:session:<digest>` — verified session metadata, short TTL.
- `<prefix>:ticket:<digest>` — session digest, single-use TTL; consumed with `GETDEL`.
- `<prefix>:rate:<bucket>:<key>:<window>` — fixed-window counters with expiry.

Passwords are necessarily present in the ephemeral source/pool JSON. Redis is private, persistence/AOF are disabled in Compose, access is password-protected, and no Redis port is published.

## Refresh and freshness semantics

- Each adapter owns its own interval; one slow/failing source cannot delay another.
- A successful non-empty adapter result replaces that source slice and sets `valid_until = fetched_at + source_max_age`. Empty or failed fetches do not extend the previous slice.
- Request-time aggregation reads all source slices, excludes every slice whose `valid_until <= now`, and deduplicates only the remaining records. Refreshing one slice never renews another.
- If no fresh slice remains, reveal and readiness fail closed.
- Source A's 45-second and source B's 90-second defaults conflict with a universal 60-second age SLO. We choose fail-closed absence rather than pretending 90-second-old data is fresh. To guarantee a hard 60-second SLO, configure every source interval with timeout/processing/jitter margin (normally 30–40 seconds or less) after confirming upstream permission.
- Upstream health is not assumed permanent. Persistent `poll_failed alias=<alias>` is an operations/configuration incident. At implementation verification time, the approved source B returned a parked/redirect interstitial rather than account markup, so strict parsing produced zero records and B remained excluded; production requires the operator to replace `SOURCE_B_URL` with an active authorized Tier-1 endpoint if dual-source redundancy is mandatory.

## Authorization protocol

1. Browser obtains a Turnstile token using the public site key.
2. `POST /api/v2/session/verify` sends it to the server. The server verifies `success`, optional expected hostname, and action. On success it creates a random session ID and stores only its digest in Redis; the raw value is an HttpOnly cookie.
3. Browser requests `POST /api/v2/reveal-ticket`. Server checks the session and rate limits, then stores a random ticket digest bound to that session.
4. Browser calls `POST /api/v2/accounts/reveal` with the ticket JSON body and CSRF custom header. Server atomically consumes the ticket, rechecks session/rate/freshness, and returns one current batch.

Why not browser HMAC: any `dynamic_secret` usable by JavaScript is readable or reproducible by the browser operator. It adds protocol choreography but no durable authorization. Server-minted one-time state provides actual replay resistance without shipping a signing secret.

## Network and proxy policy

- Direct deployments derive client IP from the socket peer and ignore forwarding headers.
- When `TRUST_PROXY_HEADERS=true`, the operator asserts that the app is reachable only through a trusted reverse proxy which overwrites `CF-Connecting-IP`/`X-Forwarded-For`. The app then uses the configured header; this flag must not be enabled on a directly exposed port.
- The default Compose host bind is loopback. A reverse proxy can join or forward to it explicitly.

## Errors and logging

Public failures use `{ "error": { "code": "...", "message": "..." } }` with generic messages. Adapters log alias, result class, latency, and count only. They never log request URL, response body, parsed username/password, raw exception string, source-specific field names, or redirect location.

## Rollback

The v2 routes are new (`/api/v2/*`); the insecure v1 credential route is removed rather than kept as a bypass. Rollback is image-level: stop the new Compose project and restore the previous image only on a private test network. Do not expose the previous v1 service publicly.
