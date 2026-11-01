# NEXUS — Codebase Map & Module Reference

This document provides a comprehensive structural guide to the NEXUS codebase, detailing the responsibilities, public interfaces, key dependencies, and inter-module relationships across backend and frontend layers.

---

## 1. Top-Level Directory Structure

```
c:\Coding\Python\NEXUS\
├── ARCHITECTURE.md                  # System architecture, differentiation pillars & API contracts
├── DATABASE_SCHEMA.md               # PostgreSQL/SQLite relational schema (17 tables & indexes)
├── IMPLEMENTATION_PLAN.md           # 24-hour vertical slice roadmap and attack milestones
├── NEXUS_MASTER_PROMPT.md           # Master prompt and non-negotiable security rules
├── README.md                        # Quickstart, local run guide, and verification summary
├── CODE_MAP.md                      # Codebase map and module reference (this file)
├── DATA_FLOW.md                     # End-to-end data flow specifications and sequence diagrams
├── DECISIONS.md                     # Architectural Decision Records (ADRs)
├── FLOW.md                          # State machines and lifecycle workflows
├── docker-compose.yml               # Multi-container orchestration specification
├── backend/                         # FastAPI application, database layer, services, test suite
└── frontend/                        # React 18 + Vite + TypeScript enterprise assurance UI
```

---

## 2. Backend Module Map (`backend/app/`)

### 2.1 Core Infrastructure (`backend/app/core/`)

