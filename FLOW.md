# NEXUS — Lifecycle Workflows, State Machines & Decision Trees

This document specifies the operational state transitions, error recovery behaviors, approval workflows, and query evaluation decision trees implemented in NEXUS.

---

## 1. Document Version Lifecycle State Machine

Each document version is immutable and moves through a deterministic series of states from upload to retirement.

```mermaid
stateDiagram-v2
    [*] --> UPLOADED: File uploaded & placed in quarantine
    UPLOADED --> PROCESSING: Validation passed; promoted to tenant storage
    
    state PROCESSING {
        [*] --> EXTRACTING: Page text extraction (PyMuPDF/docx/txt)
        EXTRACTING --> QUALITY_INSPECTION: Completeness & OCR scoring
        QUALITY_INSPECTION --> CHUNKING: Split into permission-carrying chunks
        CHUNKING --> EMBEDDING: Generate 384/1536-dim vectors
        EMBEDDING --> INDEXING: Write to tenant Chroma collection
        INDEXING --> [*]
    }

    PROCESSING --> REVIEW: Ingestion succeeds (v1 or candidate v2)
    PROCESSING --> FAILED: Parse/Extraction/Vector error (error_code logged)

    REVIEW --> ACTIVE: Client Admin approves (Atomic transaction)
    REVIEW --> FAILED: Client Admin rejects (error_code='ADMIN_REJECTED')

    ACTIVE --> SUPERSEDED: A newer version is approved for this document
    SUPERSEDED --> [*]: Retained indefinitely for historical audit & ledger lookup
    FAILED --> [*]: Terminal state; barred from RAG context
```

### State Transition Invariants

| State | RAG Context Permitted? | Download Permitted? | Allowed Transitions |
|---|---|---|---|
| `UPLOADED` | **No** | No (Quarantined) | `PROCESSING`, `FAILED` |
| `PROCESSING` | **No** | No | `REVIEW`, `FAILED` |
| `REVIEW` | **No** (Visible to Admin only) | Yes (Admin only) | `ACTIVE`, `FAILED` |
| `ACTIVE` | **Yes** (Ordinary Employees) | Yes (Authorized roles) | `SUPERSEDED` |
| `SUPERSEDED`| **No** (Barred from new queries) | Yes (Audit only) | None (Immutable historical record) |
| `FAILED` | **No** | Yes (Admin diagnosis) | None (Terminal failure) |

---

## 2. Processing Job Lifecycle & Stage Progression

Asynchronous or background ingestion tasks are tracked via `processing_jobs` records:

```mermaid
flowchart TD
    Q["QUEUED\n(Job enqueued)"] --> R["RUNNING\n(Worker picks up task)"]
    
    subgraph Stages["Stage Progression"]
        S1["EXTRACTION\n(PyMuPDF / docx / txt extraction)"]
        S2["QUALITY_INSPECTION\n(Completeness, OCR check, density)"]
        S3["CHUNKING\n(Role metadata attachment & hashing)"]
        S4["EMBEDDING\n(Local Sentence-Transformers)"]
        S5["INDEXING\n(ChromaDB collection upsert)"]
    end
    
    R --> S1 --> S2 --> S3 --> S4 --> S5
    
    S5 --> SUC["SUCCEEDED\n(Version transitioned to REVIEW)"]
    
    S1 -.->|Extraction Error| FAIL["FAILED\n(Error code & message recorded)"]
    S2 -.->|Corrupted Data| FAIL
    S3 -.->|Tokenization Error| FAIL
    S4 -.->|Embedding Timeout| FAIL
    S5 -.->|Vector DB Error| FAIL
```

---

## 3. Knowledge Change Intelligence & Approval Workflow

This workflow governs how version updates (e.g. updating an SLA from 48h to 24h) are audited, verified, and activated without risk of unreviewed policy leakage.

