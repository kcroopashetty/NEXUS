import { useState } from "react";
import { Lock, Mail, ArrowRight, ShieldCheck, Database, AlertCircle } from "lucide-react";
import { api } from "../api";
import { UserRole } from "../types";

export interface DemoPersona {
  email: string;
  name: string;
  role: UserRole;
  tenantSlug: string;
  description: string;
}

export const DEMO_PERSONAS: DemoPersona[] = [
  {
    email: "admin@a.corp",
    name: "Alice Admin",
    role: "CLIENT_ADMIN",
    tenantSlug: "tenant-a",
    description: "Alpha Financial Services Administrator (Full document upload & approval rights)",
  },
  {
    email: "emp@a.corp",
    name: "Edward Employee",
    role: "EMPLOYEE",
    tenantSlug: "tenant-a",
    description: "Alpha Financial Employee (Grounded RAG query & document browsing rights)",
  },
  {
    email: "admin@b.corp",
    name: "Bob Admin",
    role: "CLIENT_ADMIN",
    tenantSlug: "tenant-b",
    description: "Beta Healthcare Systems Administrator (Tests cross-tenant isolation)",
  },
  {
    email: "root@nexus.corp",
    name: "Platform Security Root",
    role: "PLATFORM_ADMIN",
    tenantSlug: "tenant-a",
    description: "Platform Administrator (Red-Team Sentinel & Global oversight)",
  },
];

interface Props {
  onLoginSuccess: (token: string, userProfile: any) => void;
}

export function LoginScreen({ onLoginSuccess }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleLogin = async (loginEmail?: string, loginPassword?: string) => {
    const targetEmail = loginEmail || email;
    const targetPassword = loginPassword || password;

    if (!targetEmail.trim() || !targetPassword.trim()) {
      setErrorMsg("Please enter both email and password.");
      return;
    }

    try {
      setIsLoading(true);
      setErrorMsg(null);
      await api.login(targetEmail.trim(), targetPassword.trim());
      // Server-side HttpOnly session cookie is now active.
      // Purge any tokens from localStorage to prevent XSS credential theft
      localStorage.removeItem("nexus_access_token");

      const me = await api.getMe();
      onLoginSuccess("", me);
    } catch (err: any) {
      setErrorMsg(err.message || "Invalid email or password. Please verify your credentials.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectPersona = (p: DemoPersona) => {
    setEmail(p.email);
    setPassword("NexusSecretPass123!");
    handleLogin(p.email, "NexusSecretPass123!");
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: "var(--bg-canvas)",
        padding: "24px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "480px",
          backgroundColor: "var(--bg-primary)",
          borderRadius: "16px",
          border: "1px solid var(--border-color)",
          padding: "36px",
          boxShadow: "var(--shadow-level-1)",
        }}
      >
        {/* Brand Header */}
        <div style={{ textAlign: "center", marginBottom: "28px" }}>
          <div
            style={{
              width: "48px",
              height: "48px",
              borderRadius: "10px",
              backgroundColor: "var(--brand-primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 800,
              fontSize: "24px",
              color: "#fff",
              margin: "0 auto 16px auto",
              boxShadow: "0 4px 16px rgba(17, 17, 17, 0.12)",
            }}
          >
            N
          </div>
          <h1 style={{ fontSize: "22px", fontWeight: 700, margin: "0 0 6px 0" }}>NEXUS Knowledge Gateway</h1>
          <p style={{ fontSize: "13px", color: "var(--text-secondary)", margin: 0 }}>
            Enterprise Multi-Tenant Knowledge Assistant & Continuous Assurance
          </p>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "12px 14px",
              borderRadius: "6px",
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              border: "1px solid var(--danger)",
              color: "var(--danger)",
              fontSize: "13px",
              marginBottom: "20px",
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Login Form */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleLogin();
          }}
          style={{ display: "flex", flexDirection: "column", gap: "16px" }}
        >
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "6px" }}>
              ENTERPRISE EMAIL ADDRESS
            </label>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
                borderRadius: "6px",
                padding: "10px 14px",
              }}
            >
              <Mail size={16} color="var(--text-muted)" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.corp"
                required
                style={{
                  background: "none",
                  border: "none",
                  outline: "none",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                  width: "100%",
                }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "6px" }}>
              PASSWORD
            </label>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
                borderRadius: "6px",
                padding: "10px 14px",
              }}
            >
              <Lock size={16} color="var(--text-muted)" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                style={{
                  background: "none",
                  border: "none",
                  outline: "none",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                  width: "100%",
                }}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              padding: "12px",
              borderRadius: "6px",
              backgroundColor: "var(--brand-primary)",
              border: "none",
              color: "#fff",
              fontWeight: 600,
              fontSize: "14px",
              cursor: isLoading ? "not-allowed" : "pointer",
              marginTop: "8px",
              opacity: isLoading ? 0.7 : 1,
              transition: "background-color 0.15s ease",
            }}
          >
            <span>{isLoading ? "Authenticating Session..." : "Sign In to Workspace"}</span>
            <ArrowRight size={16} />
          </button>
        </form>

        {/* Demo Personas Quick-Fill */}
        <div style={{ marginTop: "28px", borderTop: "1px solid var(--border-color)", paddingTop: "20px" }}>
          <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "12px" }}>
            Or Select an Enterprise Test Identity
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {DEMO_PERSONAS.map((p) => (
              <button
                key={p.email}
                type="button"
                onClick={() => handleSelectPersona(p)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 14px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "border-color 0.15s ease",
                }}
              >
                <div>
                  <div style={{ fontSize: "13px", fontWeight: 600 }}>{p.name}</div>
                  <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>{p.email}</div>
                </div>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: "4px",
                    backgroundColor:
                      p.role === "CLIENT_ADMIN"
                        ? "rgba(99, 102, 241, 0.15)"
                        : p.role === "PLATFORM_ADMIN"
                        ? "rgba(245, 158, 11, 0.15)"
                        : "rgba(16, 185, 129, 0.15)",
                    color:
                      p.role === "CLIENT_ADMIN"
                        ? "var(--brand-primary)"
                        : p.role === "PLATFORM_ADMIN"
                        ? "var(--warning)"
                        : "var(--success)",
                  }}
                >
                  {p.role}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Security Assurance Badges */}
        <div
          style={{
            marginTop: "24px",
            display: "flex",
            justifyContent: "center",
            gap: "16px",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <ShieldCheck size={13} color="var(--success)" />
            <span>PostgreSQL Permission Guard</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <Database size={13} color="var(--brand-primary)" />
            <span>Air-Gapped Local RAG</span>
          </div>
        </div>
      </div>
    </div>
  );
}
