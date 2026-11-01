import React, { useState, useEffect, useCallback } from "react";
import {
  UserPlus,
  Shield,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Trash2,
  Lock,
  Clock,
} from "lucide-react";
import { TenantMemberItem } from "../types";
import { api } from "../api";

interface TeamManagementViewProps {
  tenantId: string;
  tenantName: string;
  isClientAdmin: boolean;
}

export const TeamManagementView: React.FC<TeamManagementViewProps> = ({
  tenantId,
  tenantName,
  isClientAdmin,
}) => {
  const [members, setMembers] = useState<TenantMemberItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // New member form
  const [newEmail, setNewEmail] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newRole, setNewRole] = useState<"EMPLOYEE" | "CLIENT_ADMIN">("EMPLOYEE");
  const [newPassword, setNewPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showInviteForm, setShowInviteForm] = useState(false);

  const loadMembers = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await api.listMembers(tenantId);
      setMembers(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load workspace members.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  const handleAssignMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail.trim()) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await api.assignMember(tenantId, {
        email: newEmail.trim(),
        display_name: newDisplayName.trim() || undefined,
        role: newRole,
        password: newPassword.trim() || undefined,
      });

      setSuccessMessage(`Successfully assigned ${newEmail} to ${tenantName} with role ${newRole}!`);
      setNewEmail("");
      setNewDisplayName("");
      setNewPassword("");
      setShowInviteForm(false);
      await loadMembers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to assign member.";
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdateRole = async (userId: string, targetRole: "EMPLOYEE" | "CLIENT_ADMIN") => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      await api.updateMemberRole(tenantId, userId, { role: targetRole });
      setSuccessMessage(`Role updated to ${targetRole}. Permission Change Guard updated timestamp immediately.`);
      await loadMembers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update member role.";
      setErrorMessage(msg);
    }
  };

  const handleRevokeMember = async (userId: string, email: string) => {
    if (!window.confirm(`Are you sure you want to revoke workspace access for ${email}?`)) {
      return;
    }

    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      await api.revokeMember(tenantId, userId);
      setSuccessMessage(`Access revoked for ${email}. Next query attempt by this user will be immediately rejected.`);
      await loadMembers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to revoke member.";
      setErrorMessage(msg);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Title & Actions Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 700 }}>
              Team Members & Data Clearance ({members.length})
            </h2>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                padding: "3px 8px",
                borderRadius: "4px",
                backgroundColor: "rgba(16, 185, 129, 0.15)",
                color: "var(--success)",
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}
            >
              <CheckCircle2 size={12} /> Permission Change Guard: Active
            </span>
          </div>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
            Enforce real-time role clearance, document restrictions, and zero-staleness access revocation in {tenantName}
          </div>
        </div>

        {isClientAdmin && (
          <div style={{ display: "flex", gap: "10px" }}>
            <button
              onClick={() => loadMembers()}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                borderRadius: "6px",
                border: "1px solid var(--border-color)",
                backgroundColor: "var(--bg-secondary)",
                color: "var(--text-secondary)",
                cursor: "pointer",
                fontSize: "13px",
              }}
            >
              <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>
            <button
              onClick={() => setShowInviteForm(!showInviteForm)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                borderRadius: "6px",
                border: "none",
                backgroundColor: "var(--brand-primary)",
                color: "#ffffff",
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: 600,
              }}
            >
              <UserPlus size={15} />
              <span>{showInviteForm ? "Close Form" : "Assign / Invite Employee"}</span>
            </button>
          </div>
        )}
      </div>

      {/* Messages */}
      {errorMessage && (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: "8px",
            backgroundColor: "rgba(239, 68, 68, 0.12)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            color: "var(--error)",
            fontSize: "13px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <AlertTriangle size={16} />
          <span>{errorMessage}</span>
        </div>
      )}

      {successMessage && (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: "8px",
            backgroundColor: "rgba(16, 185, 129, 0.12)",
            border: "1px solid rgba(16, 185, 129, 0.3)",
            color: "var(--success)",
            fontSize: "13px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <CheckCircle2 size={16} />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Assign / Invite Form */}
      {showInviteForm && (
        <div
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderRadius: "8px",
            border: "1px solid var(--brand-primary)",
            padding: "20px 24px",
          }}
        >
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", fontWeight: 700, display: "flex", alignItems: "center", gap: "8px" }}>
            <UserPlus size={16} color="var(--brand-primary)" />
            Assign Employee to Workspace
          </h3>
          <form onSubmit={handleAssignMember} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                Employee Email *
              </label>
              <input
                type="email"
                required
                placeholder="colleague@alpha.corp"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                  boxSizing: "border-box",
                }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                Display Name
              </label>
              <input
                type="text"
                placeholder="e.g. Sarah Jenkins"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                  boxSizing: "border-box",
                }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                Role & Data Permission Level
              </label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as "EMPLOYEE" | "CLIENT_ADMIN")}
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                  boxSizing: "border-box",
                }}
              >
                <option value="EMPLOYEE">EMPLOYEE (Standard / Limited Clearance)</option>
                <option value="CLIENT_ADMIN">CLIENT_ADMIN (Full Workspace Clearance & Management)</option>
              </select>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                Initial Password (Optional)
              </label>
              <input
                type="password"
                placeholder="Defaults to temp password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                  boxSizing: "border-box",
                }}
              />
            </div>

            <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "4px" }}>
              <button
                type="button"
                onClick={() => setShowInviteForm(false)}
                style={{
                  padding: "8px 16px",
                  borderRadius: "6px",
                  border: "1px solid var(--border-color)",
                  backgroundColor: "transparent",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                  fontSize: "13px",
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                style={{
                  padding: "8px 20px",
                  borderRadius: "6px",
                  border: "none",
                  backgroundColor: "var(--brand-primary)",
                  color: "#ffffff",
                  cursor: isSubmitting ? "not-allowed" : "pointer",
                  fontSize: "13px",
                  fontWeight: 600,
                }}
              >
                {isSubmitting ? "Assigning..." : "Confirm & Assign"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Permission Clearance Architecture Callout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "16px",
        }}
      >
        <div
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
            padding: "16px 20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
            <Shield size={16} color="var(--brand-primary)" />
            <span style={{ fontSize: "14px", fontWeight: 700 }}>EMPLOYEE Role (Limited Access)</span>
          </div>
          <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: "1.6" }}>
            <li>Can query general policies, SOPs, and guidelines in this workspace.</li>
            <li><strong>BLOCKED:</strong> Cannot retrieve documents marked as Confidential or Admin-Only.</li>
            <li><strong>BLOCKED:</strong> Cannot upload documents, approve diffs, or execute security test suites.</li>
            <li>Enforced dynamically at retrieval query-time via Permission Change Guard.</li>
          </ul>
        </div>

        <div
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
            padding: "16px 20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
            <Lock size={16} color="var(--warning)" />
            <span style={{ fontSize: "14px", fontWeight: 700 }}>CLIENT_ADMIN Role (Full Access)</span>
          </div>
          <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: "1.6" }}>
            <li>Full query clearance over all workspace policies (including Confidential).</li>
            <li>Can upload new policy documents and candidate versions (v2, v3).</li>
            <li>Can review Change Intelligence diffs and atomically activate policies.</li>
            <li>Can assign/revoke employee memberships and run continuous Red-Team Sentinel tests.</li>
          </ul>
        </div>
      </div>

      {/* Members Table */}
      <div
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderRadius: "8px",
          border: "1px solid var(--border-color)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "14px 20px",
            borderBottom: "1px solid var(--border-color)",
            backgroundColor: "var(--bg-surface)",
            fontSize: "13px",
            fontWeight: 700,
            color: "var(--text-primary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span>ACTIVE WORKSPACE ROSTER</span>
          <span style={{ fontSize: "11px", fontWeight: 400, color: "var(--text-muted)" }}>
            PostgreSQL Authoritative State
          </span>
        </div>

        {isLoading ? (
          <div style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
            Loading workspace team roster...
          </div>
        ) : members.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
            No members assigned to this workspace yet. Click &quot;Assign / Invite Employee&quot; to begin.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {members.map((m) => {
              const isRevoked = m.status === "REVOKED";
              return (
                <div
                  key={m.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "14px 20px",
                    borderBottom: "1px solid var(--border-color)",
                    backgroundColor: isRevoked ? "rgba(239, 68, 68, 0.04)" : "transparent",
                    transition: "background-color 0.15s ease",
                  }}
                >
                  {/* Left: User Info */}
                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <div
                      style={{
                        width: "36px",
                        height: "36px",
                        borderRadius: "50%",
                        backgroundColor: isRevoked
                          ? "rgba(239, 68, 68, 0.15)"
                          : m.role === "CLIENT_ADMIN"
                          ? "rgba(99, 102, 241, 0.15)"
                          : "rgba(100, 116, 139, 0.15)",
                        color: isRevoked
                          ? "var(--error)"
                          : m.role === "CLIENT_ADMIN"
                          ? "var(--brand-primary)"
                          : "var(--text-secondary)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontWeight: 700,
                        fontSize: "13px",
                      }}
                    >
                      {m.user_display_name ? m.user_display_name.charAt(0).toUpperCase() : m.user_email.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontSize: "14px", fontWeight: 600, color: isRevoked ? "var(--text-muted)" : "var(--text-primary)" }}>
                          {m.user_display_name || m.user_email.split("@")[0]}
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: "4px",
                            backgroundColor:
                              m.role === "CLIENT_ADMIN"
                                ? "rgba(99, 102, 241, 0.15)"
                                : "rgba(100, 116, 139, 0.15)",
                            color:
                              m.role === "CLIENT_ADMIN"
                                ? "var(--brand-primary)"
                                : "var(--text-secondary)",
                          }}
                        >
                          {m.role}
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: "4px",
                            backgroundColor: isRevoked
                              ? "rgba(239, 68, 68, 0.15)"
                              : "rgba(16, 185, 129, 0.15)",
                            color: isRevoked ? "var(--error)" : "var(--success)",
                          }}
                        >
                          {m.status}
                        </span>
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
                        {m.user_email}
                      </div>
                    </div>
                  </div>

                  {/* Right: Last Permission Change Timestamp & Actions */}
                  <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                    <div style={{ textAlign: "right", fontSize: "11px", color: "var(--text-muted)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "4px", justifyContent: "flex-end" }}>
                        <Clock size={12} />
                        <span>Guard Checkpoint:</span>
                      </div>
                      <div>{new Date(m.last_permission_change_at).toLocaleString()}</div>
                    </div>

                    {isClientAdmin && (
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        {/* Toggle Role Button */}
                        <button
                          onClick={() => handleUpdateRole(m.user_id, m.role === "CLIENT_ADMIN" ? "EMPLOYEE" : "CLIENT_ADMIN")}
                          title={`Switch to ${m.role === "CLIENT_ADMIN" ? "EMPLOYEE" : "CLIENT_ADMIN"}`}
                          style={{
                            padding: "6px 10px",
                            borderRadius: "4px",
                            border: "1px solid var(--border-color)",
                            backgroundColor: "var(--bg-surface)",
                            color: "var(--text-secondary)",
                            cursor: "pointer",
                            fontSize: "11px",
                            fontWeight: 600,
                          }}
                        >
                          Change to {m.role === "CLIENT_ADMIN" ? "EMPLOYEE" : "ADMIN"}
                        </button>

                        {/* Revoke Button */}
                        {!isRevoked ? (
                          <button
                            onClick={() => handleRevokeMember(m.user_id, m.user_email)}
                            title="Revoke clearance immediately (Permission Change Guard)"
                            style={{
                              padding: "6px 10px",
                              borderRadius: "4px",
                              border: "1px solid rgba(239, 68, 68, 0.3)",
                              backgroundColor: "rgba(239, 68, 68, 0.08)",
                              color: "var(--error)",
                              cursor: "pointer",
                              fontSize: "11px",
                              fontWeight: 600,
                              display: "flex",
                              alignItems: "center",
                              gap: "4px",
                            }}
                          >
                            <Trash2 size={12} />
                            <span>Revoke</span>
                          </button>
                        ) : (
                          <button
                            onClick={() => handleUpdateRole(m.user_id, "EMPLOYEE")}
                            title="Restore active clearance"
                            style={{
                              padding: "6px 10px",
                              borderRadius: "4px",
                              border: "1px solid rgba(16, 185, 129, 0.3)",
                              backgroundColor: "rgba(16, 185, 129, 0.08)",
                              color: "var(--success)",
                              cursor: "pointer",
                              fontSize: "11px",
                              fontWeight: 600,
                            }}
                          >
                            Restore Access
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
