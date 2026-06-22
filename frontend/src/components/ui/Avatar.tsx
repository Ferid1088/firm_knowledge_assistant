"use client";

import React from "react";

const SIZES = { sm: 24, md: 32, lg: 40 } as const;

function initials(name = "") {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase();
}

export interface AvatarProps {
  name?: string;
  src?: string;
  size?: "sm" | "md" | "lg";
  square?: boolean;
  style?: React.CSSProperties;
}

export function Avatar({ name = "", src, size = "md", square = false, style }: AvatarProps) {
  const dim = SIZES[size];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: dim, height: dim, flex: "none",
      borderRadius: square ? "var(--r-sm)" : "var(--r-full)",
      background: src ? "transparent" : "var(--accent-900)",
      border: "1px solid var(--border-default)",
      color: "var(--accent-300)", overflow: "hidden",
      fontFamily: "var(--font-sans)", fontWeight: 600,
      fontSize: dim * 0.4, letterSpacing: "0.02em", userSelect: "none",
      ...style,
    }} aria-label={name} role="img">
      {src ? <img src={src} alt={name} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials(name)}
    </span>
  );
}
