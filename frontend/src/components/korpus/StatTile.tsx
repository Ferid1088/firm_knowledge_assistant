"use client";

import React from "react";

type StatTone = "neutral" | "accent" | "verify" | "warn";

export interface StatTileProps {
  label: string;
  value: string | number;
  unit?: string;
  icon?: React.ReactNode;
  tone?: StatTone;
}

const TONE_COLORS: Record<StatTone, string> = {
  neutral: "var(--border-subtle)",
  accent: "var(--accent)",
  verify: "var(--verify)",
  warn: "var(--warn)",
};

export function StatTile({
  label,
  value,
  unit,
  icon,
  tone = "neutral",
}: StatTileProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-4)",
        padding: "var(--sp-6)",
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
        borderLeft: `3px solid ${TONE_COLORS[tone]}`,
        borderRadius: "var(--r-md)",
      }}
    >
      {/* Label row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-3)",
        }}
      >
        {icon && (
          <span
            style={{
              display: "inline-flex",
              color: "var(--text-secondary)",
            }}
          >
            {icon}
          </span>
        )}
        <span className="text-eyebrow">{label}</span>
      </div>

      {/* Value */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "var(--sp-3)",
        }}
      >
        <span
          className="font-mono"
          style={{
            fontSize: "var(--fs-display)",
            fontWeight: "var(--fw-semibold)" as unknown as number,
            lineHeight: "var(--lh-tight)",
            color: "var(--text-strong)",
            letterSpacing: "var(--ls-tight)",
          }}
        >
          {value}
        </span>
        {unit && (
          <span
            style={{
              fontSize: "var(--fs-sm)",
              color: "var(--text-muted)",
              fontWeight: "var(--fw-medium)" as unknown as number,
            }}
          >
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}
