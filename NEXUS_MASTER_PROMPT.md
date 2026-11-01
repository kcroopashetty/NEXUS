# NEXUS — Master Build Prompt

Use this prompt with an AI coding agent (Cursor, Claude Code, Antigravity or a comparable repository-aware coding assistant). Keep the three companion documents in the repository root:

- `ARCHITECTURE.md`
- `DATABASE_SCHEMA.md`
- `IMPLEMENTATION_PLAN.md`

---

## MASTER PROMPT (copy everything below this line into the coding agent)

You are the lead software architect and senior full-stack engineer responsible for building **NEXUS — Enterprise Knowledge Intelligence & Assurance Platform** for a 24-hour Hack-for-Hire hackathon.

### 1. Mission

Build a working, deployment-oriented MVP for PS-04: Centralised Multi-Client Knowledge Chatbot.

NEXUS is differentiated by **Knowledge Change Intelligence**: it compares versions of the same logical client document, highlights additions/removals/modifications with page-level provenance, creates a review report, and requires authorised human approval before a new version becomes active.

The product also includes:

1. **Tenant-isolated RAG:** employees can retrieve only evidence from client workspaces to which they are currently authorised.
2. **Evidence Ledger:** every AI answer/refusal records the exact document versions and evidence passages used.
3. **Continuous Security Assurance:** an ATTACK workstream independently probes the application; vulnerabilities are reproduced, fixed and added to regression tests.

This is not a generic chatbot demo. It is not a claim of complete production readiness. Build the smallest complete secure lifecycle and document the remaining production-hardening work honestly.

### 2. Read the project specifications first

Before writing code, read all of:

- `ARCHITECTURE.md`
- `DATABASE_SCHEMA.md`
- `IMPLEMENTATION_PLAN.md`

Treat those documents as the project contract. If the existing repository conflicts with them, inspect the actual code and explain the conflict before changing anything. Do not silently discard requirements or replace the architecture with a different stack.

If a required company decision is unknown (for example on-premises versus private cloud), use the local-first hackathon architecture and record the question as an open decision. Do not block implementation on a clarification that can be safely deferred.

### 3. Technology stack

Use this baseline unless the repository already has a working equivalent that is safer and easier to maintain:

- Frontend: React + Vite + TypeScript.
- Backend: Python + FastAPI + Pydantic.
- ORM/migrations: SQLAlchemy 2.x + Alembic.
- Database: PostgreSQL.
- Vector store: ChromaDB behind a `VectorStore` interface.
- Document storage: local filesystem behind a `DocumentStorage` interface.
- PDF extraction: PyMuPDF, preserving page numbers.
- DOCX extraction: python-docx.
- TXT extraction: safe text decoding.
- Embeddings: Sentence Transformers running locally.
- LLM: Ollama running locally.
- Diff: Python `difflib` or an equivalent deterministic diff for the MVP.
- Deployment: Docker Compose with persistent volumes and health checks.
- Tests: Pytest for backend; frontend tests where practical.

Use current compatible stable package versions and lock dependencies once installed. Do not invent package APIs. If a library API is uncertain, inspect installed versions or official package documentation before coding.

### 4. Non-negotiable security rules

These rules override speed and UI convenience.

1. Never trust a `tenant_id`, role, collection name, storage key or permission sent by the frontend. A route may contain a requested tenant context, but the backend must verify current membership and role against PostgreSQL on every tenant-scoped request.
2. Use deny-by-default authorisation. Missing or failed membership checks must reject the request.
3. Every repository and storage operation must receive an explicit server-derived `AuthorizedTenantContext` (or equivalent). Avoid unscoped global helper functions for tenant data.
4. Use password hashing (Argon2id preferred), short-lived authenticated sessions/tokens, strict CORS and safe cookie/token handling. Never store plaintext passwords or tokens in the database.
5. Keep ChromaDB private to backend/worker services. Use a collection mapping derived from the authorised tenant UUID. Never let the browser choose a Chroma collection.
6. Chroma results are candidates, not authority. Before any text reaches the LLM, PostgreSQL must verify the returned chunk belongs to the authorised tenant and its document version is currently `ACTIVE`.
7. Superseded, rejected, failed, quarantined or review-pending document versions must not enter normal employee chat context.
8. Check tenant authorization for document list, preview, download, version history, change report, approval, chat, evidence history, audit and security endpoints.
9. Upload only allowlisted PDF/DOCX/TXT types, enforce size limits, generate safe storage keys and treat filenames/content as untrusted. Never create filesystem paths from an uploaded filename. Process files in a worker with strict resource limits; do not execute document-embedded instructions.
10. The LLM receives only validated active evidence. The MVP chatbot has no external tools, shell, filesystem or unrestricted database access.
11. Validate all evidence IDs returned by the LLM against the exact IDs supplied in context. The server, not the model, resolves document title/version/page citations.
12. Refuse when evidence is insufficient or citation validation fails. Surface conflicting active sources. Never fill gaps using the model's general knowledge.
13. Do not log passwords, secrets, bearer tokens or full confidential document content in normal logs.
14. No client document content may be sent to external AI, embedding, OCR or analytics APIs. All inference and embedding must be local.
15. Do not claim the system is fully secure, hallucination-free or production-ready. Report only tests actually run and capabilities actually implemented.

