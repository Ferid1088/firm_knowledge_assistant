"use client";

import React from "react";
import { Badge } from "@/components/ui/Badge";

export interface SourceChunkMetaProps {
  document: string;
  version?: string;
  sectionPath: string;
  chunkType: string;
  page: number;
  chunkId: string;
}

interface MetaRowProps {
  label: string;
  children: React.ReactNode;
}

function MetaRow({ label, children }: MetaRowProps) {
  return (
    <div style={{ marginBottom: "var(--sp-5)" }}>
      <div className="text-eyebrow" style={{ marginBottom: "var(--sp-2)" }}>
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

export function SourceChunkMeta({
  document,
  version,
  sectionPath,
  chunkType,
  page,
  chunkId,
}: SourceChunkMetaProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        padding: "var(--sp-6)",
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--r-md)",
      }}
    >
      {/* Document */}
      <MetaRow label="Document">
        <span
          style={{
            fontSize: "var(--fs-sm)",
            fontWeight: "var(--fw-medium)" as unknown as number,
            color: "var(--text-strong)",
          }}
        >
          {document}
        </span>
        {version && (
          <span
            style={{
              marginLeft: "var(--sp-3)",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--fs-2xs)",
              color: "var(--text-muted)",
            }}
          >
            v{version}
          </span>
        )}
      </MetaRow>

      {/* Section path */}
      <MetaRow label="Section">
        <span
          style={{
            fontSize: "var(--fs-sm)",
            color: "var(--text-body)",
            lineHeight: "var(--lh-snug)",
          }}
        >
          {sectionPath}
        </span>
      </MetaRow>

      {/* Chunk type */}
      <MetaRow label="Type">
        <Badge tone="neutral">{chunkType}</Badge>
      </MetaRow>

      {/* Page */}
      <MetaRow label="Page">
        <span
          className="font-mono"
          style={{
            fontSize: "var(--fs-sm)",
            color: "var(--text-body)",
          }}
        >
          {page}
        </span>
      </MetaRow>

      {/* Chunk ID */}
      <MetaRow label="Chunk ID">
        <span
          className="font-mono"
          style={{
            fontSize: "var(--fs-2xs)",
            color: "var(--text-muted)",
            wordBreak: "break-all",
          }}
        >
          {chunkId}
        </span>
      </MetaRow>
    </div>
  );
}
