# NEXUS — 24-Hour Implementation Plan

**Objective:** Deliver a deployment-oriented MVP that demonstrates secure multi-client knowledge retrieval and the primary USP, Knowledge Change Intelligence.  
**Team model:** DEFENCE builds the product; ATTACK independently tests it throughout development.  
**Timebox:** 24 hours. Adjust individual names based on actual team size; do not assume a fixed team count.

---

## 1. What must be true at the end of 24 hours

A judge should be able to see a complete, reproducible flow:

1. Platform admin creates three synthetic client workspaces and assigns users.
2. Client admin uploads an SOP/PDF into the correct tenant.
3. The file is validated, processed and indexed locally.
4. An employee asks a question and receives an evidence-grounded answer with document/version/page citations.
5. An unsupported question produces an honest refusal.
6. A new version of the same logical document is uploaded.
7. NEXUS shows a version comparison highlighting the changed clause.
8. Client admin reviews and approves the candidate; only then does it become active.
9. The same question now returns the new active rule.
10. A manager can inspect the older query and its original evidence/version.
11. ATTACK attempts cross-tenant access and the backend denies it; the event/test result is recorded.
12. The application continues to work in an outbound-network-blocked demonstration environment.

**Do not claim production readiness.** Demonstrate a working secure core and document the remaining performance, availability, backup, compliance and independent security-review work.

## 2. Priority definitions & Strategic Differentiation

NEXUS differentiates itself from standard enterprise platforms (Azure AI Search, AWS Bedrock, Glean) by solving the 6 persistent operational and security vulnerabilities of enterprise knowledge management:

### Strategic Differentiation Build Priorities:
1. **Evidence Passport (Priority 1 — Core Trust):** Every factual claim is bound to an exact source passage, version, and page number with server-side claim-grounding verification. Refusal occurs automatically when evidence is unverified or insufficient.
2. **Permission Change Guard (Priority 2 — Security-Critical):** Real-time query-time re-validation of user permissions against PostgreSQL; chunks carry `allowed_roles` and `classification`. Prevents stale index ACL leakage.
3. **Knowledge Integrity Engine (Priority 3 — Enterprise Knowledge):** Policy authority hierarchy (`OFFICIAL_POLICY` > `STANDARD_PROCEDURE` > `GUIDELINE` > `INFORMAL_NOTE`), supersession tracking, and active document contradiction detection with explicit user warnings.
4. **Red-Team Sentinel (Priority 4 — Assurance):** Automated continuous adversarial testing (tenant ID tampering, prompt injection, stale-version retrieval, citation manipulation) with reproducible regression runs.
5. **Document Quality Inspector (Priority 5 — Data Reliability):** Pre-indexing diagnostics reporting text extraction completeness, table structure preservation, and OCR requirement detection (`ocr_needed`).
6. **Query Trace (Priority 6 — Observability):** Granular stage-by-stage execution timeline and latency instrumentation (`Auth` → `Tenant Resolve` → `Chroma Search` → `Postgres Guard` → `Inference` → `Passport Validation`).

- **P0 — Must work:** Permission Change Guard, Evidence Passport, Knowledge Integrity Engine, Document Quality Inspector, Red-Team Sentinel, Query Trace, document upload/processing, version diff & atomic approval, local/offline execution.
- **P1 — Should work if time permits:** Advanced semantic impact graph, multi-document keyword clustering, enhanced table visualization.
- **P2 — Roadmap only:** Full enterprise OCR engine (Tesseract/Surya local daemon), multi-node HA, third-party compliance audits.

Protect P0. Do not spend P0 time on animations or decorative abstractions.

## 3. Workstream ownership

### 3.1 DEFENCE workstreams

