"use client";

import React from "react";

export interface TooltipProps {
  children: React.ReactNode;
  content: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  style?: React.CSSProperties;
}

export function Tooltip({ children, content, side = "top", style }: TooltipProps) {
  const [show, setShow] = React.useState(false);
  const pos: Record<string, React.CSSProperties> = {
    top: { bottom: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)" },
    bottom: { top: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)" },
    left: { right: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)" },
    right: { left: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)" },
  };
  return (
    <span style={{ position: "relative", display: "inline-flex", ...style }}
      onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)} onBlur={() => setShow(false)}>
      {children}
      {show && content && (
        <span role="tooltip" style={{
          position: "absolute", ...pos[side], zIndex: 1100,
          background: "var(--slate-800)", color: "var(--text-strong)",
          border: "1px solid var(--border-strong)", borderRadius: "var(--r-sm)",
          boxShadow: "var(--shadow-pop)",
          padding: "5px 9px", fontFamily: "var(--font-sans)", fontSize: "var(--fs-xs)",
          lineHeight: 1.4, whiteSpace: "nowrap", pointerEvents: "none",
        }}>{content}</span>
      )}
    </span>
  );
}
