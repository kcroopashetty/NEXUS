import { CheckCircle2, AlertTriangle, Clock } from "lucide-react";
import { QueryTrace } from "../types";

interface Props {
  trace: QueryTrace;
}

export function QueryTraceView({ trace }: Props) {
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
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
          borderBottom: "1px solid var(--border-color)",
          paddingBottom: "12px",
        }}
      >
        <div>
          <div style={{ fontSize: "14px", fontWeight: 700 }}>QUERY TRACE DIAGNOSTICS</div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
            Observable Stage-by-Stage Pipeline Execution
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "var(--text-muted)" }}>
          <Clock size={14} color="var(--color-intelligence-teal)" />
          <span style={{ fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>
            Total Latency: <strong>{trace.total_latency_ms} ms</strong>
          </span>
        </div>
      </div>

      {/* Stage Timeline */}
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {trace.stages.map((stage, idx) => {
          const isPassed = stage.status === "PASSED";
          return (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 14px",
                borderRadius: "6px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                {isPassed ? (
                  <CheckCircle2 size={16} color="var(--success)" />
                ) : (
                  <AlertTriangle size={16} color="var(--danger)" />
                )}
                <div>
                  <div style={{ fontSize: "13px", fontWeight: 600 }}>{stage.stage}</div>
                  <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>{stage.detail}</div>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: "9999px",
                    fontFamily: "var(--font-mono)",
                    backgroundColor: isPassed ? "var(--color-success-container)" : "var(--color-error-container)",
                    border: `1px solid ${isPassed ? "rgba(35, 134, 90, 0.25)" : "rgba(186, 26, 26, 0.25)"}`,
                    color: isPassed ? "var(--success)" : "var(--danger)",
                  }}
                >
                  {stage.status}
                </span>
                <span
                  style={{
                    fontSize: "11px",
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-mono)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {stage.duration_ms} ms
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