| File | Primary Classes / Functions | Responsibility |
|---|---|---|
| [`config.py`](file:///c:/Coding/Python/NEXUS/backend/app/core/config.py) | `Settings` | Pydantic-based configuration management loading `.env`, validating CORS origins, JWT secrets, storage directories, and database URLs. |
| [`errors.py`](file:///c:/Coding/Python/NEXUS/backend/app/core/errors.py) | `NexusException`, `TenantAccessDeniedError`, `ResourceNotFoundError`, `ValidationPayloadError`, `create_error_response` | Uniform enterprise JSON error envelopes (`{ "error": { "code", "message", "request_id" } }`). |
| [`security.py`](file:///c:/Coding/Python/NEXUS/backend/app/core/security.py) | `hash_password`, `verify_password`, `create_access_token`, `decode_access_token` | Argon2id password hashing and HMAC-SHA256 JWT token lifecycle management. |
| [`request_context.py`](file:///c:/Coding/Python/NEXUS/backend/app/core/request_context.py) | `RequestIdMiddleware`, `get_current_request_id` | ContextVar-backed request correlation ID tracking for distributed audit and debugging. |

### 2.2 Database & Data Access (`backend/app/db/`)

| File | Primary Symbols | Responsibility |
|---|---|---|
| [`base.py`](file:///c:/Coding/Python/NEXUS/backend/app/db/base.py) | `Base`, `utc_now` | SQLAlchemy 2.0 DeclarativeBase, standard UTC datetime helpers, and naming conventions. |
| [`session.py`](file:///c:/Coding/Python/NEXUS/backend/app/db/session.py) | `engine`, `SessionLocal`, `get_db` | Connection pooling (StaticPool for SQLite test/dev, QueuePool for PostgreSQL), foreign key pragma enforcement, FastAPI dependency injector. |

### 2.3 Domain Models (`backend/app/models/`)

All models inherit from `Base` and define composite foreign keys ensuring multi-tenant referential integrity:

| Model File | Primary Entities | Schema Role |
|---|---|---|
| [`tenant.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/tenant.py) | `Tenant` | Client workspaces / organizations. |
| [`user.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/user.py) | `User` | Global user identities, password hashes, and platform roles (`PLATFORM_ADMIN`, `USER`). |
| [`membership.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/membership.py) | `TenantMembership` | Associates users to tenants with roles (`CLIENT_ADMIN`, `EMPLOYEE`), tracking `last_permission_change_at`. |
| [`document.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/document.py) | `Document` | Logical container for versioned organizational knowledge, authority level, and category. |
| [`document_version.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/document_version.py) | `DocumentVersion` | Immutable version records with partial unique index enforcing at most one `ACTIVE` version per document. Stores `quality_score` and `ocr_needed`. |
| [`processing_job.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/processing_job.py) | `ProcessingJob` | Ingestion pipeline asynchronous execution state, stage progression, and diagnostic quality metrics. |
| [`document_page.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/document_page.py) | `DocumentPage` | Page-level text extraction with SHA-256 hashes and page number provenance. |
| [`document_chunk.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/document_chunk.py) | `DocumentChunk` | Semantic chunks with `allowed_roles`, `classification`, page spans, and vector references. |
| [`document_change.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/document_change.py) | `DocumentChange` | Comparative change reports between candidate and prior active versions. |
| [`document_change_item.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/document_change_item.py) | `DocumentChangeItem` | Granular diff items (`ADDITION`, `REMOVAL`, `MODIFICATION`) with page references and policy classifications. |
| [`document_impact_suggestion.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/document_impact_suggestion.py) | `DocumentImpactSuggestion` | Advisory notices on related active documents potentially impacted by policy changes. |
| [`query_event.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/query_event.py) | `QueryEvent` | Immutable record of user questions, synthesized answers, grounding status, and trace stages. |
| [`query_evidence.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/query_evidence.py) | `QueryEvidence` | Snapshots of exact retrieved chunks shown to LLM with claim-level validation status. |
| [`audit_event.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/audit_event.py) | `AuditEvent` | Tenant-scoped audit log capturing uploads, downloads, approvals, revocations, and logins. |
| [`security_event.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/security_event.py) | `SecurityEvent` | Security anomalies, tenant path tampering alerts, and prompt injection attempts. |
| [`security_test_run.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/security_test_run.py) | `SecurityTestRun` | Execution records for the Red-Team Sentinel adversarial test suite. |
| [`security_test_result.py`](file:///c:/Coding/Python/NEXUS/backend/app/models/security_test_result.py) | `SecurityTestResult` | Granular test case assertions (e.g. `SEC_CROSS_TENANT_DOWNLOAD`, `SEC_PROMPT_INJECTION_DEFENSE`). |

### 2.4 Core Services (`backend/app/services/`)

| Service Directory | Key Modules | Responsibility |
|---|---|---|
| `authorization/` | [`context.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/authorization/context.py) | **Permission Change Guard:** Live query-time PostgreSQL lookup validating active tenant memberships, user status, and role clearance (`CLIENT_ADMIN`, `PLATFORM_ADMIN`). |
| `storage/` | [`local.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/storage/local.py) | Quarantined file streaming, path traversal verification, safe storage key promotion. |
| `ingestion/` | [`extractor.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/ingestion/extractor.py)<br>[`quality_inspector.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/ingestion/quality_inspector.py)<br>[`chunker.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/ingestion/chunker.py)<br>[`pipeline.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/ingestion/pipeline.py) | **Document Quality Inspector:** Page-level text extraction (PyMuPDF, docx, txt), completeness and garbled ratio scoring, OCR necessity detection, role-aware chunking, vector indexing. |
| `embeddings/` | [`local.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/embeddings/local.py) | Sentence-Transformers embedding service with deterministic offline fallback for air-gapped environments. |
| `vector_store/` | [`chroma.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/vector_store/chroma.py) | Tenant-isolated Chroma collections (`nexus_t_<tenant_uuid>`) preventing cross-tenant vector contamination. |
| `retrieval/` | [`guard.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/retrieval/guard.py) | Filters vector candidate chunks against PostgreSQL `ACTIVE` version status and caller role clearances; ranks by policy authority level. |
| `llm/` | [`ollama.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/llm/ollama.py) | Local Ollama LLM integration enforcing structured JSON generation and deterministic grounded synthesis. |
| `evidence/` | [`passport.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/evidence/passport.py) | **Evidence Passport Validator:** Verifies citations against prompt context, computes grounding scores, rejects fabricated citation IDs, issues honest refusals. |
| `change_intelligence/` | [`diff.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/change_intelligence/diff.py) | **Knowledge Change Intelligence:** Deterministic `difflib` clause comparison, page number tracking, SLA/Financial classification, cross-document impact suggestions. |
| `security/` | [`sentinel.py`](file:///c:/Coding/Python/NEXUS/backend/app/services/security/sentinel.py) | **Red-Team Sentinel:** In-process automated penetration testing suite verifying 7 adversarial attack vectors against synthetic tenants. |

### 2.5 REST API Routers (`backend/app/api/v1/`)

| Route File | Prefix | Endpoints & Key Actions |
|---|---|---|
| [`health.py`](file:///c:/Coding/Python/NEXUS/backend/app/api/v1/health.py) | `/` | `GET /healthz` (liveness), `GET /readyz` (readiness checking DB, Chroma, storage). |
| [`auth.py`](file:///c:/Coding/Python/NEXUS/backend/app/api/v1/auth.py) | `/api/v1/auth`, `/api/v1` | `POST /auth/login`, `POST /auth/logout`, `GET /me`. |
| [`tenants.py`](file:///c:/Coding/Python/NEXUS/backend/app/api/v1/tenants.py) | `/api/v1/tenants` | `GET /tenants` (list authorized), `POST /tenants` (provision), `GET /{id}/members`, `POST /{id}/members`, `GET /{id}/audit-events`. |
| [`documents.py`](file:///c:/Coding/Python/NEXUS/backend/app/api/v1/tenants/{tenant_id}/documents) | `/documents` | `POST /` (upload v1), `GET /` (list), `GET /{id}` (details), `POST /{id}/versions` (upload candidate v2), `GET /{id}/versions` (history), `GET /{id}/versions/{v_id}/download`, `GET /{id}/versions/{v_id}/quality-report`, `GET /{id}/changes` (version diff). |
| [`versions.py`](file:///c:/Coding/Python/NEXUS/backend/app/api/v1/tenants/{tenant_id}/versions) | `/versions` | `POST /{version_id}/approve` (atomic human approval transaction with row lock), `POST /{version_id}/reject` (rejection). |
| [`chat.py`](file:///c:/Coding/Python/NEXUS/backend/app/api/v1/tenants/{tenant_id}) | `/chat`, `/queries` | `POST /chat/query` (grounded RAG query), `GET /queries/{id}` (evidence ledger lookup), `GET /queries/{id}/trace` (observable pipeline diagnostics). |
| [`security.py`](file:///c:/Coding/Python/NEXUS/backend/app/api/v1/security) | `/api/v1/security` | `POST /sentinel/run` (trigger automated attack suite), `GET /test-runs` (historical summaries), `GET /test-runs/{id}` (granular results). |

---

## 3. Frontend Module Map (`frontend/src/`)

The frontend is a single-page application built on React 18, Vite, and TypeScript adhering to strict enterprise design tokens.

### 3.1 Type Definitions & API Client

| File | Primary Exports | Purpose |
|---|---|---|
| [`types.ts`](file:///c:/Coding/Python/NEXUS/frontend/src/types.ts) | `TenantInfo`, `UserRole`, `DocumentRecord`, `DocumentVersionRecord`, `QualityReport`, `VersionDiffReport`, `EvidencePassport`, `QueryTrace`, `SecurityTestRunItem` | Shared contract types guaranteeing end-to-end type safety between FastAPI schemas and React UI components. |
| [`api.ts`](file:///c:/Coding/Python/NEXUS/frontend/src/api.ts) | `NexusApiClient`, `api` (singleton) | Typed HTTP client wrapping `fetch` with Bearer token authentication, error unwrapping, and centralized route definitions. |

### 3.2 Visual Components (`frontend/src/components/`)

| Component File | Primary Interface | Visual & Interactive Role |
|---|---|---|
| [`DocumentQualityModal.tsx`](file:///c:/Coding/Python/NEXUS/frontend/src/components/DocumentQualityModal.tsx) | `DocumentQualityModal` | Modal displaying the Document Quality Inspector diagnostics: completeness score, OCR necessity pill, character density, garbled character percentage, and table preservation status. |
| [`DiffViewer.tsx`](file:///c:/Coding/Python/NEXUS/frontend/src/components/DiffViewer.tsx) | `DiffViewer` | Side-by-side / unified clause comparison displaying additions (green), removals (red), and modifications (amber) with page numbers, policy domain classifications (`SLA`, `FINANCIAL`, `GOVERNANCE`), policy impact notices, and the Client Admin Approve/Reject action bar. |
| [`EvidencePassportView.tsx`](file:///c:/Coding/Python/NEXUS/frontend/src/components/EvidencePassportView.tsx) | `EvidencePassportView` | Displays the Evidence Passport: grounding score gauge, factual claims list with numbered citations, and exact cited passage excerpts with page provenance. |
| [`QueryTraceView.tsx`](file:///c:/Coding/Python/NEXUS/frontend/src/components/QueryTraceView.tsx) | `QueryTraceView` | Interactive execution timeline displaying latency in milliseconds and pass/fail diagnostics for the 6 query stages (`AUTH_VERIFY`, `VECTOR_SEARCH`, `PERMISSION_GUARD`, `INTEGRITY_CHECK`, `LLM_INFERENCE`, `EVIDENCE_VALIDATION`). |
| [`SentinelDashboard.tsx`](file:///c:/Coding/Python/NEXUS/frontend/src/components/SentinelDashboard.tsx) | `SentinelDashboard` | Continuous security assurance control center: one-click attack suite trigger, aggregate pass rates, and detailed assertion cards for the 7 adversarial test vectors. |

### 3.3 Application Shell (`frontend/src/App.tsx`)

| File | Key State & Workflows |
|---|---|
| [`App.tsx`](file:///c:/Coding/Python/NEXUS/frontend/src/App.tsx) | Manages simulated identities (Alice Admin, Edward Employee, Bob Admin, Platform Root), active workspace switching, health status monitoring, tab routing (`overview`, `documents`, `changes`, `chat`, `evidence`, `sentinel`), and quick-action query testing. |

---

## 4. Test Suite Map (`backend/tests/`)

The automated test suite contains **35 passing tests** across 6 distinct unit and security test files:

```
backend/tests/
├── conftest.py                             # Pytest fixtures: static-pooled SQLite DB session & TestClient
└── unit/
    ├── test_health.py                      # 3 tests: Liveness, readiness, request correlation IDs
    ├── test_models.py                      # 4 tests: Tenant creation, unique memberships, version constraints, ledger
    ├── test_auth_tenants.py                # 6 tests: Login, role enforcement, tenant boundary, Permission Change Guard
    ├── test_documents.py                   # 5 tests: Document upload, candidate versions, extension whitelist, download denial
    ├── test_ingestion_pipeline.py          # 6 tests: Extraction, Quality Inspector, chunking, Chroma tenant isolation
    ├── test_rag_chat.py                    # 5 tests: Grounded chat, honest refusal, inactive chunk block, query trace, ledger
    ├── test_change_intelligence.py         # 4 tests: Diff computation, employee block, atomic approval transaction, rejection
    └── test_security_sentinel.py           # 2 tests: Direct Sentinel runner execution, REST API test-runs
```

---

## 5. Architectural Invariants

When adding new features or modifying the codebase, adhere strictly to these invariants:

1. **Authoritative PostgreSQL Boundary:** Never rely on ChromaDB or client input for access control. Always pass an explicit `AuthorizedTenantContext` validated on every request.
2. **Immutable Versioning:** Document rows represent logical policies; document versions are immutable. At most one version may have status `ACTIVE` per document.
3. **Quarantine First:** Uploaded documents must always be written to the quarantine area first, validated for SHA-256 and size, before being promoted to tenant storage.
4. **Deterministic Evidence:** Every factual claim presented to the user must be grounded in an exact active chunk ID. If evidence is lacking, return `INSUFFICIENT_EVIDENCE`.

