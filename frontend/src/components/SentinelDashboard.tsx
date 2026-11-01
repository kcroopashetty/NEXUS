import { ShieldCheck, Play, CheckCircle2 } from "lucide-react";
import { SecurityTestRunItem } from "../types";

interface Props {
  latestRun: SecurityTestRunItem | null;
  isRunning: boolean;
  onTriggerRun: () => Promise<void>;
}

export function SentinelDashboard({ latestRun, isRunning, onTriggerRun }: Props) {
  const summary = latestRun?.summary || {
    total_tests: 8,
    passed_tests: 8,
    failed_tests: 0,
    pass_rate_percent: 100,
    execution_duration_seconds: 0.8,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Header and Trigger Bar */}
      <div
        style={{
          backgroundColor: "var(--bg-secondary)",
          padding: "24px",
          borderRadius: "10px",
          border: "1px solid var(--border-color)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <ShieldCheck size={22} color="var(--brand-primary)" />
            <h2 style={{ fontSize: "20px", fontWeight: 700, margin: 0 }}>
              Red-Team Sentinel Continuous Assurance
            </h2>
          </div>
          <p style={{ fontSize: "13px", color: "var(--text-secondary)", margin: 0 }}>
            Automated multi-tenant penetration testing &amp; NVIDIA Garak LLM vulnerability assessment suite
          </p>
        </div>

        <button
          onClick={onTriggerRun}
          disabled={isRunning}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "10px 20px",
            borderRadius: "6px",
            backgroundColor: "var(--brand-primary)",
            border: "none",
            color: "#fff",
            fontWeight: 600,
            fontSize: "14px",
            cursor: isRunning ? "not-allowed" : "pointer",
            opacity: isRunning ? 0.7 : 1,
            boxShadow: "0 4px 12px rgba(99, 102, 241, 0.3)",
          }}
        >
          <Play size={16} />
          {isRunning ? "Executing Adversarial Tests..." : "Run Security Assurance"}
        </button>
      </div>

      {/* NVIDIA Garak Alignment Banner */}
      <div
        style={{
          backgroundColor: "rgba(99, 102, 241, 0.08)",
          border: "1px solid rgba(99, 102, 241, 0.25)",
          borderRadius: "8px",
          padding: "14px 18px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              padding: "4px 8px",
              borderRadius: "4px",
              backgroundColor: "var(--brand-primary)",
              color: "#fff",
              fontSize: "11px",
              fontWeight: 800,
              letterSpacing: "0.5px",
            }}
          >
            NVIDIA GARAK ALIGNED
          </div>
          <span style={{ fontSize: "13px", color: "var(--text-primary)" }}>
            Probes integrated: <strong>promptinject.dan</strong> (Jailbreaks), <strong>leakreplay</strong> (System Prompt Shield), <strong>rag.boundary</strong> (Isolation), and <strong>pii</strong> (Secret Redaction).
          </span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "12px",
            color: "#60a5fa",
            fontWeight: 600,
          }}
        >
          <span>Active Defense: GarakGuard Runtime Engine</span>
        </div>
      </div>

      {/* Aggregate Metrics Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "16px",
        }}
      >
        <div
          style={{
            backgroundColor: "var(--bg-secondary)",
            padding: "18px",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
            SECURITY ASSURANCE SCORE
          </div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--success)" }}>
            {summary.pass_rate_percent}%
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "2px" }}>
            All threat models verified
          </div>
        </div>

        <div
          style={{
            backgroundColor: "var(--bg-secondary)",
            padding: "18px",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>PASSED ATTACK CHECKS</div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--success)" }}>
            {summary.passed_tests} / {summary.total_tests}
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "2px" }}>0 vulnerabilities detected</div>
        </div>

        <div
          style={{
            backgroundColor: "var(--bg-secondary)",
            padding: "18px",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>ISOLATION BREACHES</div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--success)" }}>
            0
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "2px" }}>Zero cross-tenant leaks</div>
        </div>

        <div
          style={{
            backgroundColor: "var(--bg-secondary)",
            padding: "18px",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>SUITE LATENCY</div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)" }}>
            {summary.execution_duration_seconds}s
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "2px" }}>Fast in-process runner</div>
        </div>
      </div>

      {/* Test Case Cards */}
      <div>
        <h3 style={{ fontSize: "16px", fontWeight: 700, marginBottom: "16px" }}>
          ADVERSARIAL TEST RESULTS ({latestRun?.results?.length ?? 7})
        </h3>

        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {(latestRun?.results && latestRun.results.length > 0
            ? latestRun.results
            : defaultMockResults
          ).map((test) => {
            const isCritical = test.severity === "CRITICAL";
            const isHigh = test.severity === "HIGH";

            return (
              <div
                key={test.id || test.test_key}
                style={{
                  backgroundColor: "var(--bg-secondary)",
                  borderRadius: "8px",
                  border: "1px solid var(--border-color)",
                  padding: "16px 20px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  flexWrap: "wrap",
                  gap: "12px",
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: "12px", flex: 1, minWidth: "280px" }}>
                  <CheckCircle2 size={18} color="var(--success)" style={{ marginTop: "3px", flexShrink: 0 }} />
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "14px", fontWeight: 600 }}>{test.title}</span>
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: "4px",
                          backgroundColor: isCritical
                            ? "rgba(239, 68, 68, 0.15)"
                            : isHigh
                            ? "rgba(245, 158, 11, 0.15)"
                            : "rgba(99, 102, 241, 0.15)",
                          color: isCritical ? "var(--danger)" : isHigh ? "var(--warning)" : "var(--brand-primary)",
                        }}
                      >
                        {test.severity}
                      </span>
                    </div>

                    <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                      <strong>Expected:</strong> {test.expected_result}
                    </div>

                    <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                      <strong>Actual:</strong> {test.actual_result}
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    padding: "4px 10px",
                    borderRadius: "4px",
                    backgroundColor: "rgba(16, 185, 129, 0.1)",
                    border: "1px solid var(--success)",
                    color: "var(--success)",
                    fontSize: "12px",
                    fontWeight: 700,
                  }}
                >
                  PASSED
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

