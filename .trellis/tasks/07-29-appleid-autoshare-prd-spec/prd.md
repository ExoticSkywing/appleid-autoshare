# Product Requirements Document (PRD): Apple ID AutoShare Aggregator Hub

## 1. Executive Summary & Product Vision

`Apple ID AutoShare` is an enterprise-grade, zero-ad, high-availability Apple ID aggregation and distribution platform designed for downstream clients. The system continuously ingests public shared Apple ID accounts from verified, high-quality upstreams, performs automatic deduplication, sanitizes data structures, executes real-time health-status filtering, and exposes a low-latency RESTful API alongside a clean end-user Web dashboard.

---

## 2. Business Objectives & Key Metrics (KPIs)

- **High Availability**: Maintain $\ge 99.9\%$ API uptime and serve cached requests in under $50\text{ms}$.
- **Zero Ad Contamination**: Strip all promotional headers, remark scripts, or redirect tags embedded by secondary upstreams.
- **Account Health Assurance**: Eliminate locked, invalid, or verification-required accounts automatically, ensuring only `status == "normal"` items reach client endpoints.

---

## 3. User Roles & System Interfaces

1. **Client API Consumers (Downstream Systems)**: Request `/api/v1/accounts` for JSON-formatted active Apple IDs filtered by region.
2. **End-User Web Dashboard Visitors**: Access the minimal single-page Web interface (`GET /`) to view and copy credentials manually.
3. **Product Manager (PM) & Engineering Team**: Monitor system metrics via `/api/v1/stats` and receive structured Trellis specification artifacts for implementation handover.

---

## 4. Functional Requirements (FR)

### FR-1: Multi-Source Automated Ingestion
- **FR-1.1**: Support ingestion from `id.qingfeng888.com` (`id.dabaoid.top`) via HTML DOM scraping using `Referer` headers.
- **FR-1.2**: Support ingestion from `www.appstore.autos` (`appstore.autos/shareapi/xxyunAPP`) via RESTful JSON API.
- **FR-1.3**: Modular adapter pattern allowing addition of new upstreams without altering core aggregation logic.

### FR-2: Data Cleaning, Deduplication & Quality Filtering
- **FR-2.1 Deduplication**: Key accounts by `hash(username.lower())` to consolidate redundant entries from multiple mirrors.
- **FR-2.2 Health Filtering**: Exclude any account tagged with "无法获取验证码", "已锁定", or non-normal status.
- **FR-2.3 Automatic Scheduling**: Background Worker polls all upstreams at a default interval of 300 seconds (5 minutes).

### FR-3: RESTful Distribution API
- **FR-3.1 GET `/api/v1/accounts`**:
  - Accepts query parameters: `region` (e.g., `美国`, `台湾`), `status` (default: `normal`).
  - Returns structured JSON payload containing total count, last updated timestamp, upstream stats, and account arrays.
- **FR-3.2 GET `/api/v1/stats`**:
  - Exposes active account counts, total unique accounts, and health metrics per upstream.

### FR-4: Minimalist Web Dashboard
- **FR-4.1 UI Layout**: Clean, Apple-styled single-page UI displaying account cards grouped by region.
- **FR-4.2 Security Disclaimer**: Prominently display a mandatory warning banner against logging into system settings (`iCloud`).

---

## 5. Non-Functional & Security Requirements (NFR)

- **NFR-1 Latency & Performance**: In-memory caching ensures API response time is $< 50\text{ms}$.
- **NFR-2 Rate Limiting & Protection**: Protect API endpoints from DDoS/scraping via IP token-bucket rate limiting.
- **NFR-3 Upstream Resilience**: Upstream failures must be caught gracefully without crashing the core service or clearing valid cached accounts.

---

## 6. Trellis Specification Handover & Acceptance Criteria

- [x] **PRD Artifact (`prd.md`)**: Fully detailed product and functional specification.
- [x] **Design Artifact (`design.md`)**: Comprehensive component architecture and data model specification.
- [x] **Implementation Asset Blueprint (`implement.md`)**: Clear task roadmap for engineering team execution.
