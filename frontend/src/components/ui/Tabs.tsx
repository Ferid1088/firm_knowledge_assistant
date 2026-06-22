"use client";

import React from "react";

export interface TabItem { id: string; label: string; count?: number; }

export interface TabsProps {
  tabs: TabItem[];
  value: string;
  onChange?: (id: string) => void;
  style?: React.CSSProperties;
}

export function Tabs({ tabs, value, onChange, style }: TabsProps) {
  return (
    <div role="tablist" style={{
      display: "flex", gap: 2, borderBottom: "1px solid var(--border-subtle)", ...style,
    }}>
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button key={t.id} role="tab" aria-selected={active}
            onClick={() => onChange && onChange(t.id)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 7,
              padding: "0 12px", height: 36, border: "none", background: "transparent",
              borderBottom: "2px solid " + (active ? "var(--accent)" : "transparent"),
              marginBottom: -1, cursor: "pointer",
              color: active ? "var(--text-strong)" : "var(--text-secondary)",
              fontFamily: "var(--font-sans)", fontSize: "var(--fs-sm)",
              fontWeight: active ? 600 : 500,
              transition: "color var(--dur-fast) var(--ease-out)",
              outline: "none",
            }}
            onMouseEnter={(e) => { if (!active) e.currentTarget.style.color = "var(--text-body)"; }}
            onMouseLeave={(e) => { if (!active) e.currentTarget.style.color = "var(--text-secondary)"; }}
          >
            {t.label}
            {t.count != null && (
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: "var(--fs-2xs)",
                color: active ? "var(--accent-300)" : "var(--text-muted)",
                background: active ? "var(--accent-tint)" : "var(--surface-raised)",
                padding: "1px 5px", borderRadius: "var(--r-xs)",
              }}>{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