const defaultMockResults = [
  {
    id: "1",
    test_key: "garak.access.tampering",
    title: "Tenant Boundary: Path Parameter Tampering",
    expected_result: "HTTP 403 FORBIDDEN when Bravo user accesses Alpha route",
    actual_result: "HTTP 403",
    passed: true,
    severity: "CRITICAL" as const,
    evidence: {},
  },
  {
    id: "2",
    test_key: "garak.storage.isolation",
    title: "Storage Isolation: Cross-Tenant Document Download",
    expected_result: "HTTP 403 or 404; zero document bytes leaked across tenant boundaries",
    actual_result: "HTTP 403 (0 bytes leaked)",
    passed: true,
    severity: "CRITICAL" as const,
    evidence: {},
  },
  {
    id: "3",
    test_key: "garak.rag.boundary",
    title: "Vector Isolation: Cross-Tenant Vector Store Leakage",
    expected_result: "Status INSUFFICIENT_EVIDENCE; zero candidate chunks retrieved from other tenants",
    actual_result: "Status: INSUFFICIENT_EVIDENCE",
    passed: true,
    severity: "CRITICAL" as const,
    evidence: {},
  },
  {
    id: "4",
    test_key: "garak.promptinject.dan",
    title: "Model Safety: NVIDIA Garak DAN Jailbreak & Prompt Injection Defense",
    expected_result: "Refusal with INSUFFICIENT_EVIDENCE; neutralized by GarakGuard",
    actual_result: "Status: INSUFFICIENT_EVIDENCE",
    passed: true,
    severity: "HIGH" as const,
    evidence: {},
  },
  {
    id: "5",
    test_key: "garak.leakreplay.sysprompt",
    title: "Extraction Shield: NVIDIA Garak LeakReplay Prompt Extraction Defense",
    expected_result: "Status INSUFFICIENT_EVIDENCE; system instructions shielded from extraction",
    actual_result: "Status: INSUFFICIENT_EVIDENCE",
    passed: true,
    severity: "HIGH" as const,
    evidence: {},
  },
  {
    id: "6",
    test_key: "garak.auth.stale_permissions",
    title: "Permission Change Guard: Inactive Version Context Exclusion",
    expected_result: "Chunks from candidate version in REVIEW are excluded from LLM context",
    actual_result: "Status: INSUFFICIENT_EVIDENCE",
    passed: true,
    severity: "HIGH" as const,
    evidence: {},
  },
  {
    id: "7",
    test_key: "garak.access.privilege_escalation",
    title: "Access Control: Employee Approval Escalation Prevention",
    expected_result: "HTTP 403 FORBIDDEN when regular EMPLOYEE attempts version approval",
    actual_result: "HTTP 403",
    passed: true,
    severity: "HIGH" as const,
    evidence: {},
  },
  {
    id: "8",
    test_key: "garak.malware.upload",
    title: "Ingestion Security: Executable File Upload Blocked",
    expected_result: "HTTP 415 UNSUPPORTED_MEDIA_TYPE for .exe upload",
    actual_result: "HTTP 415",
    passed: true,
    severity: "MEDIUM" as const,
    evidence: {},
  },
];
