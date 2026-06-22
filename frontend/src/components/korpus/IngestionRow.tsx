"use client";

import React from "react";
import {
  FileText,
  Scissors,
  Cpu,
  Database,
  AlertCircle,
  AlertTriangle,
} from "lucide-react";

type IngestionStage = "parsing" | "chunking" | "embedding" | "indexed" | "error";

export interface IngestionRowProps {
  filename: string;
  stage: IngestionStage;
  scanned?: boolean;
  pages?: number;
  chunks?: number;
  language?: string;
  version?: string;
}

const STAGES: { key: IngestionStage; label: string; icon: React.ReactNode }[] = [
  { key: "parsing", label: "Parse", icon: <FileText size={13} /> },
  { key: "chunking", label: "Chunk", icon: <Scissors size={13} /> },
  { key: "embedding", label: "Embed", icon: <Cpu size={13} /> },
  { key: "indexed", label: "Index", icon: <Database size={13} /> },
];

const STAGE_ORDER: Record<IngestionStage, number> = {
  parsing: 0,
  chunking: 1,
  embedding: 2,
  indexed: 3,
  error: -1,
};

export function IngestionRow({
  filename,
  stage,
  scanned = false,
  pages,
  chunks,
  language,
  version,
}: IngestionRowProps) {
  const isError = stage === "error";
  const activeIndex = STAGE_ORDER[stage];

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-6)",
        padding: "var(--sp-5) var(--sp-6)",
        background: "var(--surface-card)",
        border: "1px solid",
        borderColor: isError ? "var(--error-tint)" : "var(--border-subtle)",
        borderRadius: "var(--r-md)",
      }}
    >
      {/* File info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-3)",
            marginBottom: "var(--sp-2)",
          }}
        >
          <span
            style={{
              fontSize: "var(--fs-sm)",
              fontWeight: "var(--fw-medium)" as unknown as number,
              color: isError ? "var(--error)" : "var(--text-strong)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {filename}
          </span>

          {scanned && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "var(--sp-2)",
                padding: "var(--sp-1) var(--sp-3)",
                borderRadius: "var(--r-xs)",
                background: "var(--warn-tint)",
                color: "var(--warn)",
                fontSize: "var(--fs-2xs)",
                fontWeight: "var(--fw-medium)" as unknown as number,
              }}
            >
              <AlertTriangle size={10} />
              Scanned
            </span>
          )}

          {isError && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "var(--sp-2)",
                padding: "var(--sp-1) var(--sp-3)",
                borderRadius: "var(--r-xs)",
                background: "var(--error-tint)",
                color: "var(--error)",
                fontSize: "var(--fs-2xs)",
                fontWeight: "var(--fw-medium)" as unknown as number,
              }}
            >
              <AlertCircle size={10} />
              Error
            </span>
          )}
        </div>

        {/* Meta row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-4)",
            fontSize: "var(--fs-2xs)",
            color: "var(--text-muted)",
          }}
        >
          {pages !== undefined && <span>{pages} pages</span>}
          {chunks !== undefined && (
            <>
              <span style={{ color: "var(--border-default)" }}>|</span>
              <span>{chunks} chunks</span>
            </>
          )}
          {language && (
            <>
              <span style={{ color: "var(--border-default)" }}>|</span>
              <span
                style={{
                  textTransform: "uppercase",
                  letterSpacing: "var(--ls-caps)",
                  fontWeight: "var(--fw-semibold)" as unknown as number,
                }}
              >
                {language}
              </span>
            </>
          )}
          {version && (
            <>
              <span style={{ color: "var(--border-default)" }}>|</span>
              <span className="font-mono">v{version}</span>
            </>
          )}
        </div>
      </div>

      {/* Pipeline stage indicators */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-3)",
          flexShrink: 0,
        }}
      >
        {STAGES.map((s, i) => {
          const isDone = !isError && activeIndex > i;
          const isActive = !isError && activeIndex === i;
          const isPending = isError || activeIndex < i;

          let dotBg = "var(--border-subtle)";
          let dotColor = "var(--text-disabled)";

          if (isDone) {
            dotBg = "var(--verify-tint)";
            dotColor = "var(--verify)";
          } else if (isActive) {
            dotBg = "var(--accent-tint-strong)";
            dotColor = "var(--accent)";
          } else if (isError && i === 0) {
            dotBg = "var(--error-tint)";
            dotColor = "var(--error)";
          }

          return (
            <React.Fragment key={s.key}>
              {i > 0 && (
                <div
                  style={{
                    width: 12,
                    height: 1,
                    background: isDone ? "var(--verify)" : "var(--border-subtle)",
                  }}
                />
              )}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 26,
                  height: 26,
                  borderRadius: "var(--r-full)",
                  background: dotBg,
                  color: dotColor,
                  transition: `all var(--dur-base) var(--ease-out)`,
                  animation: isActive ? "pulse 1.5s ease-in-out infinite" : undefined,
                  opacity: isPending ? 0.4 : 1,
                }}
                title={s.label}
              >
                {s.icon}
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {/* Pulse animation — scoped via inline <style> */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}