```mermaid
flowchart TD
    START["Client Admin uploads candidate v2 for existing document"] --> INGEST["Run Ingestion & Quality Inspection"]
    INGEST --> REVIEW_STATE["Version status becomes REVIEW"]
    
    REVIEW_STATE --> COMPUTE_DIFF["Admin opens Change Intelligence tab\n(GET /tenants/{id}/documents/{id}/changes)"]
    COMPUTE_DIFF --> DET_DIFF["Execute Deterministic Difflib Comparison"]
    
    subgraph DiffEngine["Diff Engine Operations"]
        OP1["Identify ADDITIONS with page numbers"]
        OP2["Identify REMOVALS with page numbers"]
        OP3["Identify MODIFICATIONS (e.g. 48h -> 24h)"]
        OP4["Classify Policy Domain (SLA, FINANCIAL, GOVERNANCE)"]
        OP5["Scan other active tenant docs for impact notices"]
    end
    
    DET_DIFF --> DiffEngine
    DiffEngine --> REPORT["Display Visual Diff & Impact Notices in UI"]
    
    REPORT --> DECISION{"Client Admin Review Decision"}
    
    DECISION -->|Reject| REJ["POST /versions/{v2_id}/reject\nStatus becomes FAILED\nPrevious ACTIVE version remains active"]
    
    DECISION -->|Approve| APPR["POST /versions/{v2_id}/approve\nBegin Atomic DB Transaction"]
    
    subgraph AtomicTx["Atomic Approval Transaction"]
        L1["Lock parent document row (SELECT FOR UPDATE)"]
        L2["Demote existing ACTIVE versions to SUPERSEDED"]
        L3["db.flush()"]
        L4["Promote candidate v2 to ACTIVE"]
        L5["db.flush() (Partial unique index verified)"]
        L6["Mark DocumentChange as APPROVED"]
        L7["Write AuditEvent (DOCUMENT_VERSION_APPROVED)"]
        L8["db.commit()"]
    end
    
    APPR --> AtomicTx
    AtomicTx --> FINISH["v2 is now ACTIVE; immediately answers employee RAG queries;\nv1 chunks barred from new employee queries"]
```

---

## 4. Grounded RAG Query Evaluation Decision Tree

This decision tree defines how NEXUS responds to employee queries, ensuring that missing evidence, contradictory sources, or permission changes result in honest refusals rather than confident hallucinations.

```mermaid
flowchart TD
    Q["Employee submits query:\nPOST /tenants/{t_id}/chat/query"] --> AUTH{"Check live PostgreSQL membership\n(Permission Change Guard)"}
    
    AUTH -->|Member missing or revoked| E403["HTTP 403 FORBIDDEN\n(Access Denied immediately)"]
    
    AUTH -->|Active membership verified| RETRIEVE["Vector Search in nexus_t_{t_id}\nRetrieve top-K candidate chunks"]
    
    RETRIEVE --> FILTER{"Retrieval Guard Filter:\n1. Parent version currently ACTIVE?\n2. Chunk allowed_roles includes user role?"}
    
    FILTER -->|Zero chunks qualify| REFUSE_NO_EVID["HTTP 200 OK\nStatus: INSUFFICIENT_EVIDENCE\n'I cannot answer because no active authorized policy was found.'\nGrounding Score: 0%"]
    
    FILTER -->|Qualified chunks found| HIERARCHY["Rank qualified chunks by authority hierarchy:\nOFFICIAL_POLICY > STANDARD_PROCEDURE > GUIDELINE > INFORMAL_NOTE"]
    
    HIERARCHY --> CONFLICT_CHECK{"Do multiple active sources\nprovide conflicting rules/deadlines?"}
    
    CONFLICT_CHECK -->|Contradiction Detected| CONFLICT_RESP["HTTP 200 OK\nStatus: CONFLICT\nSurface both sources with citations\n'Contradictory policy provisions detected across active sources.'"]
    
    CONFLICT_CHECK -->|No Conflict| SYNTHESIS["Local Ollama Structured Synthesis\n(Untrusted evidence sandbox with Evidence IDs)"]
    
    SYNTHESIS --> PASSPORT_VAL{"Server Evidence Passport Validator:\n1. Are all cited IDs in prompt context?\n2. Does passage text support factual claims?"}
    
    PASSPORT_VAL -->|Ungrounded or Invented Citation| REFUSE_UNGROUNDED["HTTP 200 OK\nStatus: INSUFFICIENT_EVIDENCE\nUngrounded claims suppressed\n'Evidence does not contain sufficient details to answer.'"]
    
    PASSPORT_VAL -->|Claims Verified in Passages| ANSWER["HTTP 200 OK\nStatus: ANSWERED\nGrounding Score: 100%\nIssue Evidence Passport with Page Provenance\nEmit Stage-by-Stage Query Trace"]
    
    ANSWER --> RECORD_LEDGER["Persist QueryEvent & QueryEvidence snapshot\nRecord immutable audit trail"]
```

