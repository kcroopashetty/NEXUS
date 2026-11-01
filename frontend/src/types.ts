/** NEXUS Enterprise Frontend TypeScript Type Definitions */

export type UserRole = "PLATFORM_ADMIN" | "CLIENT_ADMIN" | "EMPLOYEE";

export interface TenantInfo {
  id: string;
  slug: string;
  name: string;
  status: string;
  created_at: string;
}

export interface TenantMemberItem {
  id: string;
  tenant_id: string;
  user_id: string;
  user_email: string;
  user_display_name: string;
  role: "CLIENT_ADMIN" | "EMPLOYEE";
  status: "ACTIVE" | "REVOKED" | "SUSPENDED";
  last_permission_change_at: string;
  created_at: string;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  platform_role: string;
  status: string;
  memberships: Array<{
    tenant_id: string;
    tenant_name: string;
    tenant_slug: string;
    role: UserRole;
    status: string;
  }>;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  timestamp: string;
  text: string;
  response?: ChatResponse;
  trace?: QueryTrace;
  latencyMs?: number;
}

export interface DocumentRecord {
  id: string;
  tenant_id: string;
  title: string;
  category?: string;
  description?: string;
  authority_level: "OFFICIAL_POLICY" | "GUIDELINE" | "INFORMAL_NOTE";
  effective_date?: string;
  created_at: string;
  versions?: DocumentVersionRecord[];
}

export interface DocumentVersionRecord {
  id: string;
  tenant_id: string;
  document_id: string;
  version_number: number;
  status: "UPLOADED" | "EXTRACTING" | "CHUNKING" | "EMBEDDING" | "REVIEW" | "ACTIVE" | "SUPERSEDED" | "FAILED";
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  quality_score?: number;
  ocr_needed?: boolean;
  quality_report?: QualityReport;
  created_at: string;
}

export interface QualityReport {
  score: number;
  ocr_needed: boolean;
  diagnostics: {
    total_pages: number;
    total_characters: number;
    char_density_per_page: number;
    garbled_char_ratio: number;
    whitespace_ratio: number;
    tables_detected: boolean;
  };
  passed_checks: string[];
  warnings: string[];
}

export interface ChangeItem {
  id: string;
  change_type: "ADDITION" | "REMOVAL" | "MODIFICATION";
  section_heading?: string;
  old_text?: string;
  new_text?: string;
  old_page?: number;
  new_page?: number;
  classification?: "SLA" | "FINANCIAL" | "GOVERNANCE" | "SECURITY" | "GENERAL";
  confidence?: number;
}

export interface ImpactSuggestion {
  id: string;
  related_document_id: string;
  rationale: string;
  basis: string;
  review_status: string;
}

export interface VersionDiffReport {
  change_id: string;
  document_id: string;
  document_title: string;
  from_version_id?: string;
  to_version_id: string;
  status: string;
  summary?: string;
  items: ChangeItem[];
  impact_suggestions: ImpactSuggestion[];
}

export interface GroundedClaim {
  claim_text: string;
  citation_id: string;
  verified?: boolean;
}

export interface CitedPassage {
  chunk_id: string;
  version_id: string;
  document_title: string;
  page_start: number;
  page_end: number;
  authority_level: string;
  chunk_text: string;
}

export interface EvidencePassport {
  status: "ANSWERED" | "INSUFFICIENT_EVIDENCE" | "CONFLICT" | "ERROR";
  answer: string;
  grounding_score: number;
  grounding_verified: boolean;
  claims: GroundedClaim[];
  cited_passages: CitedPassage[];
  uncertainty_note?: string;
}

export interface QueryTraceStage {
  stage: string;
  status: "PASSED" | "FAILED" | "SKIPPED";
  duration_ms: number;
  detail: string;
}

export interface QueryTrace {
  trace_id: string;
  query_id: string;
  total_latency_ms: number;
  stages: QueryTraceStage[];
}

export interface ChatResponse {
  query_id: string;
  status: "ANSWERED" | "INSUFFICIENT_EVIDENCE" | "CONFLICT" | "ERROR";
  answer: string;
  passport: EvidencePassport;
  evidence: CitedPassage[];
  latency_ms: number;
}

export interface SecurityTestResultItem {
  id: string;
  test_key: string;
  title: string;
  expected_result: string;
  actual_result: string;
  passed: boolean;
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  evidence: Record<string, any>;
}

export interface SecurityTestRunItem {
  id: string;
  suite_name: string;
  status: "RUNNING" | "PASSED" | "FAILED" | "ERROR";
  summary: {
    total_tests: number;
    passed_tests: number;
    failed_tests: number;
    pass_rate_percent: number;
    execution_duration_seconds: number;
  };
  started_at: string;
  completed_at?: string;
  results?: SecurityTestResultItem[];
}

export interface AuditEventItem {
  id: string;
  tenant_id: string;
  actor_user_id?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  outcome: string;
  metadata: Record<string, any>;
  created_at: string;
}

