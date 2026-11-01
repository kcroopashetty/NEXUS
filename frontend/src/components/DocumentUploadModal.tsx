import React, { useState } from "react";
import { X, Upload, FileText, AlertCircle, CheckCircle, Shield } from "lucide-react";
import { TenantInfo } from "../types";
import { api } from "../api";

interface DocumentUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  tenants: TenantInfo[];
  currentTenantId: string;
  isPlatformAdmin: boolean;
}

export const DocumentUploadModal: React.FC<DocumentUploadModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  tenants,
  currentTenantId,
  isPlatformAdmin,
}) => {
  const [targetTenantId, setTargetTenantId] = useState<string>(currentTenantId);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("Human Resources");
  const [authorityLevel, setAuthorityLevel] = useState<string>("OFFICIAL_POLICY");
  const [allowedRoles, setAllowedRoles] = useState<string>("EMPLOYEE,CLIENT_ADMIN");
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      const ext = selected.name.split(".").pop()?.toLowerCase();
      if (!["txt", "pdf", "docx", "md"].includes(ext || "")) {
        setErrorMessage("Unsupported file type. Please upload a .txt, .pdf, or .docx file.");
        setFile(null);
        return;
      }
      setFile(selected);
      setErrorMessage(null);
      if (!title) {
        // Derive clean title from filename
        const cleanName = selected.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
        setTitle(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMessage("Please specify a document title.");
      return;
    }
    if (!file) {
      setErrorMessage("Please select a document file to upload.");
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const formData = new FormData();
      formData.append("title", title.trim());
      formData.append("category", category);
      formData.append("authority_level", authorityLevel);
      formData.append("allowed_roles", allowedRoles);
      formData.append("classification", allowedRoles === "CLIENT_ADMIN" ? "CONFIDENTIAL" : "INTERNAL");
      formData.append("file", file);

      await api.uploadDocument(targetTenantId, formData);
      setSuccessMessage("Document successfully uploaded and inspected! It is now registered in the workspace repository.");
      setTimeout(() => {
        setIsUploading(false);
        onSuccess();
        onClose();
      }, 1200);
    } catch (err: unknown) {
      setIsUploading(false);
      const msg = err instanceof Error ? err.message : "Document upload failed.";
      setErrorMessage(msg);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "16px",
      }}
    >
      <div
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderRadius: "12px",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: "560px",
          boxShadow: "0 20px 40px rgba(0, 0, 0, 0.4)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "18px 24px",
            borderBottom: "1px solid var(--border-color)",
            backgroundColor: "var(--bg-surface)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "8px",
                backgroundColor: "rgba(99, 102, 241, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--brand-primary)",
              }}
            >
              <Upload size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Upload Policy Document</h3>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                Ingests with Document Quality Inspection & isolated embeddings
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isUploading}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: "4px",
              borderRadius: "4px",
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {errorMessage && (
            <div
              style={{
                padding: "12px 14px",
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
              <AlertCircle size={16} />
              <span>{errorMessage}</span>
            </div>
          )}

          {successMessage && (
            <div
              style={{
                padding: "12px 14px",
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
              <CheckCircle size={16} />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Tenant Target Selection (if Platform Admin) */}
          {isPlatformAdmin ? (
            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                Target Client Workspace
              </label>
              <select
                value={targetTenantId}
                onChange={(e) => setTargetTenantId(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                }}
              >
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.slug})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              Target Workspace:{" "}
              <strong style={{ color: "var(--text-primary)" }}>
                {tenants.find((t) => t.id === targetTenantId)?.name || "Current Workspace"}
              </strong>
            </div>
          )}

          {/* Title */}
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
              Document Title *
            </label>
            <input
              type="text"
              placeholder="e.g. Employee Remote Work & Security Guidelines"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              style={{
                width: "100%",
                padding: "10px 12px",
                borderRadius: "6px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
            />
          </div>

          {/* Category & Authority Level */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                  boxSizing: "border-box",
                }}
              >
                <option value="Human Resources">Human Resources</option>
                <option value="Finance & Accounting">Finance & Accounting</option>
                <option value="Compliance & Legal">Compliance & Legal</option>
                <option value="Information Security">Information Security</option>
                <option value="Operations & Support">Operations & Support</option>
              </select>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                Authority Level
              </label>
              <select
                value={authorityLevel}
                onChange={(e) => setAuthorityLevel(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                  boxSizing: "border-box",
                }}
              >
                <option value="OFFICIAL_POLICY">OFFICIAL_POLICY (Binding)</option>
                <option value="STANDARD_PROCEDURE">STANDARD_PROCEDURE (SOP)</option>
                <option value="GUIDELINE">GUIDELINE (Advisory)</option>
                <option value="INFORMAL_NOTE">INFORMAL_NOTE (Reference)</option>
              </select>
            </div>
          </div>

          {/* Access Scope / Permission Clearance */}
          <div>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
              <Shield size={14} color="var(--brand-primary)" />
              Data Clearance & Access Permission
            </label>
            <select
              value={allowedRoles}
              onChange={(e) => setAllowedRoles(e.target.value)}
              style={{
                width: "100%",
                padding: "10px 12px",
                borderRadius: "6px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
            >
              <option value="EMPLOYEE,CLIENT_ADMIN">
                All Authorized Members (Employees & Administrators)
              </option>
              <option value="CLIENT_ADMIN">
                Administrators Only (Confidential / Management Policy)
              </option>
            </select>
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
              {allowedRoles === "CLIENT_ADMIN"
                ? "🔒 Protected by Permission Change Guard: Employees will receive zero evidence chunks from this document at query time."
                : "🌐 Standard policy accessible to all team members assigned to this client workspace."}
            </div>
          </div>

          {/* File Picker Dropzone */}
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
              Policy Document File (.txt, .pdf, .docx) *
            </label>
            <label
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "20px",
                borderRadius: "8px",
                border: "2px dashed var(--border-color)",
                backgroundColor: "var(--bg-surface)",
                cursor: "pointer",
                textAlign: "center",
                gap: "8px",
              }}
            >
              <FileText size={28} color="var(--brand-primary)" />
              {file ? (
                <div>
                  <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)" }}>{file.name}</div>
                  <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>{(file.size / 1024).toFixed(1)} KB</div>
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--brand-primary)" }}>Click to browse or drop file</div>
                  <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Plain text, PDF, or Word DOCX (max 25MB)</div>
                </div>
              )}
              <input
                type="file"
                accept=".txt,.pdf,.docx,.md"
                onChange={handleFileChange}
                style={{ display: "none" }}
              />
            </label>
          </div>

          {/* Action Buttons */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px", marginTop: "8px" }}>
            <button
              type="button"
              onClick={onClose}
              disabled={isUploading}
              style={{
                padding: "10px 18px",
                borderRadius: "6px",
                border: "1px solid var(--border-color)",
                backgroundColor: "transparent",
                color: "var(--text-secondary)",
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: 600,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isUploading || !file}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "10px 20px",
                borderRadius: "6px",
                border: "none",
                backgroundColor: isUploading || !file ? "var(--bg-surface)" : "var(--brand-primary)",
                color: isUploading || !file ? "var(--text-muted)" : "#ffffff",
                cursor: isUploading || !file ? "not-allowed" : "pointer",
                fontSize: "13px",
                fontWeight: 600,
              }}
            >
              <Upload size={15} />
              <span>{isUploading ? "Inspecting & Ingesting..." : "Upload & Inspect"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

