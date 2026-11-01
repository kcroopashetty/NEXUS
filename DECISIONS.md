# NEXUS — Architectural Decision Records (ADRs)

This document captures the key architectural, security, and operational decisions made in designing and implementing the NEXUS platform, including the context, trade-offs, and consequences of each choice.

---

## Index of Decisions

- [ADR 001: Query-Time PostgreSQL Authorization over Search Index ACLs (Permission Change Guard)](#adr-001-query-time-postgresql-authorization-over-search-index-acls-permission-change-guard)
- [ADR 002: Deterministic Difflib with Page Provenance over Black-Box LLM Diffs](#adr-002-deterministic-difflib-with-page-provenance-over-black-box-llm-diffs)
- [ADR 003: Partial Unique Index and Row-Level Locking for Single Active Version Enforcement](#adr-003-partial-unique-index-and-row-level-locking-for-single-active-version-enforcement)
- [ADR 004: Tenant-Isolated Vector Collections over Shared Multi-Tenant Collections](#adr-004-tenant-isolated-vector-collections-over-shared-multi-tenant-collections)
- [ADR 005: Server-Side Evidence Passport Issuance vs Client-Side Trust](#adr-005-server-side-evidence-passport-issuance-vs-client-side-trust)
- [ADR 006: Local-First Air-Gapped Deployment over External SaaS AI APIs](#adr-006-local-first-air-gapped-deployment-over-external-saas-ai-apis)
- [ADR 007: Pre-Indexing Document Quality Inspection Gate](#adr-007-pre-indexing-document-quality-inspection-gate)
- [ADR 008: Observable Pipeline Stage Diagnostics (Query Trace)](#adr-008-observable-pipeline-stage-diagnostics-query-trace)

---

## ADR 001: Query-Time PostgreSQL Authorization over Search Index ACLs (Permission Change Guard)

### Status
**Accepted & Implemented**

### Context
In conventional enterprise search systems (such as Azure AI Search or Glean), document access control lists (ACLs) are mirrored into search index metadata during ingestion. When an administrator revokes an employee's access or demotes their role in the primary identity provider, the search index continues to serve matching chunks until an index crawl or resynchronization job completes. This synchronization lag creates a critical security window during which revoked users can retrieve confidential information.

### Decision
NEXUS establishes PostgreSQL as the authoritative source of truth for authorization. Rather than trusting permissions stored inside Chroma vectors:
1. Every tenant-scoped HTTP request derives an authoritative `AuthorizedTenantContext` by querying PostgreSQL live.
2. Chroma vector search returns candidate chunks without permission gating.
3. Before any candidate chunk reaches the LLM context, the **Retrieval Guard** filters each candidate against PostgreSQL: verifying that the chunk's parent document version is currently `ACTIVE`, that the caller's role is included in `allowed_roles`, and that the caller's membership has not been revoked.

### Consequences
- **Positive:** Revoking an employee's access takes effect immediately across all searches with zero synchronization delay.
- **Positive:** Stale vector chunks from superseded or candidate versions are physically barred from entering LLM context.
- **Negative:** Adds a fast indexed database lookup (`WHERE chunk_id IN (...) AND status='ACTIVE'`) to the query critical path (typically 4–12 ms).

---

## ADR 002: Deterministic Difflib with Page Provenance over Black-Box LLM Diffs

### Status
**Accepted & Implemented**

### Context
When policy documents evolve (e.g. updating an SLA or financial threshold), organizations require exact, auditable verification of what changed. Using an LLM to compare versions can produce subtle hallucinations, missed omissions, or nondeterministic summaries that cannot be legally relied upon during regulatory audits.

### Decision
NEXUS uses Python's deterministic `difflib.SequenceMatcher` operating over page-extracted text clauses to compute version differences.
1. Text is segmented into distinct clauses while preserving page number provenance (`old_page` and `new_page`).
2. Changes are classified into deterministic operations: `ADDITION`, `REMOVAL`, and `MODIFICATION`.
3. Clauses are classified into policy domains (`SLA`, `FINANCIAL`, `GOVERNANCE`) using pattern-matching rules.
4. LLM synthesis is strictly prohibited from altering or omitting diff items; optional LLM summaries serve purely as advisory commentary citing the underlying diff items.

### Consequences
- **Positive:** 100% reproducible, verifiable, and explainable diff reports suitable for legal and compliance audit.
- **Positive:** Zero LLM token consumption or latency during diff generation.
- **Negative:** Does not capture purely stylistic paraphrasing as semantic equivalences without high token overlap.

---

## ADR 003: Partial Unique Index and Row-Level Locking for Single Active Version Enforcement

### Status
**Accepted & Implemented**

### Context
In knowledge management systems, "split-brain" states occur when concurrent approvals or race conditions leave multiple versions of the same policy document marked as `ACTIVE`. This causes contradictory answers in RAG pipelines.

### Decision
1. NEXUS enforces a database-level partial unique index:
   ```sql
   CREATE UNIQUE INDEX uq_one_active_version_per_document
       ON document_versions(document_id) WHERE status = 'ACTIVE';
   ```
2. The version approval endpoint (`POST /versions/{version_id}/approve`) executes an atomic transaction with row-level locking on the parent `Document`:
   ```python
   doc = db.query(Document).filter(...).with_for_update().first()
   # Demote current active versions
   for pv in prior_actives:
       pv.status = "SUPERSEDED"
   db.flush()
   # Activate candidate version
   candidate_version.status = "ACTIVE"
   db.flush()
   ```

### Consequences
- **Positive:** Guaranteed at the database storage engine level that no document can ever have more than one active version.
- **Positive:** Concurrent approval attempts serialize on the document row lock, preventing race conditions.
- **Negative:** Requires careful flush ordering in ORM transactions so that demotions are emitted prior to activations.

---

## ADR 004: Tenant-Isolated Vector Collections over Shared Multi-Tenant Collections

### Status
**Accepted & Implemented**

### Context
Multi-tenant vector databases often store embeddings from all tenants in a single shared index and rely on metadata filters (`{"tenant_id": "..."}`) to segregate queries. If a filter is accidentally omitted, bypassed via software bug, or compromised via injection, cross-tenant data leakage occurs.

### Decision
NEXUS partitions vector storage by creating a dedicated, isolated Chroma collection for each tenant workspace:
`nexus_t_<tenant_uuid>`
Vector queries only ever query the caller's authorized collection name, which is derived server-side from `AuthorizedTenantContext.tenant_id`.

### Consequences
- **Positive:** Strong physical boundary: even if a query filter were omitted, the search cannot physically inspect vectors outside the caller's collection.
- **Positive:** Deleting or re-indexing a tenant's knowledge base is an isolated, single-collection operation.
- **Negative:** Chroma creates directory structures per collection, which consumes slightly more file descriptor overhead than a single monolithic index.

---

## ADR 005: Server-Side Evidence Passport Issuance vs Client-Side Trust

### Status
**Accepted & Implemented**

### Context
Many AI assistants generate citations inside the LLM markdown response (e.g. `[1]`, `(Doc A, p. 4)`). Large language models regularly invent non-existent page numbers, attribute claims to unrelated documents, or generate citations for fabricated facts.

### Decision
In NEXUS, the LLM is never allowed to issue official citations.
1. The backend supplies chunks with opaque IDs (`EVIDENCE ID: <uuid>`).
2. The model returns structured JSON containing claims and claimed evidence IDs.
3. The server-side **Evidence Passport Validator** resolves each citation ID against the exact chunks supplied in that query's prompt snapshot.
4. The server verifies that the passage content supports the claim. If an ID is invalid, unverified, or ungrounded, the system flags the claim and issues an honest refusal.

### Consequences
- **Positive:** Zero fabricated citations. The UI displays verified page numbers, document titles, and excerpted text retrieved from the database, not generated by the model.
- **Positive:** Enables mathematical grounding scores (e.g. 100% grounded vs ungrounded claims suppressed).
- **Negative:** Requires structured JSON output formatting from the model and server-side validation overhead (5–10 ms).

---

## ADR 006: Local-First Air-Gapped Deployment over External SaaS AI APIs

### Status
**Accepted & Implemented**

### Context
Enterprise policies (especially in financial, legal, and healthcare verticals) strictly forbid transmitting proprietary documents, employee queries, or ACL metadata to external third-party AI APIs (such as OpenAI or Anthropic) due to data sovereignty, compliance, and confidentiality requirements.

### Decision
NEXUS is engineered as a local-first, self-contained architecture:
1. Embeddings: Local Sentence-Transformers (`all-MiniLM-L6-v2`) running in-process with a deterministic offline fallback.
2. Inference: Local Ollama instance running self-hosted open-weights models (`llama3.2`, `mistral`, or offline grounded synthesis).
3. Storage: Local filesystem adapter with tenant path isolation and quarantine zones.
4. No network egress required during document upload, ingestion, diffing, chat, or audit.

### Consequences
- **Positive:** Complete data privacy and sovereignty; compliant with air-gapped enterprise environments.
- **Positive:** Zero recurring external API usage costs or external rate limits.
- **Negative:** Requires host machine CPU/GPU resources capable of running local embeddings and models.

---

## ADR 007: Pre-Indexing Document Quality Inspection Gate

### Status
**Accepted & Implemented**

### Context
Enterprise document repositories are filled with scanned image PDFs, broken encodings, corrupted multi-column tables, and password-protected files. Standard RAG architectures blindly chunk and embed these corrupted strings, leading to "silent failures" where chatbots produce wrong answers due to corrupted source data.

### Decision
NEXUS introduces the **Document Quality Inspector** as an obligatory pre-indexing gate:
1. Evaluates page text completeness, character density per page, garbled character ratios, and table preservation.
2. Detects scanned image pages that require optical character recognition (OCR) rather than standard text extraction.
3. Attaches an inspection report and `quality_score` to the `document_versions` record before chunking proceeds.
4. Surfaces diagnostic reports to administrators in the UI rather than simply reporting "Upload successful".

### Consequences
- **Positive:** Prevents corrupted, empty, or unreadable documents from polluting the search index.
- **Positive:** Gives administrators actionable diagnostics on why an upload may require OCR or reformatting.
- **Negative:** Adds a lightweight evaluation step during document ingestion (50–150 ms per document).

---

## ADR 008: Observable Pipeline Stage Diagnostics (Query Trace)

### Status
**Accepted & Implemented**

### Context
When an enterprise chatbot produces an ungrounded or unsatisfactory answer, debugging the failure is notoriously difficult. Was the document never retrieved? Was it filtered out by permissions? Did the LLM ignore the context? Did vector search fail?

### Decision
NEXUS instruments the RAG pipeline with stage-by-stage observable execution tracing (`QueryTrace`):
1. Measures precise latency and records explicit status (`PASSED`, `FAILED`, `SKIPPED`) across all 6 pipeline stages: `AUTH_VERIFY`, `VECTOR_SEARCH`, `PERMISSION_GUARD`, `INTEGRITY_CHECK`, `LLM_INFERENCE`, and `EVIDENCE_VALIDATION`.
2. Persists the trace alongside the query event in PostgreSQL.
3. Exposes the trace via `GET /queries/{query_id}/trace` and visualizes the timeline directly in the user interface.

### Consequences
- **Positive:** Complete operational visibility: administrators can instantly distinguish between vector retrieval misses, permission filter blocks, and model inference errors.
- **Positive:** Facilitates performance profiling and SLA tracking across each internal component.
- **Negative:** Requires stage instrumentation wrappers around each pipeline component.