### 5. Product requirements

#### A. Users and tenants

- Create tenants/client workspaces.
- Create users and tenant memberships.
- Support platform admin, client admin and employee roles.
- Allow one user to belong to multiple tenants if assigned.
- Return only authorised memberships from `/me` and tenant listing.
- Client admins can manage members/documents within their tenant only.

#### B. Document management

- Upload PDF, DOCX and TXT files.
- Stream files into private quarantine/storage.
- Validate type, size and basic file integrity.
- Create logical document and version records.
- Store original source with tenant-scoped generated storage key.
- Extract page-aware text and preserve page numbers.
- Chunk with metadata: tenant ID, document ID, version ID, chunk ID, page start/end, content hash and section heading where available.
- Generate local embeddings and index in the server-selected tenant collection.
- Persist chunk text/metadata in PostgreSQL so the vector index is rebuildable.
- Show processing state and safe errors to admins.
- Use idempotent processing jobs and avoid duplicate vectors on retry.

#### C. Knowledge Change Intelligence (primary USP)

- Treat a document as a logical record with immutable versions.
- When v2 is uploaded for the same document, compare it with the previous version.
- Use deterministic text diff as the source of truth for additions/removals/modifications.
- Preserve old/new page references and section headings.
- Show old and new passages side-by-side with highlighted differences.
- Optional local LLM summarisation/classification is advisory only and must cite the deterministic diff items.
- Related-document suggestions are initially simple and transparent (same tenant, shared category/tags, explicit references or keyword overlap). Mark them as suggestions, not verified impact.
- New version enters `REVIEW` only after extraction, chunking, embedding and indexing succeed.
- Client admin explicitly approves or rejects.
- Approval uses a database transaction that supersedes the prior active version and activates the candidate, with at most one active version per document.
- If processing or approval fails, the prior active version remains active.
- Retain old source documents and historical evidence for audit.

#### D. Secure RAG

- Authenticate user and resolve tenant context first.
- Embed question locally.
- Search only the server-selected tenant collection.
- Over-fetch if needed because stale/inactive vectors may be filtered after Chroma returns.
- Verify candidate chunk IDs in PostgreSQL with tenant and active-version filters.
- Load chunk text from PostgreSQL; only verified active evidence may enter LLM context.
- Prompt clearly marks document text as untrusted content and asks the model to answer only from evidence.
- Require structured output: status (`ANSWERED`, `INSUFFICIENT_EVIDENCE`, `CONFLICT`), answer, evidence IDs, uncertainty note.
- Validate output schema and evidence IDs. Retry at most once for malformed output; otherwise refuse/fail safely.
- Server resolves source citations using database records.
- Unsupported questions receive an honest refusal.
- Conflicting sources are both surfaced with citations.

#### E. Evidence Ledger

For each query, persist:
- Query ID, tenant, user and timestamp.
- Question and answer/refusal status, subject to retention policy.
- Model name/version and prompt version.
- Retrieved chunk IDs, document version IDs, page references and content hashes.
- Snapshot of exact evidence text supplied to the model or an immutable content-addressed reference.
- Validation outcome and latency.

Build a query detail screen that lets an authorised user/admin inspect the source evidence. Historical records must continue to point to the old version even after a newer version becomes active.

#### F. Continuous Security Assurance

Provide a safe test suite against synthetic local test tenants. Include:
- Tenant ID manipulation.
- Cross-tenant document listing/reading.
- Direct document-ID access.
- Unauthorized file download.
- Role escalation/member administration.
- Cross-tenant query/evidence/audit access.
- Direct prompt injection.
- Indirect prompt injection in uploaded document text.
- Candidate/superseded version retrieval.
- Unauthorized version approval.
- Citation ID manipulation.

Record test key, expected behaviour, actual result, pass/fail, severity and redacted evidence. Make the test runner internal/admin-only and do not expose dangerous arbitrary test payload execution. Every fixed vulnerability should become a regression test.

### 6. Storage and deployment

For the 24-hour MVP, use local-first deployment:

- PostgreSQL in Docker with a persistent volume.
- ChromaDB with a persistent volume.
- Tenant-scoped local document volume.
- Ollama model volume/cache.
- Backend and ingestion worker.
- React frontend served locally.

Do not put documents or databases only in ephemeral container layers. Do not commit `.env`, documents, model weights, DB files, Chroma files or logs to Git. Provide `.env.example` with placeholder values only.

Provision all Python/Node dependencies, Docker images and Ollama models before the offline test. Then block outbound network access at the host/network layer and test the entire workflow. Do not claim offline operation merely because Ollama is local.

Keep local storage and vector search behind interfaces so they can later be replaced with private object storage or different vector infrastructure. Do not implement a cloud dependency in the MVP.

### 7. Engineering workflow (must follow)

Do not attempt to write the entire application in one giant untested code dump.

