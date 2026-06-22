"use client";

import React from "react";

export interface TagProps {
  icon?: React.ReactNode;
  onRemove?: () => void;
  children: React.ReactNode;
}

export function Tag({ icon, onRemove, children }: TagProps) {
  const [hovered, setHovered] = React.useState(false);

  const tagStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--sp-2)",
    height: 24,
    padding: onRemove ? "0 var(--sp-2) 0 var(--sp-3)" : "0 var(--sp-3)",
    borderRadius: "var(--r-xs)",
    background: "var(--surface-raised)",
    border: "1px solid var(--border-default)",
    color: "var(--text-body)",
    fontSize: "var(--fs-xs)",
    fontFamily: "var(--font-sans)",
    lineHeight: 1,
    whiteSpace: "nowrap",
  };

  const removeStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 16,
    height: 16,
    padding: 0,
    border: "none",
    borderRadius: "var(--r-xs)",
    background: hovered ? "var(--surface-hover)" : "transparent",
    color: "var(--text-muted)",
    cursor: "pointer",
    transition: `all var(--dur-fast) var(--ease-out)`,
    outline: "none",
  };

  return (
    <span style={tagStyle}>
      {icon && (
        <span style={{ display: "inline-flex", flexShrink: 0 }}>{icon}</span>
      )}
      {children}
      {onRemove && (
        <button
          type="button"
          aria-label="Remove"
          style={removeStyle}
          onClick={onRemove}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            <path d="M2.5 2.5L7.5 7.5M7.5 2.5L2.5 7.5" />
          </svg>
        </button>
      )}
    </span>
  );
}
