# Project Specification & Trellis Architecture Plan: Apple ID AutoShare Aggregator

**Document Version:** v1.0  
**Status:** Approved for Implementation  
**Target Repository:** `git@github.com:ExoticSkywing/appleid-autoshare.git`  
**Execution Context:** To be implemented via Codex CLI using Trellis methodology.

---

## 1. Executive Summary & Vision

`Apple ID AutoShare` is an enterprise-grade, high-availability Apple ID aggregation and distribution hub. The system collects public shared Apple ID accounts from verified, high-quality upstreams, performs automatic deduplication, sanitizes data structures, executes real-time health-status filtering, and serves a zero-ad, low-latency OpenAPI endpoint alongside a clean end-user Web dashboard.

---

## 2. Technical Architecture & Component Boundaries

### 2.1 Component Breakdown

1. **Ingestion Layer (`/app/adapters/`)**
   - **`dabaoid_adapter.py`**: Intercepts and parses HTML responses from `id.dabaoid.top` using `Referer` bypass.
   - **`appstore_autos_adapter.py`**: Intercepts JSON payloads from `appstore.autos/shareapi/xxyunAPP`.
   - **Base Adapter Protocol**: Ensures modularity so new upstreams can be added seamlessly via a standardized `BaseAdapter` interface.

2. **ETL & Health Pipeline (`/app/services/`)**
   - **Deduplication**: Hash-based keying on `username.lower()`.
   - **Status Sanitizer**: Filters out accounts tagged as `locked`, `verification_required`, or `error`. Keeps only verified `normal` status items.
   - **Cache Engine**: High-performance in-memory cache with configurable TTL (default 5-minute background refresh).

3. **API & Distribution Layer (`/app/api/`)**
   - **`GET /api/v1/accounts`**: Returns JSON array of valid accounts, filterable by `region` and `status`.
   - **`GET /api/v1/stats`**: System stats, total counts, and upstream SLA breakdown.
   - **`GET /`**: Light, responsive HTML/JS dashboard for end-user manual copying.

4. **DevOps & Infrastructure Asset (`/docker/`)**
   - Containerized deployment specification (`Dockerfile` & `docker-compose.yml`).

---

## 3. Data Schema Specifications

### Account Data Object (JSON Schema)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "username": { "type": "string" },
    "password": { "type": "string" },
    "region": { "type": "string" },
    "status": { "type": "string", "enum": ["normal", "error", "locked"] },
    "status_text": { "type": "string" },
    "last_check": { "type": "string" },
    "source": { "type": "string" }
  },
  "required": ["username", "password", "region", "status", "source"]
}
```

---

## 4. Trellis Task Breakdown & Implementation Roadmap

When Codex CLI is invoked, it must execute the following structured Trellis stages:

### Stage 1: Core Framework Setup & Base Protocol
- Setup project structure under `/root/data/private_repo/appleid-autoshare`.
- Define `BaseAdapter` abstract class in `app/adapters/base.py`.

### Stage 2: Upstream Adapter Integration
- Implement `DabaoidAdapter` and `AppstoreAutosAdapter`.
- Write unit test mocks to verify parser robustness against HTML/JSON drift.

### Stage 3: Aggregation Service & In-Memory Cache
- Implement `AccountAggregator` service in `app/services/aggregator.py`.
- Add background scheduler for polling upstreams every 300 seconds.

### Stage 4: FastAPI Distribution Layer & Web UI
- Implement FastAPI routes in `app/main.py`.
- Embed minimal, modern HTML dashboard.

### Stage 5: Verification & Asset Sealing
- Validate Docker build & test endpoints.
- Commit all code assets to Git.

---

## 5. Codex Prompt for Execution (Trellis Mode)

```bash
codex exec "Please follow the Trellis methodology to implement the Apple ID AutoShare Aggregator project according to the specification at /root/data/private_repo/appleid-autoshare/TRELLIS_SPEC.md. Ensure modular architecture, error handling, and clean asset generation."
```
