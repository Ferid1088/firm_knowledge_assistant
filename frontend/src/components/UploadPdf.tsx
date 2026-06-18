"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import type { Department, IngestJobStatus } from "@/lib/types";
import { UploadIcon } from "@/components/icons";

const POLL_MS_FAST = 500;   // while waiting for type detection
const POLL_MS_SLOW = 2000;  // after type is known
const TOAST_TTL = 7000;

const ALLOWED_ACCEPT = [
  ".pdf", ".docx", ".xlsx", ".xls", ".csv",
  ".txt", ".md", ".html", ".htm", ".eml",
  ".png", ".jpg", ".jpeg", ".tiff", ".tif",
].join(",");

// Human-readable labels for the 10 types returned by type_detector.py
const DETECTED_TYPE_LABELS: Record<string, string> = {
  prose_text:       "Fließtext",
  table_structured: "Tabellendokument",
  norm_standard:    "Norm / Standard",
  technical_manual: "Technisches Handbuch",
  legal_contract:   "Vertrag / Rechtsdokument",
  report_study:     "Bericht / Studie",
  form_template:    "Formular / Vorlage",
  invoice_bill:     "Rechnung / Lieferschein",
  presentation:     "Präsentation",
  correspondence:   "E-Mail / Korrespondenz",
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

  // Department modal state
  const [departments, setDepartments] = useState<Department[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [selectedDeptIds, setSelectedDeptIds] = useState<string[]>([]);

  useEffect(() => {
    fetch("/api/departments", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Department[]) => {
        if (Array.isArray(data)) setDepartments(data.filter((d) => d.status === "active"));
      })
      .catch(() => {});
  }, []);

  const pushToast = useCallback((t: Omit<Toast, "id">) => {
    const id = ++_toastSeq;
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), TOAST_TTL);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((x) => x.id !== id));
  }, []);

  function detectedLabel(key: string | null) {
    if (!key) return null;
    return DETECTED_TYPE_LABELS[key] ?? key;
  }

  function poll(jobId: string) {
    let typeToastShown = false;
    let slowTimer: ReturnType<typeof setInterval> | null = null;

    // Fast poll until we get a doc_type, then switch to slow poll
    const fastTimer = setInterval(async () => {
      const res = await fetch(`/api/ingest/${jobId}`, { credentials: "include" });
      if (!res.ok) { clearInterval(fastTimer); return; }
      const status: IngestJobStatus = await res.json();
      setJobs((prev) => prev.map((j) => (j.job_id === jobId ? status : j)));

      // Fire type toast the moment doc_type appears (running or done)
      if (!typeToastShown && status.doc_type) {
        typeToastShown = true;
        pushToast({
          filename: status.doc_id,
          detectedType: detectedLabel(status.doc_type),
          nChunks: null,
          isError: false,
          errorMsg: null,
          isScanned: false,
        });
      }

      if (status.status === "done" || status.status === "error") {
        clearInterval(fastTimer);
        if (status.status === "error") {
          pushToast({
            filename: status.doc_id,
            detectedType: detectedLabel(status.doc_type),
            nChunks: null,
            isError: true,
            errorMsg: status.error,
            isScanned: status.is_scanned ?? false,
          });
        }
        return;
      }

      // Once we have the type, slow down polling (still in "running")
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
              pushToast({
                filename: s2.doc_id,
                detectedType: detectedLabel(s2.doc_type),
                nChunks: null,
                isError: true,
                errorMsg: s2.error,
                isScanned: s2.is_scanned ?? false,
              });
            }
          }
        }, POLL_MS_SLOW);
      }
    }, POLL_MS_FAST);
  }

  async function uploadFile(file: File, deptIds: string[]) {
    setBusy(true);
    const placeholder: IngestJobStatus = {
      job_id: "", status: "queued", doc_id: file.name,
      n_chunks: null, doc_type: null, doc_type_confidence: null,
      parser_name: null, chunker_name: null, is_scanned: null, error: null,
    };
    setJobs((prev) => [placeholder, ...prev]);

    try {
      const formData = new FormData();
      formData.append("file", file);
      // No doc_type_id — backend auto-detects via type_detector.py
      const deptParam = deptIds.length > 0 ? `?department_ids=${deptIds.join(",")}` : "";
      const res = await fetch(`/api/ingest${deptParam}`, {
        method: "POST",
        body: formData,
        credentials: "include",
      });
      const initial: IngestJobStatus = res.ok
        ? await res.json()
        : {
            job_id: "", status: "error", doc_id: file.name,
            n_chunks: null, doc_type: null, doc_type_confidence: null,
            parser_name: null, chunker_name: null, is_scanned: null,
            error: await res.text(),
          };
      setJobs((prev) => [initial, ...prev.slice(1)]);
      if (initial.job_id) poll(initial.job_id);
    } catch (err) {
      setJobs((prev) => [{
        ...prev[0], status: "error",
        error: err instanceof Error ? err.message : String(err),
      }, ...prev.slice(1)]);
    } finally {
      setBusy(false);
    }
  }

  function openPicker() {
    inputRef.current?.click();
  }

  function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    if (departments.length > 0) {
      // Show department selection modal
      setPendingFile(file);
      setSelectedDeptIds([]);
      setModalOpen(true);
    } else {
      // No departments defined — upload without department
      uploadFile(file, []);
    }
  }

  function toggleDept(id: string) {
    setSelectedDeptIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function confirmUpload() {
    if (!pendingFile) return;
    setModalOpen(false);
    uploadFile(pendingFile, selectedDeptIds);
    setPendingFile(null);
    setSelectedDeptIds([]);
  }

  function cancelUpload() {
    setModalOpen(false);
    setPendingFile(null);
    setSelectedDeptIds([]);
  }

  return (
    <div className="sidebar-upload">
      <input ref={inputRef} type="file" accept={ALLOWED_ACCEPT} hidden onChange={onFileChosen} />

      <button className="sidebar-upload-btn" onClick={openPicker} disabled={busy}>
        <UploadIcon />
        Dok. hinzufügen
      </button>

      {/* Recent jobs */}
      {jobs.length > 0 && (
        <div className="sidebar-upload-jobs">
          {jobs.slice(0, 3).map((job, i) => (
            <div key={i} className={`sidebar-upload-job upload-status-${job.status}`}>
              <span className="sidebar-upload-job-name" title={job.doc_id}>{job.doc_id}</span>
              <span className="sidebar-upload-job-status">
                {job.status === "queued" && "wartet…"}
                {job.status === "running" && (
                  job.doc_type
                    ? `${detectedLabel(job.doc_type)} – verarbeitet…`
                    : "erkennt Typ…"
                )}
                {job.status === "done" && `✓ ${job.n_chunks} Chunks${detectedLabel(job.doc_type) ? ` · ${detectedLabel(job.doc_type)}` : ""}`}
                {job.status === "error" && (job.is_scanned ? "Gescannt – kein Text" : "Fehler")}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Department selection modal */}
      {modalOpen && pendingFile && (
        <div className="dept-modal-overlay" onClick={cancelUpload}>
          <div className="dept-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dept-modal-header">
              <div className="dept-modal-title">Department auswählen</div>
              <div className="dept-modal-subtitle" title={pendingFile.name}>
                {pendingFile.name}
              </div>
            </div>
            <div className="dept-modal-body">
              <p className="dept-modal-hint">
                Wählen Sie ein oder mehrere Departments, denen dieses Dokument zugeordnet werden soll.
              </p>
              <div className="dept-modal-list">
                {departments.map((d) => (
                  <label key={d.id} className="dept-modal-option">
                    <input
                      type="checkbox"
                      checked={selectedDeptIds.includes(d.id)}
                      onChange={() => toggleDept(d.id)}
                    />
                    <span className="dept-modal-code">#{d.code}</span>
                    <span className="dept-modal-name">{d.name}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="dept-modal-footer">
              <button className="dept-modal-cancel" onClick={cancelUpload}>
                Abbrechen
              </button>
              <button className="dept-modal-confirm" onClick={confirmUpload}>
                Hochladen
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detection toasts */}
      {toasts.length > 0 && (
        <div className="doctype-toast-stack">
          {toasts.map((t) => (
            <div key={t.id} className={`doctype-toast${t.isError ? " toast-error" : ""}`}>
              <span className="doctype-toast-icon">{t.isError ? "⚠️" : "✅"}</span>
              <div className="doctype-toast-body">
                <div className="doctype-toast-label">
                  {t.isError
                    ? "Fehler beim Hochladen"
                    : t.nChunks !== null
                      ? "Dokument indexiert"
                      : "Dokumenttyp erkannt"}
                </div>
                <div className="doctype-toast-type">
                  {t.isError
                    ? (t.isScanned ? "Gescanntes Dokument – kein Textlayer" : (t.errorMsg ?? "Unbekannter Fehler"))
                    : (t.detectedType ?? "Unbekannter Typ")}
                </div>
                <div className="doctype-toast-file" title={t.filename}>{t.filename}</div>
                {!t.isError && t.nChunks !== null && (
                  <div className="doctype-toast-chunks">{t.nChunks} Chunks indexiert</div>
                )}
              </div>
              <button className="doctype-toast-close" onClick={() => dismissToast(t.id)}>×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
