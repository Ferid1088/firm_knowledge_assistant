"use client";

import React from "react";

type SwitchSize = "sm" | "md";

export interface SwitchProps {
  checked: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  size?: SwitchSize;
}

const trackWidths: Record<SwitchSize, number> = { sm: 32, md: 40 };
const trackHeights: Record<SwitchSize, number> = { sm: 18, md: 22 };
const thumbSizes: Record<SwitchSize, number> = { sm: 14, md: 18 };
const thumbOffsets: Record<SwitchSize, number> = { sm: 2, md: 2 };

export function Switch({
  checked,
  onChange,
  disabled = false,
  size = "md",
}: SwitchProps) {
  const trackW = trackWidths[size];
  const trackH = trackHeights[size];
  const thumbD = thumbSizes[size];
  const offset = thumbOffsets[size];

  const trackStyle: React.CSSProperties = {
    position: "relative",
    display: "inline-flex",
    alignItems: "center",
    width: trackW,
    height: trackH,
    borderRadius: "var(--r-full)",
    background: checked ? "var(--accent)" : "var(--border-strong)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
    transition: `background var(--dur-fast) var(--ease-out)`,
    flexShrink: 0,
    border: "none",
    padding: 0,
    outline: "none",
  };

  const thumbStyle: React.CSSProperties = {
    position: "absolute",
    width: thumbD,
    height: thumbD,
    borderRadius: "var(--r-full)",
    background: "#fff",
    boxShadow: "var(--shadow-xs)",
    transition: `transform var(--dur-fast) var(--ease-out)`,
    transform: checked
      ? `translateX(${trackW - thumbD - offset}px)`
      : `translateX(${offset}px)`,
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      style={trackStyle}
      onClick={() => {
        if (!disabled) onChange?.(!checked);
      }}
    >
      <span style={thumbStyle} />
    </button>
  );
}
