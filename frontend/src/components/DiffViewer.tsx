import { useState } from "react";
import { Check, X, Sparkles } from "lucide-react";
import { VersionDiffReport } from "../types";

interface Props {
  diff: VersionDiffReport;
  isClientAdmin: boolean;
  onApprove: (versionId: string) => Promise<void>;
  onReject: (versionId: string) => Promise<void>;
}

export function DiffViewer({ diff, isClientAdmin, onApprove, onReject }: Props) {
  const [loadingAction, setLoadingAction] = useState<"approve" | "reject" | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const handleApprove = async () => {
    try {
      setLoadingAction("approve");
      await onApprove(diff.to_version_id);
      setFeedback({ type: "success", message: "Candidate version atomically approved! It is now ACTIVE." });
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Approval failed." });
    } finally {
      setLoadingAction(null);
    }
  };

  const handleReject = async () => {
    try {
      setLoadingAction("reject");
      await onReject(diff.to_version_id);
      setFeedback({ type: "success", message: "Candidate version rejected." });
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Rejection failed." });
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Header and Summary */}
      <div
        style={{
          backgroundColor: "var(--bg-secondary)",
          padding: "20px",
          borderRadius: "8px",
          border: "1px solid var(--border-color)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>
            KNOWLEDGE CHANGE INTELLIGENCE
          </div>
          <h2 style={{ fontSize: "18px", fontWeight: 700, margin: 0 }}>{diff.document_title}</h2>
          <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
            {diff.summary || "Deterministic clause-level comparison"}
          </div>
        </div>

        {/* Action bar for Admin */}
        {diff.status === "PENDING_REVIEW" && (
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            {isClientAdmin ? (
              <>
                <button
                  onClick={handleReject}
                  disabled={loadingAction !== null}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "8px 16px",
                    borderRadius: "6px",
                    backgroundColor: "rgba(239, 68, 68, 0.1)",
                    border: "1px solid var(--danger)",
                    color: "var(--danger)",
                    fontWeight: 600,
                    fontSize: "13px",
                    cursor: "pointer",
                  }}
                >
                  <X size={16} />
                  {loadingAction === "reject" ? "Rejecting..." : "Reject Candidate"}
                </button>

                <button
                  onClick={handleApprove}
                  disabled={loadingAction !== null}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "8px 18px",
                    borderRadius: "6px",
                    backgroundColor: "var(--brand-primary)",
                    border: "none",
                    color: "#fff",
                    fontWeight: 600,
                    fontSize: "13px",
                    cursor: "pointer",
                  }}
                >
                  <Check size={16} />
                  {loadingAction === "approve" ? "Activating..." : "Approve & Activate"}
                </button>
              </>
            ) : (
              <div style={{ fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic" }}>
                Approval restricted to Client Administrators
              </div>
            )}
          </div>
        )}

        {diff.status === "APPROVED" && (
          <div
            style={{
              padding: "6px 14px",
              borderRadius: "20px",
              backgroundColor: "rgba(16, 185, 129, 0.1)",
              border: "1px solid var(--success)",
              color: "var(--success)",
              fontWeight: 600,
              fontSize: "12px",
            }}
          >
            ✓ Version Approved & Active
          </div>
        )}
      </div>

      {feedback && (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: "6px",
            backgroundColor: feedback.type === "success" ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)",
            border: `1px solid ${feedback.type === "success" ? "var(--success)" : "var(--danger)"}`,
            color: feedback.type === "success" ? "var(--success)" : "var(--danger)",
            fontSize: "13px",
            fontWeight: 500,
          }}
        >
          {feedback.message}
        </div>
      )}

      {/* Policy Impact Suggestions */}
      {diff.impact_suggestions && diff.impact_suggestions.length > 0 && (
        <div
          style={{
            backgroundColor: "rgba(99, 102, 241, 0.08)",
            padding: "16px 20px",
            borderRadius: "8px",
            border: "1px solid rgba(99, 102, 241, 0.3)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
            <Sparkles size={16} color="var(--brand-primary)" />
            <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--brand-primary)" }}>
              KNOWLEDGE INTEGRITY: POLICY IMPACT NOTICES
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {diff.impact_suggestions.map((sug) => (
              <div key={sug.id} style={{ fontSize: "13px", color: "var(--text-primary)" }}>
                • {sug.rationale}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Clause-by-clause changes */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <h3 style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-muted)", margin: "8px 0" }}>
          CLAUSE-LEVEL DIFFERENCES ({diff.items.length})
        </h3>

        {diff.items.length === 0 ? (
          <div
            style={{
              padding: "24px",
              textAlign: "center",
              color: "var(--text-muted)",
              backgroundColor: "var(--bg-secondary)",
              borderRadius: "8px",
            }}
          >
            No textual changes detected between selected versions.
          </div>
        ) : (
          diff.items.map((item) => {
            const isMod = item.change_type === "MODIFICATION";
            const isAdd = item.change_type === "ADDITION";
            const isRem = item.change_type === "REMOVAL";

            const borderColor = isAdd ? "var(--success)" : isRem ? "var(--danger)" : "var(--warning)";
            const bgTint = isAdd
              ? "rgba(16, 185, 129, 0.05)"
              : isRem
              ? "rgba(239, 68, 68, 0.05)"
              : "rgba(245, 158, 11, 0.05)";

            return (
              <div
                key={item.id}
                style={{
                  backgroundColor: bgTint,
                  border: `1px solid ${borderColor}`,
                  borderLeft: `4px solid ${borderColor}`,
                  borderRadius: "6px",
                  padding: "16px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "10px",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: "4px",
                        backgroundColor: borderColor,
                        color: "#fff",
                      }}
                    >
                      {item.change_type}
                    </span>
                    {item.classification && (
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 600,
                          padding: "2px 8px",
                          borderRadius: "4px",
                          backgroundColor: "var(--bg-surface)",
                          color: "var(--text-secondary)",
                          border: "1px solid var(--border-color)",
                        }}
                      >
                        {item.classification}
                      </span>
                    )}
                  </div>

                  <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    {isMod && `Page ${item.old_page} → Page ${item.new_page}`}
                    {isAdd && `Added to Page ${item.new_page}`}
                    {isRem && `Removed from Page ${item.old_page}`}
                  </div>
                </div>

                {/* Diff text presentation */}
                {isMod ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "13px" }}>
                    <div style={{ color: "var(--danger)", backgroundColor: "rgba(239, 68, 68, 0.08)", padding: "8px 12px", borderRadius: "4px" }}>
                      <strong>Prior Active:</strong> {item.old_text}
                    </div>
                    <div style={{ color: "var(--success)", backgroundColor: "rgba(16, 185, 129, 0.08)", padding: "8px 12px", borderRadius: "4px" }}>
                      <strong>Candidate New:</strong> {item.new_text}
                    </div>
                  </div>
                ) : isAdd ? (
                  <div style={{ fontSize: "13px", color: "var(--success)" }}>
                    {item.new_text}
                  </div>
                ) : (
                  <div style={{ fontSize: "13px", color: "var(--danger)", textDecoration: "line-through" }}>
                    {item.old_text}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