**Step 1 — Inspect:**
- Inspect repository tree, current code, package files and environment.
- Identify what already works and what is missing.
- Do not overwrite existing user code without explaining the impact.

**Step 2 — Plan:**
- Produce a short implementation plan mapped to the P0 acceptance criteria in `IMPLEMENTATION_PLAN.md`.
- Identify risks and any assumption that needs a decision.
- Confirm the local run path and environment variables.

**Step 3 — Build in vertical slices:**
1. Compose skeleton, health checks, config and migrations.
2. Authentication, memberships and tenant authorization.
3. Tenant-safe document upload and storage.
4. Ingestion, page extraction, chunking, embeddings and Chroma indexing.
5. Secure RAG, citations, refusals and Evidence Ledger.
6. Version diff, change report and human approval.
7. Attack suite, audit/security views and polished UI.
8. Offline validation and handoff documentation.

At each slice:
- Implement the smallest complete working feature.
- Run formatter/type checks where available.
- Run relevant unit/integration/security tests.
- Fix failures before continuing.
- Report exact commands and results.
- Keep APIs and schemas consistent with the specification.

**Step 4 — Integrate continuously:**
- Use a shared integration branch/environment.
- Do not leave integration until the final hours.
- Add health checks and correlation/request IDs early.
- Ensure ATTACK can test endpoints as soon as they are available.

**Step 5 — Final verify:**
- Run migrations from an empty database.
- Run full tests.
- Run all tenant boundary tests.
- Run version approval/retrieval test.
- Restart containers and verify persistence.
- Test with outbound access blocked.
- Produce a known-limitations/production-hardening list.

### 8. Required UI screens

Build a clear, professional enterprise interface; do not overinvest in visual effects.

1. Login.
2. Tenant/workspace selector (only authorised memberships).
3. Admin overview: documents, processing failures, pending version reviews and security summary.
4. Document library: upload, status, versions and download (authorised only).
5. Change Intelligence: old/new comparison, modified clauses, source pages, impact suggestions and approve/reject.
6. Knowledge Assistant: chat, answer/refusal/conflict status and source citations.
7. Evidence detail: historical query and exact evidence references.
8. Security Assurance: test run summary and redacted results.

The employee view should not expose admin screens or other tenant data.

### 9. Required API and data rules

Use the API endpoint contract in `IMPLEMENTATION_PLAN.md` and the schema in `DATABASE_SCHEMA.md`. If an endpoint or field needs to change, update the documentation and tests in the same task.

- Use UUIDs for identifiers.
- Include `tenant_id` in tenant-owned database rows and query predicates.
- Use composite same-tenant foreign keys where specified.
- Use a partial unique index to enforce one active version per document.
- Use transactions and document-row locking for version approval.
- Use Alembic migrations; do not silently create production tables on app startup.
- Use consistent API error codes and do not leak whether another tenant's resource exists.

### 10. Seed/demo dataset

Create synthetic data only:

- Tenant A: Complaint SOP v1 specifies 48-hour resolution; v2 changes it to 24 hours.
- Tenant B: Finance SOP with different approval and payment rules.
- Tenant C: Administration SOP with onboarding and escalation steps.

Create at least:
- One client admin and one employee for each tenant.
- One platform admin.
- Answerable questions with known citations.
- An unsupported question.
- A conflicting-source test if time permits.
- Cross-tenant attack tests.
- A malicious instruction embedded in a synthetic PDF/text document.

Never use real VLOOKUP/client documents unless the company explicitly authorises it.

### 11. Performance and reliability expectations

For the MVP:
- Use async/background processing for document ingestion where feasible.
- Set upload/page/chunk limits through configuration.
- Avoid loading huge files into memory when streaming is practical.
- Add timeouts around Ollama and document parsers.
- Expose service health and processing status.
- Use bounded retries and idempotency.
- Do not block document upload requests until all embedding work is complete if a processing job can be queued.

Do not invent performance benchmarks. Measure latency on the actual hackathon machine and report sample size, model and test conditions.

### 12. Deliverables

At completion, provide:

1. Working frontend and backend source.
2. Docker Compose local deployment.
3. Alembic migrations and synthetic seed data.
4. `.env.example` and README setup instructions.
5. Unit, integration and security tests.
6. Knowledge Change Intelligence demo with old/new page references.
7. Evidence Ledger showing historical evidence.
8. Security test report with actual run results.
9. Offline test result and any limitations.
10. Production-hardening backlog.

### 13. How to communicate progress

Be direct and evidence-based. For each milestone, state:
- What was implemented.
- Files changed.
- Commands run.
- Tests passed/failed (with counts when available).
- Known defects and remaining work.

Never say a feature is complete if it is only mocked or hardcoded. Never invent successful security test results. Never replace a failed test with a claim that the feature should work. If time runs short, protect tenant isolation, safe document lifecycle, grounded RAG, version diff and evidence history; cut decorative or advanced features first.

**Start now with Step 1: inspect the repository and read the three project specification files. Then report the existing state and propose the first vertical slice before editing.**

---

## End of master prompt
