"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import type { Department, IngestJobStatus } from "@/lib/types";
import { UploadCloud, Check, AlertTriangle, X } from "lucide-react";

const POLL_MS_FAST = 500;
const POLL_MS_SLOW = 2000;
const TOAST_TTL = 7000;

const ALLOWED_ACCEPT = [
  ".pdf", ".docx", ".xlsx", ".xls", ".csv",
  ".txt", ".md", ".html", ".htm", ".eml",
  ".png", ".jpg", ".jpeg", ".tiff", ".tif",
].join(",");

const DETECTED_TYPE_LABELS: Record<string, string> = {
  prose_text: "Fließtext",
  table_structured: "Tabellendokument",
  norm_standard: "Norm / Standard",
  technical_manual: "Technisches Handbuch",
  legal_contract: "Vertrag / Rechtsdokument",
  report_study: "Bericht / Studie",
  form_template: "Formular / Vorlage",
  invoice_bill: "Rechnung / Lieferschein",
  presentation: "Präsentation",
  correspondence: "E-Mail / Korrespondenz",
};

interface Toast {
  id: number;
  filename: string;
  detectedType: string | null;
  nChunks: number | null;
  isError: boolean;
  errorMsg: string | null;
  isScanned: boolean;
}

interface Props {
  allowedDocTypeIds: string[] | null;
}

let _toastSeq = 0;

