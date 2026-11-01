import React, { useState } from "react";
import { X, Upload, FileText, AlertCircle, CheckCircle, GitCompare } from "lucide-react";
import { DocumentRecord } from "../types";
import { api } from "../api";

interface CandidateVersionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  document: DocumentRecord | null;
  tenantId: string;
}

export const CandidateVersionModal: React.FC<CandidateVersionModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  document,
  tenantId,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [allowedRoles, setAllowedRoles] = useState<string>("EMPLOYEE,CLIENT_ADMIN");
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  if (!isOpen || !document) return null;

  const nextVersionNumber = (document.versions?.length || 0) + 1;

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
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setErrorMessage("Please select a candidate version file.");
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("allowed_roles", allowedRoles);
      formData.append("classification", allowedRoles === "CLIENT_ADMIN" ? "CONFIDENTIAL" : "INTERNAL");

      await api.uploadCandidateVersion(tenantId, document.id, formData);
      setSuccessMessage(
        `Version v${nextVersionNumber} successfully uploaded as candidate in REVIEW status! Diffs generated in Change Intelligence.`
      );
      setTimeout(() => {
        setIsUploading(false);
        onSuccess();
        onClose();
      }, 1400);
    } catch (err: unknown) {
      setIsUploading(false);
      const msg = err instanceof Error ? err.message : "Candidate version upload failed.";
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
          maxWidth: "520px",
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
              <GitCompare size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
                Upload Candidate Version (v{nextVersionNumber})
              </h3>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                Policy: {document.title}
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

        {/* Form */}
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

          <div
            style={{
              padding: "12px 14px",
              borderRadius: "8px",
              backgroundColor: "rgba(99, 102, 241, 0.08)",
              border: "1px solid rgba(99, 102, 241, 0.2)",
              fontSize: "12px",
              color: "var(--text-secondary)",
              lineHeight: "1.5",
            }}
          >
            Candidate versions are ingested safely into <strong>REVIEW</strong> status. They do not overwrite the live policy until an administrator reviews the diffs and approves activation.
          </div>

          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
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
          </div>

          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
              New Version Document (.txt, .pdf, .docx) *
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
                  <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--brand-primary)" }}>Click to select updated file</div>
                  <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Replaces current policy upon admin approval</div>
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
              <span>{isUploading ? "Ingesting Candidate..." : "Upload Candidate"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

