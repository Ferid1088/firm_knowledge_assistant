"use client";

import React from "react";

type ConfidenceLevel = "high" | "moderate" | "low";

export interface ConfidenceMeterProps {
  level: ConfidenceLevel;
  showLabel?: boolean;
}

const LEVEL_CONFIG: Record<
  ConfidenceLevel,
  { segments: number; color: string; label: string }
> = {
  high: { segments: 3, color: "var(--verify)", label: "High confidence" },
  moderate: { segments: 2, color: "var(--warn)", label: "Moderate confidence" },
  low: { segments: 1, color: "var(--error)", label: "Low confidence" },
};

export function ConfidenceMeter({ level, showLabel = false }: ConfidenceMeterProps) {
  const config = LEVEL_CONFIG[level];
  const TOTAL_SEGMENTS = 3;

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--sp-4)",
      }}
    >
      {/* Bar segments */}
      <div
        style={{
          display: "flex",
          gap: "var(--sp-2)",
          alignItems: "center",
        }}
        role="meter"
        aria-label={config.label}
        aria-valuenow={config.segments}
        aria-valuemin={0}
        aria-valuemax={TOTAL_SEGMENTS}
      >
        {Array.from({ length: TOTAL_SEGMENTS }).map((_, i) => {
          const isActive = i < config.segments;
          return (
            <div
              key={i}
              style={{
                width: 28,
                height: 6,
                borderRadius: "var(--r-full)",
                background: isActive ? config.color : "var(--border-subtle)",
                transition: `background var(--dur-base) var(--ease-out)`,
              }}
            />
          );
        })}
      </div>

      {/* Optional label */}
      {showLabel && (
        <span
          style={{
            fontSize: "var(--fs-xs)",
            fontWeight: "var(--fw-medium)" as unknown as number,
            color: config.color,
          }}
        >
          {config.label}
        </span>
      )}
    </div>
  );
}
