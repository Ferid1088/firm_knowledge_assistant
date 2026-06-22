"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { StatTile } from "@/components/korpus/StatTile";
import { IngestionRow } from "@/components/korpus/IngestionRow";
import type { IngestionRowProps } from "@/components/korpus/IngestionRow";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Tooltip } from "@/components/ui/Tooltip";
import type { IngestJobStatus } from "@/lib/types";
import { FileTextIcon } from "@/components/icons";
import {
  Upload,
  FileText,
  Layers,
  PieChart,
  ScanLine,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";

/* ---------- Mock data ---------- */

const DOCS = [
  { name: "HX-200_Maintenance_Manual.pdf", pages: 214, chunks: 642, lang: "EN", version: "v3", date: "2026-06-12", scanned: false },
  { name: "Betriebshandbuch_2023.pdf", pages: 188, chunks: 571, lang: "DE", version: "v1", date: "2026-06-10", scanned: false },
  { name: "Sicherheitsdatenblatt_4471.pdf", pages: 12, chunks: 38, lang: "DE", version: "v2", date: "2026-06-09", scanned: false },
  { name: "Quarterly_Compliance_Report.pdf", pages: 46, chunks: 121, lang: "EN", version: "v1", date: "2026-06-04", scanned: false },
  { name: "Scan_Altvertrag_1998.pdf", pages: 8, chunks: 0, lang: "—", version: "v1", date: "2026-06-02", scanned: true },
];

const TOTAL_CHUNKS = DOCS.reduce((s, d) => s + d.chunks, 0);
const SCANNED_COUNT = DOCS.filter((d) => d.scanned).length;

/* ---------- Ingestion stage simulation ---------- */

type SimulatedJob = IngestionRowProps & { id: string };

const STAGE_SEQUENCE: IngestionRowProps["stage"][] = [
  "parsing",
  "chunking",
  "embedding",
  "indexed",
];

/* ---------- Table header helper ---------- */

const TABLE_COLS: {
  label: string;
  align: React.CSSProperties["textAlign"];
  width?: string;
}[] = [
  { label: "Filename", align: "left" },
  { label: "Pages", align: "right", width: "80px" },
  { label: "Chunks", align: "right", width: "80px" },
  { label: "Lang", align: "center", width: "72px" },
  { label: "Version", align: "center", width: "80px" },
  { label: "Ingested", align: "left", width: "120px" },
  { label: "Actions", align: "center", width: "72px" },
];

/* ================================================================
   IngestScreen
   ================================================================ */
export default function IngestScreen() {
  /* --- Real API state (preserved) --- */
  const [jobs, setJobs] = useState<IngestJobStatus[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /* --- Simulation state --- */
  const [simJobs, setSimJobs] = useState<SimulatedJob[]>([]);

  // Poll active real jobs
  useEffect(() => {
    const activeJobs = jobs.filter(
      (j) => j.status === "queued" || j.status === "running"
    );
    if (activeJobs.length === 0) return;

    const interval = setInterval(() => {
      activeJobs.forEach((job) => {
        fetch(`/api/ingest/${job.job_id}`, { credentials: "include" })
          .then((r) => r.json())
          .then((updated: IngestJobStatus) => {
            setJobs((prev) =>
              prev.map((j) => (j.job_id === updated.job_id ? updated : j))
            );
          })
          .catch(() => {});
      });
    }, 2000);

    return () => clearInterval(interval);
  }, [jobs]);

  // Timer-driven simulation for demo: advance each sim job through stages
  useEffect(() => {
    const pending = simJobs.filter((j) => j.stage !== "indexed" && j.stage !== "error");
    if (pending.length === 0) return;

    const timer = setTimeout(() => {
      setSimJobs((prev) =>
        prev.map((j) => {
          if (j.stage === "indexed" || j.stage === "error") return j;
          const idx = STAGE_SEQUENCE.indexOf(j.stage);
          if (idx < STAGE_SEQUENCE.length - 1) {
            return { ...j, stage: STAGE_SEQUENCE[idx + 1] };
          }
          return j;
        })
      );
    }, 1800);

    return () => clearTimeout(timer);
  }, [simJobs]);

  /* --- Upload handler (real API) --- */
  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const form = new FormData();
      form.append("file", file);

      try {
        const res = await fetch("/api/ingest", {
          method: "POST",
          body: form,
          credentials: "include",
        });
        if (res.ok) {
          const data: IngestJobStatus = await res.json();
          setJobs((prev) => [data, ...prev]);
        } else {
          // Real API not available -- fall back to simulation
          startSimulation(file.name);
        }
      } catch {
        // API unreachable -- simulate for demo
        startSimulation(file.name);
      }
    }
  }, []);

  function startSimulation(filename: string) {
    const id = `sim-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setSimJobs((prev) => [
      {
        id,
        filename,
        stage: "parsing" as const,
        pages: Math.floor(Math.random() * 100) + 5,
      },
      ...prev,
    ]);
  }

  /* --- Drop / drag / file handlers --- */
  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      uploadFiles(e.dataTransfer.files);
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave() {
    setDragOver(false);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      uploadFiles(e.target.files);
      e.target.value = "";
    }
  }

  /* --- Combine real + simulated active jobs --- */
  const hasActiveWork = jobs.length > 0 || simJobs.filter((j) => j.stage !== "indexed").length > 0;

  return (
    <AppShell title="Ingestion & documents">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>

        {/* ---- Stat tiles ---- */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "var(--sp-5)",
          }}
        >
          <StatTile
            label="Total documents"
            value={DOCS.length}
            icon={<FileText size={16} />}
            tone="accent"
          />
          <StatTile
            label="Total chunks"
            value={TOTAL_CHUNKS.toLocaleString()}
            icon={<Layers size={16} />}
          />
          <StatTile
            label="Prose / Table / Reco"
            value="72 / 21 / 7"
            unit="%"
            icon={<PieChart size={16} />}
          />
          <StatTile
            label="Scanned flagged"
            value={SCANNED_COUNT}
            icon={<ScanLine size={16} />}
            tone={SCANNED_COUNT > 0 ? "warn" : "neutral"}
          />
        </div>

        {/* ---- Dropzone ---- */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "var(--sp-5)",
            height: 200,
            border: `2px dashed ${dragOver ? "var(--accent)" : "var(--border-default)"}`,
            borderRadius: "var(--r-lg)",
            background: dragOver ? "var(--accent-tint)" : "var(--surface-card)",
            cursor: "pointer",
            transition: `all var(--dur-fast) var(--ease-out)`,
          }}
        >
          <Upload
            size={32}
            style={{
              color: dragOver ? "var(--accent)" : "var(--text-muted)",
              transition: `color var(--dur-fast) var(--ease-out)`,
            }}
          />
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                fontSize: "var(--fs-body)",
                fontWeight: "var(--fw-medium)" as unknown as number,
                color: "var(--text-strong)",
              }}
            >
              Drop PDFs here, or browse
            </div>
            <div
              style={{
                fontSize: "var(--fs-xs)",
                color: "var(--text-secondary)",
                marginTop: "var(--sp-2)",
              }}
            >
              PDF files only. Files are parsed, chunked, embedded, and indexed locally.
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
          >
            Browse
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            multiple
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
        </div>

        {/* ---- Active ingestion ---- */}
        {hasActiveWork && (
          <div>
            <div className="text-eyebrow" style={{ marginBottom: "var(--sp-4)" }}>
              Active ingestion
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--sp-3)",
              }}
            >
              {/* Simulated jobs (Korpus IngestionRow) */}
              {simJobs
                .filter((j) => j.stage !== "indexed")
                .map((j) => (
                  <IngestionRow
                    key={j.id}
                    filename={j.filename}
                    stage={j.stage}
                    pages={j.pages}
                    chunks={j.chunks}
                    language={j.language}
                    version={j.version}
                    scanned={j.scanned}
                  />
                ))}

              {/* Real API jobs (legacy inline rendering for backward compat) */}
              {jobs.map((job) => {
                const stageLookup: Record<string, IngestionRowProps["stage"]> = {
                  queued: "parsing",
                  running: "embedding",
                  done: "indexed",
                  error: "error",
                };
                return (
                  <IngestionRow
                    key={job.job_id}
                    filename={job.doc_id || job.job_id}
                    stage={stageLookup[job.status] ?? "parsing"}
                    chunks={job.n_chunks ?? undefined}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* ---- Document table ---- */}
        <div>
          <div className="text-eyebrow" style={{ marginBottom: "var(--sp-4)" }}>
            Documents
          </div>
          <div
            style={{
              background: "var(--surface-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--r-md)",
              overflow: "hidden",
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "var(--fs-sm)",
              }}
            >
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  {TABLE_COLS.map((col) => (
                    <th
                      key={col.label}
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                        textAlign: col.align,
                        width: col.width,
                        fontSize: "var(--fs-2xs)",
                        fontWeight: "var(--fw-semibold)" as unknown as number,
                        color: "var(--text-secondary)",
                        letterSpacing: "var(--ls-caps)",
                        textTransform: "uppercase",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DOCS.map((doc) => (
                  <tr
                    key={doc.name}
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                    }}
                  >
                    {/* Filename */}
                    <td
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "var(--sp-3)",
                        }}
                      >
                        <span
                          style={{
                            display: "inline-flex",
                            color: doc.scanned ? "var(--warn)" : "var(--text-secondary)",
                            flexShrink: 0,
                          }}
                        >
                          {doc.scanned ? (
                            <AlertTriangle size={14} />
                          ) : (
                            <FileTextIcon />
                          )}
                        </span>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "var(--fs-sm)",
                            fontWeight: "var(--fw-medium)" as unknown as number,
                            color: doc.scanned ? "var(--text-muted)" : "var(--text-strong)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {doc.name}
                        </span>
                      </div>
                    </td>

                    {/* Pages */}
                    <td
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                        textAlign: "right",
                        fontFamily: "var(--font-mono)",
                        color: "var(--text-body)",
                      }}
                    >
                      {doc.pages}
                    </td>

                    {/* Chunks */}
                    <td
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                        textAlign: "right",
                        fontFamily: "var(--font-mono)",
                        color: doc.chunks === 0 ? "var(--text-disabled)" : "var(--text-body)",
                      }}
                    >
                      {doc.chunks === 0 ? "—" : doc.chunks}
                    </td>

                    {/* Lang */}
                    <td
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                        textAlign: "center",
                      }}
                    >
                      <Badge tone="neutral" mono>
                        {doc.lang}
                      </Badge>
                    </td>

                    {/* Version */}
                    <td
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                        textAlign: "center",
                      }}
                    >
                      <Badge tone={doc.version !== "v1" ? "accent" : "neutral"}>
                        {doc.version}
                      </Badge>
                    </td>

                    {/* Ingested date */}
                    <td
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                        fontFamily: "var(--font-mono)",
                        fontSize: "var(--fs-xs)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {doc.date}
                    </td>

                    {/* Actions */}
                    <td
                      style={{
                        padding: "var(--sp-4) var(--sp-5)",
                        textAlign: "center",
                      }}
                    >
                      <Tooltip content="Re-ingest document">
                        <IconButton
                          icon={<RefreshCw size={14} />}
                          label="Re-ingest"
                          variant="ghost"
                          size="sm"
                          disabled={doc.scanned}
                        />
                      </Tooltip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