export function UploadPdf({ allowedDocTypeIds: _allowedDocTypeIds }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [jobs, setJobs] = useState<IngestJobStatus[]>([]);
  const [busy, setBusy] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [selectedDeptIds, setSelectedDeptIds] = useState<string[]>([]);

  useEffect(() => {
    fetch("/api/departments", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Department[]) => { if (Array.isArray(data)) setDepartments(data.filter((d) => d.status === "active")); })
      .catch(() => {});
  }, []);

  const pushToast = useCallback((t: Omit<Toast, "id">) => {
    const id = ++_toastSeq;
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), TOAST_TTL);
  }, []);
  const dismissToast = useCallback((id: number) => { setToasts((prev) => prev.filter((x) => x.id !== id)); }, []);
  function detectedLabel(key: string | null) { return key ? (DETECTED_TYPE_LABELS[key] ?? key) : null; }

  function poll(jobId: string) {
    let typeToastShown = false;
    let slowTimer: ReturnType<typeof setInterval> | null = null;
    const fastTimer = setInterval(async () => {
      const res = await fetch(`/api/ingest/${jobId}`, { credentials: "include" });
      if (!res.ok) { clearInterval(fastTimer); return; }
      const status: IngestJobStatus = await res.json();
      setJobs((prev) => prev.map((j) => (j.job_id === jobId ? status : j)));
      if (!typeToastShown && status.doc_type) {
        typeToastShown = true;
        pushToast({ filename: status.doc_id, detectedType: detectedLabel(status.doc_type), nChunks: null, isError: false, errorMsg: null, isScanned: false });
      }
      if (status.status === "done" || status.status === "error") {
        clearInterval(fastTimer);
        if (status.status === "error") {
          pushToast({ filename: status.doc_id, detectedType: detectedLabel(status.doc_type), nChunks: null, isError: true, errorMsg: status.error, isScanned: status.is_scanned ?? false });
        }
        return;
      }
      if (typeToastShown && !slowTimer) {
        clearInterval(fastTimer);
        slowTimer = setInterval(async () => {
          const r2 = await fetch(`/api/ingest/${jobId}`, { credentials: "include" });
          if (!r2.ok) { clearInterval(slowTimer!); return; }
          const s2: IngestJobStatus = await r2.json();
          setJobs((prev) => prev.map((j) => (j.job_id === jobId ? s2 : j)));
          if (s2.status === "done" || s2.status === "error") {
            clearInterval(slowTimer!);
            if (s2.status === "error") {
              pushToast({ filename: s2.doc_id, detectedType: detectedLabel(s2.doc_type), nChunks: null, isError: true, errorMsg: s2.error, isScanned: s2.is_scanned ?? false });
            }
          }
        }, POLL_MS_SLOW);
      }
    }, POLL_MS_FAST);
  }

  async function uploadFile(file: File, deptIds: string[]) {
    setBusy(true);
    const placeholder: IngestJobStatus = { job_id: "", status: "queued", doc_id: file.name, n_chunks: null, doc_type: null, doc_type_confidence: null, parser_name: null, chunker_name: null, is_scanned: null, error: null };
    setJobs((prev) => [placeholder, ...prev]);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const deptParam = deptIds.length > 0 ? `?department_ids=${deptIds.join(",")}` : "";
      const res = await fetch(`/api/ingest${deptParam}`, { method: "POST", body: formData, credentials: "include" });
      let initial: IngestJobStatus;
      if (res.ok) {
        initial = await res.json();
      } else {
        let errMsg: string;
        try {
          const body = await res.json();
          errMsg = body.detail || body.error || JSON.stringify(body);
        } catch {
          errMsg = `Upload failed (${res.status})`;
        }
        initial = { job_id: "", status: "error", doc_id: file.name, n_chunks: null, doc_type: null, doc_type_confidence: null, parser_name: null, chunker_name: null, is_scanned: null, error: errMsg };
      }
      setJobs((prev) => [initial, ...prev.slice(1)]);
      if (initial.job_id) poll(initial.job_id);
    } catch (err) {
      setJobs((prev) => [{ ...prev[0], status: "error", error: err instanceof Error ? err.message : String(err) }, ...prev.slice(1)]);
    } finally {
      setBusy(false);
    }
  }

  function openPicker() { inputRef.current?.click(); }
  function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; e.target.value = "";
    if (!file) return;
    if (departments.length > 0) { setPendingFile(file); setSelectedDeptIds([]); setModalOpen(true); }
    else { uploadFile(file, []); }
  }
  function toggleDept(id: string) { setSelectedDeptIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]); }
  function confirmUpload() { if (!pendingFile) return; setModalOpen(false); uploadFile(pendingFile, selectedDeptIds); setPendingFile(null); setSelectedDeptIds([]); }
  function cancelUpload() { setModalOpen(false); setPendingFile(null); setSelectedDeptIds([]); }

  return (
    <div>
      <input ref={inputRef} type="file" accept={ALLOWED_ACCEPT} hidden onChange={onFileChosen} />

      <button onClick={openPicker} disabled={busy} style={{
        display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
        width: "100%", height: "var(--control-h-md)", padding: "0 12px",
        background: "var(--surface-raised)", color: "var(--text-body)",
        border: "1px solid var(--border-default)", borderRadius: "var(--r-sm)",
        fontFamily: "var(--font-sans)", fontSize: "var(--fs-sm)", fontWeight: 500,
        cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.5 : 1,
        transition: "background var(--dur-fast) var(--ease-out)",
      }}
        onMouseEnter={(e) => { if (!busy) e.currentTarget.style.background = "var(--surface-hover)"; }}
        onMouseLeave={(e) => e.currentTarget.style.background = "var(--surface-raised)"}
      >
        <UploadCloud size={15} /> Upload documents
      </button>

      {/* Recent jobs */}
      {jobs.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 6 }}>
          {jobs.slice(0, 3).map((job, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6, fontSize: "var(--fs-2xs)", padding: "2px 4px", color: "var(--text-muted)" }}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 500 }} title={job.doc_id}>{job.doc_id}</span>
              <span style={{
                flex: "none", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                color: job.status === "done" ? "var(--verify-300)" : job.status === "error" ? "var(--error-300)" : "var(--text-muted)",
              }} title={job.status === "error" ? (job.error ?? "Unknown error") : undefined}>
                {job.status === "queued" && "queued…"}
                {job.status === "running" && (job.doc_type ? `${detectedLabel(job.doc_type)} – processing…` : "detecting type…")}
                {job.status === "done" && `✓ ${job.n_chunks} chunks`}
                {job.status === "error" && (job.is_scanned ? "scanned – no text" : (job.error ? job.error.slice(0, 40) : "error"))}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Department selection modal */}
      {modalOpen && pendingFile && (
        <div onClick={cancelUpload} style={{
          position: "fixed", inset: 0, zIndex: 900,
          background: "var(--surface-overlay)", backdropFilter: "blur(2px)",
          display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
          animation: "k-fade var(--dur-base) var(--ease-out)",
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            width: 380, maxWidth: "100%", background: "var(--surface-card)",
            border: "1px solid var(--border-strong)", borderRadius: "var(--r-lg)",
            boxShadow: "var(--shadow-lg)", overflow: "hidden",
          }}>
            <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border-subtle)" }}>
              <h3 style={{ margin: 0, fontSize: "var(--fs-h3)", fontWeight: 600, color: "var(--text-strong)" }}>Select department</h3>
              <p style={{ margin: "4px 0 0", fontSize: "var(--fs-xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{pendingFile.name}</p>
            </div>
            <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 4, maxHeight: 260, overflowY: "auto" }}>
              {departments.map((d) => (
                <label key={d.id} style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "7px 8px",
                  borderRadius: "var(--r-sm)", cursor: "pointer", fontSize: "var(--fs-sm)", color: "var(--text-body)",
                }}
                  onMouseEnter={(e) => e.currentTarget.style.background = "var(--surface-hover)"}
                  onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                  <input type="checkbox" checked={selectedDeptIds.includes(d.id)} onChange={() => toggleDept(d.id)} style={{ accentColor: "var(--accent)", width: 14, height: 14 }} />
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>#{d.code}</span>
                  <span>{d.name}</span>
                </label>
              ))}
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, padding: "14px 18px", borderTop: "1px solid var(--border-subtle)" }}>
              <button onClick={cancelUpload} style={{
                padding: "0 14px", height: "var(--control-h-md)",
                background: "transparent", border: "1px solid transparent",
                borderRadius: "var(--r-sm)", color: "var(--text-body)",
                fontSize: "var(--fs-sm)", fontWeight: 500, cursor: "pointer",
              }}>Cancel</button>
              <button onClick={confirmUpload} style={{
                padding: "0 14px", height: "var(--control-h-md)",
                background: "var(--accent)", border: "1px solid var(--accent)",
                borderRadius: "var(--r-sm)", color: "var(--accent-fg)",
                fontSize: "var(--fs-sm)", fontWeight: 500, cursor: "pointer",
              }}>Upload</button>
            </div>
          </div>
        </div>
      )}

      {/* Toasts */}
      {toasts.length > 0 && (
        <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 1100, display: "flex", flexDirection: "column", gap: 8, pointerEvents: "none" }}>
          {toasts.map((t) => (
            <div key={t.id} style={{
              pointerEvents: "auto", display: "flex", alignItems: "flex-start", gap: 10,
              background: "var(--surface-card)", border: `1px solid ${t.isError ? "var(--error-600)" : "var(--border-default)"}`,
              borderLeft: `3px solid ${t.isError ? "var(--error-500)" : "var(--verify-500)"}`,
              borderRadius: "var(--r-md)", boxShadow: "var(--shadow-pop)",
              padding: "10px 14px", minWidth: 260, maxWidth: 360, animation: "k-fade var(--dur-base) var(--ease-out)",
            }}>
              <span style={{ flex: "none", marginTop: 2 }}>
                {t.isError ? <AlertTriangle size={16} color="var(--error-500)" /> : <Check size={16} color="var(--verify-500)" />}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "var(--fs-2xs)", fontWeight: 600, letterSpacing: "var(--ls-caps)", textTransform: "uppercase" as const, color: "var(--text-muted)", marginBottom: 2 }}>
                  {t.isError ? "Upload error" : t.nChunks !== null ? "Document indexed" : "Type detected"}
                </div>
                <div style={{ fontSize: "var(--fs-sm)", fontWeight: 600, color: "var(--text-strong)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {t.isError ? (t.isScanned ? "Scanned document – no text layer" : (t.errorMsg ?? "Unknown error")) : (t.detectedType ?? "Unknown type")}
                </div>
                <div style={{ fontSize: "var(--fs-xs)", color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 2 }} title={t.filename}>{t.filename}</div>
              </div>
              <button onClick={() => dismissToast(t.id)} style={{
                background: "none", border: "none", cursor: "pointer", padding: 0, flex: "none",
                color: "var(--text-muted)", display: "inline-flex",
              }}><X size={14} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
