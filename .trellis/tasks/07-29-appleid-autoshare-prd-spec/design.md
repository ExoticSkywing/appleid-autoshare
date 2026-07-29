# Technical Design Specification: Apple ID AutoShare Aggregator Hub

## 1. System Architecture Diagram

```
[ Upstream: dabaoid (HTML) ] ──────┐
                                   ├──> [ BaseAdapter Protocol ]
[ Upstream: appstore.autos (JSON) ] ┘                 │
                                                      ▼
                                       [ Ingestion & ETL Pipeline ]
                                                      │
                                                      ▼
                                       [ AccountAggregator & Cache ]
                                                      │
                                                      ▼
                                       [ FastAPI OpenAPI Router ]
                                                      │
                                                      ▼
                                       [ Client API / Web Dashboard ]
```

---

## 2. Component Design & Responsibilities

### 2.1 Ingestion Layer (`app/adapters/`)
- `base.py`: Defines abstract `BaseAdapter` with `@abstractmethod fetch_accounts()`.
- `dabaoid.py`: Implements Regex/DOM parser with custom HTTP headers (`Referer: https://id.qingfeng888.com/`).
- `appstore_autos.py`: Implements JSON deserializer for `appstore.autos/shareapi/xxyunAPP`.

### 2.2 Core Service & State Management (`app/services/`)
- `aggregator.py`: Manages in-memory cache, background timer polling, deduplication dictionary, and health-state verification.

### 2.3 Presentation Layer (`main.py` / `app/api/`)
- Exposes OpenAPI-compliant REST routes (`/api/v1/accounts`, `/api/v1/stats`) and embeds responsive Web UI.

---

## 3. Data Dictionary & Schemas

### `Account` Entity Model
| Field | Type | Description |
| :--- | :--- | :--- |
| `username` | String | Apple ID Email (Unique Key for Hash) |
| `password` | String | Account Password |
| `region` | String | Region display (e.g., `美国`, `台湾`) |
| `status` | String | `normal` or `error` |
| `status_text` | String | Raw text status from upstream (e.g., `正常`) |
| `last_check` | String | ISO Timestamp of last upstream verification |
| `source` | String | Identifier of source upstream adapter |