| Workstream | Responsibilities | Deliverables |
|---|---|---|
| D1 — Identity and API security | Login/session, password hashing, role checks, tenant membership dependency, strict API validation | Authenticated tenant-scoped API skeleton and security tests |
| D2 — Data and document lifecycle | PostgreSQL models/migrations, local storage adapter, upload validation, processing jobs, version states | Tenant-safe document upload and lifecycle endpoints |
| D3 — RAG and Evidence Ledger | Page-aware extraction integration, chunking, embeddings, Chroma adapter, Ollama, citation validation, query logging | Grounded chat with evidence records and refusal |
| D4 — Knowledge Change Intelligence and UI integration | Version diff, change items, review/approval, dashboard/chat/document UI, integration | Admin change report and version activation demo |

Assign people based on skills. If the team is small, combine D2+D4 or D1+D2, but keep one owner accountable for tenant authorization and one owner for end-to-end integration.

### 3.2 ATTACK workstreams

| Workstream | Responsibilities | Deliverables |
|---|---|---|
| A1 — Tenant/API attacks | Tamper tenant context, role escalation, guessed IDs, file download, query history and audit access | Reproducible API security tests and vulnerability tickets |
| A2 — AI/document/version attacks | Direct/indirect prompt injection, malicious PDF text, stale-version retrieval, malformed upload and citation manipulation | Reproducible attack corpus and regression cases |
| A3 — Retest and assurance reporting | Retest fixes, maintain run results, record severity and evidence | Security test report and demo-ready results |

ATTACK must not wait until the application is finished. Test each API as soon as a working endpoint is available. Use synthetic documents and a staging environment only.

## 4. Shared integration contract (agree in first 2 hours)

Before parallel coding, agree on:

- Repository layout and branch/merge policy.
- UUID format and tenant membership model.
- Role names: `PLATFORM_ADMIN`, `CLIENT_ADMIN`, `EMPLOYEE` (platform role and tenant role are distinct).
- API response/error envelope.
- Document/version status names.
- Chunk metadata fields and vector ID format.
- File storage interface.
- Retrieval interface.
- Environment variable names.
- Health-check endpoints.
- One shared synthetic dataset with known answers and known document version changes.

Suggested error envelope:

```json
{
  "error": {
    "code": "TENANT_ACCESS_DENIED",
    "message": "You are not authorised to access this resource.",
    "request_id": "req-uuid"
  }
}
```

Do not reveal whether another tenant's resource ID exists. Use a consistent not-found/forbidden policy that does not create an enumeration oracle.

## 5. Suggested repository layout

```text
nexus/
  frontend/
    src/
      app/
      components/
      features/
        auth/
        tenants/
        documents/
        change-intelligence/
        chat/
        evidence/
        security/
      lib/
  backend/
    app/
      api/v1/
      core/                 # config, auth, errors, request IDs
      db/                   # engine, session, migrations
      models/
      schemas/
      repositories/
      services/
        authorization/
        storage/
        ingestion/
        embeddings/
        vector_store/
        retrieval/
        change_intelligence/
        evidence/
        security/
      workers/
    tests/
      unit/
      integration/
      security/
  data/                     # local mounted persistent data; gitignored
  models/                   # local model cache or documented volume; gitignored
  docker-compose.yml
  .env.example
  ARCHITECTURE.md
  DATABASE_SCHEMA.md
  IMPLEMENTATION_PLAN.md
  NEXUS_MASTER_PROMPT.md
  README.md
```

Keep secrets, uploaded documents, model weights, database files, Chroma data and local logs out of Git. Commit `.env.example`, not `.env`.

## 6. API contract for MVP

All `/tenants/{tenant_id}/...` routes must use a shared dependency that authenticates the principal, checks the tenant is active, checks the user's membership and role, and supplies an immutable `AuthorizedTenantContext` to the service layer.

