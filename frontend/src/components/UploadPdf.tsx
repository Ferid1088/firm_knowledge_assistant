"use client";

import { useEffect, useRef, useState } from "react";
import type { DocumentType, IngestJobStatus } from "@/lib/types";
import { UploadIcon } from "@/components/icons";

const POLL_MS = 2000;

const ALLOWED_ACCEPT = [
  ".pdf", ".docx", ".xlsx", ".xls", ".csv",
  ".txt", ".md", ".html", ".htm", ".eml",
  ".png", ".jpg", ".jpeg", ".tiff", ".tif",
].join(",");

interface Props {
  /** User's allowed doc type IDs — null means unrestricted (sees all). */
  allowedDocTypeIds: string[] | null;
}

export function UploadPdf({ allowedDocTypeIds }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [allDocTypes, setAllDocTypes] = useState<DocumentType[]>([]);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedDocType, setSelectedDocType] = useState<string>("");
  const [jobs, setJobs] = useState<IngestJobStatus[]>([]);
  const [busy, setBusy] = useState(false);

  // Fetch all allowed doc types
  useEffect(() => {
    fetch("/api/doc-types", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: DocumentType[]) => {
        if (!Array.isArray(data)) return;
        // Restrict to user's allowed types if set
        const visible = allowedDocTypeIds
          ? data.filter((dt) => allowedDocTypeIds.includes(dt.id))
          : data;
        setAllDocTypes(visible);
        if (visible.length > 0) setSelectedDocType(visible[0].id);
      })
      .catch(() => {});
  }, [allowedDocTypeIds]);

  function openPicker() {
    inputRef.current?.click();
  }

  function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPendingFile(file);
    setModalOpen(true);
  }

  async function confirmUpload() {
    if (!pendingFile) return;
    setModalOpen(false);
    setBusy(true);

    const file = pendingFile;
    setPendingFile(null);

    const placeholder: IngestJobStatus = {
      job_id: "",
      status: "queued",
      doc_id: file.name,
      n_chunks: null,
      doc_type: selectedDocType || null,
      doc_type_confidence: null,
      parser_name: null,
      chunker_name: null,
      is_scanned: null,
      error: null,
    };
    setJobs((prev) => [placeholder, ...prev]);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const url = selectedDocType
        ? `/api/ingest?doc_type_id=${encodeURIComponent(selectedDocType)}`
        : "/api/ingest";

      const res = await fetch(url, { method: "POST", body: formData, credentials: "include" });
      const initial: IngestJobStatus = res.ok
        ? await res.json()
        : {
            job_id: "",
            status: "error",
            doc_id: file.name,
            n_chunks: null,
            doc_type: null,
            doc_type_confidence: null,
            parser_name: null,
            chunker_name: null,
            is_scanned: null,
            error: await res.text(),
          };

      setJobs((prev) => [initial, ...prev.slice(1)]);
      if (initial.job_id) poll(initial.job_id);
    } catch (err) {
      setJobs((prev) => [
        {
          ...prev[0],
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        },
        ...prev.slice(1),
      ]);
    } finally {
      setBusy(false);
    }
  }

  function poll(jobId: string) {
    const timer = setInterval(async () => {
      const res = await fetch(`/api/ingest/${jobId}`, { credentials: "include" });
      if (!res.ok) { clearInterval(timer); return; }
      const status: IngestJobStatus = await res.json();
      setJobs((prev) => prev.map((j) => (j.job_id === jobId ? status : j)));
      if (status.status === "done" || status.status === "error") clearInterval(timer);
    }, POLL_MS);
  }

  function docTypeName(id: string | null) {
    if (!id) return null;
    return allDocTypes.find((dt) => dt.id === id)?.name ?? id;
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
                {job.status === "running" && "verarbeitet…"}
                {job.status === "done" && `✓ ${job.n_chunks} Chunks${docTypeName(job.doc_type) ? ` · ${docTypeName(job.doc_type)}` : ""}`}
                {job.status === "error" && (job.is_scanned ? "Gescannt – kein Text" : `Fehler`)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Doc type selection modal */}
      {modalOpen && pendingFile && (
        <div className="upload-modal-overlay" onClick={() => { setModalOpen(false); setPendingFile(null); }}>
          <div className="upload-modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="upload-modal-title">Dokumenttyp auswählen</h3>
            <p className="upload-modal-file">{pendingFile.name}</p>

            {allDocTypes.length === 0 ? (
              <p className="upload-modal-note">
                Keine Dokumenttypen definiert. Bitte Admin kontaktieren.
              </p>
            ) : (
              <div className="upload-modal-types">
                {allDocTypes.map((dt) => (
                  <label key={dt.id} className={`upload-modal-type-item ${selectedDocType === dt.id ? "selected" : ""}`}>
                    <input
                      type="radio"
                      name="doc-type"
                      value={dt.id}
                      checked={selectedDocType === dt.id}
                      onChange={() => setSelectedDocType(dt.id)}
                    />
                    <span className="upload-modal-type-code">#{dt.code}</span>
                    <span className="upload-modal-type-name">{dt.name}</span>
                    {dt.description && (
                      <span className="upload-modal-type-desc">{dt.description}</span>
                    )}
                  </label>
                ))}
              </div>
            )}

            <div className="upload-modal-actions">
              <button
                className="upload-modal-confirm"
                onClick={confirmUpload}
                disabled={!selectedDocType || allDocTypes.length === 0}
              >
                Hochladen
              </button>
              <button
                className="upload-modal-cancel"
                onClick={() => { setModalOpen(false); setPendingFile(null); }}
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
