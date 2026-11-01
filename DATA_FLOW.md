# NEXUS — Data Flow & Pipeline Architecture

This document specifies the end-to-end data flows, lifecycle boundaries, storage partitioning, and pipeline execution sequences across the NEXUS platform.

---

## 1. Multi-Tenant Storage & Isolation Boundaries

NEXUS enforces strict tenant isolation across three separate storage tiers: relational state, vector collections, and physical filesystem storage. No tier trusts client-provided identifiers.

```mermaid
flowchart TD
    subgraph ClientLayer["Untrusted Client Request"]
        REQ["HTTP Request\n(Bearer JWT + Path Tenant UUID)"]
    end

    subgraph AuthLayer["FastAPI Authorization Gateway"]
        PCG["Permission Change Guard\n(Query-time PostgreSQL lookup)"]
        CTX["AuthorizedTenantContext\n(Authoritative tenant_id, user_id, role)"]
    end

    subgraph RelationalTier["Relational Store (PostgreSQL / SQLite)"]
        TM["tenant_memberships\n(tenant_id, user_id, role, last_permission_change_at)"]
        DOCS["documents & document_versions\n(tenant_id, document_id, status='ACTIVE')"]
        CHUNKS["document_chunks\n(tenant_id, allowed_roles, classification)"]
    end

    subgraph VectorTier["Vector Store (ChromaDB)"]
        COLL_A["Collection: nexus_t_<tenant_A_uuid>"]
        COLL_B["Collection: nexus_t_<tenant_B_uuid>"]
    end

    subgraph FileTier["Physical Storage Engine"]
        QUAR["./data/nexus/quarantine/<upload_uuid>"]
        FS_A["./data/nexus/tenants/<tenant_A_uuid>/documents/<doc_id>/<ver_id>/original"]
        FS_B["./data/nexus/tenants/<tenant_B_uuid>/documents/<doc_id>/<ver_id>/original"]
    end

    REQ --> PCG
    PCG --> TM
    TM --> CTX
    CTX --> DOCS
    CTX --> CHUNKS
    CTX -.->|Routes only to caller collection| COLL_A
    CTX -.->|Path traversal protected| FS_A
```

---

## 2. Document Ingestion & Quality Inspection Data Flow

When a Client Administrator uploads a document (PDF, DOCX, or TXT), it progresses through a strict five-stage pipeline before entering the review stage.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Client Admin
    participant API as FastAPI Ingestion Endpoint
    participant Store as Local Storage Adapter
    participant Ext as PyMuPDF / Extractor
    participant QI as Document Quality Inspector
    participant DB as Relational Store (PostgreSQL)
    participant Chk as Chunker & Hasher
    participant Emb as Local Sentence-Transformers
    participant Vec as ChromaDB (Tenant Collection)

    Admin->>API: POST /tenants/{id}/documents (file, title, authority)
    Note over API: Step 1: Whitelist extension & quarantine
    API->>Store: save_quarantine(stream, upload_id)
    Store-->>API: quarantine_key ("quarantine/<uuid>")
    
    Note over API: Step 2: Compute SHA-256 & verify size limit
    API->>Store: get_file_stream(quarantine_key)
    API->>API: Compute SHA-256 & byte size
    
    Note over API: Step 3: Promote to isolated tenant directory
    API->>Store: promote_from_quarantine(quarantine_key, tenant_id, doc_id, ver_id)
    Store-->>API: storage_key ("tenants/{t_id}/documents/{d_id}/{v_id}/original")
    API->>DB: INSERT document (title, authority_level)
    API->>DB: INSERT document_version (status='PROCESSING')
    API->>DB: INSERT processing_job (status='RUNNING', stage='EXTRACTION')

    Note over API,Ext: Step 4: Extraction & Quality Inspection
    API->>Ext: extract_pages(file_stream, mime_type)
    Ext-->>API: List[ExtractedPage(page_number, text, sha256)]
    API->>QI: inspect(pages)
    QI-->>API: QualityReport(score, ocr_needed, density, garbled_ratio, tables)
    API->>DB: INSERT document_pages (page_number, extracted_text, text_sha256)
    API->>DB: UPDATE document_version (quality_score, ocr_needed, quality_report)

    Note over API,Vec: Step 5: Chunking, Local Embedding & Indexing
    API->>Chk: chunk_document(pages, allowed_roles, classification)
    Chk-->>API: List[DocumentChunk]
    API->>DB: INSERT document_chunks (chunk_index, page_start, text, hash, allowed_roles)
    API->>Emb: generate_embeddings([chunk.text])
    Emb-->>API: List[vector_1536]
    API->>Vec: collection.upsert(ids, embeddings, metadatas)
    
    API->>DB: UPDATE processing_job (status='SUCCEEDED')
    API->>DB: UPDATE document_version (status='REVIEW')
    API-->>Admin: HTTP 201 Created (document_id, version_id, quality_score)
