"use client";

import React from "react";

type CardPadding = "sm" | "md" | "lg";

export interface CardProps {
  raised?: boolean;
  interactive?: boolean;
  padding?: CardPadding;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

const paddings: Record<CardPadding, string> = {
  sm: "var(--sp-5)",
  md: "var(--sp-6)",
  lg: "var(--sp-8)",
};

export function Card({
  raised = false,
  interactive = false,
  padding = "md",
  children,
  className,
  style,
}: CardProps) {
  const [hovered, setHovered] = React.useState(false);

  const baseStyle: React.CSSProperties = {
    background: raised ? "var(--surface-raised)" : "var(--surface-card)",
    border: "1px solid var(--border-default)",
    borderRadius: "var(--r-md)",
    padding: paddings[padding],
    transition: `all var(--dur-fast) var(--ease-out)`,
    ...(interactive
      ? {
          cursor: "pointer",
          transform: hovered ? "translateY(-1px)" : "translateY(0)",
          boxShadow: hovered ? "var(--shadow-sm)" : "none",
        }
      : {}),
    ...style,
  };

  return (
    <div
      className={className}
      style={baseStyle}
      onMouseEnter={interactive ? () => setHovered(true) : undefined}
      onMouseLeave={interactive ? () => setHovered(false) : undefined}
    >
      {children}
    </div>
  );
}
