"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, FileText, Table2, BookmarkCheck } from "lucide-react";

type ChunkType = "prose" | "table" | "recommendation";

export interface CitationProps {
  index: number;
  document: string;
  section: string;
  page: number;
  quote: string;
  verified: boolean;
  chunkType: ChunkType;
  active?: boolean;
  onOpen?: () => void;
}

const STRIPE_COLORS: Record<ChunkType, string> = {
  prose: "var(--accent)",
  table: "var(--warn)",
  recommendation: "var(--verify)",
};

const CHUNK_ICONS: Record<ChunkType, React.ReactNode> = {
  prose: <FileText size={12} />,
  table: <Table2 size={12} />,
  recommendation: <BookmarkCheck size={12} />,
};

export function Citation({
  index,
  document,
  section,
  page,
  quote,
  verified,
  chunkType,
  active = false,
  onOpen,
}: CitationProps) {
  const [hovered, setHovered] = React.useState(false);
  const stripeColor = STRIPE_COLORS[chunkType];

  return (
    <button
      type="button"
      onClick={onOpen}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        gap: 0,
        width: "100%",
        padding: 0,
        margin: 0,
        background: active
          ? "var(--surface-hover)"
          : hovered
          ? "var(--surface-hover)"
          : "var(--surface-card)",
        border: "1px solid",
        borderColor: active ? "var(--border-strong)" : "var(--border-subtle)",
        borderRadius: "var(--r-md)",
        cursor: onOpen ? "pointer" : "default",
        fontFamily: "var(--font-sans)",
        textAlign: "left",
        transition: `all var(--dur-fast) var(--ease-out)`,
        outline: "none",
        overflow: "hidden",
      }}
    >
      {/* Left stripe */}
      <div
        style={{
          width: 4,
          minHeight: "100%",
          background: stripeColor,
          borderRadius: "var(--r-md) 0 0 var(--r-md)",
          flexShrink: 0,
        }}
      />

      {/* Content */}
      <div style={{ flex: 1, padding: "var(--sp-5) var(--sp-6)" }}>
        {/* Header row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-4)",
            marginBottom: "var(--sp-3)",
          }}
        >
          {/* Index badge */}
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 22,
              height: 22,
              borderRadius: "var(--r-full)",
              background: stripeColor,
              color: "#fff",
              fontSize: "var(--fs-2xs)",
              fontWeight: "var(--fw-semibold)" as unknown as number,
              flexShrink: 0,
            }}
          >
            {index}
          </span>

          {/* Document name */}
          <span
            style={{
              fontSize: "var(--fs-sm)",
              fontWeight: "var(--fw-medium)" as unknown as number,
              color: "var(--text-strong)",
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {document}
          </span>

          {/* Chunk type badge */}
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--sp-2)",
              padding: "var(--sp-1) var(--sp-3)",
              borderRadius: "var(--r-xs)",
              background: "var(--surface-raised)",
              fontSize: "var(--fs-2xs)",
              color: "var(--text-secondary)",
              textTransform: "capitalize",
            }}
          >
            {CHUNK_ICONS[chunkType]}
            {chunkType}
          </span>

          {/* Verified badge */}
          {verified ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "var(--sp-2)",
                color: "var(--verify)",
                fontSize: "var(--fs-2xs)",
                fontWeight: "var(--fw-medium)" as unknown as number,
              }}
            >
              <CheckCircle2 size={13} />
              Verified
            </span>
          ) : (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "var(--sp-2)",
                color: "var(--warn)",
                fontSize: "var(--fs-2xs)",
                fontWeight: "var(--fw-medium)" as unknown as number,
              }}
            >
              <AlertTriangle size={13} />
              Unverified
            </span>
          )}
        </div>

        {/* Section + page */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-3)",
            marginBottom: "var(--sp-3)",
            fontSize: "var(--fs-xs)",
            color: "var(--text-secondary)",
          }}
        >
          <span>{section}</span>
          <span style={{ color: "var(--text-muted)" }}>|</span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--fs-2xs)",
            }}
          >
            p.{page}
          </span>
        </div>

        {/* Quote */}
        <div
          style={{
            fontSize: "var(--fs-sm)",
            lineHeight: "var(--lh-relaxed)",
            color: "var(--text-body)",
            fontStyle: "italic",
            borderLeft: "2px solid var(--border-default)",
            paddingLeft: "var(--sp-5)",
          }}
        >
          &ldquo;{quote}&rdquo;
        </div>
      </div>
    </button>
  );
}