```

---

## 3. Knowledge Change Intelligence & Approval Data Flow

When a new version (v2) of an existing policy document is uploaded, it is compared against the prior active version using deterministic clause diffing. Activation is gated on explicit human approval.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Client Admin
    participant API as Documents / Versions API
    participant Diff as Change Intelligence Engine
    participant DB as Relational Store (PostgreSQL)

    Admin->>API: GET /tenants/{t_id}/documents/{d_id}/changes?to_version_id={v2}
    API->>DB: SELECT document_pages WHERE version_id IN (v1, v2)
    DB-->>API: v1_pages, v2_pages
    API->>Diff: compute_version_diff(v1, v2)
    Note over Diff: SequenceMatcher segment-by-segment comparison
    Note over Diff: Classify policy clauses (SLA, FINANCIAL, GOVERNANCE)
    Note over Diff: Scan other active docs for impact notices
    Diff->>DB: INSERT document_changes (status='PENDING_REVIEW')
    Diff->>DB: INSERT document_change_items (ADDITION, REMOVAL, MODIFICATION)
    Diff->>DB: INSERT document_impact_suggestions (related_doc_id, rationale)
    Diff-->>API: VersionDiffReport
    API-->>Admin: HTTP 200 OK (diff report, clause highlights, impact notices)

    opt Human Rejection
        Admin->>API: POST /tenants/{t_id}/versions/{v2}/reject
        API->>DB: UPDATE document_versions SET status='FAILED' WHERE id=v2
        API->>DB: UPDATE document_changes SET status='REJECTED'
        API->>DB: INSERT audit_events (action='DOCUMENT_VERSION_REJECTED')
        API-->>Admin: HTTP 200 OK (Version 2 rejected; v1 remains ACTIVE)
    end

    opt Human Approval (Atomic Transaction)
        Admin->>API: POST /tenants/{t_id}/versions/{v2}/approve
        Note over API,DB: Begin Transaction with Row Lock
        API->>DB: SELECT * FROM documents WHERE id=d_id FOR UPDATE
        API->>DB: UPDATE document_versions SET status='SUPERSEDED' WHERE status='ACTIVE'
        API->>DB: flush()
        API->>DB: UPDATE document_versions SET status='ACTIVE' WHERE id=v2
        API->>DB: flush() (Enforces partial unique index)
        API->>DB: UPDATE document_changes SET status='APPROVED', reviewed_by=user_id
        API->>DB: INSERT audit_events (action='DOCUMENT_VERSION_APPROVED')
        API->>DB: commit()
        API-->>Admin: HTTP 200 OK (Version 2 is now ACTIVE; v1 is SUPERSEDED)
    end
```

---

## 4. Secure Grounded RAG Query & Evidence Passport Data Flow

This data flow details how a user question is answered with verifiable grounding while enforcing Permission Change Guard and generating observable Query Trace diagnostics.

```mermaid
sequenceDiagram
    autonumber
    actor User as Employee User
    participant GW as Request Context & Auth Middleware
    participant API as Chat Query API (/chat/query)
    participant Guard as Retrieval Permission Guard
    participant Chroma as ChromaDB (Tenant Collection)
    participant DB as PostgreSQL (Authoritative State)
    participant LLM as Local Ollama Service
    participant Pass as Evidence Passport Validator

    User->>GW: POST /tenants/{t_id}/chat/query (question: "What is the SLA?")
    Note over GW: Stage 1: AUTH_VERIFY (Permission Change Guard)
    GW->>DB: SELECT role, status, last_permission_change_at FROM tenant_memberships
    DB-->>GW: role='EMPLOYEE', status='ACTIVE'
    GW->>API: dispatch(AuthorizedTenantContext)

    Note over API,Chroma: Stage 2: VECTOR_SEARCH
    API->>Chroma: collection(nexus_t_{t_id}).query(embedded_query, n_results=10)
    Chroma-->>API: 10 candidate chunk IDs

    Note over API,DB: Stage 3: PERMISSION_GUARD
    API->>Guard: filter_and_rank(candidates, user_role='EMPLOYEE')
    Guard->>DB: SELECT chunk_id, version_status, allowed_roles, authority_level<br/>FROM document_chunks JOIN document_versions<br/>WHERE version_status='ACTIVE' AND allowed_roles CONTAINS 'EMPLOYEE'
    DB-->>Guard: 4 active qualified chunks (6 inactive/restricted filtered out)
    Guard-->>API: Qualified active chunks ranked by authority_level

    alt No Active Authorized Evidence Found
        API-->>User: HTTP 200 (status="INSUFFICIENT_EVIDENCE", answer="Refusal")
    end

    Note over API,LLM: Stage 4: LLM_INFERENCE
    API->>LLM: generate_structured(question, qualified_chunks)
    LLM-->>API: JSON: { status, answer, evidence_ids, claims }

    Note over API,Pass: Stage 5: EVIDENCE_VALIDATION
    API->>Pass: validate(llm_response, qualified_chunks)
    Note over Pass: Check cited chunk IDs exist in prompt snapshot
    Note over Pass: Verify factual claims match passage content
    Pass-->>API: EvidencePassport (grounding_score=100%, verified=true)

    Note over API,DB: Stage 6: AUDIT & TRACE RECORDING
    API->>DB: INSERT query_events (question, answer, status, grounding_score, trace_stages)
    API->>DB: INSERT query_evidence (query_id, chunk_id, claim_text, verified)
    API-->>User: HTTP 200 OK (answer, Evidence Passport, Cited Passages, Query Trace)
```

