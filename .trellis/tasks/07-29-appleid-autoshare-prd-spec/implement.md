# Implementation Roadmap: Apple ID AutoShare Aggregator Hub

## Task Breakdown for Engineering & PM Handover

### Phase 1: Ingestion Infrastructure (Adapters)
- [x] Create BaseAdapter protocol specification.
- [x] Implement Dabaoid HTML parsing adapter.
- [x] Implement Appstore.autos JSON API adapter.

### Phase 2: Aggregation & Data Cleaning Pipeline
- [x] Construct in-memory deduplication algorithm (`hash(username.lower())`).
- [x] Implement status filter for `status == 'normal'`.
- [x] Setup background Scheduler for 300s polling cycle.

### Phase 3: Distribution & OpenAPI Delivery
- [x] Implement `/api/v1/accounts` API endpoint with region and status filters.
- [x] Implement `/api/v1/stats` endpoint for system health metrics.
- [x] Implement clean single-page HTML/JS Web Dashboard (`/`).

### Phase 4: Quality Assurance & Verification
- [x] Add unit test suite for adapter parsers (`tests/test_adapters.py`).
- [x] Verify Docker & Docker-Compose build configurations.