---

## 5. Continuous Security Assurance & Adversarial Execution Flow

The Red-Team Sentinel execution pipeline provides automated verification of security boundaries:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Platform Admin / Security Officer
    participant API as Security API (/security/sentinel/run)
    participant Sentinel as SentinelRunner Engine
    participant DB as Relational Store (PostgreSQL)
    participant Client as Internal TestClient

    Admin->>API: POST /api/v1/security/sentinel/run
    API->>Sentinel: run_suite(started_by_user_id)
    Sentinel->>DB: INSERT security_test_runs (status='RUNNING')
    
    Note over Sentinel: Setup synthetic Victim (Alpha) and Attacker (Bravo) workspaces
    Sentinel->>DB: Seed tenant-alpha, tenant-bravo, credentials, policies
    
    Note over Sentinel,Client: Probe 1: Route Tampering
    Sentinel->>Client: GET /tenants/{alpha_id}/documents with Bravo token
    Client-->>Sentinel: HTTP 403 Forbidden (PASSED)
    
    Note over Sentinel,Client: Probe 2: Cross-Tenant File Download
    Sentinel->>Client: GET /tenants/{alpha_id}/documents/{doc}/download with Bravo token
    Client-->>Sentinel: HTTP 403 / 404 (0 bytes leaked) (PASSED)
    
    Note over Sentinel,Client: Probe 3: Vector Store Leakage
    Sentinel->>Client: POST /tenants/{bravo_id}/chat/query (Alpha confidential facts)
    Client-->>Sentinel: INSUFFICIENT_EVIDENCE (0 Alpha chunks leaked) (PASSED)
    
    Note over Sentinel,Client: Probe 4: Prompt Injection Defense
    Sentinel->>Client: POST /tenants/{alpha_id}/chat/query ("SYSTEM OVERRIDE...")
    Client-->>Sentinel: INSUFFICIENT_EVIDENCE (Model boundaries hold) (PASSED)
    
    Note over Sentinel,Client: Probe 5: Inactive Version Exclusion
    Sentinel->>Client: POST /tenants/{alpha_id}/chat/query (Query on REVIEW facts)
    Client-->>Sentinel: INSUFFICIENT_EVIDENCE (Candidate facts excluded) (PASSED)
    
    Note over Sentinel,Client: Probe 6: Unauthorized Role Escalation
    Sentinel->>Client: POST /tenants/{alpha_id}/versions/{v}/approve with EMPLOYEE token
    Client-->>Sentinel: HTTP 403 Forbidden (PASSED)
    
    Note over Sentinel,Client: Probe 7: Executable File Upload
    Sentinel->>Client: POST /tenants/{alpha_id}/documents with payload.exe
    Client-->>Sentinel: HTTP 415 Unsupported Media Type (PASSED)

    Sentinel->>DB: INSERT security_test_results (7 passed results)
    Sentinel->>DB: UPDATE security_test_runs (status='PASSED', pass_rate=100.0)
    Sentinel-->>API: SecurityTestRun Summary
    API-->>Admin: HTTP 201 Created (100% Pass Rate; 0 Breaches)
```