| Method | Endpoint | Role | Acceptance condition |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Public | Valid credentials return a session/token; invalid credentials are generic and throttled |
| POST | `/api/v1/auth/logout` | Authenticated | Session is invalidated/expired |
| GET | `/api/v1/me` | Authenticated | Returns user and authorised memberships, not arbitrary tenants |
| GET | `/api/v1/tenants` | Authenticated | Returns only active memberships |
| POST | `/api/v1/tenants` | Platform admin | Creates tenant and audit event |
| POST | `/api/v1/tenants/{tenant_id}/members` | Client admin | Adds member only to own tenant |
| POST | `/api/v1/tenants/{tenant_id}/documents` | Client admin | Stores quarantined upload, creates version and processing job |
| GET | `/api/v1/tenants/{tenant_id}/documents` | Tenant member | Lists only documents in authorised tenant |
| GET | `/api/v1/tenants/{tenant_id}/documents/{document_id}/versions` | Tenant member | Returns authorised version history |
| POST | `/api/v1/tenants/{tenant_id}/documents/{document_id}/versions` | Client admin | Creates a candidate version for the same logical document |
| GET | `/api/v1/tenants/{tenant_id}/documents/{document_id}/changes` | Client admin | Returns change report with old/new page references |
| POST | `/api/v1/tenants/{tenant_id}/versions/{version_id}/approve` | Client admin | Atomically activates candidate only after successful processing/indexing |
| POST | `/api/v1/tenants/{tenant_id}/versions/{version_id}/reject` | Client admin | Rejects candidate; previous active version remains active |
| POST | `/api/v1/tenants/{tenant_id}/chat/query` | Tenant member | Returns answer/refusal with server-validated citations and query ID |
| GET | `/api/v1/tenants/{tenant_id}/queries/{query_id}` | Authorised member/admin | Shows evidence history only if permitted by policy |
| GET | `/api/v1/tenants/{tenant_id}/audit-events` | Client admin | Tenant-scoped audit history |
| GET | `/api/v1/security/test-runs` | Platform/security admin | Shows completed test run summaries; not raw secrets/payloads |

Request tenant IDs are selectors only. The backend must verify membership and derive the authoritative context. Do not accept collection names or storage paths from the client.

## 7. 24-hour schedule and gates

### Hours 0–2 — Contracts and skeleton

**DEFENCE**
- Agree repository layout, schemas, role names, API contracts and environment variables.
- Start FastAPI, React, PostgreSQL and Docker Compose health checks.
- Create Alembic baseline migration and seed three synthetic tenants/users.
- Implement shared authentication/tenant authorization dependency skeleton.

**ATTACK**
- Draw threat model and data-flow boundaries.
- Prepare attack checklist and synthetic tenant A/B data.
- Define expected deny behaviour for every tenant-scoped route.

**Gate:** All developers can run the same app locally; API contract and test data are shared.

### Hours 2–6 — Identity, tenant boundary and upload

**DEFENCE**
- Implement password hashing, login and user memberships.
- Implement roles and tenant context dependency.
- Create document/version models and tenant-safe repositories.
- Implement upload allowlist, size limits, quarantine and private local storage.

**ATTACK**
- Tamper tenant IDs and route parameters.
- Attempt to list/read/download another tenant's documents.
- Try role escalation and unauthorized membership creation.

**Gate:** Cross-tenant access tests for users, documents and files pass before substantial RAG work proceeds.

### Hours 6–10 — Processing and indexing

**DEFENCE**
- Implement local PDF/DOCX/TXT extraction.
- Preserve page numbers and section headings where possible.
- Chunk and hash content.
- Generate embeddings locally.
- Create per-tenant Chroma collection mapping.
- Persist chunks in PostgreSQL and vectors in Chroma.
- Record processing status/failures.

**ATTACK**
- Test invalid MIME/extension, oversized files, malformed documents, path traversal filenames and hidden instructions.
- Verify failed processing does not activate a candidate.

**Gate:** Documents from A and B are indexed independently; a failed upload is clearly surfaced.

### Hours 10–14 — Secure RAG and Evidence Ledger

**DEFENCE**
- Implement tenant-scoped retrieval.
- Validate every Chroma candidate against PostgreSQL tenant and active-version state.
- Integrate Ollama and the local embedding model.
- Implement structured answer/refusal output and server-side citation resolution.
- Persist query event and exact evidence snapshot.

**ATTACK**
- Test direct and indirect prompt injection.
- Attempt cross-tenant retrieval and stale-version retrieval.
- Attempt invented citation IDs and query-history access by another tenant.

