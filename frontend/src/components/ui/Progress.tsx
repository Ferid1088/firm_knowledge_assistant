"use client";

import React from "react";

export interface ProgressProps {
  value?: number;
  tone?: "accent" | "verify" | "warn" | "error";
  height?: number;
  label?: React.ReactNode;
  style?: React.CSSProperties;
}

export function Progress({ value, tone = "accent", height = 6, label, style }: ProgressProps) {
  const color = tone === "verify" ? "var(--verify-500)" : tone === "warn" ? "var(--warn-500)" : tone === "error" ? "var(--error-500)" : "var(--accent-500)";
  const indet = value == null;
  return (
    <div style={{ width: "100%", ...style }}>
      {label && (
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: "var(--fs-xs)", color: "var(--text-secondary)" }}>
          <span>{label}</span>
          {!indet && <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>{Math.round(value)}%</span>}
        </div>
      )}
      <div style={{ width: "100%", height, background: "var(--slate-800)", borderRadius: "var(--r-full)", overflow: "hidden", position: "relative" }}>
        <div style={indet ? {
          position: "absolute", top: 0, left: 0,
          width: "35%", height: "100%", background: color, borderRadius: "var(--r-full)",
          animation: "k-indet 1.2s var(--ease-in-out) infinite",
        } : {
          width: `${Math.max(0, Math.min(100, value))}%`, height: "100%", background: color,
          borderRadius: "var(--r-full)", transition: "width var(--dur-base) var(--ease-out)",
        }} />
      </div>
    </div>
  );
}
