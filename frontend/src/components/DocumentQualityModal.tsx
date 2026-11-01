import { X, CheckCircle2, AlertTriangle, FileText, Database, ShieldAlert } from "lucide-react";
import { QualityReport } from "../types";

interface Props {
  filename: string;
  versionNumber: number;
  report: QualityReport | null;
  onClose: () => void;
}

export function DocumentQualityModal({ filename, versionNumber, report, onClose }: Props) {
  if (!report) return null;

  const scorePct = Math.round(report.score * 100);
  const isHealthy = report.score >= 0.7 && !report.ocr_needed;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "20px",
      }}
    >
      <div
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderRadius: "12px",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: "640px",
          maxHeight: "90vh",
          overflowY: "auto",
          padding: "24px",
          boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <FileText size={22} color="var(--brand-primary)" />
            <div>
              <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Document Quality Inspector</h3>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                {filename} (v{versionNumber})
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: "4px",
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Quality Score Banner */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 20px",
            borderRadius: "8px",
            backgroundColor: isHealthy ? "rgba(16, 185, 129, 0.1)" : "rgba(245, 158, 11, 0.1)",
            border: `1px solid ${isHealthy ? "var(--success)" : "var(--warning)"}`,
            marginBottom: "24px",
          }}
        >
          <div>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Inspection Outcome
            </div>
            <div
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: isHealthy ? "var(--success)" : "var(--warning)",
                marginTop: "2px",
              }}
            >
              {isHealthy ? "Ingestion Quality Verified" : "Inspection Warnings Detected"}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "28px", fontWeight: 800, color: isHealthy ? "var(--success)" : "var(--warning)" }}>
              {scorePct}%
            </div>
            <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Completeness Score</div>
          </div>
        </div>

        {/* Metrics Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "12px",
            marginBottom: "24px",
          }}
        >
          <div
            style={{
              backgroundColor: "var(--bg-surface)",
              padding: "14px",
              borderRadius: "8px",
              border: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>OCR REQUIREMENT</div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 600, fontSize: "14px" }}>
              {report.ocr_needed ? (
                <>
                  <ShieldAlert size={16} color="var(--danger)" />
                  <span style={{ color: "var(--danger)" }}>OCR Needed (Scanned)</span>
                </>
              ) : (
                <>
                  <CheckCircle2 size={16} color="var(--success)" />
                  <span style={{ color: "var(--success)" }}>Digital Text Native</span>
                </>
              )}
            </div>
          </div>

          <div
            style={{
              backgroundColor: "var(--bg-surface)",
              padding: "14px",
              borderRadius: "8px",
              border: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>TABLE DETECTION</div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 600, fontSize: "14px" }}>
              <Database size={16} color="var(--info)" />
              <span>{report.diagnostics?.tables_detected ? "Tables Preserved" : "Standard Paragraphs"}</span>
            </div>
          </div>

          <div
            style={{
              backgroundColor: "var(--bg-surface)",
              padding: "14px",
              borderRadius: "8px",
              border: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>PAGE CHAR DENSITY</div>
            <div style={{ fontWeight: 600, fontSize: "14px" }}>
              {report.diagnostics?.char_density_per_page ?? 0} chars / page
            </div>
          </div>

          <div
            style={{
              backgroundColor: "var(--bg-surface)",
              padding: "14px",
              borderRadius: "8px",
              border: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>GARBLED CHAR RATIO</div>
            <div style={{ fontWeight: 600, fontSize: "14px" }}>
              {((report.diagnostics?.garbled_char_ratio ?? 0) * 100).toFixed(2)}%
            </div>
          </div>
        </div>

        {/* Passed Checks */}
        {report.passed_checks && report.passed_checks.length > 0 && (
          <div style={{ marginBottom: "20px" }}>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "8px" }}>
              PASSED QUALITY CHECKS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {report.passed_checks.map((chk, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    fontSize: "13px",
                    color: "var(--text-secondary)",
                  }}
                >
                  <CheckCircle2 size={14} color="var(--success)" />
                  <span>{chk}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Warnings */}
        {report.warnings && report.warnings.length > 0 && (
          <div>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--warning)", marginBottom: "8px" }}>
              INSPECTION WARNINGS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {report.warnings.map((w, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    fontSize: "13px",
                    color: "var(--warning)",
                  }}
                >
                  <AlertTriangle size={14} color="var(--warning)" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

