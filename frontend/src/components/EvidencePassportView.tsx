import { ShieldCheck, AlertCircle, FileCheck, HelpCircle } from "lucide-react";
import { EvidencePassport, CitedPassage } from "../types";

interface Props {
  passport: EvidencePassport;
  passages: CitedPassage[];
}

export function EvidencePassportView({ passport, passages }: Props) {
  const isAnswered = passport.status === "ANSWERED";
  const isRefusal = passport.status === "INSUFFICIENT_EVIDENCE";
  const isConflict = passport.status === "CONFLICT";

  const scorePct = Math.round((passport.grounding_score ?? 1.0) * 100);

  return (
    <div
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderRadius: "8px",
        border: "1px solid var(--border-color)",
        padding: "20px",
        marginTop: "16px",
      }}
    >
      {/* Passport Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid var(--border-color)",
          paddingBottom: "14px",
          marginBottom: "16px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <ShieldCheck size={20} color={isAnswered ? "var(--success)" : isConflict ? "var(--warning)" : "var(--danger)"} />
          <div>
            <div style={{ fontSize: "14px", fontWeight: 700 }}>EVIDENCE PASSPORT</div>
            <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Server-Validated Claim Grounding & Authority Record
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div
            style={{
              padding: "4px 12px",
              borderRadius: "9999px",
              fontSize: "11px",
              fontWeight: 700,
              fontFamily: "var(--font-mono)",
              fontVariantNumeric: "tabular-nums",
              backgroundColor: isAnswered
                ? "var(--color-success-container)"
                : isConflict
                ? "var(--color-warning-container)"
                : "var(--color-error-container)",
              color: isAnswered ? "var(--success)" : isConflict ? "var(--warning)" : "var(--danger)",
              border: `1px solid ${
                isAnswered
                  ? "rgba(35, 134, 90, 0.25)"
                  : isConflict
                  ? "rgba(197, 138, 50, 0.25)"
                  : "rgba(186, 26, 26, 0.25)"
              }`,
            }}
          >
            {passport.status}
          </div>

          <div style={{ textAlign: "right" }}>
            <span
              style={{
                fontSize: "14px",
                fontWeight: 700,
                color: "var(--text-primary)",
                fontFamily: "var(--font-mono)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {scorePct}%
            </span>
            <span style={{ fontSize: "11px", color: "var(--text-muted)", marginLeft: "4px" }}>Grounded</span>
          </div>
        </div>
      </div>

      {/* Uncertainty or Conflict Notes */}
      {isConflict && (
        <div
          style={{
            backgroundColor: "var(--color-warning-container)",
            border: "1px solid rgba(197, 138, 50, 0.3)",
            borderRadius: "6px",
            padding: "12px",
            marginBottom: "16px",
            fontSize: "13px",
            color: "var(--warning)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <AlertCircle size={16} />
          <span>Contradictory policy provisions detected across active sources. Silently selecting one was blocked.</span>
        </div>
      )}

      {isRefusal && (
        <div
          style={{
            backgroundColor: "var(--color-error-container)",
            border: "1px solid rgba(186, 26, 26, 0.3)",
            borderRadius: "6px",
            padding: "12px",
            marginBottom: "16px",
            fontSize: "13px",
            color: "var(--danger)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <HelpCircle size={16} />
          <span>
            {passport.uncertainty_note || "Insufficient active evidence to support an answer. Refusal issued to prevent hallucination."}
          </span>
        </div>
      )}

      {/* Grounded Claims */}
      {passport.claims && passport.claims.length > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--text-muted)", marginBottom: "8px" }}>
            GROUNDED CLAIMS ({passport.claims.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {passport.claims.map((claim, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "8px",
                  fontSize: "13px",
                  padding: "8px 10px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                }}
              >
                <FileCheck size={16} color="var(--success)" style={{ marginTop: "2px", flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <span>{claim.claim_text}</span>
                  <span
                    style={{
                      marginLeft: "8px",
                      fontSize: "10px",
                      padding: "2px 8px",
                      borderRadius: "9999px",
                      backgroundColor: "var(--color-secondary-container)",
                      color: "var(--color-secondary)",
                      border: "1px solid rgba(39, 139, 155, 0.25)",
                      fontWeight: 600,
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    Citation #{idx + 1}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Cited Passages */}
      {passages && passages.length > 0 && (
        <div>
          <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--text-muted)", marginBottom: "8px" }}>
            VERIFIED SOURCE PASSAGES ({passages.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {passages.map((p, idx) => (
              <div
                key={p.chunk_id || idx}
                style={{
                  padding: "12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "6px",
                    fontSize: "12px",
                  }}
                >
                  <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {p.document_title} • Page {p.page_start}
                  </div>
                  <span
                    style={{
                      fontSize: "10px",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      backgroundColor: "rgba(16, 185, 129, 0.1)",
                      color: "var(--success)",
                      fontWeight: 600,
                    }}
                  >
                    {p.authority_level || "OFFICIAL_POLICY"}
                  </span>
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-secondary)", fontStyle: "italic", lineHeight: "1.5" }}>
                  "{p.chunk_text}"
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
