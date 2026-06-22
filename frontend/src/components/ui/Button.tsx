"use client";

import React from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  fullWidth?: boolean;
  children?: React.ReactNode;
}

const heights: Record<ButtonSize, string> = {
  sm: "var(--control-h-sm)",
  md: "var(--control-h-md)",
  lg: "var(--control-h-lg)",
};

const paddings: Record<ButtonSize, string> = {
  sm: "0 var(--sp-4)",
  md: "0 var(--sp-6)",
  lg: "0 var(--sp-8)",
};

const fontSizes: Record<ButtonSize, string> = {
  sm: "var(--fs-xs)",
  md: "var(--fs-sm)",
  lg: "var(--fs-body)",
};

const gapSizes: Record<ButtonSize, string> = {
  sm: "var(--sp-2)",
  md: "var(--sp-3)",
  lg: "var(--sp-4)",
};

function getVariantStyles(
  variant: ButtonVariant,
  disabled: boolean
): React.CSSProperties {
  if (disabled) {
    return {
      background: "var(--surface-raised)",
      color: "var(--text-disabled)",
      borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-subtle)",
      cursor: "not-allowed",
    };
  }

  switch (variant) {
    case "primary":
      return {
        background: "var(--accent)",
        color: "var(--accent-fg)",
        borderWidth: 1, borderStyle: "solid", borderColor: "transparent",
      };
    case "secondary":
      return {
        background: "var(--surface-raised)",
        color: "var(--text-body)",
        borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-default)",
      };
    case "ghost":
      return {
        background: "transparent",
        color: "var(--text-body)",
        borderWidth: 1, borderStyle: "solid", borderColor: "transparent",
      };
    case "danger":
      return {
        background: "var(--error)",
        color: "#fff",
        borderWidth: 1, borderStyle: "solid", borderColor: "transparent",
      };
  }
}

function getHoverStyles(variant: ButtonVariant): React.CSSProperties {
  switch (variant) {
    case "primary":
      return { background: "var(--accent-hover)" };
    case "secondary":
      return { background: "var(--surface-hover)", borderColor: "var(--border-strong)" };
    case "ghost":
      return { background: "var(--surface-hover)" };
    case "danger":
      return { background: "var(--error-600)" };
  }
}

function getActiveStyles(variant: ButtonVariant): React.CSSProperties {
  switch (variant) {
    case "primary":
      return { background: "var(--accent-press)" };
    case "secondary":
      return { background: "var(--surface-raised)" };
    case "ghost":
      return { background: "var(--surface-raised)" };
    case "danger":
      return { background: "var(--error-600)" };
  }
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "primary",
      size = "md",
      iconLeft,
      iconRight,
      fullWidth = false,
      disabled = false,
      children,
      style,
      type = "button",
      onMouseEnter,
      onMouseLeave,
      onMouseDown,
      onMouseUp,
      ...rest
    },
    ref
  ) {
    const [hovered, setHovered] = React.useState(false);
    const [pressed, setPressed] = React.useState(false);

    const baseStyle: React.CSSProperties = {
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      gap: gapSizes[size],
      height: heights[size],
      padding: paddings[size],
      borderRadius: "var(--r-sm)",
      fontFamily: "var(--font-sans)",
      fontSize: fontSizes[size],
      fontWeight: "var(--fw-medium)" as unknown as number,
      lineHeight: 1,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: `all var(--dur-fast) var(--ease-out)`,
      width: fullWidth ? "100%" : undefined,
      whiteSpace: "nowrap",
      userSelect: "none",
      outline: "none",
      ...getVariantStyles(variant, !!disabled),
      ...(!disabled && hovered ? getHoverStyles(variant) : {}),
      ...(!disabled && pressed ? getActiveStyles(variant) : {}),
      ...style,
    };

    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled}
        style={baseStyle}
        onMouseEnter={(e) => {
          setHovered(true);
          onMouseEnter?.(e);
        }}
        onMouseLeave={(e) => {
          setHovered(false);
          setPressed(false);
          onMouseLeave?.(e);
        }}
        onMouseDown={(e) => {
          setPressed(true);
          onMouseDown?.(e);
        }}
        onMouseUp={(e) => {
          setPressed(false);
          onMouseUp?.(e);
        }}
        {...rest}
      >
        {iconLeft && (
          <span style={{ display: "inline-flex", flexShrink: 0 }}>
            {iconLeft}
          </span>
        )}
        {children}
        {iconRight && (
          <span style={{ display: "inline-flex", flexShrink: 0 }}>
            {iconRight}
          </span>
        )}
      </button>
    );
  }
);
