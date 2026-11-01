/** Centralized Typed NEXUS API Client */

import {
  TenantInfo,
  UserProfile,
  DocumentRecord,
  DocumentVersionRecord,
  QualityReport,
  VersionDiffReport,
  ChatResponse,
  QueryTrace,
  SecurityTestRunItem,
  AuditEventItem,
  TenantMemberItem,
} from "./types";

const BASE_URL = "/api/v1";

class NexusApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const res = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      credentials: "include", // Transmit HttpOnly server-side session cookies (prevents XSS token exposure)
      headers,
    });

    if (!res.ok) {
      let errorMsg = `Request failed with status ${res.status}`;
      try {
        const errorJson = await res.json();
        if (errorJson.error?.message) {
          errorMsg = errorJson.error.message;
        } else if (errorJson.detail) {
          errorMsg = typeof errorJson.detail === "string" ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch {
        // fallback to text error
      }
      throw new Error(errorMsg);
    }

    return res.json() as Promise<T>;
  }

  // --- Auth & Tenants ---
  async login(email: string, password: string) {
    const res = await this.request<{ access_token: string; token_type: string; user: UserProfile }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    // Server has issued secure HttpOnly 'nexus_session' cookie.
    // Purge any tokens from client storage to guarantee zero token leakage via XSS/DevTools
    this.setToken(null);
    localStorage.removeItem("nexus_access_token");
    sessionStorage.clear();
    return res;
  }

  async getMe(): Promise<UserProfile> {
    return this.request<UserProfile>("/auth/me");
  }

  async logout() {
    try {
      await this.request("/auth/logout", { method: "POST" });
    } catch {
      // Ignore errors on logout
    } finally {
      this.setToken(null);
      localStorage.removeItem("nexus_access_token");
    }
  }

  async getTenants(): Promise<TenantInfo[]> {
    return this.request<TenantInfo[]>("/tenants");
  }

  // --- Documents & Ingestion ---
  async listDocuments(tenantId: string): Promise<DocumentRecord[]> {
    return this.request<DocumentRecord[]>(`/tenants/${tenantId}/documents`);
  }

  async getDocumentVersions(tenantId: string, docId: string): Promise<DocumentVersionRecord[]> {
    return this.request<DocumentVersionRecord[]>(`/tenants/${tenantId}/documents/${docId}/versions`);
  }

  async uploadDocument(tenantId: string, formData: FormData): Promise<{ document_id: string; version_id: string }> {
    return this.request<{ document_id: string; version_id: string }>(`/tenants/${tenantId}/documents`, {
      method: "POST",
      body: formData,
    });
  }

  async uploadCandidateVersion(tenantId: string, docId: string, formData: FormData): Promise<{ version_id: string }> {
    return this.request<{ version_id: string }>(`/tenants/${tenantId}/documents/${docId}/versions`, {
      method: "POST",
      body: formData,
    });
  }

  async deleteDocument(tenantId: string, docId: string): Promise<{ status: string; message: string; document_id: string }> {
    return this.request<{ status: string; message: string; document_id: string }>(`/tenants/${tenantId}/documents/${docId}`, {
      method: "DELETE",
    });
  }

  async deleteDocumentVersion(
    tenantId: string,
    docId: string,
    versionId: string
  ): Promise<{ status: string; message: string; version_id: string }> {
    return this.request<{ status: string; message: string; version_id: string }>(
      `/tenants/${tenantId}/documents/${docId}/versions/${versionId}`,
      {
        method: "DELETE",
      }
    );
  }

  async getQualityReport(tenantId: string, docId: string, versionId: string): Promise<QualityReport> {
    const data = await this.request<{ quality_report: QualityReport }>(
      `/tenants/${tenantId}/documents/${docId}/versions/${versionId}/quality-report`
    );
    return data.quality_report;
  }

  // --- Knowledge Change Intelligence ---
  async getVersionDiff(tenantId: string, docId: string, toVersionId?: string): Promise<VersionDiffReport> {
    const query = toVersionId ? `?to_version_id=${toVersionId}` : "";
    return this.request<VersionDiffReport>(`/tenants/${tenantId}/documents/${docId}/changes${query}`);
  }

  async approveVersion(tenantId: string, versionId: string) {
    return this.request<{ status: string; message: string }>(`/tenants/${tenantId}/versions/${versionId}/approve`, {
      method: "POST",
    });
  }

  async rejectVersion(tenantId: string, versionId: string) {
    return this.request<{ status: string; message: string }>(`/tenants/${tenantId}/versions/${versionId}/reject`, {
      method: "POST",
    });
  }

  // --- Grounded RAG Chat & Trace ---
  async sendChatQuery(tenantId: string, question: string): Promise<ChatResponse> {
    return this.request<ChatResponse>(`/tenants/${tenantId}/chat/query`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  }

  async getQueryTrace(tenantId: string, queryId: string): Promise<QueryTrace> {
    return this.request<QueryTrace>(`/tenants/${tenantId}/queries/${queryId}/trace`);
  }

  // --- Red-Team Sentinel ---
  async runSentinel(): Promise<SecurityTestRunItem> {
    return this.request<SecurityTestRunItem>("/security/sentinel/run", {
      method: "POST",
    });
  }

  async listSecurityRuns(): Promise<SecurityTestRunItem[]> {
    return this.request<SecurityTestRunItem[]>("/security/test-runs");
  }

  async getSecurityRunDetails(runId: string): Promise<SecurityTestRunItem> {
    return this.request<SecurityTestRunItem>(`/security/test-runs/${runId}`);
  }

  // --- Team & Permissions (Permission Change Guard) ---
  async listMembers(tenantId: string): Promise<TenantMemberItem[]> {
    return this.request<TenantMemberItem[]>(`/tenants/${tenantId}/members`);
  }

  async assignMember(
    tenantId: string,
    payload: { email: string; role: string; display_name?: string; password?: string }
  ): Promise<TenantMemberItem> {
    return this.request<TenantMemberItem>(`/tenants/${tenantId}/members`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateMemberRole(
    tenantId: string,
    userId: string,
    payload: { role?: string; status?: string }
  ): Promise<TenantMemberItem> {
    return this.request<TenantMemberItem>(`/tenants/${tenantId}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async revokeMember(tenantId: string, userId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/tenants/${tenantId}/members/${userId}`, {
      method: "DELETE",
    });
  }

  // --- Audit Trail ---
  async listAuditEvents(tenantId: string): Promise<AuditEventItem[]> {
    return this.request<AuditEventItem[]>(`/tenants/${tenantId}/audit-events`);
  }
}

export const api = new NexusApiClient();