**Gate:** Employee A can answer from A; A cannot retrieve B; unsupported question refuses; every answer has valid source metadata.

### Hours 14–18 — Knowledge Change Intelligence

**DEFENCE**
- Upload v2 for the same logical document.
- Compare page/section text with deterministic diff.
- Persist additions/removals/modifications with old/new page references.
- Show admin change report.
- Implement approve/reject endpoint with transaction and partial unique active-version index.
- Rebuild/update index safely; PostgreSQL active state remains authoritative.

**ATTACK**
- Attempt retrieval of candidate, rejected and superseded versions.
- Attempt unauthorized approval/rejection and cross-tenant change report access.
- Attempt concurrent approval or wrong-document version association.

**Gate:** Before approval, v1 still answers. After approval, v2 answers. Historical query evidence still points to v1.

### Hours 18–21 — UI integration and security regression

**DEFENCE**
- Complete navigation and essential screens: dashboard, documents, change report, chat, evidence history.
- Add clear processing/review/failed states.
- Ensure no document storage path or Chroma detail is sent to the browser.

**ATTACK**
- Run full attack suite against staging.
- Reproduce and retest each fixed vulnerability.
- Convert every discovered bug into an automated regression case.

**Gate:** Demo path can be performed without developer tools or database shell.

### Hours 21–24 — Offline run, demo and handoff

**DEFENCE**
- Freeze feature development.
- Run migrations from clean DB.
- Provision model files and dependencies before blocking network access.
- Verify Docker volumes persist after container restart.
- Run full end-to-end flow with outbound access blocked.
- Prepare setup guide and architecture explanation.

**ATTACK**
- Run final tenant isolation suite and record exact test count/results.
- Verify no cross-tenant evidence in responses or audit APIs.
- Produce a short report: attack, expected, actual, evidence, fix and retest.

**Gate:** A fresh local deployment and the full demo are reproducible. Do not report tests as passed unless actually run.

## 8. Acceptance criteria

### Identity and tenant isolation

- [ ] Unauthenticated requests to protected APIs are rejected.
- [ ] Employee cannot use a tenant without active membership.
- [ ] Changing a tenant ID in a request does not grant access.
- [ ] Document UUID guessing does not expose another tenant's resource.
- [ ] Only client admins can add members or publish document versions.
- [ ] Every tenant-scoped read/write checks tenant context.

### Document lifecycle

- [ ] Allowed file uploads are stored under generated tenant-scoped keys.
- [ ] Invalid/oversized/malformed uploads are rejected with a safe error.
- [ ] Extraction preserves page references for supported documents.
- [ ] Failed ingestion does not become active.
- [ ] A candidate version does not replace the active version before approval.
- [ ] Only one version is active per logical document.
- [ ] Superseded source files remain available for authorised history/audit.

### RAG and Evidence Ledger

- [ ] The query pipeline searches only the server-selected tenant collection.
- [ ] Chroma candidates are revalidated in PostgreSQL against tenant and active status.
- [ ] The LLM receives only validated active evidence.
- [ ] An unsupported question returns a refusal.
- [ ] Conflicting sources are surfaced rather than silently resolved.
- [ ] Returned citations are built from database metadata and point to the exact version/page.
- [ ] Model-generated unknown evidence IDs are rejected.
- [ ] Query history includes the exact evidence snapshot/reference.

### Knowledge Change Intelligence

- [ ] v1/v2 comparison shows added, removed and modified passages.
- [ ] Old/new page references appear in the change report.
- [ ] The report is tenant-scoped and admin-only if configured.
- [ ] LLM summaries are advisory and linked to deterministic diffs.
- [ ] Approve is denied to employees.
- [ ] Reject leaves the old active version untouched.
- [ ] Approval is atomic and produces an audit event.
- [ ] After approval, ordinary retrieval excludes the superseded version.

### Attack vs Defence

