"use client";

import React from "react";

export interface SpinnerProps {
  size?: number;
  color?: string;
  style?: React.CSSProperties;
}

export function Spinner({ size = 16, color = "currentColor", style }: SpinnerProps) {
  return (
    <span role="status" aria-label="Loading" style={{ display: "inline-flex", ...style }}>
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
        style={{ animation: "k-spin 0.7s linear infinite" }}>
        <circle cx="12" cy="12" r="9" stroke={color} strokeOpacity="0.2" strokeWidth="2.4" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke={color} strokeWidth="2.4" strokeLinecap="round" />
      </svg>
    </span>
  );
}
