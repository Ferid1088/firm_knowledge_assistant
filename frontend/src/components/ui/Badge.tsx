"use client";

import React from "react";

type BadgeTone = "neutral" | "accent" | "verify" | "warn" | "error";

export interface BadgeProps {
  tone?: BadgeTone;
  solid?: boolean;
  icon?: React.ReactNode;
  mono?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

const TONES: Record<BadgeTone, { fg: string; bg: string; bd: string }> = {
  neutral: { fg: "var(--text-secondary)", bg: "var(--surface-raised)", bd: "var(--border-default)" },
  accent: { fg: "var(--accent-300)", bg: "var(--accent-tint)", bd: "var(--accent-700)" },
  verify: { fg: "var(--verify-300)", bg: "var(--verify-tint)", bd: "var(--verify-600)" },
  warn: { fg: "var(--warn-300)", bg: "var(--warn-tint)", bd: "var(--warn-600)" },
  error: { fg: "var(--error-300)", bg: "var(--error-tint)", bd: "var(--error-600)" },
};

export function Badge({ tone = "neutral", solid = false, icon, mono = false, children, style: styleProp }: BadgeProps) {
  const t = TONES[tone];
  const solidStyle = solid
    ? {
        background: tone === "neutral" ? "var(--slate-700)" : `var(--${tone === "verify" ? "verify" : tone === "warn" ? "warn" : tone === "error" ? "error" : "accent"}-500)`,
        color: tone === "warn" ? "#1a1205" : "#fff",
        borderColor: "transparent",
      }
    : { background: t.bg, color: t.fg, borderColor: t.bd };

  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      height: 20, padding: "0 7px", borderRadius: "var(--r-xs)",
      border: "1px solid", borderColor: solidStyle.borderColor,
      background: solidStyle.background, color: solidStyle.color,
      fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
      fontSize: "var(--fs-2xs)", fontWeight: 600,
      letterSpacing: mono ? "-0.01em" : "0.01em", whiteSpace: "nowrap",
      lineHeight: 1,
      ...styleProp,
    }}>
      {icon && <span style={{ display: "inline-flex", flex: "none" }}>{icon}</span>}
      {children}
    </span>
  );
}
