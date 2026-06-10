"use client";

import { useRef, useState } from "react";
import type { IngestJobStatus } from "@/lib/types";

const POLL_MS = 2000;

export function UploadPdf() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [job, setJob] = useState<IngestJobStatus | null>(null);
  const [busy, setBusy] = useState(false);

  function pickFile() {
    inputRef.current?.click();
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setBusy(true);
    setJob(null);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/ingest", { method: "POST", body: formData });
      if (!res.ok) {
        setJob({
          job_id: "",
          status: "error",
          doc_id: file.name,
          n_chunks: null,
          error: await res.text(),
        });
        return;
      }
      const initial: IngestJobStatus = await res.json();
      setJob(initial);
      poll(initial.job_id);
    } catch (err) {
      setJob({
        job_id: "",
        status: "error",
        doc_id: file.name,
        n_chunks: null,
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setBusy(false);
    }
  }

  function poll(jobId: string) {
    const timer = setInterval(async () => {
      const res = await fetch(`/api/ingest/${jobId}`);
      if (!res.ok) {
        clearInterval(timer);
        return;
      }
      const status: IngestJobStatus = await res.json();
      setJob(status);
      if (status.status === "done" || status.status === "error") {
        clearInterval(timer);
      }
    }, POLL_MS);
  }

  return (
    <div className="upload-pdf">
      <input ref={inputRef} type="file" accept="application/pdf" hidden onChange={onFileChosen} />
      <button onClick={pickFile} disabled={busy || job?.status === "queued" || job?.status === "running"}>
        + PDF hinzufügen
      </button>
      {job && (
        <span className={`upload-status upload-status-${job.status}`}>
          {job.doc_id}:{" "}
          {job.status === "queued" && "wartet…"}
          {job.status === "running" && "wird verarbeitet…"}
          {job.status === "done" && `fertig (${job.n_chunks} Chunks)`}
          {job.status === "error" && `Fehler: ${job.error}`}
        </span>
      )}
    </div>
  );
}
