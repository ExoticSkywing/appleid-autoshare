# Upstream compatibility trust anchors

This directory contains a narrowly scoped supplemental CA bundle for configured upstream fetches.

`isrg-root-ye.pem` is the official self-signed **ISRG Root YE** certificate downloaded from:

- https://letsencrypt.org/certs/gen-y/root-ye.pem

Why it is here: one approved upstream currently serves a certificate chain terminating at Root YE. Let’s Encrypt documents that Root YE is not yet present in major root program trust stores. The adapter still performs normal hostname, expiry, and chain verification; it does **not** disable TLS verification. The runtime combines the platform CA bundle with this pinned official root for upstream requests only.

Review/remove this extra anchor when Root YE is broadly available in the base image trust store or the upstream switches to a broadly trusted alternate chain.