---

## 5. Query Trace Observable Execution Sequence

For every query execution, NEXUS emits an immutable `QueryTrace` capturing the latency and decisions across all six pipeline stages:

```json
{
  "trace_id": "qt-6f34e89a-0a2b-4d43-98fe-892418a0bfb2",
  "query_id": "q-884bc19e-f412-4cf5-99bc-2305a4ecb901",
  "total_latency_ms": 142,
  "stages": [
    {
      "stage": "AUTH_VERIFY",
      "status": "PASSED",
      "duration_ms": 3,
      "detail": "Verified active membership in tenant Alpha (role=EMPLOYEE)"
    },
    {
      "stage": "VECTOR_SEARCH",
      "status": "PASSED",
      "duration_ms": 32,
      "detail": "Retrieved 10 candidate chunks from Chroma collection nexus_t_tenant-a"
    },
    {
      "stage": "PERMISSION_GUARD",
      "status": "PASSED",
      "duration_ms": 11,
      "detail": "PostgreSQL verified 4 chunks active; filtered 6 candidate chunks (inactive version / role clearance)"
    },
    {
      "stage": "INTEGRITY_CHECK",
      "status": "PASSED",
      "duration_ms": 2,
      "detail": "Knowledge integrity verified: top authority OFFICIAL_POLICY; no multi-source conflicts detected"
    },
    {
      "stage": "LLM_INFERENCE",
      "status": "PASSED",
      "duration_ms": 86,
      "detail": "Local synthesis generated structured answer with 1 grounded claim"
    },
    {
      "stage": "EVIDENCE_VALIDATION",
      "status": "PASSED",
      "duration_ms": 8,
      "detail": "Evidence Passport issued: 100% citations verified against prompt snapshot"
    }
  ]
}
```

---

## 6. Red-Team Sentinel Adversarial Testing Data Flow

The Red-Team Sentinel runner executes synthetic adversarial tests against multi-tenant boundaries on-demand or as part of continuous regression testing.

```mermaid
flowchart TD
    subgraph Trigger["Sentinel Execution Engine"]
        RUN["POST /api/v1/security/sentinel/run"]
        SYN["Provision Synthetic Victim (Alpha) & Attacker (Bravo) Tenants"]
    end

    subgraph AdversarialSuite["7 Synthetic Attack Probes"]
        T1["Test 1: Route Tampering\n(Bravo token requests Alpha route) -> 403 Forbidden"]
        T2["Test 2: File Download Leak\n(Bravo attempts download of Alpha doc) -> 403 / 404"]
        T3["Test 3: Vector Store Leak\n(Bravo RAG query on Alpha proprietary facts) -> INSUFFICIENT_EVIDENCE"]
        T4["Test 4: Prompt Injection Defense\n(System Override payload submitted) -> Refused / Grounded"]
        T5["Test 5: Inactive Version Exclusion\n(Query on candidate REVIEW facts) -> Excluded from context"]
        T6["Test 6: Role Escalation Prevention\n(EMPLOYEE attempts candidate approval) -> 403 Forbidden"]
        T7["Test 7: Executable Ingestion Block\n(Upload .exe / .sh payload) -> 415 Unsupported Media Type"]
    end

    subgraph Persistence["Security Assurance Ledger"]
        RUN_REC["security_test_runs\n(run_id, suite_name, status, pass_rate, duration)"]
        RES_REC["security_test_results\n(run_id, test_key, severity, expected, actual, passed)"]
    end

    RUN --> SYN
    SYN --> T1 & T2 & T3 & T4 & T5 & T6 & T7
    T1 & T2 & T3 & T4 & T5 & T6 & T7 --> RUN_REC
    T1 & T2 & T3 & T4 & T5 & T6 & T7 --> RES_REC
```