- [ ] Attack suite contains tenant-ID tampering, direct ID access, file access, prompt injection, malicious PDF, stale-version and audit isolation tests.
- [ ] Results are recorded with actual status and reproducible evidence.
- [ ] Fixed vulnerabilities have regression tests.
- [ ] No claim of zero vulnerabilities beyond the scope of the executed test suite.

### Deployment

- [ ] Docker Compose starts all required services.
- [ ] PostgreSQL, Chroma, document and model data use persistent volumes.
- [ ] App starts without runtime cloud dependencies.
- [ ] Offline test is performed with outbound network access actually blocked.
- [ ] Container restarts do not delete documents or DB records.
- [ ] A backup/restore test is attempted or explicitly listed as not completed.

## 9. Suggested benchmark dataset

Create synthetic, non-confidential documents for three clients. Example data:

- Tenant A: Complaint SOP v1 with 48-hour resolution; v2 changes it to 24 hours.
- Tenant B: Finance SOP with a different approval threshold and payment schedule.
- Tenant C: Administration policy with onboarding steps and escalation contacts.

Create 50–100 questions if time permits, split into:

- In-scope answerable questions.
- Unsupported questions.
- Contradiction questions.
- Superseded-version questions.
- Cross-tenant questions.
- Prompt-injection questions.

Metrics:

- Answer correctness against expected answer.
- Evidence/citation correctness.
- Refusal precision/recall for unsupported questions.
- Stale-version retrieval count.
- Successful cross-tenant retrieval count.
- Median and p95 latency (only if enough samples are available).

Do not report accuracy percentages from a tiny or handpicked sample without stating the sample size and method.

## 10. Demo script (4–5 minutes)

1. Admin dashboard: show three synthetic tenants and memberships.
2. Upload Client A SOP v1; show processing/index status.
3. Employee A asks the SLA question; NEXUS returns 48 hours with document/version/page citation.
4. Ask something missing from the SOP; NEXUS refuses.
5. Upload v2; show the change report: 48 hours → 24 hours, with old/new page references.
6. Approve v2 as Client A admin.
7. Repeat the question; NEXUS returns 24 hours with v2 citation.
8. Open the earlier query in Evidence Ledger; show the original v1 evidence snapshot.
9. ATTACK runs a cross-tenant access attempt; show denial and the test/audit record.
10. Explain the offline validation and production-hardening backlog.

Keep the demo data synthetic. Avoid entering real client documents into a hackathon environment without written permission.

## 11. Feature cut order if time is slipping

Cut in this order:

1. Advanced semantic impact analysis (keep deterministic version diff).
2. Beautiful charts/analytics (keep clear status tables).
3. Multi-document relationship visualisation (keep simple related-item suggestions).
4. Rich chat history search (keep query ID and evidence page).
5. Advanced model-based change classification (keep raw diff and manual review).

Do **not** cut:

- Tenant authorization before retrieval.
- PostgreSQL active-version verification.
- Document upload validation.
- Citation validation.
- Honest refusal.
- Critical cross-tenant regression tests.

## 12. Production gap register

Before use with real client data, evaluate and implement as appropriate:

- Independent security review and penetration test.
- Formal tenant isolation verification and RLS testing.
- Data residency, client contract and retention review.
- Malware scanning and hardened parser isolation.
- Encryption key management and rotation.
- Backup and disaster recovery with measured RPO/RTO.
- High availability and load/concurrency testing.
- Monitoring, alerting, incident handling and patch process.
- Tenant onboarding/offboarding and data deletion/export.
- OCR/local processing strategy for scanned documents.
- Larger-scale ingestion queues, retries and worker autoscaling.
- Model quality evaluation and model update governance.

## 13. Final handoff checklist

- [ ] `README.md` has exact setup/run instructions.
- [ ] `.env.example` lists all required configuration without secrets.
- [ ] Database migrations are committed.
- [ ] Docker Compose uses persistent volumes and health checks.
- [ ] Synthetic seed data is reproducible.
- [ ] Unit, integration and security tests can be run with documented commands.
- [ ] Known limitations and unimplemented production controls are listed.
- [ ] Demo path is rehearsed by someone other than the primary developer.
