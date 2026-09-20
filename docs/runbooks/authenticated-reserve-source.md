# Authenticated reserve source operations

This optional Tier-1.5 source is isolated from the two primary pollers. It is disabled by default. Its endpoint and complete Cookie header are deployment secrets and must never be committed, passed as CLI arguments, pasted into tickets, or logged.

## Enable and configure

1. Confirm authorization to poll the service.
2. Inject `SOURCE_C_URL` and `SOURCE_C_COOKIE` through the deployment secret manager.
3. Set `SOURCE_C_ENABLED=true`. Keep the bounded defaults unless traffic authorization permits otherwise: 300-second poll, three samples, 250–750 ms inter-sample jitter, 600-second local freshness, 900-second upstream maximum age, and 1200-second diagnostic TTL.
4. Set `SOURCE_C_TIMEZONE` to the page's documented IANA timezone.
5. Roll workers and inspect only fixed reason codes and counters. Never inspect raw response bodies in shared logs.

Startup fails if the enabled source lacks an HTTPS endpoint without URL credentials or lacks the opaque Cookie. Disabled deployments do not require either secret.

## Credential rotation

1. In an authorized browser, sign in again and copy the complete Cookie header from an authorized request. Do not split it into sub-fields.
2. Store the new value as a new secret version; do not use shell history or command-line flags.
3. Roll workers so they consume the new secret.
4. Run the probe with the project virtual environment so pinned dependencies are used:

```bash
.venv/bin/python scripts/live_probe.py
```

The output is limited to classification, account count, and maximum source age.
5. Confirm a successful poll and a fresh independent reserve slice.
6. Revoke the old browser session and old secret version.

Repeated `auth_expired` reaches the configured alert threshold and means rotate credentials. `challenge_returned` means the authorized server-side session is not presently usable; do not automate challenge bypass. `markup_drift` means review the parser/fixture contract rather than rotating credentials.

## Degradation and rollback

A failed or empty poll never replaces or renews the previous slice. Once local freshness or upstream maximum age is exceeded, reserve records are excluded. Primary sources continue independently.

Emergency rollback: set `SOURCE_C_ENABLED=false` and roll workers. No data migration or primary-source cleanup is needed; the diagnostic reserve slice expires naturally.

## Authenticated JSON reserve (Source D)

Source D is a separate, disabled-by-default JSON slice. Inject `SOURCE_D_URL`,
`SOURCE_D_COOKIE`, and `SOURCE_D_REFERER` only through the secret manager, then
set `SOURCE_D_ENABLED=true`. The URL and Referer must be HTTPS and contain no URL
credentials. Configure its independent poll, freshness, and diagnostic TTL with
`SOURCE_D_POLL_SECONDS`, `SOURCE_D_FRESHNESS_SECONDS`, and
`SOURCE_D_SLICE_TTL_SECONDS`.

The adapter accepts only HTTP 200 with an `application/json` media type, an
integer `ret` equal to 1, a valid email, a non-empty password, and a reasonable
future Unix-seconds `expire_time`. HTTP 401/403 and `ret != 1` classify as
`auth_expired`; malformed JSON/schema/media types classify as `schema_drift`;
other HTTP and transport failures classify as `network_failed`. No raw response,
URL, Referer, Cookie, username, password, or exception is logged.

Its slice expires at the earlier of fetch time plus Source D freshness and the
authoritative `expire_time`. Failed or empty polls do not replace or extend any
slice. Primary and Source C slices are unaffected. `source_d_only` and the
compatibility alias `ikuuu_only` are server-side diagnostic delivery modes and
never fall back to another source. Do not expose those names to browser assets or
public API DTOs.

Run the redacted probe with `SOURCE_PROBE=D`; output is restricted to a fixed
classification and account count. Rotate the Cookie on `auth_expired`; rollback
by setting `SOURCE_D_ENABLED=false` and rolling workers.

## Encrypted HTML source (Q)

Source Q is a separate Tier-1 slice with internal alias `qingfeng`. It is
disabled by default. Inject `SOURCE_QINGFENG_URL` and the exact
`SOURCE_QINGFENG_REFERER` through the deployment secret manager; the two HTTPS
origins may intentionally differ. Both values reject URL credentials. Do not
paste either value into tickets, logs, CLI arguments, or fixtures.

The adapter sends a fixed generic browser header set, disables redirects and
environment proxy inheritance, verifies TLS, and enforces the common timeout
and response-size limits. It never executes upstream JavaScript. It accepts a
direct `CryptoJS.SHA256` 32-hex seed or safely decodes a bounded Dean Edwards
packer payload, then performs strict Base64, AES-256-CBC, PKCS7, and UTF-8
decoding. Only healthy cards that also claim the purchased target application
are admitted; account and ciphertext pairing never crosses card boundaries.

Enable with `SOURCE_QINGFENG_ENABLED=true`. The independent poll, freshness,
and diagnostic TTL are controlled by `SOURCE_QINGFENG_POLL_SECONDS`,
`SOURCE_QINGFENG_FRESHNESS_SECONDS`, and `SOURCE_QINGFENG_SLICE_TTL_SECONDS`.
An HTTP 403 or anti-hotlink denial is `referer_rejected`; challenge or
non-HTML responses are `challenge_returned` or `markup_drift`; missing,
ambiguous, or unsafe packed seeds are `seed_missing`, `seed_ambiguous`, or
`unsafe_packer`; a page where every otherwise-valid card fails cryptographic
validation is `decrypt_failed`. A failed or empty poll does not replace or renew
the previous slice and does not affect A/B/C/D.

For an authorized live check, run:

```bash
SOURCE_PROBE=Q .venv/bin/python scripts/live_probe.py
```

Output is limited to `classification` and `account_count`; it never includes an
account hash or any credential. The server-side modes `qingfeng_only` and
`source_qingfeng_only` select only this slice and never fall back. `all` includes
it only when enabled. Roll back by setting `SOURCE_QINGFENG_ENABLED=false` and
rolling workers; the old diagnostic slice expires naturally.

## Safe diagnostics

Allowed: internal alias, fixed reason code, duration, candidate counts, conflict count, consecutive failures, last success timestamp, and source-time age.

Forbidden: endpoint, path, Cookie or Cookie sub-fields, redirect location, HTML, raw exceptions, usernames, passwords, and supplier metadata. Do not add these fields to public API DTOs or frontend assets.
